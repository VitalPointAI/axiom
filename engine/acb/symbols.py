"""
Token symbol resolution and chain-specific utilities.

Contains:
  - TOKEN_SYMBOL_MAP: canonical symbol resolution for on-chain token IDs
  - resolve_token_symbol(): normalise token IDs to canonical symbols
  - normalize_timestamp(): convert NEAR nanoseconds to Unix seconds
  - to_human_units(): convert raw on-chain amounts to human-readable Decimals
"""

from decimal import Decimal
from typing import Optional

NEAR_TIMESTAMP_DIVISOR = 10 ** 9
"""NEAR block_timestamp is in nanoseconds; divide by 1e9 to get Unix seconds."""

NEAR_DIVISOR = Decimal("1000000000000000000000000")   # 1e24 yoctoNEAR
EVM_DIVISOR = Decimal("1000000000000000000")           # 1e18 wei

TOKEN_SYMBOL_MAP: dict[str, str] = {
    # NEAR native / wrapped
    "near": "NEAR",
    "wrap.near": "NEAR",
    # Common NEAR fungible tokens
    "token.sweat": "SWEAT",
    "meta-token.near": "META",
    "aurora": "AURORA",
    "ref.finance": "REF",
    # Common EVM tokens (lowercase checksumless addresses)
    # USDC
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",  # ETH
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": "USDC",  # Polygon
    "0x7f5c764cbc14f9669b88837ca1490cca17c31607": "USDC",  # Optimism
    # USDT
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",  # ETH
    "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": "USDT",  # Polygon
    "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58": "USDT",  # Optimism
    # WETH
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",  # ETH
    "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619": "WETH",  # Polygon
    "0x4200000000000000000000000000000000000006": "WETH",  # Optimism
    # WBTC
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",  # ETH
}


def resolve_token_symbol(
    token_id: Optional[str],
    chain: str,
    asset: Optional[str] = None,
) -> str:
    """Resolve a token identifier to a canonical uppercase symbol.

    Priority:
      1. If asset is not None (exchange transaction): return asset.upper()
      2. If token_id in TOKEN_SYMBOL_MAP: return mapped symbol
      3. If token_id is None and chain == 'near': return 'NEAR'
      4. If token_id is None and chain in EVM chains: return chain-native token
      5. Otherwise: return token_id or 'UNKNOWN'
    """
    if asset is not None:
        return asset.upper()
    if token_id is not None:
        lower = token_id.lower()
        if lower in TOKEN_SYMBOL_MAP:
            return TOKEN_SYMBOL_MAP[lower]
        return token_id.upper()
    # token_id is None — infer from chain
    if chain == "near":
        return "NEAR"
    if chain in ("ethereum", "polygon", "optimism", "cronos"):
        return "ETH"
    return "UNKNOWN"


def normalize_timestamp(block_timestamp: int, chain: str) -> int:
    """Convert chain-specific block_timestamp to Unix seconds.

    NEAR: nanoseconds -> divide by 1e9
    EVM: already seconds
    """
    if chain == "near":
        return block_timestamp // NEAR_TIMESTAMP_DIVISOR
    return block_timestamp


def to_human_units(amount_raw: int, chain: str) -> Decimal:
    """Convert raw on-chain amount to human-readable Decimal.

    NEAR: yoctoNEAR (1e24) -> NEAR
    EVM:  wei (1e18) -> ETH/token
    """
    if amount_raw is None:
        return Decimal("0")
    if chain == "near":
        return Decimal(str(amount_raw)) / NEAR_DIVISOR
    return Decimal(str(amount_raw)) / EVM_DIVISOR
