"""Shared pytest fixtures for all Axiom test modules.

Provides:
  - api_client: FastAPI TestClient with mocked DB pool
  - mock_pool: MagicMock psycopg2 SimpleConnectionPool
  - mock_conn: MagicMock psycopg2 connection
  - mock_user: Authenticated user dict (non-admin)
  - mock_admin: Authenticated user dict (admin)
  - auth_headers: Patches get_current_user to return mock_user
  - admin_auth_headers: Patches get_current_user to return mock_admin
"""

import os

# Set DATABASE_URL for test environment before any module-level imports.
# Tests use a mocked DB pool; this value is never used to connect,
# but validate_env() checks for its presence on startup.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("DB_POOL_MIN", "1")

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.dependencies import get_current_user, get_pool_dep


# ---------------------------------------------------------------------------
# DEK cleanup — zero between every test to prevent context leakage (Phase 16)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _zero_dek_between_tests():
    """Ensure the request-scoped DEK is zeroed after every test.

    This prevents DEK leakage across tests when tests call set_dek() without
    a corresponding zero_dek() (e.g. on test failure mid-way through).
    """
    yield
    try:
        from db.crypto import zero_dek
        zero_dek()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Mock database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cursor():
    """MagicMock psycopg2 cursor."""
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    return cursor


@pytest.fixture
def mock_conn(mock_cursor):
    """MagicMock psycopg2 connection that yields mock_cursor."""
    conn = MagicMock()
    conn.cursor.return_value = mock_cursor
    return conn


@pytest.fixture
def mock_pool(mock_conn):
    """MagicMock psycopg2 SimpleConnectionPool.

    getconn() returns mock_conn, putconn() is a no-op.
    """
    pool = MagicMock()
    pool.getconn.return_value = mock_conn
    pool.putconn.return_value = None
    return pool


# ---------------------------------------------------------------------------
# Auth user fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user():
    """Standard authenticated user context dict (non-admin)."""
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


@pytest.fixture
def mock_admin():
    """Authenticated admin user context dict."""
    return {
        "user_id": 2,
        "near_account_id": "admin.near",
        "is_admin": True,
        "email": "admin@example.com",
        "username": "admin",
        "codename": None,
        "viewing_as_user_id": None,
        "permission_level": None,
    }


# ---------------------------------------------------------------------------
# TestClient fixtures with mocked DB pool
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(mock_pool):
    """FastAPI TestClient with the DB pool dependency overridden.

    The get_pool_dep dependency is replaced with a mock so tests don't
    need a real PostgreSQL connection. The lifespan db.get_pool() call
    is also patched so startup doesn't require DATABASE_URL.
    """
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(mock_pool, mock_user):
    """FastAPI TestClient with both DB pool and authentication mocked.

    get_current_user is overridden to return mock_user, simulating a
    logged-in non-admin user without a real session cookie.
    """
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(mock_pool, mock_admin):
    """FastAPI TestClient with admin user authentication mocked."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()
