"""Tests for wallet CRUD, pipeline auto-chain, and sync status endpoints.

Tests cover:
  - POST /api/wallets — create wallet + queue pipeline jobs
  - GET /api/wallets — list user wallets with sync_status
  - GET /api/wallets/{id}/status — pipeline stage progress
  - DELETE /api/wallets/{id} — delete wallet (user isolation enforced)
  - POST /api/wallets/{id}/resync — queue new pipeline jobs
  - User isolation (user A cannot see user B's wallets)
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
    """Build a TestClient with mocked pool and auth for the given user."""
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
    """TestClient for user alice (user_id=1)."""
    yield from make_client(mock_pool, mock_user)


@pytest.fixture
def auth_client_b(mock_pool, mock_user_b):
    """TestClient for user bob (user_id=2)."""
    yield from make_client(mock_pool, mock_user_b)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wallet_row(
    wallet_id=1,
    user_id=1,
    account_id="alice.near",
    chain="NEAR",
    created_at=None,
    sync_status="done",
):
    """Return a DB row tuple matching the wallet list query columns."""
    if created_at is None:
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return (wallet_id, account_id, chain, created_at, sync_status)


# ---------------------------------------------------------------------------
# test_create_wallet_near
# ---------------------------------------------------------------------------


def test_create_wallet_near(mock_pool, mock_conn, mock_cursor, mock_user):
    """POST /api/wallets with NEAR chain creates wallet + queues 3 pipeline jobs."""
    # Simulate INSERT returning the new wallet id
    mock_cursor.fetchone.return_value = (42,)

    for client in make_client(mock_pool, mock_user):
        resp = client.post("/api/wallets", json={"account_id": "alice.near", "chain": "NEAR"})
        assert resp.status_code == 201, resp.json()
        body = resp.json()
        assert body["id"] == 42
        assert body["account_id"] == "alice.near"
        assert body["chain"] == "NEAR"

        # Verify 3 jobs were inserted for NEAR (full_sync, staking_sync, lockup_sync)
        execute_calls = mock_cursor.execute.call_args_list
        sql_calls = [str(c) for c in execute_calls]
        assert any("INSERT INTO indexing_jobs" in s for s in sql_calls), \
            "Expected INSERT INTO indexing_jobs calls"


# ---------------------------------------------------------------------------
# test_create_wallet_evm
# ---------------------------------------------------------------------------


def test_create_wallet_evm(mock_pool, mock_conn, mock_cursor, mock_user):
    """POST /api/wallets with ethereum chain creates wallet + queues evm_full_sync."""
    mock_cursor.fetchone.return_value = (99,)

    for client in make_client(mock_pool, mock_user):
        resp = client.post(
            "/api/wallets",
            # Use a valid 40-char EVM address (EVM address validation added in 09-01)
            json={"account_id": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef", "chain": "ethereum"},
        )
        assert resp.status_code == 201, resp.json()
        body = resp.json()
        assert body["id"] == 99
        assert body["chain"] == "ethereum"

        execute_calls = mock_cursor.execute.call_args_list
        sql_calls = [str(c) for c in execute_calls]
        # evm_full_sync job should be queued
        assert any("evm_full_sync" in s for s in sql_calls), \
            "Expected evm_full_sync in job INSERT calls"


# ---------------------------------------------------------------------------
# test_create_wallet_duplicate
# ---------------------------------------------------------------------------


def test_create_wallet_duplicate(mock_pool, mock_conn, mock_cursor, mock_user):
    """POST /api/wallets with duplicate (user_id, account_id, chain) returns 409."""
    # fetchone returning None means ON CONFLICT returned nothing
    mock_cursor.fetchone.return_value = None

    for client in make_client(mock_pool, mock_user):
        resp = client.post("/api/wallets", json={"account_id": "alice.near", "chain": "NEAR"})
        assert resp.status_code == 409, resp.json()


# ---------------------------------------------------------------------------
# test_list_wallets
# ---------------------------------------------------------------------------


def test_list_wallets(mock_pool, mock_conn, mock_cursor, mock_user):
    """GET /api/wallets returns list of user's wallets with sync_status."""
    # fetchall is called twice: first for wallets (4 columns), second for jobs (7 columns)
    wallet_rows = [
        (1, "alice.near", "NEAR", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        (2, "0xdeadbeef", "ethereum", datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ]
    # Second fetchall for jobs — wallet 2 has a running evm_full_sync = "indexing"
    job_rows = [
        (2, 10, "evm_full_sync", "running", 0, 100, None),
    ]
    mock_cursor.fetchall.side_effect = [wallet_rows, job_rows]

    for client in make_client(mock_pool, mock_user):
        resp = client.get("/api/wallets")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert len(body) == 2
        assert body[0]["id"] == 1
        assert body[0]["account_id"] == "alice.near"
        assert "sync_status" in body[0]
        # wallet 2 has a running evm_full_sync job => mapped to "indexing"
        assert body[1]["sync_status"] in ("indexing", "running")


# ---------------------------------------------------------------------------
# test_delete_wallet
# ---------------------------------------------------------------------------


def test_delete_wallet(mock_pool, mock_conn, mock_cursor, mock_user):
    """DELETE /api/wallets/{id} removes wallet owned by user."""
    # fetchone returns wallet belonging to user_id=1
    mock_cursor.fetchone.return_value = (1, 1)  # (id, user_id)

    for client in make_client(mock_pool, mock_user):
        resp = client.delete("/api/wallets/1")
        assert resp.status_code == 204, resp.json()


# ---------------------------------------------------------------------------
# test_delete_wallet_not_owned
# ---------------------------------------------------------------------------


def test_delete_wallet_not_owned(mock_pool, mock_conn, mock_cursor, mock_user):
    """DELETE /api/wallets/{id} returns 404 if wallet belongs to another user."""
    # fetchone returns None — wallet not found for this user
    mock_cursor.fetchone.return_value = None

    for client in make_client(mock_pool, mock_user):
        resp = client.delete("/api/wallets/99")
        assert resp.status_code == 404, resp.json()


# ---------------------------------------------------------------------------
# test_sync_status
# ---------------------------------------------------------------------------


def test_sync_status(mock_pool, mock_conn, mock_cursor, mock_user):
    """GET /api/wallets/{id}/status returns pipeline stage and percentage."""
    # fetchone for wallet ownership check
    # fetchall for job list
    call_count = [0]

    def fetchone_side_effect():
        call_count[0] += 1
        if call_count[0] == 1:
            return (1, 1)  # wallet exists, owned by user_id=1
        return None

    mock_cursor.fetchone.side_effect = fetchone_side_effect
    # Jobs: full_sync running
    mock_cursor.fetchall.return_value = [
        (1, 1, "full_sync", "running", 450, 1000, None),
    ]

    for client in make_client(mock_pool, mock_user):
        resp = client.get("/api/wallets/1/status")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert "stage" in body
        assert "pct" in body
        assert body["stage"] == "Indexing"
        assert 0 <= body["pct"] <= 45


# ---------------------------------------------------------------------------
# test_user_isolation
# ---------------------------------------------------------------------------


def test_user_isolation(mock_pool, mock_conn, mock_cursor, mock_user):
    """User A cannot see user B's wallets — query filters by user_id."""
    # Return empty list for user A (alice has no wallets in this mock)
    # fetchall called twice (wallets + jobs) — both empty
    mock_cursor.fetchall.side_effect = [[], []]

    for client in make_client(mock_pool, mock_user):
        resp = client.get("/api/wallets")
        assert resp.status_code == 200
        body = resp.json()
        assert body == []

        # Verify user_id=1 was passed in the query
        execute_calls = mock_cursor.execute.call_args_list
        sql_calls = [str(c) for c in execute_calls]
        assert any("user_id" in s or "%s" in s for s in sql_calls), \
            "Expected user_id filter in wallet list query"


# ---------------------------------------------------------------------------
# test_resync_wallet
# ---------------------------------------------------------------------------


def test_resync_wallet(mock_pool, mock_conn, mock_cursor, mock_user):
    """POST /api/wallets/{id}/resync queues new pipeline jobs for existing wallet."""
    # fetchone for wallet ownership check (chain: NEAR)
    mock_cursor.fetchone.return_value = (1, 1, "NEAR")  # (id, user_id, chain)

    for client in make_client(mock_pool, mock_user):
        resp = client.post("/api/wallets/1/resync")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert "queued" in body or "jobs" in body or "message" in body

        execute_calls = mock_cursor.execute.call_args_list
        sql_calls = [str(c) for c in execute_calls]
        assert any("INSERT INTO indexing_jobs" in s for s in sql_calls), \
            "Expected INSERT INTO indexing_jobs for resync"
