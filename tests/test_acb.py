"""
Test scaffolds for ACB (Adjusted Cost Base) engine.

These tests will be implemented in Phase 4 Plan 02 when ACBEngine and
ACBPool classes are built. Scaffold bodies contain pass with docstrings
describing expected behavior.

Coverage planned:
  - TestACBPool: unit tests for the per-token pool state machine
  - TestACBEngine: integration tests for cross-wallet replay and income handling
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# ACBPool — per-token pool state machine
# ---------------------------------------------------------------------------


class TestACBPool:
    """Unit tests for the ACBPool (per-token running total / ACB calculator).

    ACBPool maintains:
      - units_held: total units in the pool
      - total_cost_cad: total CAD cost basis for all units held
      - acb_per_unit_cad: total_cost_cad / units_held
    """

    def test_acquire(self):
        """Acquiring units increases pool and updates ACB per unit correctly.

        Given: empty pool
        When: acquire 10 units at $5 CAD each (cost=$50 total)
        Then: units_held=10, total_cost_cad=50, acb_per_unit=5
        """
        pass

    def test_dispose(self):
        """Disposing units removes from pool using weighted-average ACB.

        Given: pool with 10 units, total_cost=100, acb_per_unit=10
        When: dispose 4 units at $15 CAD each (proceeds=$60)
        Then: gain = 60 - (4 * 10) = 20, units_held=6, total_cost=60
        """
        pass

    def test_multi_acquire(self):
        """Multiple acquisitions at different prices produce correct average ACB.

        Given: acquire 5 @ $4 then acquire 5 @ $6
        Then: acb_per_unit = (5*4 + 5*6) / 10 = 5.00 CAD
        """
        pass

    def test_acquire_with_fee(self):
        """Acquisition fees are added to the cost basis (not deducted from proceeds).

        Given: acquire 10 units, price=$5 CAD, fee=$2 CAD
        Then: total_cost_cad = (10 * 5) + 2 = 52, acb_per_unit = 5.2
        """
        pass

    def test_dispose_with_fee(self):
        """Disposal fees reduce proceeds (increasing loss or reducing gain).

        Given: pool with acb_per_unit=10, dispose 4 units at $15/unit, fee=$2 CAD
        Then: gain = (60 - 2) - 40 = 18 (fee reduces proceeds)
        """
        pass

    def test_oversell_clamps(self):
        """Disposing more units than held is clamped to zero (no negative pool).

        Given: pool with 3 units
        When: dispose 5 units (oversell)
        Then: units_held=0, total_cost_cad=0, no exception raised
        """
        pass


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

    def test_cross_wallet_pool(self):
        """Tokens from multiple wallets (same user) share a single ACB pool.

        A user with 2 NEAR wallets should have their NEAR holdings merged
        into one ACBPool — CRA treats the user, not the wallet, as the entity.

        Verify: ACBSnapshot.units_after reflects combined holdings across wallets.
        """
        pass

    def test_staking_income_fmv(self):
        """Staking rewards generate an IncomeLedger row with FMV at receipt.

        Given: staking reward of 1.5 NEAR when NEAR=$5 USD, USD/CAD=1.40
        Then: IncomeLedger.fmv_cad = 1.5 * 5 * 1.40 = 10.50, acb_added_cad=10.50
        And: ACBPool units increase by 1.5, cost increases by 10.50
        """
        pass

    def test_swap_fee_leg_acb(self):
        """Swap fee_leg cost is correctly allocated to the disposal proceeds.

        Given: sell 100 USDC, buy 0.5 ETH, fee_leg = 2 USDC
        Then: ETH acquire cost = (0.5 ETH FMV in CAD), USDC dispose proceeds
              reduced by fee_leg FMV
        """
        pass

    def test_chronological_replay(self):
        """Engine processes events in strict block_timestamp order.

        Given: 3 classifications with timestamps T3, T1, T2
        When: engine runs
        Then: ACBSnapshots are created in T1, T2, T3 order
        """
        pass
