"""
ACB (Adjusted Cost Base) Engine — Canadian average cost method.

Implements:
  - ACBPool: per-token pool state machine with Decimal precision
  - ACBEngine: full user replay with PostgreSQL persistence
  - TOKEN_SYMBOL_MAP: canonical symbol resolution for on-chain token IDs
  - resolve_token_symbol(): normalise token IDs to canonical symbols
  - normalize_timestamp(): convert NEAR nanoseconds to Unix seconds

Canada uses the "average cost" method for calculating cost basis:
  ACB_per_unit = total_cost_of_all_units / total_units_held

Key rules:
  1. Each token tracked separately by symbol
  2. ACB pooled across ALL user wallets (user is the tax entity, not the wallet)
  3. Fees on acquisitions increase ACB
  4. Fees on disposals reduce proceeds
  5. Swap fee_leg is added to buy_leg acquisition cost
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NEAR_TIMESTAMP_DIVISOR = 10 ** 9
"""NEAR block_timestamp is in nanoseconds; divide by 1e9 to get Unix seconds."""

NEAR_DIVISOR = Decimal("1000000000000000000000000")   # 1e24 yoctoNEAR
EVM_DIVISOR = Decimal("1000000000000000000")           # 1e18 wei

# ---------------------------------------------------------------------------
# Token symbol resolution
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ACBPool — per-token in-memory pool
# ---------------------------------------------------------------------------

_EIGHT_PLACES = Decimal("0.00000001")


class ACBPool:
    """Per-token ACB pool using Decimal arithmetic (Canadian average cost method).

    Thread-safe only if used from a single thread; no locking implemented.
    All monetary values are Decimal; no float arithmetic permitted.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.total_units: Decimal = Decimal("0")
        self.total_cost_cad: Decimal = Decimal("0")

    @property
    def acb_per_unit(self) -> Decimal:
        """Current ACB per unit, quantized to 8 decimal places."""
        if self.total_units <= Decimal("0"):
            return Decimal("0")
        return (self.total_cost_cad / self.total_units).quantize(
            _EIGHT_PLACES, rounding=ROUND_HALF_UP
        )

    def acquire(
        self,
        units: Decimal,
        cost_cad: Decimal,
        fee_cad: Decimal = Decimal("0"),
    ) -> dict:
        """Record an acquisition.

        Fees increase the total cost (per CRA: acquisition cost includes fees).

        Returns snapshot dict with post-acquire pool state.
        """
        total_cost = cost_cad + fee_cad
        self.total_units += units
        self.total_cost_cad += total_cost

        return {
            "event_type": "acquire",
            "units_delta": units,
            "cost_cad_delta": total_cost,
            "total_units": self.total_units,
            "total_cost_cad": self.total_cost_cad,
            "acb_per_unit": self.acb_per_unit,
        }

    def dispose(
        self,
        units: Decimal,
        proceeds_cad: Decimal,
        fee_cad: Decimal = Decimal("0"),
    ) -> dict:
        """Record a disposal.

        Fees reduce proceeds (per CRA: fees on disposals reduce proceeds).
        If units > total_units (oversell), clamp to total_units and set needs_review=True.

        Returns snapshot dict with gain/loss calculation.
        """
        needs_review = False
        if units > self.total_units:
            needs_review = True
            units = self.total_units

        acb_per_unit_at_disposal = self.acb_per_unit
        acb_used_cad = (units * acb_per_unit_at_disposal).quantize(
            _EIGHT_PLACES, rounding=ROUND_HALF_UP
        )
        net_proceeds_cad = proceeds_cad - fee_cad
        gain_loss_cad = (net_proceeds_cad - acb_used_cad).quantize(
            _EIGHT_PLACES, rounding=ROUND_HALF_UP
        )

        # Update pool
        self.total_units -= units
        self.total_cost_cad -= acb_used_cad

        # Guard against floating-point residuals that could make total_cost negative
        if self.total_units <= Decimal("0"):
            self.total_units = Decimal("0")
            self.total_cost_cad = Decimal("0")

        return {
            "event_type": "dispose",
            "units_delta": units,
            "acb_used_cad": acb_used_cad,
            "net_proceeds_cad": net_proceeds_cad,
            "gain_loss_cad": gain_loss_cad,
            "acb_per_unit": acb_per_unit_at_disposal,
            "total_units": self.total_units,
            "total_cost_cad": self.total_cost_cad,
            "needs_review": needs_review,
        }


# ---------------------------------------------------------------------------
# ACBEngine — orchestrates full replay with DB persistence
# ---------------------------------------------------------------------------

# GainsCalculator is imported lazily inside calculate_for_user() to:
#   1. Avoid circular import (gains.py imports normalize_timestamp from acb.py)
#   2. Allow test patching via: patch("engine.acb.GainsCalculator")
# The module-level name exists so tests can patch it.
GainsCalculator = None  # type: ignore  # Replaced at runtime by lazy import below


_CLASSIFY_SQL = """
SELECT tc.id, tc.category, tc.leg_type, tc.fmv_usd, tc.fmv_cad,
       tc.staking_event_id, tc.lockup_event_id, tc.parent_classification_id,
       tc.transaction_id, tc.exchange_transaction_id,
       t.block_timestamp AS t_block_timestamp, t.amount, t.fee, t.token_id, t.chain,
       et.asset, et.quantity, et.fee AS et_fee, et.timestamp AS et_timestamp,
       se.fmv_usd AS se_fmv_usd, se.fmv_cad AS se_fmv_cad, se.amount_near AS se_amount_near,
       le.fmv_usd AS le_fmv_usd, le.fmv_cad AS le_fmv_cad, le.amount_near AS le_amount_near
FROM transaction_classifications tc
LEFT JOIN transactions t ON tc.transaction_id = t.id
LEFT JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
LEFT JOIN staking_events se ON tc.staking_event_id = se.id
LEFT JOIN lockup_events le ON tc.lockup_event_id = le.id
WHERE tc.user_id = %s
  AND tc.category NOT IN ('spam', 'transfer', 'internal_transfer')
ORDER BY COALESCE(t.block_timestamp, EXTRACT(EPOCH FROM et.timestamp)::BIGINT) ASC, tc.id ASC
"""

_SNAPSHOT_UPSERT_SQL = """
INSERT INTO acb_snapshots (
    user_id, token_symbol, classification_id, block_timestamp,
    event_type, units_delta, units_after, cost_cad_delta, total_cost_cad,
    acb_per_unit_cad, proceeds_cad, gain_loss_cad,
    price_usd, price_cad, price_estimated, needs_review
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (user_id, token_symbol, classification_id)
DO UPDATE SET
    block_timestamp = EXCLUDED.block_timestamp,
    event_type = EXCLUDED.event_type,
    units_delta = EXCLUDED.units_delta,
    units_after = EXCLUDED.units_after,
    cost_cad_delta = EXCLUDED.cost_cad_delta,
    total_cost_cad = EXCLUDED.total_cost_cad,
    acb_per_unit_cad = EXCLUDED.acb_per_unit_cad,
    proceeds_cad = EXCLUDED.proceeds_cad,
    gain_loss_cad = EXCLUDED.gain_loss_cad,
    price_usd = EXCLUDED.price_usd,
    price_cad = EXCLUDED.price_cad,
    price_estimated = EXCLUDED.price_estimated,
    needs_review = EXCLUDED.needs_review,
    updated_at = NOW()
RETURNING id
"""


class ACBEngine:
    """Full-user ACB replay engine with PostgreSQL persistence.

    Usage:
        engine = ACBEngine(psycopg2_pool, price_service)
        stats = engine.calculate_for_user(user_id=1)

    Persists per-transaction ACBSnapshot rows and delegates gain/income
    ledger writes to GainsCalculator.
    """

    def __init__(self, pool, price_service):
        """
        Args:
            pool: psycopg2 connection pool (has getconn() / putconn())
            price_service: PriceService instance for FMV lookups
        """
        self._pool = pool
        self._price_service = price_service

    def calculate_for_user(self, user_id: int) -> dict:
        """Replay all classified transactions for user, writing ACB snapshots.

        Steps:
          1. Delete existing acb_snapshots, capital_gains_ledger, income_ledger for user
          2. Fetch all classified transactions chronologically
          3. Replay each event through ACBPool instances
          4. Persist ACBSnapshot after each event
          5. Record disposals in capital_gains_ledger via GainsCalculator
          6. Record income events in income_ledger via GainsCalculator

        Returns:
            dict with snapshots_written, gains_recorded, income_recorded, tokens_processed
        """
        conn = self._pool.getconn()
        try:
            # Import GainsCalculator (deferred to avoid circular import at module load).
            # Tests patch engine.acb.GainsCalculator; check module-level name first.
            import engine.acb as _acb_mod
            _GC = _acb_mod.GainsCalculator
            if _GC is None:
                from engine.gains import GainsCalculator as _GC
                _acb_mod.GainsCalculator = _GC  # cache for subsequent calls
            gains = _GC(conn)
            gains.clear_for_user(user_id)

            # Clear ACB snapshots too (full replay from scratch)
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM acb_snapshots WHERE user_id = %s", (user_id,)
                )

            # Fetch all classified transactions
            with conn.cursor() as cur:
                cur.execute(_CLASSIFY_SQL, (user_id,))
                rows = cur.fetchall()

            # Pool per token symbol (no cross-token ACB; per CRA each token is separate)
            pools: dict[str, ACBPool] = {}

            stats = {
                "snapshots_written": 0,
                "gains_recorded": 0,
                "income_recorded": 0,
                "tokens_processed": set(),
            }

            # Group rows by parent_classification_id to handle swap multi-legs
            # parent rows are processed first; child legs are handled within parent
            parent_rows = [r for r in rows if r.leg_type in ("parent", None) or r.parent_classification_id is None]
            # Build child lookup: parent_id -> list of child rows
            child_map: dict[int, list] = {}
            for r in rows:
                if r.parent_classification_id is not None:
                    pid = r.parent_classification_id
                    child_map.setdefault(pid, [])
                    child_map[pid].append(r)

            # Only process parent rows; child legs handled inline
            for row in rows:
                # Skip child legs — they're processed when parent is handled
                if row.parent_classification_id is not None:
                    continue
                self._process_row(
                    row=row,
                    child_map=child_map,
                    pools=pools,
                    conn=conn,
                    gains=gains,
                    user_id=user_id,
                    stats=stats,
                )

            # Run superficial loss detection after all disposal rows are written
            from engine.superficial import SuperficialLossDetector
            detector = SuperficialLossDetector(conn)
            superficial_losses = detector.scan_for_user(user_id)
            if superficial_losses:
                detector.apply_superficial_losses(user_id, superficial_losses)
                logger.info(
                    "Superficial loss pass complete for user_id=%s: %d losses flagged",
                    user_id, len(superficial_losses),
                )
            stats["superficial_losses"] = len(superficial_losses)

            conn.commit()
            stats["tokens_processed"] = len(stats["tokens_processed"])
            return stats

        finally:
            self._pool.putconn(conn)

    def _get_pool(self, pools: dict, symbol: str) -> ACBPool:
        if symbol not in pools:
            pools[symbol] = ACBPool(symbol)
        return pools[symbol]

    def _resolve_fmv_cad(
        self,
        row,
        unix_ts: int,
        symbol: str,
    ) -> tuple[Optional[Decimal], Optional[Decimal], bool]:
        """Resolve FMV in CAD for a transaction row.

        Priority:
          1. row.fmv_cad (pre-captured by classifier)
          2. se_fmv_cad / le_fmv_cad (staking/lockup events)
          3. price_service.get_price_cad_at_timestamp()

        Returns (price_usd, price_cad, is_estimated)
        """
        # Pre-captured FMV from classifier
        if row.fmv_cad is not None:
            fmv_cad = Decimal(str(row.fmv_cad))
            fmv_usd = Decimal(str(row.fmv_usd)) if row.fmv_usd is not None else None
            return fmv_usd, fmv_cad, False

        # Staking event FMV
        if row.staking_event_id is not None and row.se_fmv_cad is not None:
            return (
                Decimal(str(row.se_fmv_usd)) if row.se_fmv_usd is not None else None,
                Decimal(str(row.se_fmv_cad)),
                False,
            )

        # Lockup event FMV
        if row.lockup_event_id is not None and row.le_fmv_cad is not None:
            return (
                Decimal(str(row.le_fmv_usd)) if row.le_fmv_usd is not None else None,
                Decimal(str(row.le_fmv_cad)),
                False,
            )

        # Fall back to price service
        coin_id = symbol.lower()
        try:
            price_cad, is_estimated = self._price_service.get_price_cad_at_timestamp(
                coin_id, unix_ts
            )
            return None, price_cad, is_estimated
        except Exception as exc:
            logger.warning("FMV lookup failed for %s at %s: %s", symbol, unix_ts, exc)
            return None, None, True

    def _process_row(
        self,
        row,
        child_map: dict,
        pools: dict,
        conn,
        gains,
        user_id: int,
        stats: dict,
    ) -> None:
        """Process a single parent classification row."""
        category = row.category
        chain = row.chain or "near"

        # Determine block_timestamp (raw) and unix_ts (seconds)
        raw_ts = row.t_block_timestamp
        if raw_ts is None and row.et_timestamp is not None:
            # Exchange tx: timestamp is a datetime object
            try:
                raw_ts = int(row.et_timestamp.timestamp())
            except Exception:
                raw_ts = 0
            unix_ts = raw_ts
        else:
            unix_ts = normalize_timestamp(raw_ts or 0, chain)

        # Resolve token symbol
        symbol = resolve_token_symbol(row.token_id, chain, asset=row.asset)
        stats["tokens_processed"].add(symbol)

        pool = self._get_pool(pools, symbol)

        # Resolve units
        if row.exchange_transaction_id is not None and row.quantity is not None:
            # Exchange tx: quantity is human-readable Decimal
            units = Decimal(str(row.quantity))
        elif row.amount is not None:
            units = to_human_units(int(row.amount), chain)
        else:
            units = Decimal("0")

        # Resolve fees
        if row.exchange_transaction_id is not None and row.et_fee is not None:
            fee_human = Decimal(str(row.et_fee))
        elif row.fee is not None:
            fee_human = to_human_units(int(row.fee), chain)
        else:
            fee_human = Decimal("0")

        # ---------------------------------------------------------------
        # Route by category
        # ---------------------------------------------------------------

        if category == "income":
            self._handle_income(
                row=row,
                pool=pool,
                symbol=symbol,
                units=units,
                unix_ts=unix_ts,
                raw_ts=raw_ts or 0,
                chain=chain,
                conn=conn,
                gains=gains,
                user_id=user_id,
                stats=stats,
            )

        elif category in ("capital_gain", "capital_loss"):
            children = child_map.get(row.id, [])
            sell_leg = next((c for c in children if c.leg_type == "sell_leg"), None)
            buy_leg = next((c for c in children if c.leg_type == "buy_leg"), None)
            fee_leg = next((c for c in children if c.leg_type == "fee_leg"), None)

            if sell_leg and buy_leg:
                # Multi-leg swap
                self._handle_swap(
                    parent_row=row,
                    sell_leg=sell_leg,
                    buy_leg=buy_leg,
                    fee_leg=fee_leg,
                    pools=pools,
                    conn=conn,
                    gains=gains,
                    user_id=user_id,
                    unix_ts=unix_ts,
                    raw_ts=raw_ts or 0,
                    chain=chain,
                    stats=stats,
                )
            else:
                # Simple disposal
                self._handle_disposal(
                    row=row,
                    pool=pool,
                    symbol=symbol,
                    units=units,
                    fee_human=fee_human,
                    unix_ts=unix_ts,
                    raw_ts=raw_ts or 0,
                    chain=chain,
                    conn=conn,
                    gains=gains,
                    user_id=user_id,
                    stats=stats,
                )

        elif category == "fee":
            # Gas fee = disposal at zero proceeds
            self._handle_disposal(
                row=row,
                pool=pool,
                symbol=symbol,
                units=fee_human if fee_human > 0 else units,
                fee_human=Decimal("0"),
                unix_ts=unix_ts,
                raw_ts=raw_ts or 0,
                chain=chain,
                conn=conn,
                gains=gains,
                user_id=user_id,
                stats=stats,
                proceeds_override=Decimal("0"),
            )

        # 'spam', 'transfer', 'internal_transfer' are filtered in SQL; skip others
        else:
            logger.debug("Skipping category=%s classification_id=%s", category, row.id)

    def _handle_income(
        self, row, pool, symbol, units, unix_ts, raw_ts, chain,
        conn, gains, user_id, stats,
    ):
        """Handle income events: staking reward, lockup vest, airdrop."""
        # FMV resolution: prefer staking/lockup event FMV; fallback to price service
        price_usd: Optional[Decimal] = None
        price_cad: Optional[Decimal] = None
        is_estimated = True

        if row.staking_event_id is not None and row.se_fmv_cad is not None:
            units = Decimal(str(row.se_amount_near)) if row.se_amount_near is not None else units
            price_cad = Decimal(str(row.se_fmv_cad))
            price_usd = Decimal(str(row.se_fmv_usd)) if row.se_fmv_usd is not None else None
            is_estimated = False
            source_type = "staking"
            staking_event_id = row.staking_event_id
            lockup_event_id = None
        elif row.lockup_event_id is not None and row.le_fmv_cad is not None:
            units = Decimal(str(row.le_amount_near)) if row.le_amount_near is not None else units
            price_cad = Decimal(str(row.le_fmv_cad))
            price_usd = Decimal(str(row.le_fmv_usd)) if row.le_fmv_usd is not None else None
            is_estimated = False
            source_type = "vesting"
            staking_event_id = None
            lockup_event_id = row.lockup_event_id
        else:
            # Airdrop or generic income — get price from service
            price_usd, price_cad, is_estimated = self._resolve_fmv_cad(row, unix_ts, symbol)
            source_type = "airdrop"
            staking_event_id = None
            lockup_event_id = None

        fmv_cad = price_cad or Decimal("0")
        cost_cad = units * fmv_cad
        snap = pool.acquire(units, cost_cad)

        snap_id = self._persist_snapshot(
            conn=conn,
            user_id=user_id,
            symbol=symbol,
            classification_id=row.id,
            block_timestamp=raw_ts,
            snap=snap,
            proceeds_cad=None,
            gain_loss_cad=None,
            price_usd=price_usd,
            price_cad=price_cad,
            is_estimated=is_estimated,
        )

        stats["snapshots_written"] += 1

        # Record income ledger entry
        gains.record_income(
            user_id=user_id,
            source_type=source_type,
            token_symbol=symbol,
            block_timestamp=unix_ts,
            chain=chain,
            units_received=units,
            fmv_usd=price_usd or Decimal("0"),
            fmv_cad=fmv_cad,
            staking_event_id=staking_event_id,
            lockup_event_id=lockup_event_id,
            classification_id=row.id,
        )
        stats["income_recorded"] += 1

    def _handle_disposal(
        self, row, pool, symbol, units, fee_human, unix_ts, raw_ts, chain,
        conn, gains, user_id, stats, proceeds_override=None,
    ):
        """Handle a simple disposal (sell, swap sell-leg, fee disposal)."""
        price_usd, price_cad, is_estimated = self._resolve_fmv_cad(row, unix_ts, symbol)

        if proceeds_override is not None:
            proceeds_cad = proceeds_override
        else:
            fmv_per_unit = price_cad or Decimal("0")
            proceeds_cad = units * fmv_per_unit

        # Fee in CAD
        fee_cad = fee_human * (price_cad or Decimal("0"))

        snap = pool.dispose(units, proceeds_cad, fee_cad=fee_cad)

        snap_id = self._persist_snapshot(
            conn=conn,
            user_id=user_id,
            symbol=symbol,
            classification_id=row.id,
            block_timestamp=raw_ts,
            snap=snap,
            proceeds_cad=snap["net_proceeds_cad"],
            gain_loss_cad=snap["gain_loss_cad"],
            price_usd=price_usd,
            price_cad=price_cad,
            is_estimated=is_estimated,
            needs_review=snap.get("needs_review", False),
        )

        stats["snapshots_written"] += 1

        if snap_id is not None:
            gains.record_disposal(
                user_id=user_id,
                acb_snapshot_id=snap_id,
                token_symbol=symbol,
                block_timestamp=unix_ts,
                chain=chain,
                units_disposed=snap["units_delta"],
                proceeds_cad=snap["net_proceeds_cad"],
                acb_used_cad=snap["acb_used_cad"],
                fees_cad=fee_cad,
                gain_loss_cad=snap["gain_loss_cad"],
                needs_review=snap.get("needs_review", False),
            )
            stats["gains_recorded"] += 1

    def _handle_swap(
        self, parent_row, sell_leg, buy_leg, fee_leg,
        pools, conn, gains, user_id, unix_ts, raw_ts, chain, stats,
    ):
        """Handle a multi-leg swap: dispose sell token, acquire buy token.

        Fee leg amount is added to buy leg acquisition cost (CRA treatment).
        """
        # --- Sell leg ---
        sell_symbol = resolve_token_symbol(
            sell_leg.token_id, chain, asset=sell_leg.asset
        )
        sell_pool = self._get_pool(pools, sell_symbol)

        sell_units: Decimal
        if sell_leg.exchange_transaction_id is not None and sell_leg.quantity is not None:
            sell_units = Decimal(str(sell_leg.quantity))
        elif sell_leg.amount is not None:
            sell_units = to_human_units(int(sell_leg.amount), chain)
        else:
            sell_units = Decimal("0")

        _, sell_price_cad, sell_is_est = self._resolve_fmv_cad(sell_leg, unix_ts, sell_symbol)
        sell_proceeds_cad = sell_units * (sell_price_cad or Decimal("0"))

        sell_snap = sell_pool.dispose(sell_units, sell_proceeds_cad)
        sell_snap_id = self._persist_snapshot(
            conn=conn,
            user_id=user_id,
            symbol=sell_symbol,
            classification_id=sell_leg.id,
            block_timestamp=raw_ts,
            snap=sell_snap,
            proceeds_cad=sell_snap["net_proceeds_cad"],
            gain_loss_cad=sell_snap["gain_loss_cad"],
            price_usd=None,
            price_cad=sell_price_cad,
            is_estimated=sell_is_est,
            needs_review=sell_snap.get("needs_review", False),
        )
        stats["snapshots_written"] += 1

        if sell_snap_id is not None:
            gains.record_disposal(
                user_id=user_id,
                acb_snapshot_id=sell_snap_id,
                token_symbol=sell_symbol,
                block_timestamp=unix_ts,
                chain=chain,
                units_disposed=sell_snap["units_delta"],
                proceeds_cad=sell_snap["net_proceeds_cad"],
                acb_used_cad=sell_snap["acb_used_cad"],
                fees_cad=Decimal("0"),
                gain_loss_cad=sell_snap["gain_loss_cad"],
                needs_review=sell_snap.get("needs_review", False),
            )
            stats["gains_recorded"] += 1

        # --- Fee leg (added to buy ACB) ---
        fee_cad = Decimal("0")
        if fee_leg is not None:
            fee_symbol = resolve_token_symbol(
                fee_leg.token_id, chain, asset=fee_leg.asset
            )
            _, fee_price_cad, _ = self._resolve_fmv_cad(fee_leg, unix_ts, fee_symbol)
            fee_units: Decimal
            if fee_leg.exchange_transaction_id is not None and fee_leg.quantity is not None:
                fee_units = Decimal(str(fee_leg.quantity))
            elif fee_leg.amount is not None:
                fee_units = to_human_units(int(fee_leg.amount), chain)
            else:
                fee_units = Decimal("0")
            fee_cad = fee_units * (fee_price_cad or Decimal("0"))

        # --- Buy leg ---
        buy_symbol = resolve_token_symbol(
            buy_leg.token_id, chain, asset=buy_leg.asset
        )
        buy_pool = self._get_pool(pools, buy_symbol)

        if buy_leg.exchange_transaction_id is not None and buy_leg.quantity is not None:
            buy_units = Decimal(str(buy_leg.quantity))
        elif buy_leg.amount is not None:
            buy_units = to_human_units(int(buy_leg.amount), chain)
        else:
            buy_units = Decimal("0")

        _, buy_price_cad, buy_is_est = self._resolve_fmv_cad(buy_leg, unix_ts, buy_symbol)
        buy_cost_cad = buy_units * (buy_price_cad or Decimal("0"))

        # Fee leg adds to buy ACB
        buy_snap = buy_pool.acquire(buy_units, buy_cost_cad, fee_cad=fee_cad)
        self._persist_snapshot(
            conn=conn,
            user_id=user_id,
            symbol=buy_symbol,
            classification_id=buy_leg.id,
            block_timestamp=raw_ts,
            snap=buy_snap,
            proceeds_cad=None,
            gain_loss_cad=None,
            price_usd=None,
            price_cad=buy_price_cad,
            is_estimated=buy_is_est,
        )
        stats["snapshots_written"] += 1
        stats["tokens_processed"].add(sell_symbol)
        stats["tokens_processed"].add(buy_symbol)

    def _persist_snapshot(
        self,
        conn,
        user_id: int,
        symbol: str,
        classification_id: int,
        block_timestamp: int,
        snap: dict,
        proceeds_cad: Optional[Decimal],
        gain_loss_cad: Optional[Decimal],
        price_usd: Optional[Decimal],
        price_cad: Optional[Decimal],
        is_estimated: bool = False,
        needs_review: bool = False,
    ) -> Optional[int]:
        """INSERT acb_snapshots row (ON CONFLICT DO UPDATE). Returns snapshot id."""
        event_type = snap["event_type"]
        units_delta = snap["units_delta"]
        units_after = snap["total_units"]
        cost_cad_delta = snap.get("cost_cad_delta") or snap.get("acb_used_cad") or Decimal("0")
        total_cost_cad = snap["total_cost_cad"]
        acb_per_unit_cad = snap["acb_per_unit"]

        try:
            with conn.cursor() as cur:
                cur.execute(
                    _SNAPSHOT_UPSERT_SQL,
                    (
                        user_id,
                        symbol,
                        classification_id,
                        block_timestamp,
                        event_type,
                        units_delta,
                        units_after,
                        cost_cad_delta,
                        total_cost_cad,
                        acb_per_unit_cad,
                        proceeds_cad,
                        gain_loss_cad,
                        price_usd,
                        price_cad,
                        is_estimated,
                        needs_review,
                    ),
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as exc:
            logger.error(
                "Failed to persist snapshot for user=%s symbol=%s class=%s: %s",
                user_id, symbol, classification_id, exc,
            )
            return None
