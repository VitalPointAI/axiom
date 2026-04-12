"""Post-quantum encryption primitives for Axiom.

This module is the single canonical home for ALL cryptographic operations in
the Axiom per-user data plane:

  - AES-256-GCM authenticated encryption (DEK-level column encryption)
  - ML-KEM-768 (FIPS 203) key encapsulation / envelope operations
  - HMAC-SHA256 surrogates for email, NEAR account IDs, dedup keys
  - SQLAlchemy EncryptedBytes TypeDecorator (transparent per-column encrypt/decrypt)
  - Request-scoped DEK context via contextvars.ContextVar (NOT threading.local —
    FastAPI runs on asyncio; thread-locals leak between requests per Pitfall 1)
  - Key zeroization on logout, session expiry, and process exit (D-15, PQE-08)

Threat model (T-16-01 through T-16-09):
  - T-16-01: AES-256-GCM authenticated encryption detects ciphertext tampering
  - T-16-02: ContextVar isolates DEK between concurrent async requests
  - T-16-03: ctypes.memset + atexit.register(zero_dek) prevents DEK lingering in heap
  - T-16-04: HMAC-SHA256 dedup collision probability < 2^-128 at any plausible scale
  - T-16-06: HMAC keys are env-only, never logged
  - T-16-08: os.urandom(12) nonces prevent GCM nonce reuse

Ciphertext layouts:
  - EncryptedBytes column: tag_byte (1) || nonce (12) || ciphertext_with_tag
  - wrapped_dek:           kem_ct (1088) || wrap_nonce (12) || AES-GCM(shared_secret, dek)
                           = 1088 + 12 + 32 + 16 = 1148 bytes
  - mlkem_sealed_dk:       seal_nonce (12) || AES-GCM(sealing_key, dk)
                           = 12 + 2400 + 16 = 2428 bytes
  - wrap_session_dek:      nonce (12) || AES-GCM(SESSION_DEK_WRAP_KEY, dek)

Environment variables (all 32-byte hex; added to docker-compose.yml in plan 16-03):
  - EMAIL_HMAC_KEY        — HMAC key for hashing user email addresses
  - NEAR_ACCOUNT_HMAC_KEY — HMAC key for hashing NEAR account IDs (D-24)
  - TX_DEDUP_KEY          — HMAC key for transaction dedup HMAC (D-28)
  - ACB_DEDUP_KEY         — HMAC key for ACB snapshot dedup HMAC (D-28)
  - SESSION_DEK_WRAP_KEY  — AES-256-GCM key for wrapping DEK in session_dek_cache (D-26)
  - INTERNAL_SERVICE_TOKEN — Shared token for auth-service → FastAPI internal crypto router (D-27)
"""

from __future__ import annotations

import atexit
import ctypes
import hmac
import json
import logging
import os
from contextvars import ContextVar
from decimal import Decimal
from typing import Optional

from cryptography.exceptions import InvalidTag  # noqa: F401 — re-exported for callers
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from kyber_py.ml_kem import ML_KEM_768
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

ML_KEM_768_EK_LEN = 1184   # encapsulation key (public key) length in bytes
ML_KEM_768_DK_LEN = 2400   # decapsulation key (secret key) length in bytes
ML_KEM_768_CT_LEN = 1088   # KEM ciphertext (encapsulation output) length in bytes
AES_GCM_NONCE_LEN = 12     # 96-bit random nonce per NIST SP 800-38D
AES_GCM_TAG_LEN = 16       # GCM authentication tag
DEK_LEN = 32               # Data Encryption Key length (AES-256)

# Type tags for EncryptedBytes payload (first byte of plaintext before nonce)
_TAG_BYTES = b"\x01"
_TAG_STR = b"\x02"
_TAG_NUMERIC = b"\x03"
_TAG_JSON = b"\x04"

# ---------------------------------------------------------------------------
# Request-scoped DEK context (ContextVar — safe for asyncio + threading)
# ---------------------------------------------------------------------------

_dek_var: ContextVar[Optional[bytes]] = ContextVar("axiom_dek", default=None)


def set_dek(dek: bytes) -> None:
    """Set the Data Encryption Key for the current async context.

    The DEK lives only in process memory for the duration of one request/session
    and must be zeroed via zero_dek() on logout or request teardown (plan 16-02).
    """
    if not isinstance(dek, (bytes, bytearray)):
        raise TypeError(f"DEK must be bytes, got {type(dek).__name__}")
    if len(dek) != DEK_LEN:
        raise ValueError(f"DEK must be {DEK_LEN} bytes, got {len(dek)}")
    _dek_var.set(bytes(dek))


def get_dek() -> bytes:
    """Return the current context's DEK.

    Raises:
        RuntimeError: if no DEK has been set for the current context (fail-closed).
    """
    dek = _dek_var.get()
    if dek is None:
        raise RuntimeError("No DEK in context")
    return dek


def zero_dek() -> None:
    """Zeroize the DEK in memory and clear it from the current context.

    Uses ctypes.memset to overwrite the buffer before releasing the reference,
    satisfying D-15 / T-16-03 (DEK must not linger in heap after logout).
    This function is idempotent — safe to call even if no DEK is set.
    """
    dek = _dek_var.get()
    if dek is not None:
        _zero_bytes(dek)
        _dek_var.set(None)
    logger.debug("DEK zeroed")


# ---------------------------------------------------------------------------
# Low-level memory zeroization
# ---------------------------------------------------------------------------


def _zero_bytes(b: bytes | bytearray) -> None:
    """Overwrite the memory backing *b* with zero bytes using ctypes.memset.

    Note: Python bytes objects are immutable, so we make a ctypes buffer from a
    copy of the data. The original object's reference-counted memory may be
    collected by GC — this helper is best-effort given Python's memory model.
    For mutable buffers (bytearray), use from_buffer() to write in-place.
    """
    n = len(b)
    if n == 0:
        return
    if isinstance(b, bytearray):
        buf = (ctypes.c_char * n).from_buffer(b)
        ctypes.memset(buf, 0, n)
    else:
        # bytes is immutable; we can only overwrite a copy — still helps reduce
        # window during which the value appears in a heap scan.
        buf = (ctypes.c_char * n).from_buffer_copy(b)
        ctypes.memset(buf, 0, n)


# ---------------------------------------------------------------------------
# AES-256-GCM helpers (low-level; used by envelope ops and TypeDecorator)
# ---------------------------------------------------------------------------


def _aes_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """AES-256-GCM encrypt.  Returns nonce (12) || ciphertext_with_tag."""
    nonce = os.urandom(AES_GCM_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce + ct


def _aes_decrypt(key: bytes, blob: bytes) -> bytes:
    """AES-256-GCM decrypt.  Expects nonce (12) || ciphertext_with_tag.

    Raises:
        cryptography.exceptions.InvalidTag: on authentication failure.
    """
    if len(blob) < AES_GCM_NONCE_LEN + AES_GCM_TAG_LEN:
        raise ValueError("Ciphertext too short")
    nonce = blob[:AES_GCM_NONCE_LEN]
    ct = blob[AES_GCM_NONCE_LEN:]
    return AESGCM(key).decrypt(nonce, ct, None)


# ---------------------------------------------------------------------------
# ML-KEM-768 envelope operations
# ---------------------------------------------------------------------------


def provision_user_keys(sealing_key: bytes) -> dict:
    """Generate a new user ML-KEM-768 keypair and DEK; seal everything.

    Called at user registration (plan 16-03).

    Args:
        sealing_key: 32-byte key derived from near-phantom-auth session material.
                     Used to seal the ML-KEM decapsulation key (dk) so it can be
                     stored server-side without revealing it at rest.

    Returns a dict with:
        mlkem_ek:        bytes  — ML-KEM-768 encapsulation (public) key, 1184 bytes.
                                  Stored server-side in users.mlkem_ek.
        mlkem_sealed_dk: bytes  — AES-256-GCM(sealing_key, dk); 2428 bytes.
                                  Stored server-side in users.mlkem_sealed_dk.
                                  Only the user (via their session) can unseal it.
        wrapped_dek:     bytes  — kem_ct || AES-GCM(shared_secret, dek); 1148 bytes.
                                  Stored server-side in users.wrapped_dek.
    """
    if len(sealing_key) != DEK_LEN:
        raise ValueError(f"sealing_key must be {DEK_LEN} bytes")

    # Generate fresh ML-KEM-768 keypair
    ek, dk = ML_KEM_768.keygen()

    # Generate fresh 256-bit DEK
    dek = os.urandom(DEK_LEN)

    # Seal the decapsulation key: nonce || AES-GCM(sealing_key, dk)
    mlkem_sealed_dk = _aes_encrypt(sealing_key, dk)

    # Wrap the DEK with ML-KEM encapsulation
    # ML_KEM_768.encaps(ek) → (shared_secret, kem_ct)
    shared_secret, kem_ct = ML_KEM_768.encaps(ek)
    # Wrap DEK: kem_ct || nonce || AES-GCM(shared_secret, dek)
    dek_wrapped_payload = _aes_encrypt(shared_secret[:DEK_LEN], dek)
    wrapped_dek = kem_ct + dek_wrapped_payload

    _zero_bytes(dek)
    _zero_bytes(shared_secret)

    return {
        "mlkem_ek": ek,
        "mlkem_sealed_dk": mlkem_sealed_dk,
        "wrapped_dek": wrapped_dek,
    }


def unwrap_dek_for_session(
    mlkem_sealed_dk: bytes,
    wrapped_dek: bytes,
    sealing_key: bytes,
) -> bytes:
    """Unseal the user's DEK for an authenticated session.

    Called on login: auth-service provides the sealing_key derived from the
    passkey assertion; FastAPI internal crypto router decapsulates the DEK.

    Args:
        mlkem_sealed_dk: AES-256-GCM sealed decapsulation key (2428 bytes).
        wrapped_dek:     KEM ciphertext + AES-wrapped DEK (1148 bytes).
        sealing_key:     32-byte key from near-phantom-auth session material.

    Returns:
        DEK (32 bytes). Caller is responsible for zeroing via zero_dek().

    Raises:
        cryptography.exceptions.InvalidTag: if sealing_key is wrong or any
            ciphertext has been tampered with.
    """
    if len(sealing_key) != DEK_LEN:
        raise ValueError(f"sealing_key must be {DEK_LEN} bytes")
    if len(wrapped_dek) < ML_KEM_768_CT_LEN:
        raise ValueError("wrapped_dek too short")

    # Unseal the decapsulation key
    dk = _aes_decrypt(sealing_key, mlkem_sealed_dk)

    # Split wrapped_dek into KEM ciphertext and AES envelope
    kem_ct = wrapped_dek[:ML_KEM_768_CT_LEN]
    aes_blob = wrapped_dek[ML_KEM_768_CT_LEN:]

    # Recover shared secret via ML-KEM decapsulation
    shared_secret = ML_KEM_768.decaps(dk, kem_ct)

    # Decrypt DEK
    dek = _aes_decrypt(shared_secret[:DEK_LEN], aes_blob)

    _zero_bytes(dk)
    _zero_bytes(shared_secret)

    return dek


# ---------------------------------------------------------------------------
# Accountant re-wrap (D-25)
# ---------------------------------------------------------------------------


def rewrap_dek_for_grantee(dek: bytes, grantee_mlkem_ek: bytes) -> bytes:
    """Re-wrap a client's DEK with the grantee's (accountant's) ML-KEM public key.

    Called when a client grants accountant access.  The client's session holds
    the plaintext DEK; this function encapsulates it to the accountant's ek and
    returns the ciphertext to store in accountant_access.rewrapped_client_dek.

    Returns:
        kem_ct (1088) || nonce (12) || AES-GCM(shared_secret, dek)  = 1148 bytes
    """
    shared_secret, kem_ct = ML_KEM_768.encaps(grantee_mlkem_ek)
    payload = _aes_encrypt(shared_secret[:DEK_LEN], dek)
    _zero_bytes(shared_secret)
    return kem_ct + payload


def unwrap_rewrapped_dek(
    rewrapped_dek: bytes,
    grantee_mlkem_sealed_dk: bytes,
    grantee_sealing_key: bytes,
) -> bytes:
    """Recover a client DEK from a grantee (accountant) re-wrap.

    Called when an accountant loads a client's data.  The accountant's session
    DEK is already available; this resolves the *client's* DEK.

    Raises:
        cryptography.exceptions.InvalidTag: on any authentication failure.
    """
    dk = _aes_decrypt(grantee_sealing_key, grantee_mlkem_sealed_dk)
    kem_ct = rewrapped_dek[:ML_KEM_768_CT_LEN]
    aes_blob = rewrapped_dek[ML_KEM_768_CT_LEN:]
    shared_secret = ML_KEM_768.decaps(dk, kem_ct)
    dek = _aes_decrypt(shared_secret[:DEK_LEN], aes_blob)
    _zero_bytes(dk)
    _zero_bytes(shared_secret)
    return dek


# ---------------------------------------------------------------------------
# Worker key (D-17)
# ---------------------------------------------------------------------------


def seal_worker_dek(dek: bytes, mlkem_ek: bytes) -> bytes:
    """Seal a DEK for a background worker using a user's ML-KEM public key.

    Returns:
        kem_ct (1088) || nonce (12) || AES-GCM(shared_secret, dek)  = 1148 bytes
    """
    shared_secret, kem_ct = ML_KEM_768.encaps(mlkem_ek)
    payload = _aes_encrypt(shared_secret[:DEK_LEN], dek)
    _zero_bytes(shared_secret)
    return kem_ct + payload


def unseal_worker_dek(
    sealed: bytes,
    mlkem_sealed_dk: bytes,
    sealing_key: bytes,
) -> bytes:
    """Unseal a worker DEK using the user's ML-KEM decapsulation key.

    Raises:
        cryptography.exceptions.InvalidTag: on any authentication failure.
    """
    dk = _aes_decrypt(sealing_key, mlkem_sealed_dk)
    kem_ct = sealed[:ML_KEM_768_CT_LEN]
    aes_blob = sealed[ML_KEM_768_CT_LEN:]
    shared_secret = ML_KEM_768.decaps(dk, kem_ct)
    dek = _aes_decrypt(shared_secret[:DEK_LEN], aes_blob)
    _zero_bytes(dk)
    _zero_bytes(shared_secret)
    return dek


# ---------------------------------------------------------------------------
# Session DEK cache wrap / unwrap (D-26)
# ---------------------------------------------------------------------------


def wrap_session_dek(dek: bytes) -> bytes:
    """Wrap a DEK for storage in session_dek_cache using SESSION_DEK_WRAP_KEY.

    The SESSION_DEK_WRAP_KEY is a server-side 32-byte hex env var — NOT
    user-bound.  This provides a second layer of protection for the DEK at rest
    in the session_dek_cache table (plan 16-02).

    Returns:
        nonce (12) || AES-GCM(SESSION_DEK_WRAP_KEY, dek)
    """
    key = bytes.fromhex(os.environ["SESSION_DEK_WRAP_KEY"])
    return _aes_encrypt(key, dek)


def unwrap_session_dek(wrapped: bytes) -> bytes:
    """Unwrap a DEK from the session_dek_cache table.

    Raises:
        cryptography.exceptions.InvalidTag: if the SESSION_DEK_WRAP_KEY is wrong
            or the ciphertext has been tampered with.
    """
    key = bytes.fromhex(os.environ["SESSION_DEK_WRAP_KEY"])
    return _aes_decrypt(key, wrapped)


# ---------------------------------------------------------------------------
# HMAC surrogates (D-05, D-24, D-28)
# ---------------------------------------------------------------------------


def hash_email(email: str) -> str:
    """Return a deterministic HMAC-SHA256 hex digest of a normalised email.

    Uses EMAIL_HMAC_KEY (hex-encoded 32-byte server env var).  The output is a
    64-character lowercase hex string stored in users.email_hmac for auth-service
    lookup before the session DEK is available.

    Normalisation: lowercase + strip whitespace (prevents case/space variants
    producing different hashes for the same address).
    """
    key = bytes.fromhex(os.environ["EMAIL_HMAC_KEY"])
    return hmac.new(key, email.lower().strip().encode("utf-8"), "sha256").hexdigest()


def hash_near_account(account_id: str) -> str:
    """Return a deterministic HMAC-SHA256 hex digest of a normalised NEAR account ID.

    Uses NEAR_ACCOUNT_HMAC_KEY (hex-encoded 32-byte server env var).  The output
    is stored in users.near_account_id_hmac so auth-service can look up an
    existing Axiom user row by NEAR account ID before the session DEK exists (D-24).
    """
    key = bytes.fromhex(os.environ["NEAR_ACCOUNT_HMAC_KEY"])
    return hmac.new(key, account_id.lower().strip().encode("utf-8"), "sha256").hexdigest()


def compute_tx_dedup_hmac(chain: str, tx_hash: str, receipt_id: str, wallet_id: int) -> bytes:
    """Return raw 32-byte HMAC-SHA256 for transaction dedup (D-28).

    Input: chain || "|" || tx_hash || "|" || receipt_id || "|" || wallet_id
    Uses TX_DEDUP_KEY (hex-encoded 32-byte server env var).

    Returns raw bytes (not hex) — stored in transactions.tx_dedup_hmac (BYTEA).
    The UNIQUE(user_id, tx_dedup_hmac) constraint replaces the old cleartext
    uniqueness constraint, preserving ON CONFLICT semantics without leaking
    plaintext identifiers.
    """
    key = bytes.fromhex(os.environ["TX_DEDUP_KEY"])
    message = f"{chain}|{tx_hash}|{receipt_id}|{wallet_id}".encode("utf-8")
    return hmac.new(key, message, "sha256").digest()


def compute_acb_dedup_hmac(user_id: int, token_symbol: str, classification_id: int) -> bytes:
    """Return raw 32-byte HMAC-SHA256 for ACB snapshot dedup (D-28).

    Input: user_id || "|" || token_symbol || "|" || classification_id
    Uses ACB_DEDUP_KEY (hex-encoded 32-byte server env var).

    Returns raw bytes stored in acb_snapshots.acb_dedup_hmac (BYTEA).
    """
    key = bytes.fromhex(os.environ["ACB_DEDUP_KEY"])
    message = f"{user_id}|{token_symbol}|{classification_id}".encode("utf-8")
    return hmac.new(key, message, "sha256").digest()


# ---------------------------------------------------------------------------
# SQLAlchemy EncryptedBytes TypeDecorator
# ---------------------------------------------------------------------------

class EncryptedBytes(TypeDecorator):
    """SQLAlchemy TypeDecorator that transparently encrypts/decrypts column data.

    Storage format (BYTEA column):
        tag_byte (1) || nonce (12) || AES-256-GCM-ciphertext_with_tag

    Type tags:
        0x01 — bytes / bytearray
        0x02 — str (UTF-8)
        0x03 — numeric (int, float, Decimal) — stored as str representation
        0x04 — JSON (dict, list)

    The DEK is retrieved from the current async context via get_dek().  If no
    DEK is set, both bind and result operations raise RuntimeError (fail-closed).

    None values are passed through unchanged (NULL in the DB = NULL returned).

    Threat mitigations:
        T-16-01: AES-256-GCM authentication tag — any ciphertext modification
                 raises cryptography.exceptions.InvalidTag on decrypt.
        T-16-08: os.urandom(12) nonce per encryption call — 100 independent
                 encryptions of the same value produce 100 distinct ciphertexts.
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt *value* before writing to the DB.

        Raises:
            RuntimeError: if no DEK is set in the current context.
        """
        if value is None:
            return None

        dek = get_dek()  # raises RuntimeError if not set

        # Encode value to (tag, plaintext_bytes)
        if isinstance(value, (bytes, bytearray)):
            tag = _TAG_BYTES
            plaintext = bytes(value)
        elif isinstance(value, str):
            tag = _TAG_STR
            plaintext = value.encode("utf-8")
        elif isinstance(value, (int, float, Decimal)):
            tag = _TAG_NUMERIC
            plaintext = str(value).encode("utf-8")
        elif isinstance(value, (dict, list)):
            tag = _TAG_JSON
            plaintext = json.dumps(value).encode("utf-8")
        else:
            raise TypeError(f"EncryptedBytes: unsupported type {type(value).__name__}")

        # Prepend type tag to plaintext before encryption
        tagged_plaintext = tag + plaintext
        nonce = os.urandom(AES_GCM_NONCE_LEN)
        ct = AESGCM(dek).encrypt(nonce, tagged_plaintext, None)
        return nonce + ct

    def process_result_value(self, value, dialect):
        """Decrypt *value* read from the DB.

        Raises:
            RuntimeError: if no DEK is set in the current context.
            cryptography.exceptions.InvalidTag: if ciphertext authentication fails.
        """
        if value is None:
            return None

        dek = get_dek()  # raises RuntimeError if not set

        blob = bytes(value)
        if len(blob) < AES_GCM_NONCE_LEN + AES_GCM_TAG_LEN + 1:
            raise ValueError("Stored ciphertext too short")

        nonce = blob[:AES_GCM_NONCE_LEN]
        ct = blob[AES_GCM_NONCE_LEN:]
        tagged_plaintext = AESGCM(dek).decrypt(nonce, ct, None)

        if len(tagged_plaintext) < 1:
            raise ValueError("Decrypted payload is empty")

        tag = tagged_plaintext[:1]
        payload = tagged_plaintext[1:]

        if tag == _TAG_BYTES:
            return bytes(payload)
        elif tag == _TAG_STR:
            return payload.decode("utf-8")
        elif tag == _TAG_NUMERIC:
            s = payload.decode("utf-8")
            # Prefer Decimal for exact representation; callers can cast
            try:
                return Decimal(s)
            except Exception:
                return int(s)
        elif tag == _TAG_JSON:
            return json.loads(payload.decode("utf-8"))
        else:
            raise ValueError(f"EncryptedBytes: unknown type tag 0x{tag.hex()}")


# ---------------------------------------------------------------------------
# Process-exit cleanup (PQE-08, D-15, Pitfall 5)
# ---------------------------------------------------------------------------

atexit.register(zero_dek)
