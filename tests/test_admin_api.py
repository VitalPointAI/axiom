"""Tests for admin cost dashboard and indexing status API endpoints.

Tests:
  - GET /api/admin/cost-summary returns monthly cost aggregation
  - GET /api/admin/cost-summary?chain=near filters by chain
  - GET /api/admin/indexing-status returns per-chain health
  - GET /api/admin/budget-alerts returns chains exceeding monthly budget
  - All admin endpoints require authentication
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.dependencies import get_current_user, get_pool_dep


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
def mock_admin():
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


@pytest.fixture
def admin_client(mock_pool, mock_admin):
    """TestClient with admin auth and mock DB."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


@pytest.fixture
def user_client(mock_pool, mock_user):
    """TestClient with non-admin user and mock DB."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client(mock_pool):
    """TestClient with no auth (no dependency override)."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/admin/cost-summary tests
# ---------------------------------------------------------------------------


class TestCostSummary:
    def test_cost_summary_returns_monthly_data(self, admin_client, mock_cursor):
        """Admin cost-summary returns list of monthly cost records."""
        mock_cursor.fetchall.return_value = [
            ("near", "neardata_xyz", "block_fetch", "2026-03-01", 100, 0.0),
            ("ethereum", "etherscan", "wallet_txns", "2026-03-01", 50, 0.25),
        ]

        resp = admin_client.get("/api/admin/cost-summary")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        # First record should have expected fields
        first = data[0]
        assert "chain" in first
        assert "provider" in first
        assert "call_type" in first
        assert "month" in first
        assert "call_count" in first
        assert "total_cost_usd" in first

    def test_cost_summary_filtered_by_chain(self, admin_client, mock_cursor):
        """Admin cost-summary?chain=near filters rows to near chain only."""
        mock_cursor.fetchall.return_value = [
            ("near", "neardata_xyz", "block_fetch", "2026-03-01", 100, 0.0),
        ]

        resp = admin_client.get("/api/admin/cost-summary?chain=near")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["chain"] == "near"
        # Verify chain filter was passed to SQL
        call_args = mock_cursor.execute.call_args
        assert call_args is not None
        sql = call_args[0][0]
        assert "chain" in sql.lower()

    def test_cost_summary_empty_result(self, admin_client, mock_cursor):
        """Admin cost-summary returns empty list when no data."""
        mock_cursor.fetchall.return_value = []

        resp = admin_client.get("/api/admin/cost-summary")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_cost_summary_requires_admin(self, user_client):
        """Non-admin user gets 403 from cost-summary endpoint."""
        resp = user_client.get("/api/admin/cost-summary")
        assert resp.status_code == 403

    def test_cost_summary_requires_auth(self, unauth_client):
        """Unauthenticated request gets 401 from cost-summary endpoint."""
        resp = unauth_client.get("/api/admin/cost-summary")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/indexing-status tests
# ---------------------------------------------------------------------------


class TestIndexingStatus:
    def test_indexing_status_returns_per_chain_data(self, admin_client, mock_cursor):
        """Admin indexing-status returns per-chain health records."""
        mock_cursor.fetchall.return_value = [
            ("near", True, "NearStreamFetcher", "2026-03-21T10:00:00", "completed", "2026-03-21T10:05:00"),
            ("ethereum", True, "EVMFetcher", "2026-03-21T09:00:00", "running", None),
        ]

        resp = admin_client.get("/api/admin/indexing-status")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        first = data[0]
        assert "chain" in first
        assert "enabled" in first
        assert "fetcher_class" in first

    def test_indexing_status_empty(self, admin_client, mock_cursor):
        """Admin indexing-status returns empty list when no chains configured."""
        mock_cursor.fetchall.return_value = []

        resp = admin_client.get("/api/admin/indexing-status")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_indexing_status_requires_admin(self, user_client):
        """Non-admin user gets 403 from indexing-status endpoint."""
        resp = user_client.get("/api/admin/indexing-status")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/admin/budget-alerts tests
# ---------------------------------------------------------------------------


class TestBudgetAlerts:
    def test_budget_alerts_returns_over_budget_chains(self, admin_client, mock_cursor):
        """Admin budget-alerts returns chains exceeding monthly budget."""
        # Query returns rows: (chain, monthly_budget_usd, current_spend)
        mock_cursor.fetchall.return_value = [
            ("ethereum", 10.0, 15.5),
        ]

        resp = admin_client.get("/api/admin/budget-alerts")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        alert = data[0]
        assert "chain" in alert
        assert "monthly_budget_usd" in alert
        assert "current_spend_usd" in alert
        assert alert["chain"] == "ethereum"
        assert alert["current_spend_usd"] > alert["monthly_budget_usd"]

    def test_budget_alerts_empty_when_all_under_budget(self, admin_client, mock_cursor):
        """Admin budget-alerts returns empty list when all chains are under budget."""
        mock_cursor.fetchall.return_value = []

        resp = admin_client.get("/api/admin/budget-alerts")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_budget_alerts_requires_admin(self, user_client):
        """Non-admin user gets 403 from budget-alerts endpoint."""
        resp = user_client.get("/api/admin/budget-alerts")
        assert resp.status_code == 403
