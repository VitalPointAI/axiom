"""Pydantic request/response schemas for the internal crypto router (plan 16-02).

These models validate the three IPC endpoints used by auth-service to delegate
ML-KEM-768 operations to FastAPI (D-27).

All hex string fields use Field validators for length and character constraints
so invalid inputs are rejected before any crypto operations are attempted.
"""

from pydantic import BaseModel, Field


class KeygenRequest(BaseModel):
    """POST /internal/crypto/keygen — generate ML-KEM keypair + wrapped DEK."""

    sealing_key_hex: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-fA-F]{64}$",
        description="32-byte sealing key (hex) derived from near-phantom-auth session material.",
    )


class KeygenResponse(BaseModel):
    """Response from /internal/crypto/keygen."""

    mlkem_ek_hex: str = Field(
        ...,
        description="ML-KEM-768 encapsulation (public) key — 1184 bytes = 2368 hex chars.",
    )
    mlkem_sealed_dk_hex: str = Field(
        ...,
        description=(
            "AES-256-GCM sealed decapsulation key — "
            "nonce(12) + AES-GCM(sealing_key, dk=2400) + tag(16) = 2428 bytes = 4856 hex chars."
        ),
    )
    wrapped_dek_hex: str = Field(
        ...,
        description=(
            "KEM-wrapped DEK — kem_ct(1088) + nonce(12) + AES-GCM(shared_secret, dek=32) + tag(16) "
            "= 1148 bytes = 2296 hex chars."
        ),
    )


class UnwrapSessionDekRequest(BaseModel):
    """POST /internal/crypto/unwrap-session-dek — unseal DEK and re-wrap for session cache."""

    sealing_key_hex: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-fA-F]{64}$",
        description="32-byte sealing key (hex) — same key used during keygen.",
    )
    mlkem_sealed_dk_hex: str = Field(
        ...,
        description="Sealed decapsulation key (hex) from users.mlkem_sealed_dk.",
    )
    wrapped_dek_hex: str = Field(
        ...,
        description="KEM-wrapped DEK (hex) from users.wrapped_dek.",
    )


class UnwrapSessionDekResponse(BaseModel):
    """Response from /internal/crypto/unwrap-session-dek.

    The returned blob is the DEK ALREADY wrapped with SESSION_DEK_WRAP_KEY so
    auth-service can store it directly in session_dek_cache.encrypted_dek.
    The plaintext DEK is zeroed inside the endpoint before this response is returned.
    """

    session_dek_wrapped_hex: str = Field(
        ...,
        description=(
            "DEK wrapped with SESSION_DEK_WRAP_KEY — "
            "nonce(12) + AES-GCM(SESSION_DEK_WRAP_KEY, dek=32) + tag(16) = 60 bytes = 120 hex chars."
        ),
    )


class RewrapDekRequest(BaseModel):
    """POST /internal/crypto/rewrap-dek — re-wrap a DEK for accountant access (D-25)."""

    session_dek_wrapped_hex: str = Field(
        ...,
        description="Current session_dek_cache row encrypted_dek value (hex).",
    )
    grantee_mlkem_ek_hex: str = Field(
        ...,
        description="Accountant's ML-KEM-768 encapsulation key (hex) — 1184 bytes = 2368 hex chars.",
    )


class RewrapDekResponse(BaseModel):
    """Response from /internal/crypto/rewrap-dek."""

    rewrapped_dek_hex: str = Field(
        ...,
        description=(
            "Client DEK re-wrapped with grantee's ML-KEM ek — "
            "kem_ct(1088) + nonce(12) + AES-GCM(shared_secret, dek=32) + tag(16) "
            "= 1148 bytes = 2296 hex chars. "
            "Stored in accountant_access.rewrapped_client_dek."
        ),
    )
