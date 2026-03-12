"""Test suite for EVM method signature decoding and swap detection.

Covers CLASS-05 EVM path: decoding Ethereum/EVM transaction method signatures
to identify swaps, liquidity events, and contract interactions.
Groups multi-token ERC20/NFT transfers sharing a base tx_hash into unified
operations (prevents Pitfall 3: multiple SELL classifications for one swap).
"""

import pytest
from engine.evm_decoder import EVMDecoder


@pytest.fixture
def decoder():
    return EVMDecoder()


class TestSwapDetection:
    """EVM swap detection via known DEX method signatures."""

    def test_uniswap_v2_detected(self, decoder):
        """Uniswap V2 swapExactTokensForTokens() -> is_swap=True."""
        tx = {"raw_data": {"input": "0x38ed1739000000000000000000000000"}}
        result = decoder.detect_swap(tx)
        assert result["is_swap"] is True
        assert result["method_name"] == "swapExactTokensForTokens"

    def test_uniswap_v3_detected(self, decoder):
        """Uniswap V3 exactInputSingle() method sig -> is_swap=True."""
        tx = {"raw_data": {"input": "0x414bf389000000000000000000000000"}}
        result = decoder.detect_swap(tx)
        assert result["is_swap"] is True
        assert result["method_name"] == "exactInputSingle"

    def test_normal_transfer_not_swap(self, decoder):
        """Plain ETH transfer (no input data) -> is_swap=False."""
        tx_empty = {"raw_data": {"input": ""}}
        result = decoder.detect_swap(tx_empty)
        assert result["is_swap"] is False
        assert result["method_name"] is None

        tx_0x = {"raw_data": {"input": "0x"}}
        result = decoder.detect_swap(tx_0x)
        assert result["is_swap"] is False

    def test_all_v2_signatures_detected(self, decoder):
        """All 6 Uniswap V2 method signatures are detected as swaps."""
        v2_sigs = [
            ("0x38ed1739", "swapExactTokensForTokens"),
            ("0x8803dbee", "swapTokensForExactTokens"),
            ("0x7ff36ab5", "swapExactETHForTokens"),
            ("0x4a25d94a", "swapTokensForExactETH"),
            ("0x18cbafe5", "swapExactTokensForETH"),
            ("0xfb3bdb41", "swapETHForExactTokens"),
        ]
        for sig, method in v2_sigs:
            tx = {"raw_data": {"input": sig + "aabbccdd"}}
            result = decoder.detect_swap(tx)
            assert result["is_swap"] is True, f"Expected is_swap=True for {sig}"
            assert result["method_name"] == method

    def test_all_v3_signatures_detected(self, decoder):
        """All 4 Uniswap V3 method signatures are detected as swaps."""
        v3_sigs = [
            ("0x414bf389", "exactInputSingle"),
            ("0xc04b8d59", "exactInput"),
            ("0xdb3e2198", "exactOutputSingle"),
            ("0xf28c0498", "exactOutput"),
        ]
        for sig, method in v3_sigs:
            tx = {"raw_data": {"input": sig + "aabbccdd"}}
            result = decoder.detect_swap(tx)
            assert result["is_swap"] is True, f"Expected is_swap=True for {sig}"
            assert result["method_name"] == method


class TestMethodSignatures:
    """EVM known method signature table coverage."""

    def test_known_signatures_mapped(self, decoder):
        """Signature lookup table covers all 10 Uniswap V2/V3 signatures."""
        assert len(decoder.DEX_SIGNATURES) == 10
        assert "0x38ed1739" in decoder.DEX_SIGNATURES
        assert "0x414bf389" in decoder.DEX_SIGNATURES
        assert decoder.DEX_SIGNATURES["0x38ed1739"] == "swapExactTokensForTokens"
        assert decoder.DEX_SIGNATURES["0x414bf389"] == "exactInputSingle"

    def test_lending_signatures_present(self, decoder):
        """Lending signature table (Aave V2) is populated."""
        assert len(decoder.LENDING_SIGNATURES) >= 4
        assert "0xe8eda9df" in decoder.LENDING_SIGNATURES  # deposit

    def test_lp_signatures_present(self, decoder):
        """LP signature table (Uniswap addLiquidity etc) is populated."""
        assert len(decoder.LP_SIGNATURES) >= 4
        assert "0xe8e33700" in decoder.LP_SIGNATURES  # addLiquidity

    def test_detect_defi_type_swap(self, decoder):
        """detect_defi_type returns type='swap' for DEX signatures."""
        tx = {"raw_data": {"input": "0x38ed1739aabbccdd"}}
        result = decoder.detect_defi_type(tx)
        assert result["type"] == "swap"
        assert result["method_name"] == "swapExactTokensForTokens"
        assert result["confidence"] >= 0.9

    def test_detect_defi_type_lending(self, decoder):
        """detect_defi_type returns type='lending' for Aave signatures."""
        tx = {"raw_data": {"input": "0xe8eda9dfaabbccdd"}}
        result = decoder.detect_defi_type(tx)
        assert result["type"] == "lending"

    def test_detect_defi_type_lp(self, decoder):
        """detect_defi_type returns type='lp' for LP signatures."""
        tx = {"raw_data": {"input": "0xe8e33700aabbccdd"}}
        result = decoder.detect_defi_type(tx)
        assert result["type"] == "lp"

    def test_detect_defi_type_unknown(self, decoder):
        """detect_defi_type returns type='unknown' for unrecognized signatures."""
        tx = {"raw_data": {"input": "0xdeadbeefaabbccdd"}}
        result = decoder.detect_defi_type(tx)
        assert result["type"] == "unknown"


class TestMultiTokenGrouping:
    """ERC20/NFT multi-transfer grouping by base tx_hash."""

    def test_related_logs_grouped(self, decoder):
        """tx_hash 0xabc-0, 0xabc-1, 0xabc-2 -> grouped under base 0xabc."""
        txs = [
            {"tx_hash": "0xabc-0", "amount": 100},
            {"tx_hash": "0xabc-1", "amount": 200},
            {"tx_hash": "0xabc-2", "amount": 300},
        ]
        groups = decoder.group_by_base_tx_hash(txs)
        assert "0xabc" in groups
        assert len(groups["0xabc"]) == 3

    def test_unrelated_not_grouped(self, decoder):
        """tx_hash 0xabc-0 and 0xdef-0 -> separate groups."""
        txs = [
            {"tx_hash": "0xabc-0", "amount": 100},
            {"tx_hash": "0xdef-0", "amount": 200},
        ]
        groups = decoder.group_by_base_tx_hash(txs)
        assert "0xabc" in groups
        assert "0xdef" in groups
        assert len(groups) == 2

    def test_plain_hash_no_suffix(self, decoder):
        """tx_hash without logIndex suffix is keyed as-is."""
        txs = [{"tx_hash": "0xfull", "amount": 50}]
        groups = decoder.group_by_base_tx_hash(txs)
        assert "0xfull" in groups
        assert len(groups["0xfull"]) == 1

    def test_mixed_plain_and_suffixed(self, decoder):
        """Mix of plain and suffixed hashes grouped correctly."""
        txs = [
            {"tx_hash": "0xabc-0", "amount": 100},
            {"tx_hash": "0xabc-1", "amount": 200},
            {"tx_hash": "0xdef", "amount": 300},
        ]
        groups = decoder.group_by_base_tx_hash(txs)
        assert len(groups["0xabc"]) == 2
        assert len(groups["0xdef"]) == 1
