"""Test scaffolds for the transaction classification engine.

Covers CLASS-01 (NEAR rule-based), CLASS-02 (wallet graph / internal transfers),
CLASS-03 (staking reward linkage), CLASS-04 (lockup vest linkage),
CLASS-05 (EVM classification), and multi-leg decomposition.

All test methods are pending stubs that will be implemented in subsequent plans
(03-02 through 03-05). They are marked with pytest.skip() so they are visible
in the test collection output but do not fail.
"""

import pytest


class TestNearClassification:
    """CLASS-01: NEAR on-chain rule-based classification."""

    def test_staking_deposit(self):
        """deposit_and_stake method_name -> StakingDeposit category."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_dex_swap(self):
        """ft_transfer_call to known DEX contract -> Swap (decomposes to legs)."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_basic_transfer(self):
        """Plain NEAR transfer with no method_name -> Transfer category."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_unknown_function_call(self):
        """Unrecognised method_name -> Unknown category, needs_review=True."""
        pytest.skip("Pending implementation in plan 03-02")


class TestExchangeClassification:
    """CLASS-01: Exchange transaction classification."""

    def test_buy_classified(self):
        """Exchange tx_type='BUY' -> CryptoAcquisition category."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_sell_classified(self):
        """Exchange tx_type='SELL' -> CryptoDisposal category."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_reward_classified(self):
        """Exchange tx_type='REWARD' or 'STAKING_INCOME' -> StakingIncome category."""
        pytest.skip("Pending implementation in plan 03-02")


class TestEVMClassification:
    """CLASS-05: EVM on-chain classification."""

    def test_evm_swap_detected(self):
        """EVM tx with known swap method signature -> Swap category."""
        pytest.skip("Pending implementation in plan 03-05")

    def test_evm_transfer(self):
        """EVM plain ETH transfer -> Transfer category."""
        pytest.skip("Pending implementation in plan 03-05")


class TestMultiLegDecomposition:
    """Swap decomposition into parent + sell_leg + buy_leg + fee_leg."""

    def test_swap_creates_parent_and_legs(self):
        """DEX swap -> 1 parent row + 2 child legs (sell + buy) in DB."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_leg_index_ordering(self):
        """Multi-leg rows have ascending leg_index (0, 1, 2...)."""
        pytest.skip("Pending implementation in plan 03-02")


class TestStakingRewardLinkage:
    """CLASS-03: Link staking income classifications to staking_events."""

    def test_links_to_staking_event(self):
        """StakingIncome classification sets staking_event_id to matching epoch event."""
        pytest.skip("Pending implementation in plan 03-03")

    def test_no_duplicate_income(self):
        """Re-running classifier on same tx does not create duplicate income record."""
        pytest.skip("Pending implementation in plan 03-03")


class TestLockupVestLinkage:
    """CLASS-04: Link lockup vest classifications to lockup_events."""

    def test_links_to_lockup_event(self):
        """LockupVest classification sets lockup_event_id to matching vest event."""
        pytest.skip("Pending implementation in plan 03-04")


class TestSwapDecomposition:
    """Advanced multi-leg decomposition edge cases."""

    def test_dex_swap_3_legs(self):
        """Swap with fee_leg -> parent + sell_leg + buy_leg + fee_leg (4 rows total)."""
        pytest.skip("Pending implementation in plan 03-02")
