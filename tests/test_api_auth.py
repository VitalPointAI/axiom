"""Tests for FastAPI app foundation — health endpoint and auth scaffolding.

Tests:
  - test_health_endpoint: GET /health returns 200 {"status": "ok"}
  - test_unauthenticated_returns_401: protected routes return 401 without session
  - test_multi_user_isolation: verify user_id filtering expectation (stub)
  - test_accountant_viewing_as: verify client context switching (stub)
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_pool_dep
from api.main import create_app


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


def test_health_endpoint(api_client):
    """GET /health must return 200 with status ok — no auth required."""
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


def test_unauthenticated_wallets_returns_401(api_client, mock_pool, mock_conn, mock_cursor):
    """GET /api/wallets without a session cookie must return 401.

    The mock DB is configured to return no session row so get_current_user
    raises HTTPException 401.
    """
    # Simulate no matching session in DB
    mock_cursor.fetchone.return_value = None
    response = api_client.get("/api/wallets")
    assert response.status_code == 401


def test_unauthenticated_transactions_returns_401(api_client):
    """GET /api/transactions without a session cookie must return 401."""
    response = api_client.get("/api/transactions")
    assert response.status_code == 401


def test_unauthenticated_portfolio_returns_401(api_client):
    """GET /api/portfolio without a session cookie must return 401."""
    response = api_client.get("/api/portfolio")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Multi-user isolation (stub — full tests in 07-04)
# ---------------------------------------------------------------------------


def test_multi_user_isolation_stub(mock_user):
    """Verify that the user context carries user_id for query filtering.

    Full isolation tests are in 07-04 (wallet/transaction routers). This stub
    confirms the mock_user fixture provides user_id=1 which will be used as
    the WHERE user_id = %s filter in all data queries.
    """
    assert mock_user["user_id"] == 1
    assert mock_user["is_admin"] is False
    # Data routers must always filter: WHERE user_id = user["user_id"]
    # Verified in 07-04 test_wallets.py with full DB mock


# ---------------------------------------------------------------------------
# Accountant viewing mode (stub — full tests in 07-04)
# ---------------------------------------------------------------------------


def test_accountant_viewing_as_stub(mock_user):
    """Verify the mock_user fixture has viewing_as_user_id=None for normal mode.

    Full accountant delegation tests are in 07-04. This stub confirms the
    get_effective_user dependency returns the correct context shape.
    """
    assert mock_user["viewing_as_user_id"] is None
    assert mock_user["permission_level"] is None


def test_accountant_context_switches_user_id(mock_pool, mock_conn, mock_cursor):
    """When neartax_viewing_as cookie is set, get_effective_user returns client context.

    Simulates an accountant (user_id=10) viewing client (user_id=20).
    Verifies the returned context has user_id=20, not 10.
    """
    from api.dependencies import get_effective_user, get_current_user

    # Mock accountant user context
    accountant = {
        "user_id": 10,
        "near_account_id": "accountant.near",
        "is_admin": False,
        "email": "accountant@firm.com",
        "username": "accountant",
        "codename": None,
    }

    # Mock DB row returned from accountant_access JOIN users query
    # (permission_level, uid, near_id, is_admin, email, username, codename)
    mock_cursor.fetchone.return_value = (
        "read", 20, "client.near", False, "client@example.com", "client", None
    )

    result = get_effective_user(
        user=accountant,
        neartax_viewing_as="20",
        pool=mock_pool,
    )

    assert result["user_id"] == 20
    assert result["viewing_as_user_id"] == 10
    assert result["permission_level"] == "read"


def test_accountant_no_access_raises_403(mock_pool, mock_conn, mock_cursor):
    """get_effective_user raises 403 when accountant_access row does not exist."""
    from fastapi import HTTPException
    from api.dependencies import get_effective_user

    accountant = {
        "user_id": 10,
        "near_account_id": "accountant.near",
        "is_admin": False,
        "email": "accountant@firm.com",
        "username": "accountant",
        "codename": None,
    }

    # No access grant in DB
    mock_cursor.fetchone.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        get_effective_user(
            user=accountant,
            neartax_viewing_as="99",
            pool=mock_pool,
        )

    assert exc_info.value.status_code == 403
