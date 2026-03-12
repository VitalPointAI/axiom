"""Test scaffolds for EVM method signature decoding and swap detection.

Covers CLASS-05 EVM path: decoding Ethereum/EVM transaction method signatures
to identify swaps, liquidity events, and contract interactions.

All test methods are pending stubs that will be implemented in plan 03-05.
They are marked with pytest.skip() so they are visible in the test collection
output but do not fail.
"""

import pytest


class TestSwapDetection:
    """EVM swap detection via known DEX method signatures."""

    def test_uniswap_v2_detected(self):
        """Uniswap V2 swapExactTokensForTokens() -> Swap category."""
        pytest.skip("Pending implementation in plan 03-05")

    def test_uniswap_v3_detected(self):
        """Uniswap V3 exactInputSingle() method sig -> Swap category."""
        pytest.skip("Pending implementation in plan 03-05")

    def test_normal_transfer_not_swap(self):
        """Plain ETH transfer (no input data) -> Transfer category, not Swap."""
        pytest.skip("Pending implementation in plan 03-05")


class TestMethodSignatures:
    """EVM known method signature table coverage."""

    def test_known_signatures_mapped(self):
        """Signature lookup table covers at minimum: Uniswap V2/V3, transfer(), approve()."""
        pytest.skip("Pending implementation in plan 03-05")
