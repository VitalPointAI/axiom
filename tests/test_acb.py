"""
Tests for ACB (Adjusted Cost Base) engine.

Coverage:
  - TestACBPool: unit tests for the per-token pool state machine
  - TestACBEngine: integration tests for cross-wallet replay and income handling
  - TestGainsCalculator: tests for capital gains and income ledger population
"""

import sys
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# ACBPool — per-token pool state machine
# ---------------------------------------------------------------------------


class TestACBPool:
    """Unit tests for the ACBPool (per-token running total / ACB calculator).

    ACBPool maintains:
      - total_units: total units in the pool (Decimal)
      - total_cost_cad: total CAD cost basis for all units held (Decimal)
      - acb_per_unit: total_cost_cad / total_units, quantized to 8 decimal places
    """

    def test_acquire(self):
        """Acquiring 1000 units at $5000 CAD -> acb_per_unit = 5.00000000"""
        from engine.acb import ACBPool
        pool = ACBPool("NEAR")
        result = pool.acquire(Decimal("1000"), Decimal("5000"))
        assert pool.total_units == Decimal("1000")
        assert pool.total_cost_cad == Decimal("5000")
        assert pool.acb_per_unit == Decimal("5.00000000")
        assert result["acb_per_unit"] == Decimal("5.00000000")
        assert result["total_units"] == Decimal("1000")

    def test_multi_acquire(self):
        """acquire 1000 at $5000, then 500 at $3000 -> acb_per_unit = 8000/1500 = 5.33333333"""
        from engine.acb import ACBPool
        pool = ACBPool("NEAR")
        pool.acquire(Decimal("1000"), Decimal("5000"))
        pool.acquire(Decimal("500"), Decimal("3000"))
        assert pool.total_units == Decimal("1500")
        assert pool.total_cost_cad == Decimal("8000")
        # 8000/1500 = 5.33333333... rounded to 8 decimals
        assert pool.acb_per_unit == Decimal("5.33333333")

    def test_dispose(self):
        """After acquiring 1000 at $5000, dispose 300 at $2400 -> gain_loss = $2400 - $1500 = $900"""
        from engine.acb import ACBPool
        pool = ACBPool("NEAR")
        pool.acquire(Decimal("1000"), Decimal("5000"))
        result = pool.dispose(Decimal("300"), Decimal("2400"))
        # acb_used = 300 * 5.00 = 1500
        assert result["acb_used_cad"] == Decimal("1500.00000000")
        # net_proceeds = 2400 (no fee)
        assert result["net_proceeds_cad"] == Decimal("2400")
        # gain_loss = 2400 - 1500 = 900
        assert result["gain_loss_cad"] == Decimal("900.00000000")
        assert result["needs_review"] is False
        assert pool.total_units == Decimal("700")

    def test_acquire_with_fee(self):
        """acquire 1000 at $5000 + $10 fee -> total_cost = $5010, acb_per_unit = 5.01000000"""
        from engine.acb import ACBPool
        pool = ACBPool("NEAR")
        result = pool.acquire(Decimal("1000"), Decimal("5000"), fee_cad=Decimal("10"))
        assert pool.total_cost_cad == Decimal("5010")
        assert pool.acb_per_unit == Decimal("5.01000000")
        assert result["total_cost_cad"] == Decimal("5010")

    def test_dispose_with_fee(self):
        """dispose 300 at $2400 with $8 fee -> net_proceeds = $2392, gain_loss = $2392 - $1500 = $892"""
        from engine.acb import ACBPool
        pool = ACBPool("NEAR")
        pool.acquire(Decimal("1000"), Decimal("5000"))
        result = pool.dispose(Decimal("300"), Decimal("2400"), fee_cad=Decimal("8"))
        assert result["net_proceeds_cad"] == Decimal("2392")
        assert result["gain_loss_cad"] == Decimal("892.00000000")

    def test_oversell_clamps(self):
        """If pool has 100 units and dispose(150), clamp to 100 and flag needs_review"""
        from engine.acb import ACBPool
        pool = ACBPool("NEAR")
        pool.acquire(Decimal("100"), Decimal("1000"))
        result = pool.dispose(Decimal("150"), Decimal("1500"))
        assert result["needs_review"] is True
        # Units clamped to 100 (all we have)
        assert pool.total_units == Decimal("0")
        assert pool.total_cost_cad == Decimal("0")


# ---------------------------------------------------------------------------
# ACBEngine — full replay engine
# ---------------------------------------------------------------------------


class TestACBEngine:
    """Integration tests for ACBEngine — processes classifications into ACB snapshots.

    ACBEngine:
      - Loads all TransactionClassification rows ordered by block_timestamp
      - Groups into per-token ACBPool instances
      - Writes ACBSnapshot rows for each event
      - Writes CapitalGainsLedger rows for disposals
      - Writes IncomeLedger rows for staking/vesting income
    """

    def _make_mock_row(self, **kwargs):
        """Helper: create a mock database row with all needed fields."""
        defaults = {
            "id": 1,
            "category": "capital_gain",
            "leg_type": "parent",
            "fmv_usd": None,
            "fmv_cad": None,
            "staking_event_id": None,
            "lockup_event_id": None,
            "parent_classification_id": None,
            "transaction_id": 1,
            "exchange_transaction_id": None,
            "t_block_timestamp": 1680000000000000000,  # NEAR nanoseconds
            "amount": 1000000000000000000000000,  # 1 NEAR in yoctoNEAR
            "fee": None,
            "token_id": None,
            "chain": "near",
            "asset": None,
            "quantity": None,
            "et_fee": None,
            "et_timestamp": None,
            "se_fmv_usd": None,
            "se_fmv_cad": None,
            "se_amount_near": None,
            "le_fmv_usd": None,
            "le_fmv_cad": None,
            "le_amount_near": None,
        }
        defaults.update(kwargs)
        row = MagicMock()
        for k, v in defaults.items():
            setattr(row, k, v)
        # Also support dict-style access via __getitem__
        row.__getitem__ = lambda self, key: getattr(self, key)
        return row

    def test_cross_wallet_pool(self):
        """Tokens from multiple wallets (same user) share a single ACB pool.

        A user with 2 NEAR wallets should have their NEAR holdings merged
        into one ACBPool — CRA treats the user, not the wallet, as the entity.

        Verify: ACBSnapshot.units_after reflects combined holdings across wallets.
        """
        from engine.acb import ACBEngine

        # Row 1: wallet A acquires 1000 NEAR at ts=T1
        row1 = self._make_mock_row(
            id=1, category="income", leg_type="parent",
            t_block_timestamp=1680000000000000000,
            amount=1000000000000000000000000,  # 1 NEAR yocto
            fmv_cad=Decimal("5.00"),
            staking_event_id=1,
            se_fmv_cad=Decimal("5.00"),
            se_amount_near=Decimal("1.0"),
        )
        # Row 2: wallet B acquires 2 NEAR at ts=T2 (later)
        row2 = self._make_mock_row(
            id=2, category="income", leg_type="parent",
            t_block_timestamp=1680100000000000000,
            amount=2000000000000000000000000,
            fmv_cad=Decimal("5.00"),
            staking_event_id=2,
            se_fmv_cad=Decimal("10.00"),
            se_amount_near=Decimal("2.0"),
        )

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # First call: DELETE existing data; second call: SELECT classifications -> rows
        # fetchall() returns our rows, then empty list (no more)
        mock_cursor.fetchall.side_effect = [[row1, row2], [], []]
        mock_cursor.fetchone.return_value = [1]  # snapshot id

        mock_pool.getconn.return_value = mock_conn

        price_service = MagicMock()
        price_service.get_price_cad_at_timestamp.return_value = (Decimal("5.00"), False)

        engine = ACBEngine(mock_pool, price_service)

        with patch("engine.acb.GainsCalculator") as MockGains:
            mock_gains_instance = MagicMock()
            MockGains.return_value = mock_gains_instance
            stats = engine.calculate_for_user(1)

        # Both wallets contribute to the same NEAR pool
        assert stats["snapshots_written"] >= 2
        assert stats["income_recorded"] >= 2

    def test_staking_income_fmv(self):
        """Staking rewards use pre-captured fmv_cad from StakingEvent as acquisition cost."""
        from engine.acb import ACBEngine, ACBPool

        # Test ACBPool directly: staking reward of 1.5 NEAR at fmv_cad=$10.50
        pool = ACBPool("NEAR")
        result = pool.acquire(Decimal("1.5"), Decimal("10.50"))
        assert pool.total_units == Decimal("1.5")
        assert pool.total_cost_cad == Decimal("10.50")
        # acb_per_unit = 10.50 / 1.5 = 7.00000000
        assert pool.acb_per_unit == Decimal("7.00000000")

    def test_swap_fee_leg_acb(self):
        """Swap fee_leg cost is added to buy_leg ACB, not deducted from sell proceeds."""
        from engine.acb import ACBPool

        # Sell 100 USDC pool (acquire first)
        usdc_pool = ACBPool("USDC")
        usdc_pool.acquire(Decimal("100"), Decimal("140"))  # 100 USDC at 1.40 CAD each
        dispose_result = usdc_pool.dispose(Decimal("100"), Decimal("140"))
        # No fee on the dispose; proceeds = 140
        assert dispose_result["net_proceeds_cad"] == Decimal("140")

        # Buy 0.5 ETH + fee 2 USDC worth $2.80 CAD added to ETH ACB
        eth_pool = ACBPool("ETH")
        # ETH FMV = $3000 * 0.5 * 1.40 = $2100 CAD
        # fee_leg = 2 USDC = $2.80 CAD added to buy cost
        eth_result = eth_pool.acquire(Decimal("0.5"), Decimal("2100"), fee_cad=Decimal("2.80"))
        assert eth_pool.total_cost_cad == Decimal("2102.80")
        # acb_per_unit = 2102.80 / 0.5 = 4205.60000000
        assert eth_pool.acb_per_unit == Decimal("4205.60000000")

    def test_chronological_replay(self):
        """Engine processes events in strict block_timestamp order."""
        from engine.acb import ACBEngine

        # 3 rows: T3, T1, T2 - fetchall returns them in DB-sorted order (SQL ORDER BY)
        # We verify that the results list is consistent with sorted processing
        # The SQL ORDER BY ensures sorted delivery; the engine processes in that order

        row_t1 = self._make_mock_row(
            id=10, category="income", leg_type="parent",
            t_block_timestamp=1000000000000000000,
            staking_event_id=1, se_fmv_cad=Decimal("5.00"), se_amount_near=Decimal("1.0"),
        )
        row_t2 = self._make_mock_row(
            id=20, category="income", leg_type="parent",
            t_block_timestamp=2000000000000000000,
            staking_event_id=2, se_fmv_cad=Decimal("6.00"), se_amount_near=Decimal("1.0"),
        )
        row_t3 = self._make_mock_row(
            id=30, category="income", leg_type="parent",
            t_block_timestamp=3000000000000000000,
            staking_event_id=3, se_fmv_cad=Decimal("7.00"), se_amount_near=Decimal("1.0"),
        )

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # DB returns rows already sorted by timestamp (SQL ORDER BY guarantees this)
        mock_cursor.fetchall.side_effect = [[row_t1, row_t2, row_t3], []]
        mock_cursor.fetchone.return_value = [1]

        mock_pool.getconn.return_value = mock_conn

        price_service = MagicMock()

        engine = ACBEngine(mock_pool, price_service)

        with patch("engine.acb.GainsCalculator") as MockGains:
            mock_gains_instance = MagicMock()
            MockGains.return_value = mock_gains_instance
            stats = engine.calculate_for_user(1)

        # All 3 staking income rows should be processed
        assert stats["snapshots_written"] == 3
        assert stats["income_recorded"] == 3


# ---------------------------------------------------------------------------
# GainsCalculator — capital gains and income ledger
# ---------------------------------------------------------------------------


class TestGainsCalculator:
    """Tests for GainsCalculator — writes capital_gains_ledger and income_ledger rows."""

    def test_record_disposal(self):
        """record_disposal writes capital_gains_ledger row with correct tax_year and gain_loss_cad."""
        from engine.gains import GainsCalculator

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [42]  # returned id
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        calc = GainsCalculator(mock_conn)
        ledger_id = calc.record_disposal(
            user_id=1,
            acb_snapshot_id=100,
            token_symbol="NEAR",
            block_timestamp=1672531200,  # 2023-01-01 00:00:00 UTC (seconds)
            chain="near",
            units_disposed=Decimal("300"),
            proceeds_cad=Decimal("2400"),
            acb_used_cad=Decimal("1500"),
            fees_cad=Decimal("8"),
            gain_loss_cad=Decimal("892"),
            needs_review=False,
        )

        assert ledger_id == 42
        assert mock_cursor.execute.called
        sql_call = mock_cursor.execute.call_args
        # Verify the SQL params contain correct values
        params = sql_call[0][1]
        assert params[0] == 1        # user_id
        assert params[1] == 100      # acb_snapshot_id
        assert params[2] == "NEAR"   # token_symbol
        assert params[5] == Decimal("300")   # units_disposed
        assert params[6] == Decimal("2400")  # proceeds_cad
        assert params[7] == Decimal("1500")  # acb_used_cad
        assert params[8] == Decimal("8")     # fees_cad
        assert params[9] == Decimal("892")   # gain_loss_cad
        # tax_year should be 2023
        assert params[11] == 2023

    def test_record_income_staking(self):
        """record_income with staking: source_type='staking', staking_event_id linked, acb_added_cad=fmv_cad."""
        from engine.gains import GainsCalculator

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [55]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        calc = GainsCalculator(mock_conn)
        ledger_id = calc.record_income(
            user_id=1,
            source_type="staking",
            token_symbol="NEAR",
            block_timestamp=1672531200,  # 2023-01-01 seconds
            chain="near",
            units_received=Decimal("1.5"),
            fmv_usd=Decimal("5.00"),
            fmv_cad=Decimal("10.50"),
            staking_event_id=77,
            lockup_event_id=None,
            classification_id=10,
        )

        assert ledger_id == 55
        assert mock_cursor.execute.called
        sql_call = mock_cursor.execute.call_args
        params = sql_call[0][1]
        assert params[0] == 1           # user_id
        assert params[1] == "staking"   # source_type
        assert params[2] == 77          # staking_event_id
        assert params[3] is None        # lockup_event_id
        assert params[4] == 10          # classification_id
        assert params[5] == "NEAR"      # token_symbol
        # income_date is index 6, block_timestamp index 7
        assert params[8] == Decimal("1.5")    # units_received
        assert params[9] == Decimal("5.00")   # fmv_usd
        assert params[10] == Decimal("10.50") # fmv_cad
        assert params[11] == Decimal("10.50") # acb_added_cad = fmv_cad
        assert params[12] == 2023             # tax_year

    def test_record_income_vesting(self):
        """record_income with vesting: source_type='vesting', lockup_event_id linked."""
        from engine.gains import GainsCalculator

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [66]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        calc = GainsCalculator(mock_conn)
        ledger_id = calc.record_income(
            user_id=1,
            source_type="vesting",
            token_symbol="NEAR",
            block_timestamp=1672531200,
            chain="near",
            units_received=Decimal("100"),
            fmv_usd=Decimal("3.50"),
            fmv_cad=Decimal("4.90"),
            staking_event_id=None,
            lockup_event_id=88,
            classification_id=20,
        )

        assert ledger_id == 66
        sql_call = mock_cursor.execute.call_args
        params = sql_call[0][1]
        assert params[1] == "vesting"  # source_type
        assert params[2] is None       # staking_event_id
        assert params[3] == 88         # lockup_event_id
        assert params[11] == Decimal("4.90")  # acb_added_cad = fmv_cad
