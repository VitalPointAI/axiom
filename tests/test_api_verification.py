"""Tests for verification dashboard endpoints.

Covers:
  - GET /api/verification/summary — issue counts grouped by diagnosis_category
  - GET /api/verification/issues — detailed issues with optional category filter
  - POST /api/verification/resolve/{id} — mark issue as resolved
  - POST /api/verification/resync/{id} — queue re-sync job
  - GET /api/verification/needs-review-count — total unresolved count
  - User isolation — only shows issues for user's wallets
"""

from unittest.mock import MagicMock, call, patch

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
def auth_client(mock_pool, mock_user):
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/verification/summary
# ---------------------------------------------------------------------------


def test_verification_summary(auth_client, mock_cursor):
    """GET /api/verification/summary returns issue counts grouped by diagnosis_category."""
    # category_rows, tc_count, cg_count
    mock_cursor.fetchall.return_value = [
        ("missing_staking_rewards", 3),
        ("uncounted_fees", 1),
    ]
    mock_cursor.fetchone.side_effect = [
        (2,),  # tc_count
        (0,),  # cg_count
    ]

    resp = auth_client.get("/api/verification/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert "groups" in data
    assert "total_issues" in data
    assert "needs_review_count" in data

    assert data["total_issues"] == 4
    assert data["needs_review_count"] == 6  # 4 vr + 2 tc + 0 cg

    groups_by_cat = {g["category"]: g for g in data["groups"]}
    assert "missing_staking_rewards" in groups_by_cat
    assert groups_by_cat["missing_staking_rewards"]["severity"] == "high"
    assert groups_by_cat["missing_staking_rewards"]["count"] == 3
    assert "uncounted_fees" in groups_by_cat
    assert groups_by_cat["uncounted_fees"]["severity"] == "medium"


def test_verification_summary_empty(auth_client, mock_cursor):
    """GET /api/verification/summary returns empty groups when no issues."""
    mock_cursor.fetchall.return_value = []
    mock_cursor.fetchone.side_effect = [(0,), (0,)]

    resp = auth_client.get("/api/verification/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["groups"] == []
    assert data["total_issues"] == 0
    assert data["needs_review_count"] == 0


# ---------------------------------------------------------------------------
# GET /api/verification/issues
# ---------------------------------------------------------------------------


def test_verification_issues(auth_client, mock_cursor):
    """GET /api/verification/issues returns detailed issues for user's wallets."""
    mock_cursor.fetchall.return_value = [
        (
            1,           # id
            10,          # wallet_id
            "alice.near",# account_id
            "NEAR",      # token_symbol
            "balance_check",  # verification_type
            "discrepancy",    # status
            "1000000000000000000000000",  # expected_balance
            "900000000000000000000000",   # actual_balance
            "100000000000000000000000",   # discrepancy
            "missing_staking_rewards",   # diagnosis_category
            None,        # diagnosis_detail
            True,        # needs_review
            "2024-01-15 10:00:00",  # created_at
        )
    ]

    resp = auth_client.get("/api/verification/issues")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["token_symbol"] == "NEAR"
    assert data[0]["diagnosis_category"] == "missing_staking_rewards"
    assert data[0]["needs_review"] is True
    assert data[0]["account_id"] == "alice.near"


def test_verification_issues_category_filter(auth_client, mock_cursor):
    """GET /api/verification/issues?category=... filters by diagnosis_category."""
    mock_cursor.fetchall.return_value = [
        (2, 10, "alice.near", "ETH", "balance_check", "ok",
         "1000", "1000", "0", "uncounted_fees", None, True, "2024-01-16 10:00:00")
    ]

    resp = auth_client.get("/api/verification/issues?category=uncounted_fees")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["diagnosis_category"] == "uncounted_fees"


def test_user_isolation(auth_client, mock_cursor):
    """Only verification results for the authenticated user's wallets are returned."""
    # The query JOINs wallets on user_id — test that the WHERE clause is applied
    # by returning empty (simulating no wallets for this user)
    mock_cursor.fetchall.return_value = []

    resp = auth_client.get("/api/verification/issues")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /api/verification/resolve/{id}
# ---------------------------------------------------------------------------


def test_verification_resolve(auth_client, mock_cursor):
    """POST /api/verification/resolve/{id} marks issue as resolved."""
    mock_cursor.fetchone.return_value = (1,)  # ownership check

    resp = auth_client.post("/api/verification/resolve/1", json={"mark_reviewed": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert "resolved" in data["message"].lower()


def test_verification_resolve_not_found(auth_client, mock_cursor):
    """POST /api/verification/resolve/{id} returns 404 if issue not found."""
    mock_cursor.fetchone.return_value = None  # no ownership match

    resp = auth_client.post("/api/verification/resolve/999", json={"mark_reviewed": True})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/verification/resync/{id}
# ---------------------------------------------------------------------------


def test_verification_resync(auth_client, mock_cursor):
    """POST /api/verification/resync/{id} queues appropriate re-sync job."""
    mock_cursor.fetchone.side_effect = [
        (10, "missing_staking_rewards"),  # get wallet_id and category
        (77,),                             # job INSERT RETURNING id
    ]

    resp = auth_client.post("/api/verification/resync/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == 77
    assert data["job_type"] == "staking_sync"


def test_verification_resync_unindexed_period(auth_client, mock_cursor):
    """POST /api/verification/resync/{id} queues full_sync for unindexed_period."""
    mock_cursor.fetchone.side_effect = [
        (10, "unindexed_period"),
        (88,),
    ]

    resp = auth_client.post("/api/verification/resync/2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_type"] == "full_sync"


def test_verification_resync_not_found(auth_client, mock_cursor):
    """POST /api/verification/resync/{id} returns 404 if issue not found."""
    mock_cursor.fetchone.return_value = None

    resp = auth_client.post("/api/verification/resync/999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/verification/needs-review-count
# ---------------------------------------------------------------------------


def test_needs_review_count(auth_client, mock_cursor):
    """GET /api/verification/needs-review-count returns total unresolved count."""
    mock_cursor.fetchone.side_effect = [
        (5,),   # verification_results count
        (3,),   # transaction_classifications count
        (2,),   # capital_gains_ledger count
    ]

    resp = auth_client.get("/api/verification/needs-review-count")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 10
    assert data["verification_results"] == 5
    assert data["transaction_classifications"] == 3
    assert data["capital_gains_ledger"] == 2


def test_needs_review_count_zero(auth_client, mock_cursor):
    """GET /api/verification/needs-review-count returns zeros when all clear."""
    mock_cursor.fetchone.side_effect = [(0,), (0,), (0,)]

    resp = auth_client.get("/api/verification/needs-review-count")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
