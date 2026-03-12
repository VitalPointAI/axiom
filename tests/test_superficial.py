"""
Test scaffolds for SuperficialLossDetector.

These tests will be implemented in Phase 4 Plan 02 when SuperficialLossDetector
is built. Scaffold bodies contain pass with docstrings describing expected behavior.

Canadian tax superficial loss rule (ITA s.54):
  A capital loss is superficial if:
    1. The taxpayer (or affiliated person) disposed of property at a loss, AND
    2. The same or identical property was acquired in the period starting 30 days
       before AND ending 30 days after the disposition date.

  The denied (superficial) loss is added to the ACB of the reacquired property.

Coverage planned:
  - TestSuperficialLoss: detection, proration, cross-exchange, and edge cases
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# SuperficialLossDetector
# ---------------------------------------------------------------------------


class TestSuperficialLoss:
    """Tests for SuperficialLossDetector — identifies and flags superficial losses.

    SuperficialLossDetector:
      - Scans CapitalGainsLedger rows where gain_loss_cad < 0
      - Checks ACBSnapshot rows within ±30 days for re-acquisitions
      - Excludes re-acquisitions from the same parent transaction (wash-sale
        via swap where sell_leg and buy_leg are in the same tx)
      - Sets is_superficial_loss=True and denied_loss_cad on the ledger row
      - denied_loss_cad is added to ACB of reacquired units
    """

    def test_full_rebuy_denial(self):
        """Full rebuy within 30 days causes full loss denial.

        Given: sell 100 NEAR at a loss of $200 CAD on Day 0
        When: buy 100 NEAR (or more) within 30 days before or after
        Then: is_superficial_loss=True, denied_loss_cad=$200 (full loss denied)
        """
        pass

    def test_partial_rebuy_prorated(self):
        """Partial rebuy causes prorated denial proportional to units reacquired.

        Given: sell 100 NEAR at a loss of $200 CAD on Day 0
        When: buy 60 NEAR within the 30-day window
        Then: denied_loss_cad = 200 * (60/100) = $120, remaining $80 is allowed
        """
        pass

    def test_exchange_rebuy(self):
        """Rebuy on a different exchange still triggers superficial loss.

        Given: sell 50 ETH on Coinbase at a loss on Day 0
        When: buy 50 ETH on Crypto.com on Day 15
        Then: is_superficial_loss=True (same token, user-level pool, same 30-day window)
        """
        pass

    def test_no_rebuy_no_flag(self):
        """Loss without rebuy within 30 days is a clean capital loss.

        Given: sell 100 NEAR at a loss of $150 CAD on Day 0
        When: no NEAR acquired in [-30, +30] day window
        Then: is_superficial_loss=False, denied_loss_cad=None
        """
        pass

    def test_exclude_same_parent_tx(self):
        """Swap's buy_leg does not trigger superficial loss on its own sell_leg.

        Given: swap NEAR -> ETH classified as sell_leg (NEAR loss) + buy_leg (ETH)
        When: NEAR sell_leg has a loss and ETH buy_leg is within 30 days
        But: they share the same parent_classification_id
        Then: ETH buy_leg is excluded from superficial loss detection for NEAR
        """
        pass
