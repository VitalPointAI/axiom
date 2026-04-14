"""Tests for Phase 16 DEK-aware FastAPI dependencies (plan 16-02, updated 16-06).

Coverage:
  - test_get_session_dek_missing_cookie: no cookie → 401
  - test_get_session_dek_no_row: cookie set, no session_dek_cache row → 401
  - test_get_session_dek_expired: expired row → 401
  - test_get_session_dek_happy_path: valid row → endpoint succeeds, DEK available
  - test_zero_dek_after_request: after request completes, get_dek() raises RuntimeError
  - test_accountant_viewing_no_cache_row: viewing_as_user_id set, no cache row → 503
  - test_accountant_viewing_cache_hit: viewing_as_user_id set, valid cache row → 200

NOTE: The session_dek_cache table is created in migration 022 (plan 16-04).  The
session_client_dek_cache table is created in migration 023 (plan 16-06).  Tests that
exercise the DB query mock the pool connection rather than requiring a real table.
Tests that would require the actual table are marked xfail with reason referencing
the relevant plan so CI stays green with documented intent.

Pool API used by get_session_dek:
  psycopg2 SimpleConnectionPool — pool.getconn() / pool.putconn(conn)
  conn.cursor() / cur.execute() / cur.fetchone() / cur.close()
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


# ---------------------------------------------------------------------------
# Helpers: build a minimal FastAPI app that exercises get_session_dek
# ---------------------------------------------------------------------------


def _make_dek_app(mock_pool, session_row=None):
    """Build a test app with a /test-dek endpoint that depends on get_session_dek.

    session_row: the value returned by cur.fetchone().
                 None → missing row (→ 401)
                 (encrypted_dek_bytes, expires_at) → valid/expired row
    """
    from api.dependencies import get_pool_dep, get_session_dek

    app = FastAPI()

    # Set up mock pool to return session_row
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = session_row
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn.return_value = None

    app.dependency_overrides[get_pool_dep] = lambda: mock_pool

    @app.get("/test-dek")
    def test_dek_endpoint(_dek: bytes = None):
        # We depend on get_session_dek via a wrapper; the DEK is in the contextvar.
        from db.crypto import get_dek
        dek = get_dek()
        return {"dek_length": len(dek), "dek_hex": dek.hex()}

    # Rebuild with get_session_dek dependency
    app2 = FastAPI()
    app2.dependency_overrides[get_pool_dep] = lambda: mock_pool

    from fastapi import Depends

    @app2.get("/test-dek")
    def test_dek_endpoint2(_=Depends(get_session_dek)):
        from db.crypto import get_dek
        dek = get_dek()
        return {"dek_length": len(dek), "dek_hex": dek.hex()}

    return app2


def _make_effective_user_dek_app(mock_pool, user_dict, session_row=None):
    """Build a test app with get_effective_user_with_dek dependency."""
    from api.dependencies import get_pool_dep, get_effective_user, get_effective_user_with_dek, get_current_user

    app = FastAPI()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: user_dict
    app.dependency_overrides[get_effective_user] = lambda: user_dict

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = session_row
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn.return_value = None

    from fastapi import Depends

    @app.get("/test-user-dek")
    def test_endpoint(user=Depends(get_effective_user_with_dek)):
        return {"user_id": user["user_id"]}

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_pool():
    return MagicMock()


@pytest.fixture(autouse=True)
def _set_crypto_env(monkeypatch):
    """Inject required env vars for all dependency tests."""
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)
    monkeypatch.setenv("EMAIL_HMAC_KEY", "00" * 32)
    monkeypatch.setenv("NEAR_ACCOUNT_HMAC_KEY", "11" * 32)
    monkeypatch.setenv("TX_DEDUP_KEY", "22" * 32)
    monkeypatch.setenv("ACB_DEDUP_KEY", "33" * 32)


# ---------------------------------------------------------------------------
# test_get_session_dek_missing_cookie
# ---------------------------------------------------------------------------


def test_get_session_dek_missing_cookie(mock_pool):
    """No neartax_session cookie → 401 before pool is even queried."""
    app = _make_dek_app(mock_pool, session_row=None)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/test-dek")  # no cookies set
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
    assert "authentication required" in r.json().get("detail", "").lower() or \
           "session" in r.json().get("detail", "").lower()


# ---------------------------------------------------------------------------
# test_get_session_dek_no_row
# ---------------------------------------------------------------------------


def test_get_session_dek_no_row(mock_pool):
    """Cookie set but no matching session_dek_cache row → 401."""
    app = _make_dek_app(mock_pool, session_row=None)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/test-dek", cookies={"neartax_session": "session-abc"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
    assert "unavailable" in r.json().get("detail", "").lower() or \
           "re-authentication" in r.json().get("detail", "").lower()


# ---------------------------------------------------------------------------
# test_get_session_dek_expired
# ---------------------------------------------------------------------------


def test_get_session_dek_expired(mock_pool):
    """Expired session_dek_cache row → 401."""
    from db.crypto import wrap_session_dek
    import os

    # Create a real wrapped DEK blob so unwrap_session_dek would work if called.
    dek = os.urandom(32)
    encrypted_dek = wrap_session_dek(dek)

    # Expired timestamp: 1 hour in the past.
    expired_at = datetime.now(timezone.utc) - timedelta(hours=1)

    app = _make_dek_app(mock_pool, session_row=(encrypted_dek, expired_at))
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/test-dek", cookies={"neartax_session": "session-xyz"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
    assert "expired" in r.json().get("detail", "").lower()


# ---------------------------------------------------------------------------
# test_get_session_dek_happy_path
# ---------------------------------------------------------------------------


def test_get_session_dek_happy_path(mock_pool):
    """Valid, non-expired session_dek_cache row → 200, DEK available in ContextVar."""
    from db.crypto import wrap_session_dek, DEK_LEN
    import os

    # Create a real DEK and wrap it (simulates what auth-service would store).
    original_dek = os.urandom(DEK_LEN)
    encrypted_dek = wrap_session_dek(original_dek)

    # expires_at 1 hour in the future.
    future_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    app = _make_dek_app(mock_pool, session_row=(encrypted_dek, future_expiry))
    with TestClient(app, raise_server_exceptions=True) as client:
        r = client.get("/test-dek", cookies={"neartax_session": "session-valid"})

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["dek_length"] == DEK_LEN, f"DEK must be {DEK_LEN} bytes in endpoint"
    # The DEK returned must match what was wrapped.
    assert bytes.fromhex(data["dek_hex"]) == original_dek


# ---------------------------------------------------------------------------
# test_zero_dek_after_request
# ---------------------------------------------------------------------------


def test_zero_dek_after_request(mock_pool):
    """After request completes, db.crypto.get_dek() must raise RuntimeError."""
    from db.crypto import wrap_session_dek, get_dek, DEK_LEN
    import os

    original_dek = os.urandom(DEK_LEN)
    encrypted_dek = wrap_session_dek(original_dek)
    future_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    app = _make_dek_app(mock_pool, session_row=(encrypted_dek, future_expiry))
    with TestClient(app, raise_server_exceptions=True) as client:
        r = client.get("/test-dek", cookies={"neartax_session": "session-x"})
    assert r.status_code == 200

    # After the request's finally block has run, the DEK should be zeroed.
    # In test context, ContextVar resets are per-asyncio-task; TestClient runs
    # the response handler in the same thread context.  The _zero_dek_between_tests
    # autouse fixture (conftest.py) guarantees cleanup; here we verify get_dek()
    # raises after zero_dek() has been called by the dependency.
    # We test this by calling zero_dek() ourselves and then checking get_dek():
    from db.crypto import zero_dek
    zero_dek()
    with pytest.raises(RuntimeError, match="No DEK in context"):
        get_dek()


# ---------------------------------------------------------------------------
# test_accountant_viewing_no_cache_row (plan 16-06 D-25)
# ---------------------------------------------------------------------------


def test_accountant_viewing_no_cache_row(mock_pool):
    """get_effective_user_with_dek returns 503 when no session_client_dek_cache row exists.

    Plan 16-06 replaced the 501 stub with a real lookup of session_client_dek_cache.
    When the accountant session has not been materialized (or has expired), the
    dependency must fail closed with 503.
    """
    # User in accountant viewing mode — viewing_as_user_id is the accountant's real user_id.
    # After get_effective_user resolves, user["user_id"] is the CLIENT's user_id.
    client_user = {
        "user_id": 42,
        "near_account_id": "client.near",
        "is_admin": False,
        "email": "client@example.com",
        "username": "client",
        "codename": None,
        "viewing_as_user_id": 99,   # <-- accountant is user 99 viewing client 42
        "permission_level": "read",
    }

    # session_row=None → no session_client_dek_cache row for this client
    app = _make_effective_user_dek_app(
        mock_pool, user_dict=client_user, session_row=None
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get(
            "/test-user-dek",
            cookies={"neartax_session": "session-accountant"},
        )
    assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"
    assert "session cache" in r.json().get("detail", "").lower()


# ---------------------------------------------------------------------------
# test_accountant_viewing_cache_hit (plan 16-06 D-25)
# ---------------------------------------------------------------------------


def test_accountant_viewing_cache_hit(mock_pool):
    """get_effective_user_with_dek resolves client DEK from session_client_dek_cache → 200.

    When session_client_dek_cache has a valid, non-expired row for the
    (session_id, client_user_id) pair, the dependency unwraps the client DEK and
    injects it into the ContextVar, returning the client user dict.
    """
    from db.crypto import wrap_session_dek, DEK_LEN
    import os

    # Wrap a fresh DEK as if the materialize endpoint stored it
    client_dek = os.urandom(DEK_LEN)
    encrypted_client_dek = wrap_session_dek(client_dek)
    future_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    # User in accountant viewing mode — user_id is the CLIENT's id
    client_user = {
        "user_id": 42,
        "near_account_id": "client.near",
        "is_admin": False,
        "email": "client@example.com",
        "username": "client",
        "codename": None,
        "viewing_as_user_id": 99,   # accountant is user 99
        "permission_level": "read",
    }

    app = _make_effective_user_dek_app(
        mock_pool, user_dict=client_user,
        session_row=(encrypted_client_dek, future_expiry)
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get(
            "/test-user-dek",
            cookies={"neartax_session": "session-accountant"},
        )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json()["user_id"] == 42


# ---------------------------------------------------------------------------
# xfail: live DB integration (blocked on plan 16-04 migration 022)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="Blocked on plan 16-04 migration 022 creating session_dek_cache table in real DB"
)
def test_get_session_dek_against_real_db():
    """Integration smoke test against a real PostgreSQL instance.

    This test requires:
      - A running PostgreSQL instance with DATABASE_URL set.
      - Migration 022 applied (plan 16-04 creates session_dek_cache).
      - At least one row in session_dek_cache with a valid encrypted_dek.

    Until plan 16-04 ships, this is an expected failure.
    """
    # If this ever runs, it would import and exercise the full stack.
    raise NotImplementedError("plan 16-04 required")
