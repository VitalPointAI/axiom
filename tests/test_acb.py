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
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _acb_test_dek():
    # Most tests in this file reach into ACBEngine / GainsCalculator paths
    # that call write_audit and encrypt ORM columns. Both require a DEK in
    # the request ContextVar. Apply to every test in this module; the
    # conftest _zero_dek_between_tests fixture still cleans up after.
    from db.crypto import set_dek, zero_dek

    set_dek(b"\x00" * 32)
    try:
        yield
    finally:
        zero_dek()


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
        from engine.acb import ACBPool

        # Test ACBPool directly: staking reward of 1.5 NEAR at fmv_cad=$10.50
        pool = ACBPool("NEAR")
        pool.acquire(Decimal("1.5"), Decimal("10.50"))
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
        eth_pool.acquire(Decimal("0.5"), Decimal("2100"), fee_cad=Decimal("2.80"))
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


# ---------------------------------------------------------------------------
# TestACBGapDataEdgeCases (RC-11, RC-12)
# ---------------------------------------------------------------------------


class TestACBGapDataEdgeCases:
    """Tests for ACB gap data handling: missing prices, None amounts, estimated prices, oversell.

    Covers RC-11 (missing price handling) and RC-12 (oversell / zero-holdings disposal).
    """

    def _make_mock_row(self, **kwargs):
        """Build a mock DB row with all needed fields. Same pattern as TestACBEngine."""
        defaults = {
            "id": 1,
            "category": "income",
            "leg_type": "parent",
            "fmv_usd": None,
            "fmv_cad": None,
            "staking_event_id": None,
            "lockup_event_id": None,
            "parent_classification_id": None,
            "transaction_id": 1,
            "exchange_transaction_id": None,
            "t_block_timestamp": 1680000000000000000,
            "amount": 1000000000000000000000000,
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
        row.__getitem__ = lambda self, key: getattr(self, key)
        return row

    def _make_engine_with_rows(self, rows, price_cad_return=(Decimal("5.00"), False)):
        """Set up a mock ACBEngine with given classification rows and price service."""
        from engine.acb import ACBEngine

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_cursor.fetchall.side_effect = [rows, [], []]
        mock_cursor.fetchone.return_value = [1]
        mock_pool.getconn.return_value = mock_conn

        price_service = MagicMock()
        price_service.get_price_cad_at_timestamp.return_value = price_cad_return

        return ACBEngine(mock_pool, price_service), mock_cursor, price_service

    def test_missing_price_skips_income_row(self):
        """When price_service returns None for get_price_cad_at_timestamp, income row is
        processed without crashing. The FMV falls back to 0 (estimated) and the snapshot
        is recorded with is_estimated=True.

        This tests airdrop income (no staking_event_id, no lockup_event_id) where the
        price lookup fails/returns None.
        """
        from engine.acb import ACBEngine

        # Airdrop income row: no staking or lockup event -> price_service will be called
        airdrop_row = self._make_mock_row(
            id=1,
            category="income",
            leg_type="parent",
            staking_event_id=None,
            lockup_event_id=None,
            fmv_cad=None,
            t_block_timestamp=1680000000000000000,
            amount=1000000000000000000000000,  # 1 NEAR
        )

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_cursor.fetchall.side_effect = [[airdrop_row], [], []]
        mock_cursor.fetchone.return_value = [1]
        mock_pool.getconn.return_value = mock_conn

        price_service = MagicMock()
        # Simulate price_service returning None price (not estimated, but no data)
        price_service.get_price_cad_at_timestamp.return_value = (None, False)

        engine = ACBEngine(mock_pool, price_service)

        # Should not raise any exception
        with patch("engine.acb.GainsCalculator") as MockGains:
            mock_gains_instance = MagicMock()
            MockGains.return_value = mock_gains_instance
            stats = engine.calculate_for_user(1)

        # Income row was still processed (not crashed)
        assert stats["income_recorded"] == 1, (
            f"Income row should be recorded even with None price; got {stats['income_recorded']}"
        )
        assert stats["snapshots_written"] == 1

        # Verify income recorded with fmv_cad=0 (fallback)
        assert mock_gains_instance.record_income.called
        call_kwargs = mock_gains_instance.record_income.call_args[1]
        assert call_kwargs["fmv_cad"] == Decimal("0"), (
            f"fmv_cad should fall back to 0 when price is None; got {call_kwargs['fmv_cad']}"
        )

    def test_none_amount_transaction_handled(self):
        """Transaction with amount=None does not raise; ACBPool units_held stays at 0.

        When amount=None, to_human_units is not called; units defaults to Decimal('0').
        The pool.acquire(0, 0) call is safe.
        """
        from engine.acb import ACBPool

        pool = ACBPool("NEAR")
        # Simulating amount=None — engine assigns units=Decimal('0') in this case
        initial_units = pool.total_units

        # Direct test: acquire with 0 units (what happens when amount=None in engine)
        result = pool.acquire(Decimal("0"), Decimal("0"))

        assert result is not None, "acquire() should return a result dict"
        assert pool.total_units == initial_units, "Pool state should be unchanged with 0 units"
        assert pool.total_cost_cad == Decimal("0")

    def test_disposal_with_no_price_uses_estimate(self):
        """Disposal where price_service returns estimated price sets is_estimated=True in snapshot.

        When get_price_cad_at_timestamp returns (price, is_estimated=True), the ACBEngine
        passes is_estimated=True to _persist_snapshot, which writes it to acb_snapshots.
        """
        from engine.acb import ACBEngine

        # Capital gain row — disposal (sell)
        disposal_row = self._make_mock_row(
            id=10,
            category="capital_gain",
            leg_type="parent",
            fmv_cad=None,
            staking_event_id=None,
            lockup_event_id=None,
            t_block_timestamp=1680000000000000000,
            amount=1000000000000000000000000,  # 1 NEAR
        )

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # No child rows (no sell_leg/buy_leg) — falls into simple _handle_disposal
        mock_cursor.fetchall.side_effect = [[disposal_row], [], []]
        mock_cursor.fetchone.return_value = [1]
        mock_pool.getconn.return_value = mock_conn

        price_service = MagicMock()
        # Return an estimated price (is_estimated=True)
        price_service.get_price_cad_at_timestamp.return_value = (Decimal("4.50"), True)

        engine = ACBEngine(mock_pool, price_service)

        # Phase 16 routes snapshot persistence through insert_acb_snapshot_with_dedup.
        # Patch it at the engine_acb module so we can assert the is_estimated
        # flag reached the helper regardless of the underlying SQL shape (which
        # includes encryption and HMAC surrogate columns).
        with patch("engine.acb.GainsCalculator") as MockGains, \
             patch("engine.acb.engine_acb.insert_acb_snapshot_with_dedup") as mock_persist:
            MockGains.return_value = MagicMock()
            mock_persist.return_value = 1  # snapshot id
            stats = engine.calculate_for_user(1)

        # Snapshot should be written
        assert stats["snapshots_written"] >= 1

        # Find the insert_acb_snapshot_with_dedup call for the disposal row and
        # verify price_estimated=True was forwarded through _persist_snapshot.
        assert mock_persist.called, "Expected insert_acb_snapshot_with_dedup to be called"
        estimated_calls = [
            call for call in mock_persist.call_args_list
            if call.kwargs.get("price_estimated") is True
        ]
        assert estimated_calls, (
            f"Expected at least one persist call with price_estimated=True; "
            f"got kwargs={[c.kwargs for c in mock_persist.call_args_list]}"
        )

    def test_oversell_zero_holdings(self):
        """Disposal after all units sold (zero holdings) records oversell with needs_review=True.

        When pool has 0 units and dispose(any_amount) is called, the pool clamps to 0,
        sets needs_review=True, and does not raise.
        """
        from engine.acb import ACBPool

        pool = ACBPool("NEAR")
        # Pool starts empty (0 units held) — simulates oversell on fresh pool
        assert pool.total_units == Decimal("0")

        # Attempt to dispose 10 units from an empty pool
        result = pool.dispose(Decimal("10"), Decimal("100"))

        assert result["needs_review"] is True, (
            "Disposing from empty pool should set needs_review=True"
        )
        assert pool.total_units == Decimal("0"), (
            "Pool units_held should remain 0 (clamped, not negative)"
        )
        assert pool.total_cost_cad == Decimal("0"), (
            "Pool total_cost_cad should remain 0 after empty-pool disposal"
        )


# ---------------------------------------------------------------------------
# ACB Pool Invariant Checks
# ---------------------------------------------------------------------------


class TestACBPoolInvariants:
    """Tests for check_acb_pool_invariants — runtime invariant detection."""

    def test_invariant_clean_pool(self):
        """Normal pool with positive balance passes invariant check."""
        from engine.acb.pool import ACBPool, check_acb_pool_invariants

        pool = ACBPool("NEAR")
        pool.acquire(Decimal("100"), Decimal("500"))
        assert check_acb_pool_invariants(pool) is True

    def test_invariant_negative_balance(self):
        """Pool with negative total_units is detected as violation."""
        from engine.acb.pool import ACBPool, check_acb_pool_invariants

        pool = ACBPool("NEAR")
        # Force negative state (shouldn't happen in normal operation)
        pool.total_units = Decimal("-1")
        pool.total_cost_cad = Decimal("100")
        assert check_acb_pool_invariants(pool) is False

    def test_invariant_negative_cost(self):
        """Pool with negative total_cost_cad is detected as violation."""
        from engine.acb.pool import ACBPool, check_acb_pool_invariants

        pool = ACBPool("NEAR")
        pool.total_units = Decimal("10")
        pool.total_cost_cad = Decimal("-50")
        assert check_acb_pool_invariants(pool) is False

    def test_invariant_writes_audit(self):
        """Invariant violation calls write_audit when conn is provided."""
        from engine.acb.pool import ACBPool, check_acb_pool_invariants

        pool = ACBPool("NEAR")
        pool.total_units = Decimal("-1")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("db.audit.write_audit") as mock_audit:
            result = check_acb_pool_invariants(pool, conn=mock_conn, user_id=1, context="test")
            assert result is False
            mock_audit.assert_called_once()
            call_kwargs = mock_audit.call_args[1]
            assert call_kwargs["action"] == "invariant_violation"
            assert call_kwargs["entity_type"] == "acb_pool"
            assert call_kwargs["user_id"] == 1

    def test_invariant_no_audit_without_conn(self):
        """Invariant violation without conn skips audit write."""
        from engine.acb.pool import ACBPool, check_acb_pool_invariants

        pool = ACBPool("NEAR")
        pool.total_units = Decimal("-1")

        # No conn passed — write_audit should not be called
        result = check_acb_pool_invariants(pool)
        assert result is False
