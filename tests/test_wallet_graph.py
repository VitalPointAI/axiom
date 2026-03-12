"""Unit tests for WalletGraph — PostgreSQL-backed wallet ownership and transfer detection.

Covers CLASS-02: identifying internal transfers between wallets owned by the same user,
cross-chain bridge transfer matching, and wallet discovery suggestions.

All tests use mocked DB connections — no live database required.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from engine.wallet_graph import WalletGraph


def make_pool(fetchall_return=None, fetchone_return=None):
    """Create a mock psycopg2 ThreadedConnectionPool with a mock cursor."""
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_return or []
    cursor.fetchone.return_value = fetchone_return

    conn = MagicMock()
    conn.cursor.return_value = cursor

    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool, conn, cursor


class TestInternalTransferDetection:
    """CLASS-02: Both-sides-owned detection makes transfers non-taxable."""

    def test_both_owned_is_internal(self):
        """Transfer where sender AND receiver are owned wallets of same user -> Internal."""
        # Two rows means both addresses found in user's wallets
        pool, conn, cursor = make_pool(fetchall_return=[("alice.near",), ("bob.near",)])
        wg = WalletGraph(pool)
        result = wg.is_internal_transfer(user_id=1, from_addr="alice.near", to_addr="bob.near")
        assert result is True
        pool.putconn.assert_called_once_with(conn)

    def test_one_not_owned_is_external(self):
        """Transfer where receiver is not in user's wallet list -> External (taxable disposal)."""
        # Only one row — only sender is owned
        pool, conn, cursor = make_pool(fetchall_return=[("alice.near",)])
        wg = WalletGraph(pool)
        result = wg.is_internal_transfer(user_id=1, from_addr="alice.near", to_addr="external.near")
        assert result is False


class TestCrossChainMatching:
    """CLASS-02: Cross-chain bridge transfer matching by amount + timestamp."""

    def test_matching_amount_and_time(self):
        """NEAR out + EVM in, same amount within 5% + 30-min window -> bridge pair detected."""
        # Simulate two transactions: NEAR out and EVM in
        # tx_a: id=10, chain='near', direction='out', amount=1000000, timestamp=1000000
        # tx_b: id=20, chain='evm',  direction='in',  amount=980000,  timestamp=1001000
        out_txs = [(10, "near", Decimal("1000000"), 1000000)]
        in_txs = [(20, "evm", Decimal("980000"), 1001000)]

        pool = MagicMock()
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        pool.getconn.return_value = conn

        # first call fetchall -> out_txs, second -> in_txs
        cursor.fetchall.side_effect = [out_txs, in_txs]

        wg = WalletGraph(pool)
        pairs = wg.find_cross_chain_transfer_pairs(user_id=1, amount_tolerance=0.05, window_minutes=30)

        assert len(pairs) == 1
        pair = pairs[0]
        assert pair["tx_a"] == 10
        assert pair["tx_b"] == 20
        assert pair["confidence"] > 0
        assert pair["amount_diff_pct"] < 0.05
        assert pair["time_diff_min"] < 30

    def test_outside_window_no_match(self):
        """Same amount but > 30-min apart -> not matched as bridge pair."""
        out_txs = [(10, "near", Decimal("1000000"), 1000000)]
        # 2 hours apart = 7200 seconds
        in_txs = [(20, "evm", Decimal("1000000"), 1007200)]

        pool = MagicMock()
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        pool.getconn.return_value = conn
        cursor.fetchall.side_effect = [out_txs, in_txs]

        wg = WalletGraph(pool)
        pairs = wg.find_cross_chain_transfer_pairs(user_id=1, window_minutes=30)

        assert len(pairs) == 0


class TestFalsePositivePrevention:
    """CLASS-02: Prevent cross-user false positive internal transfer matches."""

    def test_different_users_no_match(self):
        """Transactions from different user_ids must never be matched.

        The user_id filter in the SQL query prevents this at the DB level.
        We verify the query is scoped by checking execute() is called with user_id param.
        """
        pool = MagicMock()
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        pool.getconn.return_value = conn
        # Return one outgoing tx for user 1, but no matching incoming txs
        cursor.fetchall.side_effect = [
            [(10, "near", Decimal("1000000"), 1000000)],  # out txs for user 1
            [],  # no in txs (different user's txs not returned)
        ]

        wg = WalletGraph(pool)
        pairs = wg.find_cross_chain_transfer_pairs(user_id=1, window_minutes=30)

        assert len(pairs) == 0

        # Verify user_id=1 was passed to both SQL queries
        calls = cursor.execute.call_args_list
        for call in calls:
            args = call[0]
            if len(args) > 1:
                params = args[1]
                assert 1 in params, "user_id must be in query params to prevent cross-user matches"


class TestWalletDiscovery:
    """Wallet graph high-frequency counterparty suggestions."""

    def test_high_frequency_counterparty_suggested(self):
        """Address appearing in >= min_transfers transactions -> suggested as new owned wallet."""
        # Simulate counterparty appearing 5 times
        rows = [("stranger.near", "near", 5, "alice.near")]
        pool, conn, cursor = make_pool(fetchall_return=rows)

        wg = WalletGraph(pool)
        suggestions = wg.suggest_wallet_discovery(user_id=1, min_transfers=3)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s["address"] == "stranger.near"
        assert s["chain"] == "near"
        assert s["transfer_count"] == 5
        assert s["confidence"] > 0

    def test_low_frequency_counterparty_not_suggested(self):
        """Address with fewer than min_transfers interactions -> not suggested."""
        # Empty result from DB means no counterparty meets threshold
        pool, conn, cursor = make_pool(fetchall_return=[])

        wg = WalletGraph(pool)
        suggestions = wg.suggest_wallet_discovery(user_id=1, min_transfers=3)

        assert len(suggestions) == 0
