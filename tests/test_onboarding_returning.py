"""Unit tests for /api/users/me endpoint — returning-user onboarding detection (D-21).

Tests cover:
  - GET /api/users/me returns mlkem_ek_provisioned=true when user has mlkem_ek
  - GET /api/users/me returns mlkem_ek_provisioned=false when user has no mlkem_ek
  - GET /api/users/me includes wallet_count field
  - GET /api/users/me includes onboarding_completed_at field
  - GET /api/users/me returns 200 for authenticated user

All tests mock the DB pool. The endpoint uses get_effective_user (no DEK required —
mlkem_ek_provisioned is a metadata-level check not requiring decryption).
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_effective_user, get_pool_dep
from api.main import create_app

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


@pytest.fixture
def mock_cursor():
    cursor = MagicMock()
    cursor.fetchone.return_value = (True, None)   # (mlkem_ek_provisioned, onboarding_completed_at)
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
    """Build a TestClient with mocked pool and auth."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_effective_user] = lambda: MOCK_USER
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/users/me tests
# ---------------------------------------------------------------------------


def test_users_me_mlkem_ek_provisioned(mock_pool, mock_cursor):
    """GET /api/users/me returns mlkem_ek_provisioned=true when user has mlkem_ek."""
    # fetchone for user query: (mlkem_ek_provisioned=True, onboarding_completed_at=None)
    # fetchone for wallet count: (0,)
    mock_cursor.fetchone.side_effect = [(True, None), (0,)]

    for client in _make_client(mock_pool):
        response = client.get("/api/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["mlkem_ek_provisioned"] is True
    assert "wallet_count" in data
    assert "onboarding_completed_at" in data


def test_users_me_mlkem_ek_not_provisioned(mock_pool, mock_cursor):
    """GET /api/users/me returns mlkem_ek_provisioned=false when user has no mlkem_ek."""
    # fetchone for user query: (mlkem_ek_provisioned=False, onboarding_completed_at=None)
    # fetchone for wallet count: (0,)
    mock_cursor.fetchone.side_effect = [(False, None), (0,)]

    for client in _make_client(mock_pool):
        response = client.get("/api/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["mlkem_ek_provisioned"] is False


def test_users_me_wallet_count(mock_pool, mock_cursor):
    """GET /api/users/me includes wallet_count reflecting the user's wallets."""
    mock_cursor.fetchone.side_effect = [(True, None), (3,)]

    for client in _make_client(mock_pool):
        response = client.get("/api/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["wallet_count"] == 3


def test_users_me_onboarding_completed_at_null(mock_pool, mock_cursor):
    """GET /api/users/me returns onboarding_completed_at=null when not completed."""
    mock_cursor.fetchone.side_effect = [(True, None), (0,)]

    for client in _make_client(mock_pool):
        response = client.get("/api/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["onboarding_completed_at"] is None


def test_users_me_includes_user_id(mock_pool, mock_cursor):
    """GET /api/users/me includes the user_id field."""
    mock_cursor.fetchone.side_effect = [(False, None), (0,)]

    for client in _make_client(mock_pool):
        response = client.get("/api/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == MOCK_USER["user_id"]


def test_users_me_no_auth_returns_401(mock_pool):
    """GET /api/users/me without auth returns 401."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    # No auth override — get_effective_user will fail with no session cookie
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/users/me")
    assert response.status_code == 401
