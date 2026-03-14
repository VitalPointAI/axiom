"""EVM transaction decoder for DeFi protocol detection.

Detects DEX swaps, LP operations, and lending interactions by method signature
and event log patterns. Groups related ERC20/NFT transfers sharing a base tx_hash
into unified operations (prevents Pitfall 3: multiple SELL classifications for
one swap — a Uniswap swap generates multiple Transfer events that share a parent
tx_hash with logIndex suffixes like hash-0, hash-1, hash-2).

Usage::

    decoder = EVMDecoder()
    result = decoder.detect_swap(tx)
    # {'is_swap': True, 'method_name': 'swapExactTokensForTokens', 'dex_type': 'uniswap_v2'}

    groups = decoder.group_by_base_tx_hash(transactions)
    # {'0xabc': [tx0, tx1, tx2]}  # all share parent 0xabc
"""

from typing import Optional

try:
    from eth_utils import to_checksum_address
    _HAS_ETH_UTILS = True
except ImportError:
    _HAS_ETH_UTILS = False


def _bytes_to_hex_address(addr_bytes: bytes) -> str:
    """Convert 20 raw bytes to a lowercase hex Ethereum address string."""
    hex_addr = "0x" + addr_bytes.hex()
    if _HAS_ETH_UTILS:
        try:
            return to_checksum_address(hex_addr)
        except Exception:
            pass
    return hex_addr.lower()


class EVMDecoder:
    """Decodes EVM transactions to identify DeFi interaction types.

    Uses 4-byte method selector matching against known protocol signatures.
    No DB access required — purely data-driven.
    """

    # Uniswap V2 router method signatures (4-byte selectors, lowercase hex)
    # Source: Uniswap V2 Router02 ABI
    DEX_SIGNATURES: dict[str, str] = {
        "0x38ed1739": "swapExactTokensForTokens",
        "0x8803dbee": "swapTokensForExactTokens",
        "0x7ff36ab5": "swapExactETHForTokens",
        "0x4a25d94a": "swapTokensForExactETH",
        "0x18cbafe5": "swapExactTokensForETH",
        "0xfb3bdb41": "swapETHForExactTokens",
        # Uniswap V3 SwapRouter
        "0x414bf389": "exactInputSingle",
        "0xc04b8d59": "exactInput",
        "0xdb3e2198": "exactOutputSingle",
        "0xf28c0498": "exactOutput",
    }

    # Aave V2 lending pool method signatures
    LENDING_SIGNATURES: dict[str, str] = {
        "0xe8eda9df": "deposit",       # Aave V2 deposit
        "0x69328dec": "withdraw",      # Aave V2 withdraw
        "0xa415bcad": "borrow",        # Aave V2 borrow
        "0x573ade81": "repay",         # Aave V2 repay
        "0xd65dc7a1": "flashLoan",     # Aave V2 flashLoan
    }

    # Uniswap V2/V3 liquidity provision method signatures
    LP_SIGNATURES: dict[str, str] = {
        "0xe8e33700": "addLiquidity",
        "0xf305d719": "addLiquidityETH",
        "0xbaa2abde": "removeLiquidity",
        "0x02751cec": "removeLiquidityETH",
        "0xaf2979eb": "removeLiquidityETHSupportingFeeOnTransferTokens",
        "0x2195995c": "removeLiquidityWithPermit",
    }

    def decode_multi_hop_path(self, path_bytes: bytes) -> list:
        """Decode a Uniswap V3 packed path into an ordered list of token addresses.

        Uniswap V3 path encoding:
            [token_addr (20 bytes)][fee (3 bytes)][token_addr (20 bytes)] ...

        Args:
            path_bytes: Raw bytes from the ``path`` parameter of an exactInput call.

        Returns:
            List of checksummed (or lowercase) hex addresses in hop order.
            Returns an empty list when input is too short or malformed.
        """
        if len(path_bytes) < 20:
            return []

        addresses: list[str] = []

        # First token is at offset 0
        addresses.append(_bytes_to_hex_address(path_bytes[0:20]))

        # Each subsequent token is at: 20 + N * 23  (20 addr + 3 fee per hop)
        offset = 20
        while offset + 23 <= len(path_bytes):
            # Skip 3-byte fee, then read next 20-byte address
            addr_start = offset + 3
            addr_end = addr_start + 20
            addresses.append(_bytes_to_hex_address(path_bytes[addr_start:addr_end]))
            offset += 23

        return addresses

    def _decode_exact_input_path(self, input_hex: str) -> list:
        """Decode the ``path`` parameter from an exactInput calldata hex string.

        ABI layout after the 4-byte selector for exactInput
        ``(bytes path, address recipient, uint256 deadline,
          uint256 amountIn, uint256 amountOutMinimum)``:

          [0:32]    offset-to-path within the tuple (big-endian uint256)
          [32:64]   recipient (padded address)
          [64:96]   deadline
          [96:128]  amountIn
          [128:160] amountOutMinimum
          [offset:offset+32]  path byte-length (uint256)
          [offset+32:...]     path bytes

        Returns decoded token address list, or [] on any decoding failure.
        """
        try:
            # Strip selector (first 8 hex chars after '0x')
            normalized = input_hex.lower()
            if not normalized.startswith("0x"):
                normalized = "0x" + normalized
            calldata = bytes.fromhex(normalized[2:])  # full calldata including selector
            if len(calldata) < 4:
                return []
            params = calldata[4:]  # drop 4-byte selector

            if len(params) < 32:
                return []

            # First 32 bytes: offset to the path data within the tuple
            path_offset = int.from_bytes(params[0:32], "big")

            # At path_offset: 32 bytes for the byte-length of path
            if path_offset + 32 > len(params):
                return []
            path_len = int.from_bytes(params[path_offset:path_offset + 32], "big")

            path_start = path_offset + 32
            path_end = path_start + path_len
            if path_end > len(params):
                return []
            path_bytes = params[path_start:path_end]

            return self.decode_multi_hop_path(path_bytes)
        except Exception:
            return []

    def _extract_selector(self, input_hex: str) -> Optional[str]:
        """Extract the 4-byte method selector from an input hex string.

        Args:
            input_hex: The 'input' field of an EVM transaction (hex string).
                       Empty string or '0x' means plain ETH transfer.

        Returns:
            Lowercase selector like '0x38ed1739', or None if no selector.
        """
        if not input_hex or input_hex in ("0x", "0X", ""):
            return None
        # Normalize to lowercase and ensure 0x prefix
        normalized = input_hex.lower()
        if not normalized.startswith("0x"):
            normalized = "0x" + normalized
        # Need at least 0x + 8 hex chars = 10 chars total
        if len(normalized) < 10:
            return None
        return normalized[:10]

    def detect_swap(self, tx: dict) -> dict:
        """Detect if an EVM transaction is a DEX swap.

        Reads the first 4 bytes of the input calldata and matches against
        known Uniswap V2/V3 method selectors.

        For Uniswap V3 exactInput transactions, additionally decodes the packed
        multi-hop path to determine the number of swaps and the token address
        sequence.

        Args:
            tx: dict with 'raw_data' dict containing 'input' field (hex string).
                Example: {'raw_data': {'input': '0x38ed1739...'}}

        Returns:
            dict with keys:
                - is_swap (bool): True if a known swap selector was matched
                - method_name (str|None): human-readable method name, or None
                - dex_type (str|None): 'uniswap_v2', 'uniswap_v3', or None
                - hop_count (int): number of swap hops (1 for standard swaps,
                  N-1 for N-token exactInput paths). Always 1 for non-swap.
                - token_path (list[str]): ordered token addresses for multi-hop
                  exactInput swaps; empty list for standard swaps or on failure.
        """
        raw_data = tx.get("raw_data") or {}
        input_hex = raw_data.get("input", "")
        selector = self._extract_selector(input_hex)

        if selector is None:
            return {
                "is_swap": False,
                "method_name": None,
                "dex_type": None,
                "hop_count": 1,
                "token_path": [],
            }

        if selector in self.DEX_SIGNATURES:
            method_name = self.DEX_SIGNATURES[selector]
            # V3 methods are the last 4 keys (exactInputSingle, exactInput,
            # exactOutputSingle, exactOutput)
            v3_methods = {"exactInputSingle", "exactInput", "exactOutputSingle", "exactOutput"}
            dex_type = "uniswap_v3" if method_name in v3_methods else "uniswap_v2"

            # Multi-hop path decoding for exactInput only
            token_path: list[str] = []
            hop_count = 1
            if method_name == "exactInput":
                token_path = self._decode_exact_input_path(input_hex)
                if len(token_path) >= 2:
                    hop_count = len(token_path) - 1

            return {
                "is_swap": True,
                "method_name": method_name,
                "dex_type": dex_type,
                "hop_count": hop_count,
                "token_path": token_path,
            }

        return {
            "is_swap": False,
            "method_name": None,
            "dex_type": None,
            "hop_count": 1,
            "token_path": [],
        }

    def detect_defi_type(self, tx: dict) -> dict:
        """Detect DeFi interaction type (swap, lending, LP, or unknown).

        Checks DEX_SIGNATURES first, then LENDING_SIGNATURES, then LP_SIGNATURES.

        Args:
            tx: dict with 'raw_data' dict containing 'input' field.

        Returns:
            dict with keys:
                - type (str): 'swap' | 'lending' | 'lp' | 'unknown'
                - method_name (str|None): human-readable method name
                - confidence (float): 0.0–1.0
        """
        raw_data = tx.get("raw_data") or {}
        input_hex = raw_data.get("input", "")
        selector = self._extract_selector(input_hex)

        if selector is None:
            return {"type": "unknown", "method_name": None, "confidence": 0.0}

        if selector in self.DEX_SIGNATURES:
            return {
                "type": "swap",
                "method_name": self.DEX_SIGNATURES[selector],
                "confidence": 0.95,
            }

        if selector in self.LENDING_SIGNATURES:
            return {
                "type": "lending",
                "method_name": self.LENDING_SIGNATURES[selector],
                "confidence": 0.90,
            }

        if selector in self.LP_SIGNATURES:
            return {
                "type": "lp",
                "method_name": self.LP_SIGNATURES[selector],
                "confidence": 0.90,
            }

        return {"type": "unknown", "method_name": None, "confidence": 0.0}

    def group_by_base_tx_hash(self, transactions: list) -> dict:
        """Group EVM transactions by base tx_hash (strips -logIndex suffix).

        ERC20/NFT token transfers in Phase 2 use tx_hash = hash-logIndex
        (e.g. '0xabc123...-0', '0xabc123...-1') because multiple Transfer
        events share the same parent transaction hash. A single Uniswap swap
        generates at minimum two Transfer events (token out + token in).

        Grouping by base hash allows the classifier to treat a set of related
        transfers as one swap rather than classifying each leg independently
        (which would incorrectly generate multiple SELL events per swap).

        Args:
            transactions: list of dicts, each containing a 'tx_hash' key.

        Returns:
            dict mapping base_tx_hash -> list of transaction dicts.
            Example: {'0xabc': [tx_leg_0, tx_leg_1, tx_leg_2]}
        """
        groups: dict[str, list] = {}
        for tx in transactions:
            tx_hash = tx.get("tx_hash", "")
            # Strip logIndex suffix: '0xabc-2' -> '0xabc', '0xfull' -> '0xfull'
            base_hash = tx_hash.split("-")[0] if "-" in tx_hash else tx_hash
            if base_hash not in groups:
                groups[base_hash] = []
            groups[base_hash].append(tx)
        return groups
