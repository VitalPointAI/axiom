"""Unit tests for CostTracker — mock pool/cursor, no live database."""

import time
from unittest.mock import MagicMock

import pytest

from indexers.cost_tracker import CostTracker


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    pool.getconn.return_value = conn
    conn.cursor.return_value = cursor
    return pool, conn, cursor


class TestCostTrackerTrack:
    def test_track_inserts_cost_log(self, mock_pool):
        pool, conn, cursor = mock_pool
        tracker = CostTracker(pool)

        with tracker.track("near", "neardata_xyz", "block_fetch", estimated_cost=0.0):
            time.sleep(0.01)  # Simulate some work

        # Should have called INSERT INTO api_cost_log
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        assert "api_cost_log" in sql
        assert "INSERT" in sql.upper()

        # Check params contain chain, provider, call_type
        params = cursor.execute.call_args[0][1]
        assert params[0] == "near"
        assert params[1] == "neardata_xyz"
        assert params[2] == "block_fetch"
        # response_ms should be > 0
        assert params[3] > 0

        conn.commit.assert_called_once()

    def test_track_records_elapsed_time(self, mock_pool):
        pool, conn, cursor = mock_pool
        tracker = CostTracker(pool)

        with tracker.track("ethereum", "etherscan", "wallet_txns"):
            time.sleep(0.05)

        params = cursor.execute.call_args[0][1]
        response_ms = params[3]
        assert response_ms >= 40  # At least ~50ms minus scheduling jitter

    def test_track_still_logs_on_exception(self, mock_pool):
        pool, conn, cursor = mock_pool
        tracker = CostTracker(pool)

        with pytest.raises(ValueError):
            with tracker.track("near", "neardata_xyz", "block_fetch"):
                raise ValueError("API error")

        # Should still insert cost log even on error
        cursor.execute.assert_called_once()
        conn.commit.assert_called_once()

    def test_track_default_cost_zero(self, mock_pool):
        pool, conn, cursor = mock_pool
        tracker = CostTracker(pool)

        with tracker.track("xrp", "xrpl", "balance_check"):
            pass

        params = cursor.execute.call_args[0][1]
        assert params[4] == 0.0  # estimated_cost_usd default


class TestCostTrackerGetMonthlySummary:
    def test_get_monthly_summary_all_chains(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchall.return_value = [
            ("near", "neardata_xyz", "block_fetch", "2026-03-01", 100, 0.0),
            ("ethereum", "etherscan", "wallet_txns", "2026-03-01", 50, 0.25),
        ]
        tracker = CostTracker(pool)

        result = tracker.get_monthly_summary()

        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        assert "api_cost_monthly" in sql
        assert len(result) == 2

    def test_get_monthly_summary_filtered_by_chain(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchall.return_value = [
            ("near", "neardata_xyz", "block_fetch", "2026-03-01", 100, 0.0),
        ]
        tracker = CostTracker(pool)

        result = tracker.get_monthly_summary(chain="near")

        sql = cursor.execute.call_args[0][0]
        assert "WHERE" in sql.upper()
        assert len(result) == 1


class TestCostTrackerBudgetAlert:
    def test_check_budget_alert_over_budget(self, mock_pool):
        pool, conn, cursor = mock_pool
        # First call: get monthly_budget_usd from chain_sync_config
        # Second call: get current month total from api_cost_monthly
        cursor.fetchone.side_effect = [
            (10.0,),  # monthly_budget_usd = $10
            (15.0,),  # current spend = $15
        ]
        tracker = CostTracker(pool)

        assert tracker.check_budget_alert("near") is True

    def test_check_budget_alert_under_budget(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchone.side_effect = [
            (10.0,),  # budget
            (5.0,),   # spend
        ]
        tracker = CostTracker(pool)

        assert tracker.check_budget_alert("near") is False

    def test_check_budget_alert_no_budget_set(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchone.side_effect = [
            (None,),  # no budget set
        ]
        tracker = CostTracker(pool)

        assert tracker.check_budget_alert("near") is False
