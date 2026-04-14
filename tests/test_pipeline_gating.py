"""Tests verifying pipeline DEK gating and in-memory encrypted-column filtering.

Coverage (plan 16-06 requirements):
  - test_wallets_list_requires_dek: /api/wallets without session_dek_cache row → 401
  - test_transactions_list_requires_dek: /api/transactions without DEK → 401
  - test_portfolio_requires_dek: /api/portfolio without DEK → 401
  - test_verification_requires_dek: /api/verification/issues without DEK → 401
  - test_reports_list_requires_dek: /api/reports without DEK → 401
  - test_audit_requires_dek: /api/audit/history without DEK → 401
  - test_staking_requires_dek: /api/staking without DEK → 401
  - test_transactions_in_memory_filter_direction: direction filter applied in Python after decrypt
  - test_transactions_in_memory_filter_no_match: filter returns empty when no rows match
  - test_verification_in_memory_filter_category: diagnosis_category grouped in Python

All tests use mock pools so they do not require a running database.  DB-backed
end-to-end tests (requiring RUN_MIGRATION_TESTS=1) are deferred to plan 16-07.
"""

import contextlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.dependencies import (
    get_current_user,
    get_effective_user,
    get_effective_user_with_dek,
    get_pool_dep,
)

_TEST_DEK = b"\x00" * 32


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dek_override(user_dict):
    """Async override for get_effective_user_with_dek that injects a test DEK.

    Must be async so ContextVar writes are visible to the async route handler
    (sync dep overrides run in a threadpool where ContextVar.set() does not
    propagate to the asyncio task — see plan 16-06 session summary).
    """
    from db.crypto import set_dek

    async def _override():
        set_dek(_TEST_DEK)
        return user_dict

    return _override


@contextlib.contextmanager
def _make_no_dek_client(mock_pool, user_dict):
    """Build a TestClient that has a valid session but NO session_dek_cache row.

    The get_effective_user_with_dek dependency is NOT overridden — the real
    implementation will attempt a DB lookup and receive None (missing row → 401).
    """
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    # Override get_current_user and get_effective_user so auth passes, but do NOT
    # override get_effective_user_with_dek — we want the real DEK gate to trigger.
    app.dependency_overrides[get_current_user] = lambda: user_dict
    app.dependency_overrides[get_effective_user] = lambda: user_dict

    # Cursor returns None → no session_dek_cache row → 401
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool.getconn.return_value = mock_conn

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    app.dependency_overrides.clear()


@contextlib.contextmanager
def _make_dek_client(mock_pool, user_dict, extra_fetchall_side_effect=None):
    """Build a TestClient with a valid DEK injected via the test override."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: user_dict
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(user_dict)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    if extra_fetchall_side_effect is not None:
        mock_cursor.fetchall.side_effect = extra_fetchall_side_effect
    else:
        mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool.getconn.return_value = mock_conn

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, mock_cursor
    app.dependency_overrides.clear()


_USER = {
    "user_id": 1,
    "near_account_id": "alice.near",
    "is_admin": False,
    "email": "alice@example.com",
    "username": "alice",
    "codename": None,
    "viewing_as_user_id": None,
    "permission_level": None,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_pool():
    return MagicMock()


@pytest.fixture(autouse=True)
def _set_crypto_env(monkeypatch):
    """Inject required env vars for all pipeline gating tests."""
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)
    monkeypatch.setenv("EMAIL_HMAC_KEY", "00" * 32)
    monkeypatch.setenv("NEAR_ACCOUNT_HMAC_KEY", "11" * 32)
    monkeypatch.setenv("TX_DEDUP_KEY", "22" * 32)
    monkeypatch.setenv("ACB_DEDUP_KEY", "33" * 32)


# ---------------------------------------------------------------------------
# DEK gating tests — each pipeline entry must return 401 without a session DEK
# ---------------------------------------------------------------------------


def test_wallets_list_requires_dek(mock_pool):
    """GET /api/wallets returns 401 when no session_dek_cache row exists.

    The wallets router uses get_effective_user_with_dek; the real dependency
    queries session_dek_cache and raises 401 if no row is found.
    """
    with _make_no_dek_client(mock_pool, _USER) as client:
        r = client.get("/api/wallets", cookies={"neartax_session": "sess-x"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_transactions_list_requires_dek(mock_pool):
    """GET /api/transactions returns 401 when no session_dek_cache row exists."""
    with _make_no_dek_client(mock_pool, _USER) as client:
        r = client.get("/api/transactions", cookies={"neartax_session": "sess-x"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_portfolio_requires_dek(mock_pool):
    """GET /api/portfolio returns 401 when no session_dek_cache row exists."""
    with _make_no_dek_client(mock_pool, _USER) as client:
        r = client.get("/api/portfolio", cookies={"neartax_session": "sess-x"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_verification_requires_dek(mock_pool):
    """GET /api/verification/issues returns 401 when no session_dek_cache row exists."""
    with _make_no_dek_client(mock_pool, _USER) as client:
        r = client.get("/api/verification/issues", cookies={"neartax_session": "sess-x"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_reports_list_requires_dek(mock_pool):
    """GET /api/reports/status returns 401 when no session_dek_cache row exists."""
    with _make_no_dek_client(mock_pool, _USER) as client:
        r = client.get("/api/reports/status", cookies={"neartax_session": "sess-x"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_audit_requires_dek(mock_pool):
    """GET /api/audit/history returns 401 when no session_dek_cache row exists."""
    with _make_no_dek_client(mock_pool, _USER) as client:
        r = client.get(
            "/api/audit/history?entity_type=transaction_classification",
            cookies={"neartax_session": "sess-x"},
        )
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_staking_requires_dek(mock_pool):
    """GET /api/staking returns 401 when no session_dek_cache row exists."""
    with _make_no_dek_client(mock_pool, _USER) as client:
        r = client.get("/api/staking", cookies={"neartax_session": "sess-x"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# In-memory filter tests — D-07 pattern
# ---------------------------------------------------------------------------


def test_transactions_in_memory_filter_tax_category(mock_pool):
    """Transactions router filters by tax_category in Python after decrypting rows.

    D-07: SQL no longer filters on encrypted columns.  The router fetches all
    on-chain rows for the user's wallets, decrypts, then applies tax_category filter
    in Python.  This test verifies that only 'income' rows survive when
    tax_category='income' is passed.

    Mock returns 3 rows: 2 with category='income', 1 with category='capital_gain'.
    Router's fetchall side_effect provides: wallet IDs, on-chain rows, exchange rows.
    """
    # Wallet ID fetch
    wallet_rows = [(1,)]
    # On-chain transaction rows (13 columns): id, chain, block_ts, tx_hash, direction,
    # counterparty, amount, token_id, action_type, category, confidence, needs_review, notes
    onchain_rows = [
        (1, "NEAR", "2024-01-01T00:00:00", "hash1", "in",
         None, "100", "NEAR", "transfer", "income", 0.9, False, None),
        (2, "NEAR", "2024-01-02T00:00:00", "hash2", "out",
         None, "50", "NEAR", "transfer", "capital_gain", 0.8, False, None),
        (3, "NEAR", "2024-01-03T00:00:00", "hash3", "in",
         None, "200", "NEAR", "transfer", "income", 0.95, False, None),
    ]
    exchange_rows = []

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(_USER)

    mock_cursor = MagicMock()
    mock_cursor.fetchall.side_effect = [wallet_rows, onchain_rows, exchange_rows]
    mock_cursor.fetchone.return_value = None
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool.getconn.return_value = mock_conn

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            r = client.get("/api/transactions?tax_category=income")

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    txs = data if isinstance(data, list) else data.get("transactions", data)
    # Only 'income' rows should survive the in-memory tax_category filter.
    assert len(txs) == 2, (
        f"Expected 2 'income' rows after tax_category filter, got: {len(txs)}. "
        f"Response: {data}"
    )
    # All returned rows should have tax_category='income'
    for tx in txs:
        assert tx["tax_category"] == "income", f"Unexpected tax_category: {tx['tax_category']}"

    app.dependency_overrides.clear()


def test_transactions_in_memory_filter_no_match(mock_pool):
    """tax_category filter returns empty list when no rows match.

    All on-chain rows have tax_category='capital_gain'; filtering for
    tax_category='income' should produce an empty result, not a 500 error.
    """
    wallet_rows = [(1,)]
    onchain_rows = [
        (1, "NEAR", "2024-01-01T00:00:00", "hash1", "out",
         None, "100", "NEAR", "transfer", "capital_gain", 0.8, False, None),
    ]
    exchange_rows = []

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(_USER)

    mock_cursor = MagicMock()
    mock_cursor.fetchall.side_effect = [wallet_rows, onchain_rows, exchange_rows]
    mock_cursor.fetchone.return_value = None
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool.getconn.return_value = mock_conn

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            r = client.get("/api/transactions?tax_category=income")

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    txs = data if isinstance(data, list) else data.get("transactions", data)
    assert len(txs) == 0, f"Expected 0 'income' rows, got: {len(txs)}. Response: {data}"

    app.dependency_overrides.clear()


def test_verification_in_memory_filter_category(mock_pool):
    """Verification summary groups diagnosis_category in Python (not SQL GROUP BY).

    D-07: the verification router fetches individual (diagnosis_category,) rows
    and uses Python Counter to group them — because diagnosis_category is encrypted.
    This test verifies the grouping produces correct counts per category.
    """
    from api.dependencies import get_effective_user_with_dek

    category_rows = [
        ("missing_staking_rewards",),
        ("missing_staking_rewards",),
        ("uncounted_fees",),
        ("missing_staking_rewards",),
    ]

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(_USER)

    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = category_rows
    mock_cursor.fetchone.side_effect = [(1,), (0,)]  # tc_count, cg_count
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool.getconn.return_value = mock_conn

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            r = client.get("/api/verification/summary")

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert "groups" in data
    groups_by_cat = {g["category"]: g for g in data["groups"]}
    assert groups_by_cat["missing_staking_rewards"]["count"] == 3
    assert groups_by_cat["uncounted_fees"]["count"] == 1

    app.dependency_overrides.clear()
