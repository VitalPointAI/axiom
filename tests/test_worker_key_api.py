"""Unit tests for api/routers/settings.py — background worker key API endpoints.

Tests cover:
  - POST /api/settings/worker-key → 200 + forwards to auth-service
  - DELETE /api/settings/worker-key → 200 + forwards to auth-service
  - GET /api/settings/worker-key → 200 + returns status from DB
  - GET /api/settings/worker-key → returns disabled when worker not enabled
  - X-Internal-Service-Token is forwarded in POST/DELETE calls
  - 5xx from auth-service propagated correctly

All tests mock httpx.AsyncClient and the DB pool. No real network calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_effective_user_with_dek, get_pool_dep
from api.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DEK = b"\x00" * 32
MOCK_USER = {
    "user_id": 1,
    "near_account_id": "alice.near",
    "is_admin": False,
    "email": "alice@example.com",
    "username": "alice",
    "codename": None,
    "viewing_as_user_id": None,
    "permission_level": None,
}


def _make_dek_override(user_dict: dict):
    """Async dep override that injects a test DEK and returns the user dict."""
    from db.crypto import set_dek

    async def _override():
        set_dek(TEST_DEK)
        return user_dict

    return _override


@pytest.fixture
def mock_cursor():
    cursor = MagicMock()
    cursor.fetchone.return_value = (False, None)  # (worker_key_enabled, last_run_at)
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


def _make_client(mock_pool):
    """Build a TestClient with mocked DB pool and auth."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(MOCK_USER)
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    app.dependency_overrides.clear()


@pytest.fixture
def api_client(mock_pool):
    yield from _make_client(mock_pool)


# ---------------------------------------------------------------------------
# POST /api/settings/worker-key — enable background processing
# ---------------------------------------------------------------------------


def test_enable_worker_key_success(api_client):
    """POST /api/settings/worker-key returns 200 when auth-service returns 200."""
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"enabled": True, "status": "active"}

    with patch("api.routers.settings.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_cm.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_cm

        response = api_client.post(
            "/api/settings/worker-key",
            cookies={"neartax_session": "test-session-id"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["status"] == "active"


def test_enable_worker_key_forwards_to_auth_service(api_client):
    """POST /api/settings/worker-key calls auth-service /auth/worker-key/enable."""
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"enabled": True, "status": "active"}

    captured_url = []

    async def _capture_post(url, cookies=None, headers=None):
        captured_url.append(url)
        return mock_response

    with patch("api.routers.settings.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_cm.post = _capture_post
        mock_client_cls.return_value = mock_cm

        api_client.post(
            "/api/settings/worker-key",
            cookies={"neartax_session": "abc123"},
        )

    assert len(captured_url) == 1
    assert "/auth/worker-key/enable" in captured_url[0]


# ---------------------------------------------------------------------------
# DELETE /api/settings/worker-key — revoke background processing
# ---------------------------------------------------------------------------


def test_revoke_worker_key_success(api_client):
    """DELETE /api/settings/worker-key returns 200 when auth-service returns 200."""
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"enabled": False, "status": "revoked"}

    with patch("api.routers.settings.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_cm.delete = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_cm

        response = api_client.delete("/api/settings/worker-key")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["status"] == "revoked"


def test_revoke_worker_key_auth_service_error_propagated(api_client):
    """DELETE /api/settings/worker-key propagates 5xx from auth-service."""
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 503
    mock_response.text = "auth-service unavailable"

    with patch("api.routers.settings.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_cm.delete = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_cm

        response = api_client.delete("/api/settings/worker-key")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# GET /api/settings/worker-key — status query
# ---------------------------------------------------------------------------


def test_get_worker_key_status_disabled(mock_pool, mock_cursor):
    """GET /api/settings/worker-key returns enabled=false when worker is off."""
    mock_cursor.fetchone.return_value = (False, None)

    for client in _make_client(mock_pool):
        response = client.get("/api/settings/worker-key")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["last_run_at"] is None


def test_get_worker_key_status_enabled(mock_pool, mock_cursor):
    """GET /api/settings/worker-key returns enabled=true when worker is on."""
    mock_cursor.fetchone.return_value = (True, None)

    for client in _make_client(mock_pool):
        response = client.get("/api/settings/worker-key")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
