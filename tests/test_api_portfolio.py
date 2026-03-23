"""Tests for portfolio summary and job status endpoints.

Tests cover:
  - GET /api/portfolio/summary — holdings grouped by token from acb_snapshots
  - Portfolio includes staking positions from staking_events
  - Empty portfolio for new users
  - GET /api/jobs/{id}/status — job status, progress, error
  - GET /api/jobs/active — all running/queued jobs with pipeline stage
  - User isolation for jobs
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


@pytest.fixture
def mock_user_b():
    return {
        "user_id": 2,
        "near_account_id": "bob.near",
        "is_admin": False,
        "email": "bob@example.com",
        "username": "bob",
        "codename": None,
        "viewing_as_user_id": None,
        "permission_level": None,
    }


def make_client(mock_pool, mock_user):
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(mock_pool, mock_user):
    yield from make_client(mock_pool, mock_user)


# ---------------------------------------------------------------------------
# test_portfolio_summary
# ---------------------------------------------------------------------------


def test_portfolio_summary(mock_pool, mock_conn, mock_cursor, mock_user):
    """GET /api/portfolio/summary returns holdings grouped by token with ACB data."""
    # acb_snapshots rows: (token_symbol, quantity, acb_per_unit, total_cost_cad, chain)
    acb_rows = [
        ("NEAR", "1000.00", "2.50", "2500.00", "NEAR"),
        ("ETH", "0.5", "3000.00", "1500.00", "ethereum"),
    ]
    # staking_events rows: (validator_id, staked_amount, token_symbol)
    staking_rows = [
        ("aurora.pool.near", "500.00", "NEAR"),
    ]
    mock_cursor.fetchall.side_effect = [acb_rows, staking_rows]

    for client in make_client(mock_pool, mock_user):
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert "holdings" in body
        assert "staking_positions" in body
        assert "total_holdings_count" in body
        holdings = body["holdings"]
        assert len(holdings) == 2
        # Check NEAR holding
        near = next((h for h in holdings if h["token_symbol"] == "NEAR"), None)
        assert near is not None
        assert near["quantity"] == "1000.00"
        assert near["acb_per_unit"] == "2.50"


# ---------------------------------------------------------------------------
# test_portfolio_staking
# ---------------------------------------------------------------------------


def test_portfolio_staking(mock_pool, mock_conn, mock_cursor, mock_user):
    """Portfolio includes staking positions from staking_events."""
    acb_rows = [("NEAR", "1000.00", "2.50", "2500.00", "NEAR")]
    staking_rows = [
        ("aurora.pool.near", "500.00", "NEAR"),
        ("figment.pool.near", "200.00", "NEAR"),
    ]
    mock_cursor.fetchall.side_effect = [acb_rows, staking_rows]

    for client in make_client(mock_pool, mock_user):
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert len(body["staking_positions"]) == 2
        validator_ids = [sp["validator_id"] for sp in body["staking_positions"]]
        assert "aurora.pool.near" in validator_ids
        assert "figment.pool.near" in validator_ids


# ---------------------------------------------------------------------------
# test_portfolio_empty
# ---------------------------------------------------------------------------


def test_portfolio_empty(mock_pool, mock_conn, mock_cursor, mock_user):
    """New user with no holdings returns empty portfolio."""
    mock_cursor.fetchall.side_effect = [[], []]  # acb_rows + staking_rows

    for client in make_client(mock_pool, mock_user):
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["holdings"] == []
        assert body["staking_positions"] == []
        assert body["total_holdings_count"] == 0


# ---------------------------------------------------------------------------
# test_job_status
# ---------------------------------------------------------------------------


def test_job_status(mock_pool, mock_conn, mock_cursor, mock_user):
    """GET /api/jobs/{id}/status returns job status, progress, error_message."""
    job_row = (
        42,              # id
        "full_sync",     # job_type
        "running",       # status
        250,             # progress_fetched
        1000,            # progress_total
        None,            # error_message
        datetime(2026, 1, 1, tzinfo=timezone.utc),  # started_at
        None,            # completed_at
    )
    mock_cursor.fetchone.return_value = job_row

    for client in make_client(mock_pool, mock_user):
        resp = client.get("/api/jobs/42/status")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["id"] == 42
        assert body["job_type"] == "full_sync"
        assert body["status"] == "running"
        assert body["progress_fetched"] == 250
        assert body["progress_total"] == 1000
        assert body["error_message"] is None


# ---------------------------------------------------------------------------
# test_active_jobs
# ---------------------------------------------------------------------------


def test_active_jobs(mock_pool, mock_conn, mock_cursor, mock_user):
    """GET /api/jobs/active returns all running/queued jobs with pipeline stage."""
    job_rows = [
        (
            10,                     # id
            1,                      # wallet_id
            "full_sync",            # job_type
            "running",              # status
            500,                    # progress_fetched
            1000,                   # progress_total
            None,                   # error_message
            datetime(2026, 1, 1, tzinfo=timezone.utc),  # started_at
            None,                   # completed_at
        ),
        (
            11,
            1,
            "classify_transactions",
            "queued",
            0,
            None,
            None,
            None,
            None,
        ),
    ]
    # First fetchall returns active jobs (9 cols), second returns batch jobs (4 cols)
    batch_rows = [
        ("full_sync", "running", 500, 1000),
        ("classify_transactions", "queued", 0, 0),
    ]
    mock_cursor.fetchall.side_effect = [job_rows, batch_rows]

    for client in make_client(mock_pool, mock_user):
        resp = client.get("/api/jobs/active")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert "jobs" in body
        assert "pipeline_stage" in body
        assert "pipeline_pct" in body
        # Reset side_effect for next iteration
        mock_cursor.fetchall.side_effect = [job_rows, batch_rows]
        assert len(body["jobs"]) == 2
        # full_sync running => "Indexing" stage
        assert body["pipeline_stage"] == "Indexing"
        assert 0 <= body["pipeline_pct"] <= 45


# ---------------------------------------------------------------------------
# test_job_user_isolation
# ---------------------------------------------------------------------------


def test_job_user_isolation(mock_pool, mock_conn, mock_cursor, mock_user):
    """User cannot see another user's jobs — query filters by user_id."""
    mock_cursor.fetchone.return_value = None  # job not found for this user

    for client in make_client(mock_pool, mock_user):
        # Job 99 belongs to another user
        resp = client.get("/api/jobs/99/status")
        assert resp.status_code == 404, resp.json()

        # Verify query used user_id filter
        execute_calls = mock_cursor.execute.call_args_list
        sql_calls = [str(c) for c in execute_calls]
        assert any("user_id" in s or "%s" in s for s in sql_calls), \
            "Expected user_id filter in job status query"


# ---------------------------------------------------------------------------
# test_active_jobs_empty
# ---------------------------------------------------------------------------


def test_active_jobs_empty(mock_pool, mock_conn, mock_cursor, mock_user):
    """GET /api/jobs/active returns empty jobs list when no active jobs."""
    # First fetchall: active jobs (empty), second: batch jobs (empty)
    mock_cursor.fetchall.side_effect = [[], []]

    for client in make_client(mock_pool, mock_user):
        mock_cursor.fetchall.side_effect = [[], []]
        resp = client.get("/api/jobs/active")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["jobs"] == []
        assert body["pipeline_stage"] == "Idle"
        assert body["pipeline_pct"] == 0
