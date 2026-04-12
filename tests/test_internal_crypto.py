"""Integration tests for api/routers/internal_crypto.py (plan 16-02).

Tests the three loopback-only internal crypto endpoints:
  - POST /internal/crypto/keygen
  - POST /internal/crypto/unwrap-session-dek
  - POST /internal/crypto/rewrap-dek

All tests are self-contained — no database required.  The DB pool is mocked
via conftest fixtures; the crypto operations call db.crypto directly.

Coverage:
  - test_keygen_happy_path: correct blobs, correct byte lengths
  - test_keygen_missing_token: 401 on missing X-Internal-Service-Token
  - test_keygen_wrong_token: 401 on wrong token value
  - test_keygen_token_not_configured: 503 when INTERNAL_SERVICE_TOKEN env missing
  - test_keygen_bad_sealing_key: 422 on malformed hex input
  - test_unwrap_session_dek_roundtrip: keygen → unwrap-session-dek → db.crypto.unwrap_session_dek → 32-byte DEK
  - test_rewrap_dek_roundtrip: keygen for two users → rewrap → manually unwrap with grantee dk → original DEK
  - test_loopback_guard_in_production: non-loopback IP rejected 403 (direct unit test of _require_loopback)
  - test_loopback_guard_bypassed_in_dev: non-loopback IP allowed in non-production
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOKEN = "test-token-" + "x" * 40
_VALID_HEADERS = {"X-Internal-Service-Token": _TOKEN}
_SEALING_KEY_HEX = "aa" * 32   # 32 bytes, valid 64-hex-char string


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    """TestClient with env vars for all crypto operations.

    AXIOM_ENV is unset so the loopback IP check is bypassed (TestClient uses
    127.0.0.1 as client, but we want to test token guards independently).
    """
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", _TOKEN)
    monkeypatch.setenv("EMAIL_HMAC_KEY", "00" * 32)
    monkeypatch.setenv("NEAR_ACCOUNT_HMAC_KEY", "11" * 32)
    monkeypatch.setenv("TX_DEDUP_KEY", "22" * 32)
    monkeypatch.setenv("ACB_DEDUP_KEY", "33" * 32)
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)
    monkeypatch.delenv("AXIOM_ENV", raising=False)  # ensure loopback check bypassed

    from api.dependencies import get_pool_dep
    from api.main import create_app
    app = create_app()

    mock_pool = MagicMock()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


@pytest.fixture()
def client_no_token(monkeypatch):
    """TestClient with INTERNAL_SERVICE_TOKEN env var absent."""
    monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)
    monkeypatch.delenv("AXIOM_ENV", raising=False)

    from api.dependencies import get_pool_dep
    from api.main import create_app
    app = create_app()

    mock_pool = MagicMock()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ---------------------------------------------------------------------------
# Token guard tests
# ---------------------------------------------------------------------------


def test_keygen_missing_token(client):
    """POST /internal/crypto/keygen without token header returns 401."""
    r = client.post(
        "/internal/crypto/keygen",
        json={"sealing_key_hex": _SEALING_KEY_HEX},
    )
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_keygen_wrong_token(client):
    """POST /internal/crypto/keygen with wrong token value returns 401."""
    r = client.post(
        "/internal/crypto/keygen",
        json={"sealing_key_hex": _SEALING_KEY_HEX},
        headers={"X-Internal-Service-Token": "wrong-token"},
    )
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_keygen_token_not_configured(client_no_token):
    """POST /internal/crypto/keygen when INTERNAL_SERVICE_TOKEN not set returns 503."""
    r = client_no_token.post(
        "/internal/crypto/keygen",
        json={"sealing_key_hex": _SEALING_KEY_HEX},
        headers={"X-Internal-Service-Token": "anything"},
    )
    assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_keygen_bad_sealing_key(client):
    """POST /internal/crypto/keygen with non-hex sealing_key returns 422."""
    r = client.post(
        "/internal/crypto/keygen",
        json={"sealing_key_hex": "not-hex" + "x" * 57},  # 64 chars but invalid hex
        headers=_VALID_HEADERS,
    )
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


def test_keygen_short_sealing_key(client):
    """POST /internal/crypto/keygen with too-short sealing_key returns 422."""
    r = client.post(
        "/internal/crypto/keygen",
        json={"sealing_key_hex": "aa" * 16},  # 32 hex chars instead of 64
        headers=_VALID_HEADERS,
    )
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# Happy path: keygen
# ---------------------------------------------------------------------------


def test_keygen_happy_path(client):
    """POST /internal/crypto/keygen with valid token returns 200 with correct blob lengths."""
    r = client.post(
        "/internal/crypto/keygen",
        json={"sealing_key_hex": _SEALING_KEY_HEX},
        headers=_VALID_HEADERS,
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()

    # Verify field presence
    assert "mlkem_ek_hex" in data
    assert "mlkem_sealed_dk_hex" in data
    assert "wrapped_dek_hex" in data

    # Verify byte lengths (hex is 2x byte length)
    ek_bytes = bytes.fromhex(data["mlkem_ek_hex"])
    sealed_dk_bytes = bytes.fromhex(data["mlkem_sealed_dk_hex"])
    wrapped_dek_bytes = bytes.fromhex(data["wrapped_dek_hex"])

    assert len(ek_bytes) == 1184, f"Expected ek=1184 bytes, got {len(ek_bytes)}"
    # sealed_dk = nonce(12) + AES-GCM(sealing_key, dk=2400) + tag(16) = 2428 bytes
    assert len(sealed_dk_bytes) == 2428, f"Expected sealed_dk=2428 bytes, got {len(sealed_dk_bytes)}"
    # wrapped_dek = kem_ct(1088) + nonce(12) + AES-GCM(shared_secret, dek=32) + tag(16) = 1148 bytes
    assert len(wrapped_dek_bytes) == 1148, f"Expected wrapped_dek=1148 bytes, got {len(wrapped_dek_bytes)}"


def test_keygen_produces_unique_keys(client):
    """Two keygen calls with the same sealing_key produce distinct keypairs."""
    payload = {"sealing_key_hex": _SEALING_KEY_HEX}
    r1 = client.post("/internal/crypto/keygen", json=payload, headers=_VALID_HEADERS)
    r2 = client.post("/internal/crypto/keygen", json=payload, headers=_VALID_HEADERS)
    assert r1.status_code == 200
    assert r2.status_code == 200
    # ML-KEM keygen is randomised; keys must differ
    assert r1.json()["mlkem_ek_hex"] != r2.json()["mlkem_ek_hex"]


# ---------------------------------------------------------------------------
# Unwrap-session-dek round-trip
# ---------------------------------------------------------------------------


def test_unwrap_session_dek_roundtrip(client):
    """keygen → unwrap-session-dek → db.crypto.unwrap_session_dek → 32-byte DEK."""
    # Step 1: keygen
    r_keygen = client.post(
        "/internal/crypto/keygen",
        json={"sealing_key_hex": _SEALING_KEY_HEX},
        headers=_VALID_HEADERS,
    )
    assert r_keygen.status_code == 200
    kg = r_keygen.json()

    # Step 2: unwrap-session-dek (returns DEK wrapped with SESSION_DEK_WRAP_KEY)
    r_unwrap = client.post(
        "/internal/crypto/unwrap-session-dek",
        json={
            "sealing_key_hex": _SEALING_KEY_HEX,
            "mlkem_sealed_dk_hex": kg["mlkem_sealed_dk_hex"],
            "wrapped_dek_hex": kg["wrapped_dek_hex"],
        },
        headers=_VALID_HEADERS,
    )
    assert r_unwrap.status_code == 200, f"Expected 200: {r_unwrap.text}"
    session_dek_wrapped_hex = r_unwrap.json()["session_dek_wrapped_hex"]
    assert session_dek_wrapped_hex, "Response must include session_dek_wrapped_hex"

    # Step 3: decrypt the session-wrapped blob → must produce a 32-byte DEK
    from db.crypto import unwrap_session_dek, DEK_LEN
    dek = unwrap_session_dek(bytes.fromhex(session_dek_wrapped_hex))
    assert len(dek) == DEK_LEN, f"Unwrapped DEK must be {DEK_LEN} bytes, got {len(dek)}"


def test_unwrap_session_dek_wrong_sealing_key(monkeypatch):
    """unwrap-session-dek with mismatched sealing_key raises InvalidTag (server error).

    The endpoint does not catch InvalidTag — it propagates up as a 500 or the
    TestClient re-raises it when raise_server_exceptions=True.  We test with
    raise_server_exceptions=False and confirm the status is not 200.
    """
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", _TOKEN)
    monkeypatch.setenv("EMAIL_HMAC_KEY", "00" * 32)
    monkeypatch.setenv("NEAR_ACCOUNT_HMAC_KEY", "11" * 32)
    monkeypatch.setenv("TX_DEDUP_KEY", "22" * 32)
    monkeypatch.setenv("ACB_DEDUP_KEY", "33" * 32)
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)
    monkeypatch.delenv("AXIOM_ENV", raising=False)

    from api.dependencies import get_pool_dep
    from api.main import create_app
    from unittest.mock import MagicMock, patch as _patch
    app = create_app()
    mock_pool = MagicMock()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool

    with _patch("indexers.db.get_pool", return_value=mock_pool), \
         _patch("indexers.db.close_pool"):
        # raise_server_exceptions=False: server errors return 500 instead of raising
        with TestClient(app, raise_server_exceptions=False) as client:
            # keygen with key A
            r_keygen = client.post(
                "/internal/crypto/keygen",
                json={"sealing_key_hex": _SEALING_KEY_HEX},
                headers=_VALID_HEADERS,
            )
            assert r_keygen.status_code == 200
            kg = r_keygen.json()

            # unwrap-session-dek with key B → InvalidTag → 500
            wrong_key = "bb" * 32
            r = client.post(
                "/internal/crypto/unwrap-session-dek",
                json={
                    "sealing_key_hex": wrong_key,
                    "mlkem_sealed_dk_hex": kg["mlkem_sealed_dk_hex"],
                    "wrapped_dek_hex": kg["wrapped_dek_hex"],
                },
                headers=_VALID_HEADERS,
            )
    # Must not be 200 — wrong key must cause an error
    assert r.status_code != 200, "Wrong sealing key should not produce a successful response"


# ---------------------------------------------------------------------------
# Rewrap-dek round-trip (D-25)
# ---------------------------------------------------------------------------


def test_rewrap_dek_roundtrip(client, monkeypatch):
    """Two keygens → rewrap → unwrap with grantee dk+sealing_key → original DEK."""
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)

    sealing_key_a = "aa" * 32
    sealing_key_b = "bb" * 32

    # Keygen for user A
    r_a = client.post(
        "/internal/crypto/keygen",
        json={"sealing_key_hex": sealing_key_a},
        headers=_VALID_HEADERS,
    )
    assert r_a.status_code == 200
    kg_a = r_a.json()

    # Keygen for user B (the grantee/accountant)
    r_b = client.post(
        "/internal/crypto/keygen",
        json={"sealing_key_hex": sealing_key_b},
        headers=_VALID_HEADERS,
    )
    assert r_b.status_code == 200
    kg_b = r_b.json()

    # Unwrap user A's DEK into session format
    r_unwrap_a = client.post(
        "/internal/crypto/unwrap-session-dek",
        json={
            "sealing_key_hex": sealing_key_a,
            "mlkem_sealed_dk_hex": kg_a["mlkem_sealed_dk_hex"],
            "wrapped_dek_hex": kg_a["wrapped_dek_hex"],
        },
        headers=_VALID_HEADERS,
    )
    assert r_unwrap_a.status_code == 200
    session_dek_a_hex = r_unwrap_a.json()["session_dek_wrapped_hex"]

    # Recover user A's plaintext DEK for comparison
    from db.crypto import unwrap_session_dek, DEK_LEN
    dek_a_original = unwrap_session_dek(bytes.fromhex(session_dek_a_hex))
    assert len(dek_a_original) == DEK_LEN

    # Rewrap user A's DEK for user B's encapsulation key
    r_rewrap = client.post(
        "/internal/crypto/rewrap-dek",
        json={
            "session_dek_wrapped_hex": session_dek_a_hex,
            "grantee_mlkem_ek_hex": kg_b["mlkem_ek_hex"],
        },
        headers=_VALID_HEADERS,
    )
    assert r_rewrap.status_code == 200, f"Expected 200: {r_rewrap.text}"
    rewrapped_hex = r_rewrap.json()["rewrapped_dek_hex"]

    # User B manually unwraps the rewrapped DEK using their dk + sealing_key
    # This simulates plan 16-06's unwrap_rewrapped_dek path.
    from db.crypto import unwrap_rewrapped_dek
    dek_a_via_b = unwrap_rewrapped_dek(
        bytes.fromhex(rewrapped_hex),
        bytes.fromhex(kg_b["mlkem_sealed_dk_hex"]),
        bytes.fromhex(sealing_key_b),
    )
    assert len(dek_a_via_b) == DEK_LEN, f"Unwrapped DEK must be {DEK_LEN} bytes"
    assert dek_a_via_b == dek_a_original, (
        "Rewrapped DEK must decrypt to same plaintext DEK as user A's original"
    )


# ---------------------------------------------------------------------------
# Loopback IP guard (unit test — not TestClient)
# ---------------------------------------------------------------------------


def test_loopback_guard_in_production(monkeypatch):
    """_require_loopback raises 403 for non-loopback IPs in production."""
    monkeypatch.setenv("AXIOM_ENV", "production")

    from fastapi import HTTPException
    from api.routers.internal_crypto import _require_loopback

    # Build a minimal mock Request with a non-loopback client
    mock_client = MagicMock()
    mock_client.host = "203.0.113.1"   # TEST-NET-3, definitely not loopback
    mock_request = MagicMock()
    mock_request.client = mock_client

    with pytest.raises(HTTPException) as exc_info:
        _require_loopback(mock_request)
    assert exc_info.value.status_code == 403


def test_loopback_guard_allows_localhost_in_production(monkeypatch):
    """_require_loopback allows 127.0.0.1 in production."""
    monkeypatch.setenv("AXIOM_ENV", "production")

    from api.routers.internal_crypto import _require_loopback

    mock_client = MagicMock()
    mock_client.host = "127.0.0.1"
    mock_request = MagicMock()
    mock_request.client = mock_client

    # Must not raise
    _require_loopback(mock_request)


def test_loopback_guard_bypassed_in_dev(monkeypatch):
    """_require_loopback does nothing in non-production environments."""
    monkeypatch.delenv("AXIOM_ENV", raising=False)

    from api.routers.internal_crypto import _require_loopback

    mock_client = MagicMock()
    mock_client.host = "8.8.8.8"  # non-loopback
    mock_request = MagicMock()
    mock_request.client = mock_client

    # Must not raise — non-production bypasses the guard
    _require_loopback(mock_request)
