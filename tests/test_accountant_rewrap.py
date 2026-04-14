"""Tests for accountant grant/revoke/materialize endpoints and DEK viewing path.

Coverage (plan 16-06 requirements, D-25):
  - test_grant_creates_rewrapped_dek: POST /api/accountant/grant stores rewrapped_client_dek
  - test_grant_unknown_accountant_returns_404: grant with unknown email_hmac → 404
  - test_revoke_deletes_grant: DELETE /api/accountant/access/{id} removes the row
  - test_revoke_wrong_owner_returns_404: client B cannot revoke client A's grant
  - test_materialize_no_grants_returns_zero: no active grants → materialized=0
  - test_accountant_viewing_no_cache_returns_503: viewing-as without cache row → 503
  - test_accountant_viewing_cache_hit_returns_200: valid cache row → 200

All tests use mock pools and do not require a running database.  The full
integration path (seed DB, insert real rows, verify end-to-end) is deferred
to plan 16-07 and gated on RUN_MIGRATION_TESTS=1.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.dependencies import (
    get_current_user,
    get_effective_user,
    get_effective_user_with_dek,
    get_pool_dep,
)

_TEST_DEK = b"\x01" * 32


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dek_override(user_dict):
    """Async override for get_effective_user_with_dek that injects a test DEK."""
    from db.crypto import set_dek

    async def _override():
        set_dek(_TEST_DEK)
        return user_dict

    return _override


def _make_pool_and_cursor(fetchone_side=None, fetchall_side=None):
    """Build mock pool wiring."""
    mock_cursor = MagicMock()
    if fetchone_side is not None:
        mock_cursor.fetchone.side_effect = fetchone_side
    else:
        mock_cursor.fetchone.return_value = None
    if fetchall_side is not None:
        mock_cursor.fetchall.side_effect = fetchall_side
    else:
        mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn.return_value = None
    return mock_pool, mock_cursor


_CLIENT_USER = {
    "user_id": 10,
    "near_account_id": "client.near",
    "is_admin": False,
    "email": "client@example.com",
    "username": "client",
    "codename": None,
    "viewing_as_user_id": None,
    "permission_level": None,
}

_ACCOUNTANT_USER = {
    "user_id": 20,
    "near_account_id": "acct.near",
    "is_admin": False,
    "email": "acct@example.com",
    "username": "acct",
    "codename": None,
    "viewing_as_user_id": None,
    "permission_level": None,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_crypto_env(monkeypatch):
    """Inject required env vars for all accountant rewrap tests."""
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)
    monkeypatch.setenv("EMAIL_HMAC_KEY", "00" * 32)
    monkeypatch.setenv("NEAR_ACCOUNT_HMAC_KEY", "11" * 32)
    monkeypatch.setenv("TX_DEDUP_KEY", "22" * 32)
    monkeypatch.setenv("ACB_DEDUP_KEY", "33" * 32)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-internal-token")


# ---------------------------------------------------------------------------
# POST /api/accountant/grant
# ---------------------------------------------------------------------------


def test_grant_creates_rewrapped_dek():
    """POST /api/accountant/grant INSERTs a row with rewrapped_client_dek.

    The accountant must have a valid ML-KEM public key (mlkem_ek).
    The endpoint fetches the accountant's mlkem_ek, calls rewrap_dek_for_grantee,
    and stores the result in accountant_access.
    """
    from db.crypto import ML_KEM_768_EK_LEN
    from kyber_py.ml_kem import ML_KEM_768

    # Generate a real ML-KEM-768 keypair for the accountant so rewrapping works
    acct_ek, _acct_dk = ML_KEM_768.keygen()
    assert len(acct_ek) == ML_KEM_768_EK_LEN

    # Mock: first fetchone → accountant lookup (returns user_id + mlkem_ek)
    # second is the RETURNING from the INSERT
    mock_pool, mock_cursor = _make_pool_and_cursor(
        fetchone_side=[
            (20, acct_ek),  # SELECT id, mlkem_ek FROM users WHERE email_hmac = ?
            (99,),           # INSERT ... RETURNING id
        ]
    )

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: _CLIENT_USER
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(_CLIENT_USER)

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            r = client.post(
                "/api/accountant/grant",
                json={
                    "accountant_email_hmac": "abc123hmac",
                    "access_level": "read",
                },
            )

    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["grant_id"] == 99
    assert data["accountant_user_id"] == 20

    # Verify that an INSERT was called with a non-empty rewrapped_client_dek.
    # execute calls: [SELECT users, INSERT accountant_access, SELECT RETURNING]
    all_calls = mock_cursor.execute.call_args_list
    insert_calls = [
        c for c in all_calls
        if "INSERT" in str(c[0][0]).upper()
    ]
    assert len(insert_calls) >= 1, f"Expected at least one INSERT call, got: {[str(c[0][0])[:50] for c in all_calls]}"
    insert_params = insert_calls[0][0][1]
    # params: (accountant_user_id, client_user_id, access_level, rewrapped_client_dek)
    rewrapped_dek_blob = insert_params[3]
    assert rewrapped_dek_blob is not None
    assert len(rewrapped_dek_blob) > 32, "rewrapped DEK must be a proper KEM-wrapped blob"

    app.dependency_overrides.clear()


def test_grant_unknown_accountant_returns_404():
    """POST /api/accountant/grant returns 404 when email_hmac doesn't match any user."""
    mock_pool, _ = _make_pool_and_cursor(fetchone_side=[None])

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: _CLIENT_USER
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(_CLIENT_USER)

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.post(
                "/api/accountant/grant",
                json={
                    "accountant_email_hmac": "unknown-hmac",
                    "access_level": "read",
                },
            )

    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
    app.dependency_overrides.clear()


def test_grant_accountant_no_mlkem_key_returns_400():
    """POST /api/accountant/grant returns 400 when accountant has no ML-KEM key."""
    mock_pool, _ = _make_pool_and_cursor(
        fetchone_side=[(20, None)]  # mlkem_ek is NULL
    )

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: _CLIENT_USER
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(_CLIENT_USER)

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.post(
                "/api/accountant/grant",
                json={
                    "accountant_email_hmac": "some-hmac",
                    "access_level": "read",
                },
            )

    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    assert "ml-kem" in r.json()["detail"].lower() or "key" in r.json()["detail"].lower()
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# DELETE /api/accountant/access/{grant_id}
# ---------------------------------------------------------------------------


def test_revoke_deletes_grant():
    """DELETE /api/accountant/access/{grant_id} removes the grant row.

    Only the data owner (client) can revoke their own grants.
    Returns {"revoked": True, "grant_id": N} on success.
    """
    mock_pool, mock_cursor = _make_pool_and_cursor(
        fetchone_side=[(99,)]  # RETURNING id from DELETE
    )

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: _CLIENT_USER

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            r = client.delete("/api/accountant/access/99")

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["revoked"] is True
    assert data["grant_id"] == 99

    # Verify DELETE was issued with the right client_user_id scope
    delete_call = mock_cursor.execute.call_args_list[-1]
    sql = str(delete_call[0][0]).upper()
    assert "DELETE" in sql
    params = delete_call[0][1]
    # params should be (grant_id=99, client_user_id=10)
    assert 99 in params, f"grant_id=99 should be in DELETE params: {params}"
    assert 10 in params, f"client_user_id=10 should be in DELETE params: {params}"

    app.dependency_overrides.clear()


def test_revoke_wrong_owner_returns_404():
    """DELETE /api/accountant/access/{grant_id} returns 404 when grant not owned by caller.

    Client B cannot revoke client A's grant — the SQL WHERE clause enforces ownership
    via client_user_id = current_user_id.  Returning None from DELETE RETURNING means
    the row was not found or not owned.
    """
    mock_pool, _ = _make_pool_and_cursor(fetchone_side=[None])

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    # This is user 2 (not the grant owner)
    other_user = {**_CLIENT_USER, "user_id": 2}
    app.dependency_overrides[get_current_user] = lambda: other_user

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.delete("/api/accountant/access/99")

    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/accountant/sessions/materialize (internal endpoint)
# ---------------------------------------------------------------------------


def test_materialize_no_grants_returns_zero():
    """POST /api/accountant/sessions/materialize returns {materialized: 0} when no grants exist.

    If the accountant has no active grants (or all rewrapped_client_deks are NULL),
    the endpoint materializes zero rows and returns without error.
    """

    sealing_key = bytes.fromhex("44" * 32)  # 32 bytes

    mock_pool, mock_cursor = _make_pool_and_cursor(
        fetchall_side=[[]],  # no grants
    )
    # session lookup
    mock_cursor.fetchone.return_value = None  # session_client_dek_cache fetch doesn't run

    # For the _materialize inner function: first fetchall = grant_rows
    mock_cursor.fetchall.return_value = []

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            r = client.post(
                "/api/accountant/sessions/materialize",
                json={
                    "accountant_user_id": 20,
                    "session_id": "sess-acct-001",
                    "sealing_key_hex": sealing_key.hex(),
                },
                headers={"X-Internal-Service-Token": "test-internal-token"},
            )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["materialized"] == 0

    app.dependency_overrides.clear()


def test_materialize_missing_token_returns_401():
    """POST /api/accountant/sessions/materialize returns 401 without INTERNAL_SERVICE_TOKEN."""
    mock_pool, _ = _make_pool_and_cursor()

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.post(
                "/api/accountant/sessions/materialize",
                json={
                    "accountant_user_id": 20,
                    "session_id": "sess-001",
                    "sealing_key_hex": "44" * 32,
                },
                # No X-Internal-Service-Token header
            )

    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Accountant viewing via get_effective_user_with_dek (D-25)
# ---------------------------------------------------------------------------


def test_accountant_viewing_no_cache_returns_503():
    """get_effective_user_with_dek returns 503 when session_client_dek_cache has no row.

    When an accountant switches to a client (viewing_as_user_id set), the dependency
    must look up session_client_dek_cache.  Missing row → 503 (not materialized).
    """

    # Accountant user after get_effective_user resolves: user_id is the client's id
    viewing_user = {
        **_CLIENT_USER,
        "user_id": 10,                    # client's user_id (after resolution)
        "viewing_as_user_id": 20,         # accountant is user 20
    }

    mock_pool, mock_cursor = _make_pool_and_cursor()
    mock_cursor.fetchone.return_value = None  # no session_client_dek_cache row

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: viewing_user
    app.dependency_overrides[get_effective_user] = lambda: viewing_user
    # Do NOT override get_effective_user_with_dek — let the real one run

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get(
                "/api/wallets",
                cookies={"neartax_session": "sess-acct"},
            )

    assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"
    assert "session cache" in r.json().get("detail", "").lower()

    app.dependency_overrides.clear()


def test_accountant_viewing_cache_hit_returns_200():
    """Accountant with valid session_client_dek_cache row can access client data.

    The real get_effective_user_with_dek dependency is exercised:
      1. Sees viewing_as_user_id is set
      2. Queries session_client_dek_cache with (session_id, client_user_id)
      3. Unwraps the client DEK with SESSION_DEK_WRAP_KEY
      4. Injects client DEK via set_dek()
    The wallets endpoint then returns 200 with an empty list (no wallets in mock).
    """
    from db.crypto import wrap_session_dek, DEK_LEN

    # Create a valid session-wrapped client DEK
    client_dek = os.urandom(DEK_LEN)
    encrypted_client_dek = wrap_session_dek(client_dek)

    from datetime import datetime, timedelta, timezone
    future_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    # Accountant user after get_effective_user resolves
    viewing_user = {
        **_CLIENT_USER,
        "user_id": 10,           # client's user_id
        "viewing_as_user_id": 20,  # accountant user_id
    }

    mock_pool, mock_cursor = _make_pool_and_cursor()
    # session_client_dek_cache lookup returns a valid row
    mock_cursor.fetchone.return_value = (encrypted_client_dek, future_expiry)
    mock_cursor.fetchall.return_value = []  # empty wallet list

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: viewing_user
    app.dependency_overrides[get_effective_user] = lambda: viewing_user
    # Real get_effective_user_with_dek — no override

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            r = client.get(
                "/api/wallets",
                cookies={"neartax_session": "sess-acct"},
            )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    app.dependency_overrides.clear()
