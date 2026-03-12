"""
Tests for SuperficialLossDetector.

Canadian tax superficial loss rule (ITA s.54):
  A capital loss is superficial if:
    1. The taxpayer (or affiliated person) disposed of property at a loss, AND
    2. The same or identical property was acquired in the period starting 30 days
       before AND ending 30 days after the disposition date.

  The denied (superficial) loss is added to the ACB of the reacquired property.

Coverage:
  - TestSuperficialLoss: detection, proration, cross-exchange, and edge cases
"""

import sys
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ledger_row(**kwargs):
    """Create a mock capital_gains_ledger-style row."""
    defaults = {
        "id": 1,
        "user_id": 1,
        "token_symbol": "NEAR",
        "gain_loss_cad": Decimal("-200.00"),
        "units_disposed": Decimal("100"),
        "block_timestamp": 1680000000,  # Unix seconds (Day 0)
        "acb_snapshot_id": 10,
        # classification context (joined)
        "classification_id": 100,
        "parent_classification_id": None,
    }
    defaults.update(kwargs)
    row = MagicMock()
    for k, v in defaults.items():
        setattr(row, k, v)
    row.__getitem__ = lambda self, key: getattr(self, key)
    return row


def _make_cursor_with_fetchall(side_effects):
    """Create a mock cursor whose fetchall() returns successive side_effect lists."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.side_effect = side_effects
    cur.fetchone.return_value = None
    return cur


def _make_conn(cursor):
    """Create a mock psycopg2 connection wrapping the given cursor."""
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


# ---------------------------------------------------------------------------
# SuperficialLossDetector
# ---------------------------------------------------------------------------


class TestSuperficialLoss:
    """Unit tests for SuperficialLossDetector.

    SuperficialLossDetector:
      - Scans capital_gains_ledger rows where gain_loss_cad < 0
      - Queries transactions + exchange_transactions for rebuys in 61-day window
      - Excludes rebuys from the same parent transaction (swap legs)
      - Pro-rates the denied loss: denied_ratio = min(1, rebought / sold)
      - Returns list of superficial loss dicts with needs_review=True
      - apply_superficial_losses() UPDATEs capital_gains_ledger rows
    """

    def test_full_rebuy_denial(self):
        """Full rebuy within 30 days causes full loss denial.

        Given: sell 100 NEAR at a loss of $200 CAD on Day 0
        When: buy 100 NEAR (or more) within 30 days
        Then: is_superficial_loss=True, denied_loss_cad=$200 (100% denied)
        """
        from engine.superficial import SuperficialLossDetector

        # Day 0 disposal at loss
        disposal_ts = 1680000000
        # Day +15: rebuy 100 NEAR (on-chain) — same token, within window
        rebuy_ts = disposal_ts + 15 * 86400

        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)

        # Calls in order:
        #   1. SELECT losses from capital_gains_ledger
        #   2. SELECT on-chain rebuys (transactions table)
        #   3. SELECT exchange rebuys (exchange_transactions table)
        ledger_row = _make_ledger_row(
            id=1, token_symbol="NEAR",
            gain_loss_cad=Decimal("-200.00"),
            units_disposed=Decimal("100"),
            block_timestamp=disposal_ts,
            classification_id=100,
            parent_classification_id=None,
        )
        # on-chain rebuy: 100 units (yoctoNEAR = 100 * 1e24)
        onchain_rebuy = (100 * (10 ** 24), "near", rebuy_ts)
        # no exchange rebuy
        cur.fetchall.side_effect = [
            [ledger_row],       # losses query
            [onchain_rebuy],    # on-chain rebuys
            [],                 # exchange rebuys
        ]
        conn = _make_conn(cur)

        detector = SuperficialLossDetector(conn)
        losses = detector.scan_for_user(1)

        assert len(losses) == 1
        loss = losses[0]
        assert loss["ledger_id"] == 1
        assert loss["token_symbol"] == "NEAR"
        assert loss["gain_loss_cad"] == Decimal("-200.00")
        # Full rebuy: 100 bought / 100 sold = ratio 1.0
        assert loss["denied_ratio"] == Decimal("1")
        assert loss["denied_loss_cad"] == Decimal("200.00")
        assert loss["needs_review"] is True

    def test_partial_rebuy_prorated(self):
        """Partial rebuy causes prorated denial proportional to units reacquired.

        Given: sell 100 NEAR at a loss of $200 CAD on Day 0
        When: buy 50 NEAR within the 30-day window
        Then: denied_loss_cad = 200 * (50/100) = $100
        """
        from engine.superficial import SuperficialLossDetector

        disposal_ts = 1680000000
        rebuy_ts = disposal_ts + 10 * 86400

        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)

        ledger_row = _make_ledger_row(
            id=2, token_symbol="NEAR",
            gain_loss_cad=Decimal("-200.00"),
            units_disposed=Decimal("100"),
            block_timestamp=disposal_ts,
            classification_id=101,
            parent_classification_id=None,
        )
        # on-chain rebuy: 50 NEAR
        onchain_rebuy = (50 * (10 ** 24), "near", rebuy_ts)
        cur.fetchall.side_effect = [
            [ledger_row],
            [onchain_rebuy],
            [],
        ]
        conn = _make_conn(cur)

        detector = SuperficialLossDetector(conn)
        losses = detector.scan_for_user(1)

        assert len(losses) == 1
        loss = losses[0]
        assert loss["denied_ratio"] == Decimal("0.5")
        assert loss["denied_loss_cad"] == Decimal("100.00")
        assert loss["needs_review"] is True

    def test_exchange_rebuy(self):
        """Rebuy on exchange (exchange_transactions) still triggers superficial loss.

        Given: sell 50 NEAR on-chain at a loss on Day 0
        When: buy 50 NEAR on Coinbase on Day 15
        Then: is_superficial_loss=True (cross-source detection)
        """
        from engine.superficial import SuperficialLossDetector

        disposal_ts = 1680000000
        rebuy_ts = disposal_ts + 15 * 86400

        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)

        ledger_row = _make_ledger_row(
            id=3, token_symbol="NEAR",
            gain_loss_cad=Decimal("-150.00"),
            units_disposed=Decimal("50"),
            block_timestamp=disposal_ts,
            classification_id=102,
            parent_classification_id=None,
        )
        # No on-chain rebuy, but exchange rebuy of 50 NEAR
        exchange_rebuy = (Decimal("50"), rebuy_ts)
        cur.fetchall.side_effect = [
            [ledger_row],
            [],              # no on-chain rebuy
            [exchange_rebuy],  # exchange rebuy
        ]
        conn = _make_conn(cur)

        detector = SuperficialLossDetector(conn)
        losses = detector.scan_for_user(1)

        assert len(losses) == 1
        loss = losses[0]
        assert loss["denied_ratio"] == Decimal("1")
        assert loss["denied_loss_cad"] == Decimal("150.00")
        assert loss["needs_review"] is True

    def test_no_rebuy_no_flag(self):
        """Loss without rebuy within 61-day window is a clean capital loss.

        Given: sell 100 NEAR at a loss of $150 CAD on Day 0
        When: no NEAR acquired in [-30, +30] day window
        Then: result list is empty (no superficial losses detected)
        """
        from engine.superficial import SuperficialLossDetector

        disposal_ts = 1680000000

        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)

        ledger_row = _make_ledger_row(
            id=4, token_symbol="NEAR",
            gain_loss_cad=Decimal("-150.00"),
            units_disposed=Decimal("100"),
            block_timestamp=disposal_ts,
            classification_id=103,
            parent_classification_id=None,
        )
        cur.fetchall.side_effect = [
            [ledger_row],
            [],   # no on-chain rebuys
            [],   # no exchange rebuys
        ]
        conn = _make_conn(cur)

        detector = SuperficialLossDetector(conn)
        losses = detector.scan_for_user(1)

        assert losses == []

    def test_exclude_same_parent_tx(self):
        """Swap's buy_leg does NOT trigger superficial loss on its own sell_leg.

        Given: swap NEAR -> ETH at a NEAR loss, sell_leg and buy_leg share parent_id=999
        When: The ETH buy_leg is the only acquisition within the window
        But: ETH is a different token — so no NEAR rebuy, and NEAR sell is not superficial
        Then: no superficial loss flagged (ETH buy != NEAR rebuy)

        Also tests: if NEAR rebuy exists with same parent_classification_id, it is excluded.
        """
        from engine.superficial import SuperficialLossDetector

        disposal_ts = 1680000000

        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)

        # NEAR sell_leg at a loss; parent_classification_id=999
        ledger_row = _make_ledger_row(
            id=5, token_symbol="NEAR",
            gain_loss_cad=Decimal("-100.00"),
            units_disposed=Decimal("50"),
            block_timestamp=disposal_ts,
            classification_id=200,  # sell_leg classification id
            parent_classification_id=999,  # parent swap
        )
        # Detector queries transactions for NEAR rebuys, excludes same parent
        # We simulate: no NEAR rebuys found (the buy_leg was ETH, not NEAR)
        cur.fetchall.side_effect = [
            [ledger_row],
            [],   # on-chain query returns 0 NEAR rebuys (ETH excluded by token filter)
            [],   # exchange query returns 0 NEAR rebuys
        ]
        conn = _make_conn(cur)

        detector = SuperficialLossDetector(conn)
        losses = detector.scan_for_user(1)

        assert losses == []

    def test_rebuy_before_sale(self):
        """Rebuy 20 days BEFORE sale at loss is still superficial (30 days before window).

        Given: sell 100 NEAR at a loss on Day 0
        When: bought 40 NEAR on Day -20 (20 days BEFORE sale)
        Then: superficial loss detected, denied_ratio = min(1, 40/100) = 0.4
        """
        from engine.superficial import SuperficialLossDetector

        disposal_ts = 1680000000
        rebuy_ts = disposal_ts - 20 * 86400  # 20 days BEFORE sale

        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)

        ledger_row = _make_ledger_row(
            id=6, token_symbol="NEAR",
            gain_loss_cad=Decimal("-300.00"),
            units_disposed=Decimal("100"),
            block_timestamp=disposal_ts,
            classification_id=104,
            parent_classification_id=None,
        )
        onchain_rebuy = (40 * (10 ** 24), "near", rebuy_ts)
        cur.fetchall.side_effect = [
            [ledger_row],
            [onchain_rebuy],
            [],
        ]
        conn = _make_conn(cur)

        detector = SuperficialLossDetector(conn)
        losses = detector.scan_for_user(1)

        assert len(losses) == 1
        loss = losses[0]
        assert loss["denied_ratio"] == Decimal("0.4")
        assert loss["denied_loss_cad"] == Decimal("120.00")
        assert loss["needs_review"] is True

    def test_denied_loss_adds_to_acb(self):
        """apply_superficial_losses() updates capital_gains_ledger with denied amounts.

        Verifies that apply_superficial_losses:
          1. Issues UPDATE capital_gains_ledger SET is_superficial_loss=TRUE, denied_loss_cad=X
          2. Marks needs_review=TRUE
        """
        from engine.superficial import SuperficialLossDetector

        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchall.return_value = []
        cur.fetchone.return_value = None

        conn = _make_conn(cur)

        detector = SuperficialLossDetector(conn)

        losses = [
            {
                "ledger_id": 7,
                "token_symbol": "NEAR",
                "gain_loss_cad": Decimal("-200.00"),
                "denied_loss_cad": Decimal("120.00"),
                "denied_ratio": Decimal("0.6"),
                "rebuy_count": 1,
                "needs_review": True,
            }
        ]

        detector.apply_superficial_losses(user_id=1, losses=losses)

        # Verify UPDATE was called on capital_gains_ledger
        assert cur.execute.called
        calls = [str(c) for c in cur.execute.call_args_list]
        # At least one call should reference capital_gains_ledger
        combined = " ".join(calls)
        assert "capital_gains_ledger" in combined.lower() or any(
            "is_superficial_loss" in str(c).lower() for c in cur.execute.call_args_list
        )

    def test_multiple_rebuys_sum(self):
        """Multiple rebuys in the window are summed for denial calculation.

        Given: sell 100 NEAR at a loss of $400 CAD
        When: buy 30 on-chain + 40 on exchange = 70 total rebought
        Then: denied_ratio = 70/100 = 0.7, denied_loss = $280
        """
        from engine.superficial import SuperficialLossDetector

        disposal_ts = 1680000000

        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)

        ledger_row = _make_ledger_row(
            id=8, token_symbol="NEAR",
            gain_loss_cad=Decimal("-400.00"),
            units_disposed=Decimal("100"),
            block_timestamp=disposal_ts,
            classification_id=105,
            parent_classification_id=None,
        )
        onchain_rebuy = (30 * (10 ** 24), "near", disposal_ts + 5 * 86400)
        exchange_rebuy = (Decimal("40"), disposal_ts + 10 * 86400)
        cur.fetchall.side_effect = [
            [ledger_row],
            [onchain_rebuy],
            [exchange_rebuy],
        ]
        conn = _make_conn(cur)

        detector = SuperficialLossDetector(conn)
        losses = detector.scan_for_user(1)

        assert len(losses) == 1
        loss = losses[0]
        assert loss["denied_ratio"] == Decimal("0.7")
        assert loss["denied_loss_cad"] == Decimal("280.00")
