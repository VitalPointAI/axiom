"""Test scaffolds for the wallet ownership graph and internal transfer detection.

Covers CLASS-02: identifying transfers between wallets owned by the same user
(internal transfers are non-taxable moves, not disposals).

All test methods are pending stubs that will be implemented in plan 03-02.
They are marked with pytest.skip() so they are visible in the test collection
output but do not fail.
"""

import pytest


class TestInternalTransferDetection:
    """CLASS-02: Both-sides-owned detection makes transfers non-taxable."""

    def test_both_owned_is_internal(self):
        """Transfer where sender AND receiver are owned wallets of same user -> Internal."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_one_not_owned_is_external(self):
        """Transfer where receiver is not in user's wallet list -> External (taxable disposal)."""
        pytest.skip("Pending implementation in plan 03-02")


class TestCrossChainMatching:
    """CLASS-02: Cross-chain bridge transfer matching by amount + timestamp."""

    def test_matching_amount_and_time(self):
        """NEAR out + EVM in, same amount within 10-min window -> bridge pair detected."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_outside_window_no_match(self):
        """Same amount but > 10-min apart -> not matched as bridge pair."""
        pytest.skip("Pending implementation in plan 03-02")


class TestFalsePositivePrevention:
    """CLASS-02: Prevent cross-user false positive internal transfer matches."""

    def test_different_users_no_match(self):
        """Same amount + time between two different users -> not an internal transfer."""
        pytest.skip("Pending implementation in plan 03-02")


class TestWalletDiscovery:
    """Wallet graph high-frequency counterparty suggestions."""

    def test_high_frequency_counterparty_suggested(self):
        """Address appearing in > N transactions -> suggested as new owned wallet."""
        pytest.skip("Pending implementation in plan 03-02")
