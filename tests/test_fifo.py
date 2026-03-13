"""
Unit tests for engine/fifo.py — FIFOTracker lot-level tracking.

Test class:
  - TestFIFOTracker: 8 tests covering acquire, dispose, holdings, COGS, FIFO vs ACB.

All tests use known numeric examples with Decimal arithmetic.
"""

import unittest
from decimal import Decimal


class TestFIFOTracker(unittest.TestCase):
    """Tests for FIFOTracker — lot-level FIFO inventory valuation."""

    def test_acquire_creates_two_lots(self):
        """Test 1: Acquiring 10 units at $5 then 5 units at $10 creates two lots."""
        from engine.fifo import FIFOTracker
        tracker = FIFOTracker()
        tracker.acquire('NEAR', Decimal('10'), Decimal('5'), timestamp=1000)
        tracker.acquire('NEAR', Decimal('5'), Decimal('10'), timestamp=2000)
        holdings = tracker.get_holdings('NEAR')
        self.assertEqual(len(holdings), 2)
        self.assertEqual(holdings[0]['units'], Decimal('10'))
        self.assertEqual(holdings[0]['cost_per_unit_cad'], Decimal('5'))
        self.assertEqual(holdings[1]['units'], Decimal('5'))
        self.assertEqual(holdings[1]['cost_per_unit_cad'], Decimal('10'))

    def test_dispose_fifo_first_lot(self):
        """Test 2: Disposing 8 units uses FIFO: first lot (10@$5, take 8) = cost $40."""
        from engine.fifo import FIFOTracker
        tracker = FIFOTracker()
        tracker.acquire('NEAR', Decimal('10'), Decimal('5'), timestamp=1000)
        tracker.acquire('NEAR', Decimal('5'), Decimal('10'), timestamp=2000)
        disposals = tracker.dispose('NEAR', Decimal('8'), Decimal('12'), timestamp=3000)
        # Should take 8 from first lot at $5 each = $40 cost
        total_cost = sum(d['cost_cad'] for d in disposals)
        self.assertEqual(total_cost, Decimal('40'))
        self.assertFalse(any(d.get('needs_review', False) for d in disposals))

    def test_dispose_exhausts_first_lot_takes_from_second(self):
        """Test 3: Disposing more than oldest lot exhausts first lot, takes from second."""
        from engine.fifo import FIFOTracker
        tracker = FIFOTracker()
        tracker.acquire('NEAR', Decimal('10'), Decimal('5'), timestamp=1000)
        tracker.acquire('NEAR', Decimal('5'), Decimal('10'), timestamp=2000)
        # Dispose 12 units: 10 from first lot + 2 from second
        disposals = tracker.dispose('NEAR', Decimal('12'), Decimal('15'), timestamp=3000)
        self.assertEqual(len(disposals), 2)
        # First disposal: 10 units from lot 1 at $5 = $50
        self.assertEqual(disposals[0]['units_from_lot'], Decimal('10'))
        self.assertEqual(disposals[0]['cost_cad'], Decimal('50'))
        # Second disposal: 2 units from lot 2 at $10 = $20
        self.assertEqual(disposals[1]['units_from_lot'], Decimal('2'))
        self.assertEqual(disposals[1]['cost_cad'], Decimal('20'))

    def test_remaining_lots_after_partial_disposal(self):
        """Test 4: Remaining lots after disposal reflect correct quantities."""
        from engine.fifo import FIFOTracker
        tracker = FIFOTracker()
        tracker.acquire('NEAR', Decimal('10'), Decimal('5'), timestamp=1000)
        tracker.acquire('NEAR', Decimal('5'), Decimal('10'), timestamp=2000)
        tracker.dispose('NEAR', Decimal('8'), Decimal('12'), timestamp=3000)
        holdings = tracker.get_holdings('NEAR')
        # Should have 2 remaining: 2 units from lot 1, 5 units from lot 2
        total_units = sum(h['units'] for h in holdings)
        self.assertEqual(total_units, Decimal('7'))
        # First remaining lot should have 2 units at $5
        self.assertEqual(holdings[0]['units'], Decimal('2'))
        self.assertEqual(holdings[0]['cost_per_unit_cad'], Decimal('5'))

    def test_get_holdings_returns_lot_details(self):
        """Test 5: get_holdings() returns list of remaining lots with quantity, cost_per_unit, total_cost."""
        from engine.fifo import FIFOTracker
        tracker = FIFOTracker()
        tracker.acquire('BTC', Decimal('2'), Decimal('30000'), timestamp=1000)
        holdings = tracker.get_holdings('BTC')
        self.assertEqual(len(holdings), 1)
        lot = holdings[0]
        self.assertIn('units', lot)
        self.assertIn('cost_per_unit_cad', lot)
        self.assertIn('total_cost_cad', lot)
        self.assertIn('acquisition_timestamp', lot)
        self.assertEqual(lot['total_cost_cad'], Decimal('60000'))

    def test_get_cogs_returns_cost_of_disposed_lots_in_year(self):
        """Test 6: get_cogs(year) returns total cost of lots disposed during the year."""
        from engine.fifo import FIFOTracker
        import datetime
        # Acquire at timestamps in 2024
        ts_jan = int(datetime.datetime(2024, 1, 15, tzinfo=datetime.timezone.utc).timestamp())
        ts_mar = int(datetime.datetime(2024, 3, 20, tzinfo=datetime.timezone.utc).timestamp())
        ts_dispose = int(datetime.datetime(2024, 6, 1, tzinfo=datetime.timezone.utc).timestamp())
        tracker = FIFOTracker()
        tracker.acquire('NEAR', Decimal('10'), Decimal('5'), timestamp=ts_jan)
        tracker.acquire('NEAR', Decimal('5'), Decimal('10'), timestamp=ts_mar)
        tracker.dispose('NEAR', Decimal('8'), Decimal('12'), timestamp=ts_dispose)
        cogs = tracker.get_cogs(2024)
        # Disposed 8 units from first lot at $5 = $40
        self.assertEqual(cogs, Decimal('40'))

    def test_fifo_different_result_than_acb(self):
        """Test 7: FIFO produces different gain/loss than ACB average cost for same transactions."""
        from engine.fifo import FIFOTracker
        from engine.acb import ACBPool
        # Buy 10 at $5, then 10 at $15. Sell 10 at $20.
        # ACB average cost: (10*5 + 10*15) / 20 = $10/unit; sell 10 = $100 cost, proceeds $200, gain = $100
        # FIFO: sell from first lot at $5; 10 units * $5 = $50 cost, proceeds $200, gain = $150
        acb_pool = ACBPool('NEAR')
        acb_pool.acquire(Decimal('10'), Decimal('50'))   # 10 units at $5 total = $50
        acb_pool.acquire(Decimal('10'), Decimal('150'))  # 10 units at $15 total = $150
        acb_snap = acb_pool.dispose(Decimal('10'), Decimal('200'))
        acb_gain = acb_snap['gain_loss_cad']

        fifo = FIFOTracker()
        fifo.acquire('NEAR', Decimal('10'), Decimal('5'), timestamp=1000)
        fifo.acquire('NEAR', Decimal('10'), Decimal('15'), timestamp=2000)
        disposals = fifo.dispose('NEAR', Decimal('10'), Decimal('20'), timestamp=3000)
        fifo_cost = sum(d['cost_cad'] for d in disposals)
        fifo_proceeds = Decimal('10') * Decimal('20')
        fifo_gain = fifo_proceeds - fifo_cost

        # ACB gain = $100; FIFO gain = $150 — they differ
        self.assertNotEqual(acb_gain, fifo_gain)
        self.assertEqual(acb_gain, Decimal('100.00000000'))
        self.assertEqual(fifo_gain, Decimal('150'))

    def test_oversell_handled_with_needs_review(self):
        """Test 8: Oversell (dispose more than held) handled gracefully with needs_review flag."""
        from engine.fifo import FIFOTracker
        tracker = FIFOTracker()
        tracker.acquire('NEAR', Decimal('5'), Decimal('10'), timestamp=1000)
        # Dispose 10 units but only 5 held
        disposals = tracker.dispose('NEAR', Decimal('10'), Decimal('15'), timestamp=2000)
        # Should return partial disposals and flag needs_review
        self.assertTrue(any(d.get('needs_review', False) for d in disposals))
        # Total units from lot should not exceed 5
        total_disposed = sum(d['units_from_lot'] for d in disposals)
        self.assertLessEqual(total_disposed, Decimal('5'))

    def test_replay_from_snapshots(self):
        """Test 9: replay_from_snapshots replays acquire/dispose events."""
        from engine.fifo import FIFOTracker
        rows = [
            {
                'token_symbol': 'NEAR',
                'event_type': 'acquire',
                'units_delta': Decimal('10'),
                'cost_cad_delta': Decimal('50'),   # 10 units * $5
                'block_timestamp': 1000,
            },
            {
                'token_symbol': 'NEAR',
                'event_type': 'acquire',
                'units_delta': Decimal('5'),
                'cost_cad_delta': Decimal('75'),   # 5 units * $15
                'block_timestamp': 2000,
            },
            {
                'token_symbol': 'NEAR',
                'event_type': 'dispose',
                'units_delta': Decimal('8'),
                'cost_cad_delta': Decimal('120'),  # proceeds (ignored for FIFO cost)
                'block_timestamp': 3000,
            },
        ]
        tracker = FIFOTracker()
        tracker.replay_from_snapshots(rows)
        holdings = tracker.get_holdings('NEAR')
        # 10 + 5 - 8 = 7 units remain
        total_units = sum(h['units'] for h in holdings)
        self.assertEqual(total_units, Decimal('7'))


if __name__ == '__main__':
    unittest.main()
