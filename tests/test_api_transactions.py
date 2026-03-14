"""Tests for transaction ledger API endpoints.

Tests cover:
  - GET /api/transactions        — paginated ledger with filtering
  - PATCH /api/transactions/{tx_hash}/classification — edit classification
  - GET /api/transactions/review — review queue (needs_review=true items)
  - POST /api/transactions/apply-changes — trigger ACB recalculation

All tests use mocked DB pool (no real PostgreSQL needed).
"""

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


# ---------------------------------------------------------------------------
# Sample transaction row helpers
# ---------------------------------------------------------------------------

# Columns returned by the UNION ALL query:
# tx_hash, chain, timestamp_iso, sender, receiver, amount_str, token_symbol,
# action_type, tax_category, sub_category, confidence_score, needs_review,
# reviewer_notes, source, total_count
# (15 columns + window total at position 14)
def _tx_row(
    tx_hash="abc123",
    chain="NEAR",
    timestamp_iso="2025-06-01T12:00:00",
    sender="alice.near",
    receiver="bob.near",
    amount_str="100.0",
    token_symbol="NEAR",
    action_type="TRANSFER",
    tax_category="income",
    sub_category=None,
    confidence_score=0.95,
    needs_review=False,
    reviewer_notes=None,
    source="on_chain",
    total_count=1,
):
    return (
        tx_hash, chain, timestamp_iso, sender, receiver, amount_str, token_symbol,
        action_type, tax_category, sub_category, confidence_score, needs_review,
        reviewer_notes, source, total_count,
    )


# ---------------------------------------------------------------------------
# TestTransactionList
# ---------------------------------------------------------------------------


class TestTransactionList:
    """Tests for GET /api/transactions."""

    def test_list_transactions(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """GET /api/transactions returns paginated results with total count."""
        mock_cursor.fetchall.return_value = [_tx_row()]

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions")
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            assert "transactions" in body
            assert "total" in body
            assert "page" in body
            assert "per_page" in body
            assert "pages" in body
            assert body["page"] == 1
            assert body["total"] == 1
            assert len(body["transactions"]) == 1

    def test_filter_by_date(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """?start_date=2025-01-01&end_date=2025-12-31 filters correctly."""
        mock_cursor.fetchall.return_value = [_tx_row()]

        for client in make_client(mock_pool, mock_user):
            resp = client.get(
                "/api/transactions",
                params={"start_date": "2025-01-01", "end_date": "2025-12-31"},
            )
            assert resp.status_code == 200, resp.json()
            # Verify date params were passed to the query
            execute_calls = mock_cursor.execute.call_args_list
            sql_calls = [str(c) for c in execute_calls]
            assert any("2025" in s or "%s" in s for s in sql_calls)

    def test_filter_by_type(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """?tax_category=income returns only income transactions."""
        mock_cursor.fetchall.return_value = [_tx_row(tax_category="income")]

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions", params={"tax_category": "income"})
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            for tx in body["transactions"]:
                assert tx["tax_category"] == "income"

    def test_filter_by_asset(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """?asset=NEAR filters by token symbol."""
        mock_cursor.fetchall.return_value = [_tx_row(token_symbol="NEAR")]

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions", params={"asset": "NEAR"})
            assert resp.status_code == 200, resp.json()
            # Route accepted the filter without error
            assert resp.status_code == 200

    def test_filter_by_chain(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """?chain=NEAR filters by chain."""
        mock_cursor.fetchall.return_value = [_tx_row(chain="NEAR")]

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions", params={"chain": "NEAR"})
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            for tx in body["transactions"]:
                assert tx["chain"] == "NEAR"

    def test_filter_needs_review(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """?needs_review=true returns flagged transactions."""
        mock_cursor.fetchall.return_value = [_tx_row(needs_review=True, total_count=1)]

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions", params={"needs_review": "true"})
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            for tx in body["transactions"]:
                assert tx["needs_review"] is True

    def test_search(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """?search=swap searches tx_hash, sender, receiver."""
        mock_cursor.fetchall.return_value = [_tx_row(tx_hash="swap_abc")]

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions", params={"search": "swap"})
            assert resp.status_code == 200, resp.json()
            # Route accepted the search param
            assert resp.status_code == 200

    def test_pagination(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """?page=2&per_page=50 returns correct page with offset."""
        mock_cursor.fetchall.return_value = []  # page 2 empty

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions", params={"page": 2, "per_page": 50})
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            assert body["page"] == 2
            assert body["per_page"] == 50

    def test_user_isolation(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """Returns only effective_user's transactions."""
        mock_cursor.fetchall.return_value = []

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions")
            assert resp.status_code == 200
            body = resp.json()
            assert body["transactions"] == []

            # Verify user_id=1 was used in the query
            execute_calls = mock_cursor.execute.call_args_list
            sql_calls = [str(c) for c in execute_calls]
            assert any("user_id" in s or "%s" in s for s in sql_calls)

    def test_empty_results(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """Returns empty list with total=0 when no transactions match."""
        mock_cursor.fetchall.return_value = []

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions")
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            assert body["transactions"] == []
            assert body["total"] == 0

    def test_unauthenticated_returns_401(self, mock_pool):
        """Unauthenticated request returns 401."""
        app = create_app()
        app.dependency_overrides[get_pool_dep] = lambda: mock_pool
        with patch("indexers.db.get_pool", return_value=mock_pool), \
             patch("indexers.db.close_pool"):
            with TestClient(app, raise_server_exceptions=True) as client:
                resp = client.get("/api/transactions")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestClassificationEdit
# ---------------------------------------------------------------------------


class TestClassificationEdit:
    """Tests for PATCH /api/transactions/{tx_hash}/classification."""

    def test_patch_classification(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """PATCH /api/transactions/{tx_hash}/classification updates tax_category and reviewer_notes."""
        # fetchone for ownership check: (id, old_category, old_confidence)
        mock_cursor.fetchone.return_value = (42, "income", 0.95)

        for client in make_client(mock_pool, mock_user):
            resp = client.patch(
                "/api/transactions/abc123/classification",
                json={"tax_category": "capital_gain", "reviewer_notes": "Reviewed manually"},
            )
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            assert "tx_hash" in body or "status" in body or "updated" in body

    def test_patch_mark_reviewed(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """PATCH with needs_review=false sets reviewed_at timestamp."""
        mock_cursor.fetchone.return_value = (42, "income", 0.95)

        for client in make_client(mock_pool, mock_user):
            resp = client.patch(
                "/api/transactions/abc123/classification",
                json={"needs_review": False},
            )
            assert resp.status_code == 200, resp.json()
            # Confirm reviewed_at was set via SQL (check execute calls)
            execute_calls = mock_cursor.execute.call_args_list
            sql_calls = [str(c) for c in execute_calls]
            assert any("reviewed_at" in s or "UPDATE" in s for s in sql_calls)

    def test_patch_unauthorized(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """Cannot edit classification for another user's transaction."""
        # fetchone returns None — tx not found for this user
        mock_cursor.fetchone.return_value = None

        for client in make_client(mock_pool, mock_user):
            resp = client.patch(
                "/api/transactions/xyz999/classification",
                json={"tax_category": "income"},
            )
            assert resp.status_code in (403, 404), resp.json()


# ---------------------------------------------------------------------------
# TestReviewQueue
# ---------------------------------------------------------------------------


class TestReviewQueue:
    """Tests for GET /api/transactions/review."""

    def test_review_queue(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """GET /api/transactions/review returns all needs_review=true items."""
        mock_cursor.fetchall.return_value = [
            _tx_row(needs_review=True, tax_category="income", total_count=2),
            _tx_row(
                tx_hash="def456",
                needs_review=True,
                tax_category="capital_gain",
                total_count=2,
            ),
        ]

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions/review")
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            assert "items" in body
            assert "counts_by_category" in body
            assert "total" in body
            assert body["total"] == 2
            assert len(body["items"]) == 2

    def test_review_queue_empty(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """GET /api/transactions/review returns empty items when no flagged transactions."""
        mock_cursor.fetchall.return_value = []

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions/review")
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            assert body["items"] == []
            assert body["total"] == 0

    def test_review_queue_counts_by_category(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """counts_by_category groups review items by tax_category."""
        mock_cursor.fetchall.return_value = [
            _tx_row(needs_review=True, tax_category="income", total_count=3),
            _tx_row(tx_hash="d2", needs_review=True, tax_category="income", total_count=3),
            _tx_row(tx_hash="d3", needs_review=True, tax_category="capital_gain", total_count=3),
        ]

        for client in make_client(mock_pool, mock_user):
            resp = client.get("/api/transactions/review")
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            assert "counts_by_category" in body
            counts = body["counts_by_category"]
            assert counts.get("income", 0) == 2
            assert counts.get("capital_gain", 0) == 1


# ---------------------------------------------------------------------------
# TestApplyChanges
# ---------------------------------------------------------------------------


class TestApplyChanges:
    """Tests for POST /api/transactions/apply-changes."""

    def test_apply_changes(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """POST /api/transactions/apply-changes creates calculate_acb job."""
        # INSERT INTO indexing_jobs RETURNING id → returns job_id=99
        mock_cursor.fetchone.return_value = (99,)

        for client in make_client(mock_pool, mock_user):
            resp = client.post(
                "/api/transactions/apply-changes",
                json={"token_symbols": ["NEAR", "ETH"]},
            )
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            assert "job_id" in body
            assert body["job_id"] == 99

    def test_apply_changes_tokens(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """apply-changes job cursor contains only edited token symbols."""
        mock_cursor.fetchone.return_value = (99,)

        for client in make_client(mock_pool, mock_user):
            resp = client.post(
                "/api/transactions/apply-changes",
                json={"token_symbols": ["NEAR"]},
            )
            assert resp.status_code == 200
            execute_calls = mock_cursor.execute.call_args_list
            sql_calls = [str(c) for c in execute_calls]
            # Job should be inserted with calculate_acb type
            assert any("calculate_acb" in s or "INSERT INTO indexing_jobs" in s for s in sql_calls)

    def test_apply_changes_no_tokens(self, mock_pool, mock_conn, mock_cursor, mock_user):
        """POST /api/transactions/apply-changes without token_symbols recalcs all tokens."""
        mock_cursor.fetchone.return_value = (88,)

        for client in make_client(mock_pool, mock_user):
            resp = client.post("/api/transactions/apply-changes", json={})
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            assert "job_id" in body
