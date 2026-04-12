"""Wave 0 unit tests for db/crypto.py — Phase 16 post-quantum encryption foundation.

Coverage:
  - ML-KEM-768 keygen and KAT-style verification (PQE-01)
  - Envelope round-trip: provision_user_keys + unwrap_dek_for_session (PQE-02)
  - Tamper detection: wrapped_dek mutation raises InvalidTag (T-16-01)
  - Wrong sealing key rejection (T-16-01)
  - DEK zeroization: get_dek() raises RuntimeError after zero_dek() (PQE-08, T-16-03)
  - Context isolation: ContextVar isolates DEK between contexts (T-16-02)
  - HMAC surrogates: email, near-account, tx dedup, ACB dedup (PQE-04, D-24, D-28)
  - Accountant re-wrap round-trip (D-25)
  - Worker key round-trip (D-17, PQE-06)

All tests are pure unit tests — no network calls, no DB calls, no file I/O.
"""

import os

import pytest
from cryptography.exceptions import InvalidTag
from kyber_py.ml_kem import ML_KEM_768


# ---------------------------------------------------------------------------
# Autouse fixture: set required HMAC env vars for every test in this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _crypto_env(monkeypatch):
    """Inject deterministic HMAC/wrap keys for all crypto tests."""
    monkeypatch.setenv("EMAIL_HMAC_KEY", "00" * 32)
    monkeypatch.setenv("NEAR_ACCOUNT_HMAC_KEY", "11" * 32)
    monkeypatch.setenv("TX_DEDUP_KEY", "22" * 32)
    monkeypatch.setenv("ACB_DEDUP_KEY", "33" * 32)
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)


# ---------------------------------------------------------------------------
# ML-KEM-768 keygen and KAT verification
# ---------------------------------------------------------------------------


def test_mlkem_keygen():
    """ML_KEM_768.keygen() produces (ek, dk) with correct lengths."""
    ek, dk = ML_KEM_768.keygen()
    assert len(ek) == 1184, f"Expected ek=1184 bytes, got {len(ek)}"
    assert len(dk) == 2400, f"Expected dk=2400 bytes, got {len(dk)}"
    # Keys must be distinct bytes
    assert ek != dk


def test_mlkem_kat():
    """ML-KEM-768 encaps/decaps round-trip produces matching shared secrets.

    We do not run full NIST KAT vectors here (kyber-py is upstream-tested);
    instead we verify the fundamental correctness property:
      - encaps(ek) -> (shared_secret_sender, kem_ct)
      - decaps(dk, kem_ct) -> shared_secret_receiver
      - shared_secret_sender == shared_secret_receiver
    and that a tampered kem_ct produces a different (wrong) shared secret.
    """
    ek, dk = ML_KEM_768.keygen()

    # Correct round-trip
    shared_secret_sender, kem_ct = ML_KEM_768.encaps(ek)
    shared_secret_receiver = ML_KEM_768.decaps(dk, kem_ct)
    assert shared_secret_sender == shared_secret_receiver, "Shared secrets must match"
    assert len(shared_secret_sender) == 32, "ML-KEM-768 shared secret must be 32 bytes"

    # Tampered kem_ct should produce a *different* shared secret (ML-KEM implicit rejection)
    tampered_ct = bytearray(kem_ct)
    tampered_ct[42] ^= 0xFF
    wrong_ss = ML_KEM_768.decaps(dk, bytes(tampered_ct))
    assert wrong_ss != shared_secret_sender, "Tampered ciphertext must yield wrong shared secret"


# ---------------------------------------------------------------------------
# Envelope round-trip
# ---------------------------------------------------------------------------


def test_dek_roundtrip():
    """provision_user_keys + unwrap_dek_for_session restores the DEK."""
    from db.crypto import provision_user_keys, unwrap_dek_for_session, DEK_LEN

    sealing_key = os.urandom(32)
    result = provision_user_keys(sealing_key)

    assert "mlkem_ek" in result
    assert "mlkem_sealed_dk" in result
    assert "wrapped_dek" in result
    assert len(result["mlkem_ek"]) == 1184
    assert len(result["mlkem_sealed_dk"]) == 2428   # 12 nonce + 2400 dk + 16 tag
    assert len(result["wrapped_dek"]) == 1148        # 1088 kem_ct + 12 nonce + 32 dek + 16 tag

    recovered_dek = unwrap_dek_for_session(
        result["mlkem_sealed_dk"],
        result["wrapped_dek"],
        sealing_key,
    )
    assert len(recovered_dek) == DEK_LEN
    # DEK must not be the same bytes as the ek/dk/wrapped blobs
    assert recovered_dek != result["mlkem_ek"][:32]


def test_dek_tamper():
    """Flipping one byte of wrapped_dek raises InvalidTag."""
    from db.crypto import provision_user_keys, unwrap_dek_for_session

    sealing_key = os.urandom(32)
    result = provision_user_keys(sealing_key)

    tampered = bytearray(result["wrapped_dek"])
    tampered[100] ^= 0xFF

    with pytest.raises(InvalidTag):
        unwrap_dek_for_session(
            result["mlkem_sealed_dk"],
            bytes(tampered),
            sealing_key,
        )


def test_wrong_sealing_key():
    """unwrap_dek_for_session with wrong sealing_key raises InvalidTag."""
    from db.crypto import provision_user_keys, unwrap_dek_for_session

    sealing_key = os.urandom(32)
    wrong_key = os.urandom(32)
    # Ensure keys are actually different
    while wrong_key == sealing_key:
        wrong_key = os.urandom(32)

    result = provision_user_keys(sealing_key)

    with pytest.raises(InvalidTag):
        unwrap_dek_for_session(
            result["mlkem_sealed_dk"],
            result["wrapped_dek"],
            wrong_key,
        )


# ---------------------------------------------------------------------------
# DEK zeroization and context isolation
# ---------------------------------------------------------------------------


def test_dek_zeroization():
    """After zero_dek(), get_dek() raises RuntimeError."""
    from db.crypto import set_dek, get_dek, zero_dek

    dek = bytearray(b"AXIOM_DEK_" + b"\x42" * 22)
    set_dek(bytes(dek))
    assert get_dek() == bytes(dek)
    zero_dek()
    with pytest.raises(RuntimeError, match="No DEK in context"):
        get_dek()


def test_context_isolation():
    """DEK set in a child copy_context() does not leak into the parent context."""
    import contextvars
    from db.crypto import set_dek, get_dek, zero_dek

    dek_a = b"A" * 32
    dek_b = b"B" * 32
    set_dek(dek_a)

    def run_b():
        set_dek(dek_b)
        assert get_dek() == dek_b

    ctx = contextvars.copy_context()
    ctx.run(run_b)
    assert get_dek() == dek_a  # parent context unchanged
    zero_dek()


# ---------------------------------------------------------------------------
# HMAC surrogates
# ---------------------------------------------------------------------------


def test_email_hmac():
    """hash_email is case/whitespace-insensitive and produces 64-char hex."""
    from db.crypto import hash_email

    result1 = hash_email("Foo@Bar.com")
    result2 = hash_email("foo@bar.com")
    result3 = hash_email("  FOO@BAR.COM  ")
    assert result1 == result2 == result3, "Email HMAC must be case/space-insensitive"
    assert len(result1) == 64, "HMAC-SHA256 hex digest must be 64 chars"

    # Different emails must produce different hashes
    result_other = hash_email("other@example.com")
    assert result1 != result_other, "Different emails must produce different HMACs"

    # Verify it is hex
    int(result1, 16)


def test_near_account_hmac():
    """hash_near_account is case/whitespace-insensitive and produces 64-char hex."""
    from db.crypto import hash_near_account

    r1 = hash_near_account("VitalPointAI.near")
    r2 = hash_near_account("vitalpointai.near")
    r3 = hash_near_account("  VITALPOINTAI.NEAR  ")
    assert r1 == r2 == r3, "NEAR account HMAC must be case/space-insensitive"
    assert len(r1) == 64

    r_other = hash_near_account("alice.near")
    assert r1 != r_other, "Different accounts must produce different HMACs"


def test_tx_dedup_hmac():
    """compute_tx_dedup_hmac returns 32 raw bytes; deterministic for same inputs."""
    from db.crypto import compute_tx_dedup_hmac

    h1 = compute_tx_dedup_hmac("NEAR", "abc123", "rec456", 7)
    h2 = compute_tx_dedup_hmac("NEAR", "abc123", "rec456", 7)
    assert h1 == h2, "Same inputs must produce same HMAC"
    assert isinstance(h1, bytes)
    assert len(h1) == 32, "HMAC-SHA256 raw digest must be 32 bytes"

    h_diff = compute_tx_dedup_hmac("NEAR", "abc123", "rec789", 7)
    assert h1 != h_diff, "Different receipt_id must produce different HMAC"


def test_acb_dedup_hmac():
    """compute_acb_dedup_hmac returns 32 raw bytes; deterministic for same inputs."""
    from db.crypto import compute_acb_dedup_hmac

    h1 = compute_acb_dedup_hmac(1, "NEAR", 42)
    h2 = compute_acb_dedup_hmac(1, "NEAR", 42)
    assert h1 == h2, "Same inputs must produce same HMAC"
    assert isinstance(h1, bytes)
    assert len(h1) == 32

    h_diff = compute_acb_dedup_hmac(2, "NEAR", 42)
    assert h1 != h_diff, "Different user_id must produce different HMAC"


# ---------------------------------------------------------------------------
# Accountant re-wrap round-trip
# ---------------------------------------------------------------------------


def test_rewrap_dek_roundtrip():
    """DEK -> rewrap for grantee ek -> unwrap with grantee dk -> original DEK."""
    from db.crypto import (
        provision_user_keys,
        unwrap_dek_for_session,
        rewrap_dek_for_grantee,
        unwrap_rewrapped_dek,
    )

    # Client provisioning
    client_sealing_key = os.urandom(32)
    client_keys = provision_user_keys(client_sealing_key)
    client_dek = unwrap_dek_for_session(
        client_keys["mlkem_sealed_dk"],
        client_keys["wrapped_dek"],
        client_sealing_key,
    )

    # Grantee (accountant) provisioning
    grantee_sealing_key = os.urandom(32)
    grantee_keys = provision_user_keys(grantee_sealing_key)

    # Rewrap client DEK with accountant's public key
    rewrapped = rewrap_dek_for_grantee(client_dek, grantee_keys["mlkem_ek"])

    # Accountant unwraps client DEK
    recovered = unwrap_rewrapped_dek(
        rewrapped,
        grantee_keys["mlkem_sealed_dk"],
        grantee_sealing_key,
    )
    assert recovered == client_dek, "Accountant rewrap must recover original client DEK"


# ---------------------------------------------------------------------------
# Worker key round-trip
# ---------------------------------------------------------------------------


def test_worker_key_roundtrip():
    """seal_worker_dek -> unseal_worker_dek -> original DEK."""
    from db.crypto import (
        provision_user_keys,
        unwrap_dek_for_session,
        seal_worker_dek,
        unseal_worker_dek,
    )

    sealing_key = os.urandom(32)
    user_keys = provision_user_keys(sealing_key)
    dek = unwrap_dek_for_session(
        user_keys["mlkem_sealed_dk"],
        user_keys["wrapped_dek"],
        sealing_key,
    )

    sealed = seal_worker_dek(dek, user_keys["mlkem_ek"])
    recovered = unseal_worker_dek(sealed, user_keys["mlkem_sealed_dk"], sealing_key)
    assert recovered == dek, "Worker DEK round-trip must restore original DEK"
