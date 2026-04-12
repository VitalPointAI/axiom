"""Unit tests for db.crypto.EncryptedBytes TypeDecorator — Phase 16 Wave 0.

Tests call process_bind_param() and process_result_value() directly (no
SQLAlchemy session needed — unit-testing the TypeDecorator class in isolation).

Coverage:
  - Round-trip for str, bytes, int, Decimal, dict (PQE-03)
  - None passthrough (NULL in DB = NULL returned, no AESGCM call)
  - Missing DEK raises RuntimeError on both bind and read (fail-closed, T-16-01)
  - Ciphertext length verification (1 tag + 12 nonce + plaintext + 16 GCM tag)
  - Tamper detection: one-bit flip raises InvalidTag (T-16-01)
  - Nonce uniqueness: 100 encryptions of same value produce 100 distinct ciphertexts (T-16-08)
"""

from decimal import Decimal

import pytest
from cryptography.exceptions import InvalidTag


# ---------------------------------------------------------------------------
# Autouse fixture: HMAC/wrap env vars (mirrors test_crypto.py)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _crypto_env(monkeypatch):
    """Inject deterministic crypto keys for all TypeDecorator tests."""
    monkeypatch.setenv("EMAIL_HMAC_KEY", "00" * 32)
    monkeypatch.setenv("NEAR_ACCOUNT_HMAC_KEY", "11" * 32)
    monkeypatch.setenv("TX_DEDUP_KEY", "22" * 32)
    monkeypatch.setenv("ACB_DEDUP_KEY", "33" * 32)
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)


# ---------------------------------------------------------------------------
# Helper: encrypt then decrypt via TypeDecorator
# ---------------------------------------------------------------------------


def _roundtrip(value):
    """Bind *value* through EncryptedBytes, then read the result back."""
    from db.crypto import EncryptedBytes

    enc = EncryptedBytes()
    ciphertext = enc.process_bind_param(value, None)
    return enc.process_result_value(ciphertext, None)


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


def test_bind_param_roundtrip_str():
    """String value round-trips through EncryptedBytes as str."""
    from db.crypto import set_dek

    set_dek(b"\x00" * 32)
    result = _roundtrip("hello")
    assert result == "hello"
    assert isinstance(result, str)


def test_bind_param_roundtrip_bytes():
    """Bytes value round-trips through EncryptedBytes as bytes."""
    from db.crypto import set_dek

    set_dek(b"\x00" * 32)
    original = b"\x00\x01\x02"
    result = _roundtrip(original)
    assert result == original
    assert isinstance(result, bytes)


def test_bind_param_roundtrip_int():
    """Integer value round-trips through EncryptedBytes (recovered as Decimal or int)."""
    from db.crypto import set_dek

    set_dek(b"\x00" * 32)
    result = _roundtrip(123456789)
    assert int(result) == 123456789


def test_bind_param_roundtrip_decimal():
    """Decimal value round-trips with exact value preservation."""
    from db.crypto import set_dek

    set_dek(b"\x00" * 32)
    original = Decimal("1.23456789")
    result = _roundtrip(original)
    assert Decimal(result) == original


def test_bind_param_roundtrip_dict():
    """Dict value round-trips through EncryptedBytes via JSON encoding."""
    from db.crypto import set_dek

    set_dek(b"\x00" * 32)
    original = {"a": 1, "b": [2, 3]}
    result = _roundtrip(original)
    assert result == original
    assert isinstance(result, dict)


def test_bind_param_none_passthrough():
    """None binds as None and reads back as None without calling AESGCM."""
    from db.crypto import EncryptedBytes, zero_dek

    zero_dek()  # ensure no DEK is set — None should not need one
    enc = EncryptedBytes()
    ciphertext = enc.process_bind_param(None, None)
    assert ciphertext is None
    result = enc.process_result_value(None, None)
    assert result is None


# ---------------------------------------------------------------------------
# Missing DEK failure tests
# ---------------------------------------------------------------------------


def test_missing_dek_raises_on_bind():
    """process_bind_param raises RuntimeError when no DEK is set."""
    from db.crypto import EncryptedBytes, zero_dek

    zero_dek()  # ensure clean state
    with pytest.raises(RuntimeError, match="No DEK in context"):
        EncryptedBytes().process_bind_param("hello", None)


def test_missing_dek_raises_on_read():
    """process_result_value raises RuntimeError when no DEK is set."""
    from db.crypto import EncryptedBytes, set_dek, zero_dek

    # First, create a real ciphertext so we have something to pass to result_value
    set_dek(b"\x00" * 32)
    ciphertext = EncryptedBytes().process_bind_param("hello", None)
    zero_dek()  # clear DEK after bind

    with pytest.raises(RuntimeError, match="No DEK in context"):
        EncryptedBytes().process_result_value(ciphertext, None)


# ---------------------------------------------------------------------------
# Ciphertext structure tests
# ---------------------------------------------------------------------------


def test_ciphertext_length():
    """Binding a 10-byte plaintext produces the expected ciphertext length.

    Layout: nonce (12) || AES-GCM(tag_byte (1) + plaintext + tag (16))
    Total = 12 + 1 + 10 + 16 = 39 bytes.
    """
    from db.crypto import EncryptedBytes, set_dek

    set_dek(b"\x00" * 32)
    plaintext = "0123456789"  # 10 bytes as UTF-8
    ciphertext = EncryptedBytes().process_bind_param(plaintext, None)
    assert isinstance(ciphertext, bytes)
    expected = 12 + 1 + len(plaintext.encode("utf-8")) + 16
    assert len(ciphertext) == expected, (
        f"Expected ciphertext length {expected}, got {len(ciphertext)}"
    )


def test_tamper_detection():
    """Flipping one byte of the stored ciphertext raises InvalidTag on decrypt."""
    from db.crypto import EncryptedBytes, set_dek

    set_dek(b"\x00" * 32)
    enc = EncryptedBytes()
    ciphertext = enc.process_bind_param("sensitive data", None)

    # Flip a byte in the ciphertext (beyond the 12-byte nonce to ensure it hits the tag/ct)
    tampered = bytearray(ciphertext)
    tampered[15] ^= 0xFF
    tampered_bytes = bytes(tampered)

    with pytest.raises(InvalidTag):
        enc.process_result_value(tampered_bytes, None)


def test_nonce_uniqueness():
    """Binding same value 100 times produces 100 distinct ciphertexts."""
    from db.crypto import set_dek, EncryptedBytes

    set_dek(b"\x00" * 32)
    enc = EncryptedBytes()
    cts = {enc.process_bind_param("same", None) for _ in range(100)}
    assert len(cts) == 100, "All 100 ciphertexts must be unique (random nonce)"
