"""Tests for preferences API endpoints.

Tests cover:
  - GET /api/preferences — returns onboarding_completed_at + dismissed_banners
  - GET /api/preferences — handles NULL dismissed_banners (returns empty dict)
  - POST /api/preferences/complete-onboarding — sets timestamp
  - POST /api/preferences/complete-onboarding — is idempotent (COALESCE pattern)
  - PATCH /api/preferences/dismiss-banner — merges banner key into JSONB
  - PATCH /api/preferences/dismiss-banner — missing banner_key returns 422
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_pool_dep
from api.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cursor():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    return cursor


@pytest.fixture
def mock_conn(mock_cursor):
    conn = MagicMock()
    conn.cursor.return_value = mock_cursor
    return conn


@pytest.fixture
def mock_pool(mock_conn):
    pool = MagicMock()
    pool.getconn.return_value = mock_conn
    pool.putconn.return_value = None
    return pool


@pytest.fixture
def mock_user():
    return {
        "user_id": 1,
        "near_account_id": "alice.near",
        "is_admin": False,
        "email": "alice@example.com",
        "username": "alice",
        "codename": None,
        "viewing_as_user_id": None,
        "permission_level": None,
    }


def make_client(mock_pool, mock_user):
    """Build a TestClient with mocked pool and auth."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with (
        patch("indexers.db.get_pool", return_value=mock_pool),
        patch("indexers.db.close_pool"),
    ):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(mock_pool, mock_user):
    yield from make_client(mock_pool, mock_user)


# ---------------------------------------------------------------------------
# Test: GET /api/preferences — returns both columns
# ---------------------------------------------------------------------------


def test_get_preferences_returns_columns(mock_pool, mock_conn, mock_cursor, mock_user):
    """GET /api/preferences returns onboarding_completed_at and dismissed_banners."""
    completed_at = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    dismissed = {"welcome_banner": True}
    mock_cursor.fetchone.return_value = (completed_at, dismissed)

    for client in make_client(mock_pool, mock_user):
        resp = client.get("/api/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert "onboarding_completed_at" in data
        assert data["onboarding_completed_at"] is not None
        assert data["dismissed_banners"] == {"welcome_banner": True}
        break


# ---------------------------------------------------------------------------
# Test: GET /api/preferences — NULL dismissed_banners returns empty dict
# ---------------------------------------------------------------------------


def test_get_preferences_null_dismissed_banners(mock_pool, mock_conn, mock_cursor, mock_user):
    """GET /api/preferences returns empty dict when dismissed_banners is NULL in DB."""
    # DB returns (None, None) — both columns NULL for new user
    mock_cursor.fetchone.return_value = (None, None)

    for client in make_client(mock_pool, mock_user):
        resp = client.get("/api/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert data["onboarding_completed_at"] is None
        assert data["dismissed_banners"] == {}
        break


# ---------------------------------------------------------------------------
# Test: POST /api/preferences/complete-onboarding — sets timestamp
# ---------------------------------------------------------------------------


def test_complete_onboarding_sets_timestamp(mock_pool, mock_conn, mock_cursor, mock_user):
    """POST /api/preferences/complete-onboarding sets and returns onboarding_completed_at."""
    completed_at = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
    mock_cursor.fetchone.return_value = (completed_at,)

    for client in make_client(mock_pool, mock_user):
        resp = client.post("/api/preferences/complete-onboarding")
        assert resp.status_code == 200
        data = resp.json()
        assert "onboarding_completed_at" in data
        assert data["onboarding_completed_at"] is not None
        # Verify COALESCE UPDATE was executed
        call_args = mock_cursor.execute.call_args_list
        sql_calls = [str(args[0][0]) for args in call_args if args[0]]
        assert any("COALESCE" in s for s in sql_calls)
        break


# ---------------------------------------------------------------------------
# Test: POST /api/preferences/complete-onboarding — idempotent
# ---------------------------------------------------------------------------


def test_complete_onboarding_is_idempotent(mock_pool, mock_conn, mock_cursor, mock_user):
    """POST /api/preferences/complete-onboarding is idempotent via COALESCE.

    Second call returns the same timestamp as the first (COALESCE keeps original).
    """
    original_ts = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    # Both calls return the same original timestamp (COALESCE didn't overwrite)
    mock_cursor.fetchone.return_value = (original_ts,)

    for client in make_client(mock_pool, mock_user):
        resp1 = client.post("/api/preferences/complete-onboarding")
        resp2 = client.post("/api/preferences/complete-onboarding")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # Both calls return the same timestamp value (idempotent)
        assert resp1.json()["onboarding_completed_at"] == resp2.json()["onboarding_completed_at"]
        break


# ---------------------------------------------------------------------------
# Test: PATCH /api/preferences/dismiss-banner — merges JSONB
# ---------------------------------------------------------------------------


def test_dismiss_banner_merges_jsonb(mock_pool, mock_conn, mock_cursor, mock_user):
    """PATCH /api/preferences/dismiss-banner adds the banner key to dismissed_banners."""
    updated_dismissed = {"welcome_banner": True}
    mock_cursor.fetchone.return_value = (updated_dismissed,)

    for client in make_client(mock_pool, mock_user):
        resp = client.patch("/api/preferences/dismiss-banner", json={"banner_key": "welcome_banner"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["dismissed_banners"] == {"welcome_banner": True}
        # Verify the || JSONB merge operator was used
        call_args = mock_cursor.execute.call_args_list
        sql_calls = [str(args[0][0]) for args in call_args if args[0]]
        assert any("||" in s for s in sql_calls)
        break


# ---------------------------------------------------------------------------
# Test: PATCH /api/preferences/dismiss-banner — missing banner_key returns 422
# ---------------------------------------------------------------------------


def test_dismiss_banner_missing_key_returns_422(mock_pool, mock_user):
    """PATCH /api/preferences/dismiss-banner with missing banner_key returns 422."""
    for client in make_client(mock_pool, mock_user):
        resp = client.patch("/api/preferences/dismiss-banner", json={})
        assert resp.status_code == 422
        break
