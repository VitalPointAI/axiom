"""Integration tests for runtime invariant checks across subsystems.

Covers:
  - Reconciler wallet coverage invariant
  - Reconciler undiagnosed discrepancy invariant
  - Exchange parser post-parse validation
"""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Reconciler invariants
# ---------------------------------------------------------------------------


class TestReconcilerInvariants:
    """Tests for reconciler wallet coverage and diagnosis completeness."""

    def _make_pool(self, wallets=None, undiagnosed=None):
        """Build mock pool returning wallets and undiagnosed results."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # fetchall returns: wallets query, then undiagnosed query
        side_effects = [wallets or []]
        mock_cursor.fetchall.side_effect = side_effects
        mock_conn.cursor.return_value = mock_cursor

        pool = MagicMock()
        pool.getconn.return_value = mock_conn
        return pool, mock_conn, mock_cursor

    def test_coverage_all_wallets(self):
        """All wallets reconciled -> coverage_complete=True."""
        from verify.reconcile import BalanceReconciler

        wallets = [
            (1, "alice.near", "near"),
            (2, "bob.near", "near"),
        ]
        pool, conn, cur = self._make_pool(wallets=wallets)

        # Second call for undiagnosed check
        cur.fetchall.side_effect = [wallets, []]

        reconciler = BalanceReconciler(pool)

        with patch.object(reconciler, "_reconcile_wallet", return_value="within_tolerance"):
            stats = reconciler.reconcile_user(user_id=1)

        assert stats["coverage_complete"] is True
        assert stats["wallets_checked"] == 2

    def test_reconciler_returns_coverage_complete(self):
        """Stats dict includes coverage_complete key."""
        from verify.reconcile import BalanceReconciler

        pool, conn, cur = self._make_pool(wallets=[])
        cur.fetchall.side_effect = [[], []]
        reconciler = BalanceReconciler(pool)
        stats = reconciler.reconcile_user(user_id=1)
        assert "coverage_complete" in stats


class TestExchangeParserInvariants:
    """Tests for exchange parser post-parse row validation."""

    def test_zero_amount_flagged(self):
        """Row with quantity=0 sets needs_review and logs violation."""
        from indexers.exchange_parsers.base import BaseExchangeParser

        parser = BaseExchangeParser()
        parsed = {"quantity": "0", "tx_date": "2024-01-01", "asset": "BTC"}
        result = parser.validate_parsed_row(parsed, {})

        assert result.get("needs_review") is True
        assert "zero_or_missing_amount" in result.get("_invariant_violations", [])

    def test_missing_date_flagged(self):
        """Row with no tx_date sets needs_review."""
        from indexers.exchange_parsers.base import BaseExchangeParser

        parser = BaseExchangeParser()
        parsed = {"quantity": "1.5", "tx_date": None, "asset": "ETH"}
        result = parser.validate_parsed_row(parsed, {})

        assert result.get("needs_review") is True
        assert "missing_date" in result.get("_invariant_violations", [])

    def test_missing_asset_flagged(self):
        """Row with empty asset sets needs_review."""
        from indexers.exchange_parsers.base import BaseExchangeParser

        parser = BaseExchangeParser()
        parsed = {"quantity": "1.0", "tx_date": "2024-01-01", "asset": ""}
        result = parser.validate_parsed_row(parsed, {})

        assert result.get("needs_review") is True
        assert "missing_asset" in result.get("_invariant_violations", [])

    def test_valid_row_passes(self):
        """Normal row passes validation without modification."""
        from indexers.exchange_parsers.base import BaseExchangeParser

        parser = BaseExchangeParser()
        parsed = {"quantity": "1.5", "tx_date": "2024-01-01", "asset": "BTC"}
        result = parser.validate_parsed_row(parsed, {})

        assert result.get("needs_review") is None or result.get("needs_review") is False
        assert "_invariant_violations" not in result

    def test_none_amount_flagged(self):
        """Row with quantity=None sets needs_review."""
        from indexers.exchange_parsers.base import BaseExchangeParser

        parser = BaseExchangeParser()
        parsed = {"quantity": None, "tx_date": "2024-01-01", "asset": "BTC"}
        result = parser.validate_parsed_row(parsed, {})

        assert result.get("needs_review") is True
