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


# ---------------------------------------------------------------------------
# Helpers for constructing ABI-encoded exactInput calldata
# ---------------------------------------------------------------------------

def _build_v3_path(token_addrs: list[str], fees: list[int] | None = None) -> bytes:
    """Build Uniswap V3 path bytes: [addr(20)][fee(3)][addr(20)]...

    Args:
        token_addrs: List of hex addresses (with or without 0x prefix).
        fees: Optional list of fee values (len = len(token_addrs) - 1).
              Defaults to 3000 (0.3%) for each hop.
    """
    if fees is None:
        fees = [3000] * (len(token_addrs) - 1)

    result = b""
    for i, addr in enumerate(token_addrs):
        addr_bytes = bytes.fromhex(addr.removeprefix("0x").zfill(40))
        result += addr_bytes
        if i < len(fees):
            fee_val = fees[i]
            result += fee_val.to_bytes(3, "big")
    return result


def _build_exact_input_calldata(path_bytes: bytes) -> str:
    """ABI-encode exactInput(params) where params.path = path_bytes.

    exactInput ABI: (bytes path, address recipient, uint256 deadline,
                     uint256 amountIn, uint256 amountOutMinimum)
    The tuple is ABI-encoded; path is a dynamic bytes at offset 0.

    Layout after selector (4 bytes):
      [0:32]   offset to path bytes within the tuple = 0x20 (32 = start of first dynamic param)
      [32:64]  recipient (address, padded to 32 bytes)
      [64:96]  deadline
      [96:128] amountIn
      [128:160] amountOutMinimum
      [160:192] path length (uint256)
      [192:...] path data (padded to 32-byte boundary)
    """
    # Selector for exactInput: 0xc04b8d59
    selector = bytes.fromhex("c04b8d59")

    # The tuple ABI encoding for (bytes, address, uint256, uint256, uint256)
    # In a tuple, the first field (bytes) is dynamic, so the first 32 bytes
    # is an offset pointing to the bytes data within the tuple.
    # Offset = position where dynamic data starts = 5 * 32 = 160 bytes from start of tuple
    offset_to_path = (5 * 32).to_bytes(32, "big")

    recipient = (0xDEADBEEF).to_bytes(32, "big")
    deadline = (9999999999).to_bytes(32, "big")
    amount_in = (1000000000000000000).to_bytes(32, "big")
    amount_out_min = (900000000000000000).to_bytes(32, "big")

    path_len = len(path_bytes).to_bytes(32, "big")
    # Pad path to 32-byte boundary
    pad = (32 - len(path_bytes) % 32) % 32
    path_padded = path_bytes + b"\x00" * pad

    calldata = selector + offset_to_path + recipient + deadline + amount_in + amount_out_min + path_len + path_padded
    return "0x" + calldata.hex()


# ---------------------------------------------------------------------------
# Multi-hop path decoding tests
# ---------------------------------------------------------------------------

class TestMultiHopPathDecoding:
    """Uniswap V3 exactInput multi-hop path decoding."""

    TOKEN_A = "0x" + "aa" * 20
    TOKEN_B = "0x" + "bb" * 20
    TOKEN_C = "0x" + "cc" * 20
    TOKEN_D = "0x" + "dd" * 20

    def test_multi_hop_2_token_path(self, decoder):
        """decode_multi_hop_path with 2 tokens returns [tokenA, tokenB]."""
        path = _build_v3_path([self.TOKEN_A, self.TOKEN_B])
        result = decoder.decode_multi_hop_path(path)
        assert len(result) == 2
        assert result[0].lower() == self.TOKEN_A.lower()
        assert result[1].lower() == self.TOKEN_B.lower()

    def test_multi_hop_3_token_path(self, decoder):
        """decode_multi_hop_path with 3 tokens (A->B->C) returns all 3 addresses."""
        path = _build_v3_path([self.TOKEN_A, self.TOKEN_B, self.TOKEN_C])
        result = decoder.decode_multi_hop_path(path)
        assert len(result) == 3
        assert result[0].lower() == self.TOKEN_A.lower()
        assert result[1].lower() == self.TOKEN_B.lower()
        assert result[2].lower() == self.TOKEN_C.lower()

    def test_multi_hop_4_token_path(self, decoder):
        """decode_multi_hop_path with 4 tokens returns all 4 addresses."""
        path = _build_v3_path([self.TOKEN_A, self.TOKEN_B, self.TOKEN_C, self.TOKEN_D])
        result = decoder.decode_multi_hop_path(path)
        assert len(result) == 4
        assert result[0].lower() == self.TOKEN_A.lower()
        assert result[3].lower() == self.TOKEN_D.lower()

    def test_multi_hop_detect_swap_hop_count_standard(self, decoder):
        """detect_swap returns hop_count=1 for standard non-exactInput swap."""
        tx = {"raw_data": {"input": "0x38ed1739" + "00" * 100}}
        result = decoder.detect_swap(tx)
        assert result["is_swap"] is True
        assert result["hop_count"] == 1
        assert result["token_path"] == []

    def test_multi_hop_detect_swap_3_token_path(self, decoder):
        """detect_swap on exactInput with 3-token path returns hop_count=2 and token_path."""
        path = _build_v3_path([self.TOKEN_A, self.TOKEN_B, self.TOKEN_C])
        calldata = _build_exact_input_calldata(path)
        tx = {"raw_data": {"input": calldata}}
        result = decoder.detect_swap(tx)
        assert result["is_swap"] is True
        assert result["hop_count"] == 2
        assert len(result["token_path"]) == 3
        assert result["token_path"][0].lower() == self.TOKEN_A.lower()
        assert result["token_path"][2].lower() == self.TOKEN_C.lower()

    def test_multi_hop_non_exact_input_hop_count_1(self, decoder):
        """detect_swap with non-exactInput selector returns hop_count=1 (backward compat)."""
        tx = {"raw_data": {"input": "0x414bf389" + "aa" * 100}}
        result = decoder.detect_swap(tx)
        assert result["is_swap"] is True
        assert result["hop_count"] == 1

    def test_multi_hop_malformed_path_returns_empty(self, decoder):
        """decode_multi_hop_path with short input returns empty list (no crash)."""
        result = decoder.decode_multi_hop_path(b"")
        assert result == []

        result = decoder.decode_multi_hop_path(b"\x00" * 10)
        assert result == []
