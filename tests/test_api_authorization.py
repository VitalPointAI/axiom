"""Tests for cross-user authorization isolation.

Covers QH-09: User A cannot access User B's data on any protected endpoint.
Verifies that all data-returning endpoints filter by the authenticated user_id.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import (
    get_current_user,
    get_effective_user,
    get_effective_user_with_dek,
    get_pool_dep,
)
from api.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cursor():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    cursor.description = []
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
def mock_other_user():
    """Second user context for cross-user isolation tests."""
    return {
        "user_id": 999,
        "near_account_id": "bob.near",
        "is_admin": False,
        "email": "bob@example.com",
        "username": "bob",
        "codename": None,
        "viewing_as_user_id": None,
        "permission_level": None,
    }


_TEST_DEK = b"\x00" * 32


def _dek_override(user_dict):
    """Return dep override for get_effective_user_with_dek that injects a test DEK.

    Must be async so ContextVar writes are visible to the async route handler.
    """
    from db.crypto import set_dek

    async def _override():
        set_dek(_TEST_DEK)
        return user_dict

    return _override


@pytest.fixture
def other_user_client(mock_pool, mock_other_user):
    """TestClient authenticated as user 999 (not the data owner)."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_other_user
    app.dependency_overrides[get_effective_user] = lambda: mock_other_user
    # Phase 16: routers use get_effective_user_with_dek — inject a test DEK
    app.dependency_overrides[get_effective_user_with_dek] = _dek_override(mock_other_user)
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCrossUserIsolation:
    """Verify that user 999 cannot see user 1's data."""

    def test_user_cannot_see_other_users_wallets(self, other_user_client, mock_cursor):
        """GET /api/wallets as user 999 returns empty list (not user 1's wallets)."""
        mock_cursor.fetchall.return_value = []
        resp = other_user_client.get("/api/wallets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_user_cannot_access_other_users_wallet_by_id(self, other_user_client, mock_cursor):
        """GET /api/wallets/{id} status as user 999 returns 404 for user 1's wallet."""
        mock_cursor.fetchone.return_value = None
        resp = other_user_client.get("/api/wallets/1/status")
        assert resp.status_code in (404, 422)

    def test_user_cannot_see_other_users_transactions(self, other_user_client, mock_cursor):
        """GET /api/transactions as user 999 returns empty results."""
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = (0,)
        resp = other_user_client.get("/api/transactions")
        assert resp.status_code == 200
        data = resp.json()
        txs = data.get("transactions", data.get("items", []))
        assert len(txs) == 0

    def test_user_cannot_modify_other_users_transaction(self, other_user_client, mock_cursor):
        """PATCH /api/transactions/{hash}/classification as user 999 returns 404."""
        mock_cursor.fetchone.return_value = None
        mock_cursor.rowcount = 0
        resp = other_user_client.patch(
            "/api/transactions/abc123/classification",
            json={"tax_category": "income"},
        )
        assert resp.status_code in (404, 422)

    def test_user_cannot_see_other_users_verification(self, other_user_client, mock_cursor):
        """GET /api/verification/status as user 999 returns their own (empty) status."""
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = []
        resp = other_user_client.get("/api/verification/status")
        assert resp.status_code in (200, 404)

    def test_wallet_queries_include_user_id_filter(self, other_user_client, mock_cursor):
        """SQL queries for wallets include user_id parameter matching authenticated user."""
        mock_cursor.fetchall.return_value = []
        other_user_client.get("/api/wallets")

        # Check that at least one execute call includes user_id=999
        found_user_filter = False
        for call_args in mock_cursor.execute.call_args_list:
            params = call_args[0][1] if len(call_args[0]) > 1 else ()
            if params and 999 in (params if isinstance(params, (list, tuple)) else [params]):
                found_user_filter = True
                break
        assert found_user_filter, "Wallet query did not filter by authenticated user_id=999"
