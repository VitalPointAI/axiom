"""Loopback-only internal crypto router (D-26, D-27).

Exposes three ML-KEM-768 / DEK management endpoints that auth-service calls over
the Docker internal network to perform post-quantum crypto operations without
requiring a TypeScript ML-KEM library (D-27).

Security controls (T-16-10):
  - Token guard:    X-Internal-Service-Token header must match INTERNAL_SERVICE_TOKEN
                    env var, compared via hmac.compare_digest to prevent timing attacks.
  - Loopback guard: When AXIOM_ENV=production, requests from non-loopback source IPs
                    are rejected 403. In dev/test, the guard is bypassed.
  - Schema hidden:  include_in_schema=False keeps these routes out of OpenAPI docs.

Threat mitigations addressed here:
  - T-16-10: Token + loopback guards prevent public internet access.
  - T-16-11: Plaintext DEK is zeroed in finally blocks before response is returned;
             endpoints only return wrapped blobs, never raw DEK bytes.
  - T-16-13: SESSION_DEK_WRAP_KEY AES-GCM auth tag catches any tampered cache rows.
"""

import hmac as _hmac
import ipaddress
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from db import crypto as _c
from api.schemas.internal_crypto import (
    KeygenRequest,
    KeygenResponse,
    RewrapDekRequest,
    RewrapDekResponse,
    UnwrapSessionDekRequest,
    UnwrapSessionDekResponse,
)

router = APIRouter(
    prefix="/internal/crypto",
    tags=["internal-crypto"],
    include_in_schema=False,
)

# Networks considered "loopback" for the IP guard.
_LOOPBACK_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def _constant_time_eq(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing oracle attacks."""
    return _hmac.compare_digest(a.encode(), b.encode())


def _require_internal_token(
    x_internal_service_token: Annotated[str | None, Header()] = None,
) -> None:
    """Dependency: reject requests that lack a valid INTERNAL_SERVICE_TOKEN header.

    Returns 503 if the server env var is not configured (misconfiguration guard).
    Returns 401 if the header is missing or does not match.
    """
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="INTERNAL_SERVICE_TOKEN not configured on server",
        )
    if not x_internal_service_token or not _constant_time_eq(
        x_internal_service_token, expected
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing internal service token",
        )


def _require_loopback(request: Request) -> None:
    """Reject requests from non-loopback IPs when AXIOM_ENV=production.

    In development / test environments the guard is skipped so that TestClient
    (which always reports 127.0.0.1) and developers can call the endpoints freely.
    """
    if os.environ.get("AXIOM_ENV") != "production":
        return
    client_host = request.client.host if request.client else None
    if not client_host:
        raise HTTPException(status_code=403, detail="No client host information")
    try:
        addr = ipaddress.ip_address(client_host)
    except ValueError:
        raise HTTPException(status_code=403, detail=f"Invalid client host: {client_host}")
    if not any(addr in net for net in _LOOPBACK_NETS):
        raise HTTPException(
            status_code=403,
            detail=f"Non-loopback access denied from {client_host}",
        )


# Shared dependency list applied to all three endpoints.
_AUTH_DEPS = [Depends(_require_internal_token)]


# ---------------------------------------------------------------------------
# POST /internal/crypto/keygen
# ---------------------------------------------------------------------------


@router.post("/keygen", response_model=KeygenResponse, dependencies=_AUTH_DEPS)
async def keygen(req: KeygenRequest, request: Request) -> KeygenResponse:
    """Generate a new ML-KEM-768 keypair + 256-bit DEK, sealed for the user.

    Called by auth-service at user registration.

    The plaintext sealing_key is zeroed in the finally block before the response
    is returned (T-16-11). The returned blobs contain no raw key material.

    Returns:
        mlkem_ek_hex:        hex(1184-byte encapsulation key)
        mlkem_sealed_dk_hex: hex(AES-GCM sealed decapsulation key, 2428 bytes)
        wrapped_dek_hex:     hex(kem_ct + AES-GCM wrapped DEK, 1148 bytes)
    """
    _require_loopback(request)
    sealing_key = bytes.fromhex(req.sealing_key_hex)
    try:
        result = _c.provision_user_keys(sealing_key)
        return KeygenResponse(
            mlkem_ek_hex=result["mlkem_ek"].hex(),
            mlkem_sealed_dk_hex=result["mlkem_sealed_dk"].hex(),
            wrapped_dek_hex=result["wrapped_dek"].hex(),
        )
    finally:
        _c._zero_bytes(sealing_key)


# ---------------------------------------------------------------------------
# POST /internal/crypto/unwrap-session-dek
# ---------------------------------------------------------------------------


@router.post(
    "/unwrap-session-dek",
    response_model=UnwrapSessionDekResponse,
    dependencies=_AUTH_DEPS,
)
async def unwrap_session_dek(
    req: UnwrapSessionDekRequest, request: Request
) -> UnwrapSessionDekResponse:
    """Unseal a user's DEK and re-wrap it for storage in session_dek_cache.

    Called by auth-service after login when the user's passkey assertion yields the
    sealing_key.  The plaintext DEK is never returned over IPC — it is wrapped with
    SESSION_DEK_WRAP_KEY and zeroed inside this endpoint (T-16-11).

    auth-service stores the returned session_dek_wrapped_hex directly as
    session_dek_cache.encrypted_dek.

    Returns:
        session_dek_wrapped_hex: hex(nonce + AES-GCM(SESSION_DEK_WRAP_KEY, dek))
    """
    _require_loopback(request)
    sealing_key = bytes.fromhex(req.sealing_key_hex)
    sealed_dk = bytes.fromhex(req.mlkem_sealed_dk_hex)
    wrapped = bytes.fromhex(req.wrapped_dek_hex)
    dek = b""
    try:
        dek = _c.unwrap_dek_for_session(sealed_dk, wrapped, sealing_key)
        session_wrap = _c.wrap_session_dek(dek)
        return UnwrapSessionDekResponse(session_dek_wrapped_hex=session_wrap.hex())
    finally:
        _c._zero_bytes(sealing_key)
        if dek:
            _c._zero_bytes(dek)


# ---------------------------------------------------------------------------
# POST /internal/crypto/rewrap-dek
# ---------------------------------------------------------------------------


@router.post("/rewrap-dek", response_model=RewrapDekResponse, dependencies=_AUTH_DEPS)
async def rewrap_dek(req: RewrapDekRequest, request: Request) -> RewrapDekResponse:
    """Re-wrap a client's DEK with the grantee's (accountant's) ML-KEM public key.

    Called by auth-service when a client grants an accountant access (D-25).
    Reads the client's session-wrapped DEK from session_dek_cache, decrypts it,
    re-encapsulates to the grantee's ek, and returns the ciphertext for storage
    in accountant_access.rewrapped_client_dek.

    The plaintext DEK is zeroed before the response is returned (T-16-11).

    Returns:
        rewrapped_dek_hex: hex(kem_ct + AES-GCM(grantee_shared_secret, dek))
    """
    _require_loopback(request)
    session_wrapped = bytes.fromhex(req.session_dek_wrapped_hex)
    grantee_ek = bytes.fromhex(req.grantee_mlkem_ek_hex)
    dek = b""
    try:
        dek = _c.unwrap_session_dek(session_wrapped)
        rewrapped = _c.rewrap_dek_for_grantee(dek, grantee_ek)
        return RewrapDekResponse(rewrapped_dek_hex=rewrapped.hex())
    finally:
        if dek:
            _c._zero_bytes(dek)
