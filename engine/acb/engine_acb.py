"""
ACBEngine — full user ACB replay with PostgreSQL persistence.

Usage:
    engine = ACBEngine(psycopg2_pool, price_service)
    stats = engine.calculate_for_user(user_id=1)

Persists per-transaction ACBSnapshot rows and delegates gain/income
ledger writes to GainsCalculator.
"""

from decimal import Decimal
from typing import Optional
import logging

from engine.acb.pool import ACBPool, check_acb_pool_invariants
from engine.acb.symbols import resolve_token_symbol, normalize_timestamp, to_human_units
from db.audit import write_audit

logger = logging.getLogger(__name__)

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
       et.asset, et.quantity, et.fee AS et_fee, et.tx_date AS et_timestamp,
       se.fmv_usd AS se_fmv_usd, se.fmv_cad AS se_fmv_cad, se.amount_near AS se_amount_near,
       le.fmv_usd AS le_fmv_usd, le.fmv_cad AS le_fmv_cad, le.amount_near AS le_amount_near
FROM transaction_classifications tc
LEFT JOIN transactions t ON tc.transaction_id = t.id
LEFT JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
LEFT JOIN staking_events se ON tc.staking_event_id = se.id
LEFT JOIN lockup_events le ON tc.lockup_event_id = le.id
WHERE tc.user_id = %s
  AND tc.category NOT IN ('spam', 'transfer', 'internal_transfer')
ORDER BY COALESCE(t.block_timestamp, EXTRACT(EPOCH FROM et.tx_date)::BIGINT) ASC, tc.id ASC
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
    """Full-user ACB replay engine with PostgreSQL persistence."""

    def __init__(self, pool, price_service):
        self._pool = pool
        self._price_service = price_service

    def calculate_for_user(self, user_id: int) -> dict:
        """Replay all classified transactions for user, writing ACB snapshots."""
        conn = self._pool.getconn()
        try:
            import engine.acb as _acb_mod
            _GC = _acb_mod.GainsCalculator
            if _GC is None:
                from engine.gains import GainsCalculator as _GC
                _acb_mod.GainsCalculator = _GC
            gains = _GC(conn)
            gains.clear_for_user(user_id)

            with conn.cursor() as cur:
                cur.execute("DELETE FROM acb_snapshots WHERE user_id = %s", (user_id,))

            with conn.cursor() as cur:
                cur.execute(_CLASSIFY_SQL, (user_id,))
                rows = cur.fetchall()

            pools: dict[str, ACBPool] = {}
            stats = {
                "snapshots_written": 0,
                "gains_recorded": 0,
                "income_recorded": 0,
                "tokens_processed": set(),
            }

            child_map: dict[int, list] = {}
            for r in rows:
                if r.parent_classification_id is not None:
                    pid = r.parent_classification_id
                    child_map.setdefault(pid, [])
                    child_map[pid].append(r)

            for row in rows:
                if row.parent_classification_id is not None:
                    continue
                self._process_row(
                    row=row, child_map=child_map, pools=pools,
                    conn=conn, gains=gains, user_id=user_id, stats=stats,
                )

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

            # Write one audit row per token after the full replay (not per-transaction).
            # This prevents audit table bloat while still recording the final ACB state.
            for symbol, pool in pools.items():
                write_audit(
                    conn,
                    user_id=user_id,
                    entity_type="acb_snapshot",
                    entity_id=None,
                    action="acb_calculation",
                    new_value={
                        "symbol": symbol,
                        "total_units": str(pool.total_units),
                        "total_cost_cad": str(pool.total_cost_cad),
                    },
                    actor_type="system",
                )

            conn.commit()
            stats["tokens_processed"] = len(stats["tokens_processed"])
            return stats
        finally:
            self._pool.putconn(conn)

    def _get_pool(self, pools: dict, symbol: str) -> ACBPool:
        if symbol not in pools:
            pools[symbol] = ACBPool(symbol)
        return pools[symbol]

    def _resolve_fmv_cad(self, row, unix_ts: int, symbol: str) -> tuple[Optional[Decimal], Optional[Decimal], bool]:
        """Resolve FMV in CAD for a transaction row."""
        if row.fmv_cad is not None:
            fmv_cad = Decimal(str(row.fmv_cad))
            fmv_usd = Decimal(str(row.fmv_usd)) if row.fmv_usd is not None else None
            return fmv_usd, fmv_cad, False
        if row.staking_event_id is not None and row.se_fmv_cad is not None:
            return (
                Decimal(str(row.se_fmv_usd)) if row.se_fmv_usd is not None else None,
                Decimal(str(row.se_fmv_cad)), False,
            )
        if row.lockup_event_id is not None and row.le_fmv_cad is not None:
            return (
                Decimal(str(row.le_fmv_usd)) if row.le_fmv_usd is not None else None,
                Decimal(str(row.le_fmv_cad)), False,
            )
        coin_id = symbol.lower()
        try:
            price_cad, is_estimated = self._price_service.get_price_cad_at_timestamp(coin_id, unix_ts)
            return None, price_cad, is_estimated
        except Exception as exc:
            logger.warning("FMV lookup failed for %s at %s: %s", symbol, unix_ts, exc)
            return None, None, True

    def _process_row(self, row, child_map, pools, conn, gains, user_id, stats):
        """Process a single parent classification row."""
        category = row.category
        chain = row.chain or "near"
        raw_ts = row.t_block_timestamp
        if raw_ts is None and row.et_timestamp is not None:
            try:
                raw_ts = int(row.et_timestamp.timestamp())
            except Exception:
                raw_ts = 0
            unix_ts = raw_ts
        else:
            unix_ts = normalize_timestamp(raw_ts or 0, chain)

        symbol = resolve_token_symbol(row.token_id, chain, asset=row.asset)
        stats["tokens_processed"].add(symbol)
        pool = self._get_pool(pools, symbol)

        if row.exchange_transaction_id is not None and row.quantity is not None:
            units = Decimal(str(row.quantity))
        elif row.amount is not None:
            units = to_human_units(int(row.amount), chain)
        else:
            units = Decimal("0")

        if row.exchange_transaction_id is not None and row.et_fee is not None:
            fee_human = Decimal(str(row.et_fee))
        elif row.fee is not None:
            fee_human = to_human_units(int(row.fee), chain)
        else:
            fee_human = Decimal("0")

        if category == "income":
            self._handle_income(row=row, pool=pool, symbol=symbol, units=units,
                                unix_ts=unix_ts, raw_ts=raw_ts or 0, chain=chain,
                                conn=conn, gains=gains, user_id=user_id, stats=stats)
        elif category in ("capital_gain", "capital_loss"):
            children = child_map.get(row.id, [])
            sell_leg = next((c for c in children if c.leg_type == "sell_leg"), None)
            buy_leg = next((c for c in children if c.leg_type == "buy_leg"), None)
            fee_leg = next((c for c in children if c.leg_type == "fee_leg"), None)
            if sell_leg and buy_leg:
                self._handle_swap(parent_row=row, sell_leg=sell_leg, buy_leg=buy_leg,
                                  fee_leg=fee_leg, pools=pools, conn=conn, gains=gains,
                                  user_id=user_id, unix_ts=unix_ts, raw_ts=raw_ts or 0,
                                  chain=chain, stats=stats)
            else:
                self._handle_disposal(row=row, pool=pool, symbol=symbol, units=units,
                                      fee_human=fee_human, unix_ts=unix_ts, raw_ts=raw_ts or 0,
                                      chain=chain, conn=conn, gains=gains, user_id=user_id, stats=stats)
        elif category == "fee":
            self._handle_disposal(row=row, pool=pool, symbol=symbol,
                                  units=fee_human if fee_human > 0 else units,
                                  fee_human=Decimal("0"), unix_ts=unix_ts, raw_ts=raw_ts or 0,
                                  chain=chain, conn=conn, gains=gains, user_id=user_id, stats=stats,
                                  proceeds_override=Decimal("0"))
        else:
            logger.debug("Skipping category=%s classification_id=%s", category, row.id)

    def _handle_income(self, row, pool, symbol, units, unix_ts, raw_ts, chain, conn, gains, user_id, stats):
        """Handle income events: staking reward, lockup vest, airdrop."""
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
            price_usd, price_cad, is_estimated = self._resolve_fmv_cad(row, unix_ts, symbol)
            source_type = "airdrop"
            staking_event_id = None
            lockup_event_id = None

        fmv_cad = price_cad or Decimal("0")
        cost_cad = units * fmv_cad
        snap = pool.acquire(units, cost_cad)
        check_acb_pool_invariants(pool, conn=conn, user_id=user_id, context=f"income:{row.id}")

        self._persist_snapshot(
            conn=conn, user_id=user_id, symbol=symbol, classification_id=row.id,
            block_timestamp=raw_ts, snap=snap, proceeds_cad=None, gain_loss_cad=None,
            price_usd=price_usd, price_cad=price_cad, is_estimated=is_estimated,
        )
        stats["snapshots_written"] += 1

        gains.record_income(
            user_id=user_id, source_type=source_type, token_symbol=symbol,
            block_timestamp=unix_ts, chain=chain, units_received=units,
            fmv_usd=price_usd or Decimal("0"), fmv_cad=fmv_cad,
            staking_event_id=staking_event_id, lockup_event_id=lockup_event_id,
            classification_id=row.id,
        )
        stats["income_recorded"] += 1

    def _handle_disposal(self, row, pool, symbol, units, fee_human, unix_ts, raw_ts, chain,
                         conn, gains, user_id, stats, proceeds_override=None):
        """Handle a simple disposal (sell, swap sell-leg, fee disposal)."""
        price_usd, price_cad, is_estimated = self._resolve_fmv_cad(row, unix_ts, symbol)
        if proceeds_override is not None:
            proceeds_cad = proceeds_override
        else:
            proceeds_cad = units * (price_cad or Decimal("0"))
        fee_cad = fee_human * (price_cad or Decimal("0"))
        snap = pool.dispose(units, proceeds_cad, fee_cad=fee_cad)
        check_acb_pool_invariants(pool, conn=conn, user_id=user_id, context=f"disposal:{row.id}")

        snap_id = self._persist_snapshot(
            conn=conn, user_id=user_id, symbol=symbol, classification_id=row.id,
            block_timestamp=raw_ts, snap=snap, proceeds_cad=snap["net_proceeds_cad"],
            gain_loss_cad=snap["gain_loss_cad"], price_usd=price_usd, price_cad=price_cad,
            is_estimated=is_estimated, needs_review=snap.get("needs_review", False),
        )
        stats["snapshots_written"] += 1

        if snap_id is not None:
            gains.record_disposal(
                user_id=user_id, acb_snapshot_id=snap_id, token_symbol=symbol,
                block_timestamp=unix_ts, chain=chain, units_disposed=snap["units_delta"],
                proceeds_cad=snap["net_proceeds_cad"], acb_used_cad=snap["acb_used_cad"],
                fees_cad=fee_cad, gain_loss_cad=snap["gain_loss_cad"],
                needs_review=snap.get("needs_review", False),
            )
            stats["gains_recorded"] += 1

    def _handle_swap(self, parent_row, sell_leg, buy_leg, fee_leg, pools, conn, gains,
                     user_id, unix_ts, raw_ts, chain, stats):
        """Handle a multi-leg swap: dispose sell token, acquire buy token."""
        # --- Sell leg ---
        sell_symbol = resolve_token_symbol(sell_leg.token_id, chain, asset=sell_leg.asset)
        sell_pool = self._get_pool(pools, sell_symbol)
        if sell_leg.exchange_transaction_id is not None and sell_leg.quantity is not None:
            sell_units = Decimal(str(sell_leg.quantity))
        elif sell_leg.amount is not None:
            sell_units = to_human_units(int(sell_leg.amount), chain)
        else:
            sell_units = Decimal("0")

        _, sell_price_cad, sell_is_est = self._resolve_fmv_cad(sell_leg, unix_ts, sell_symbol)
        sell_proceeds_cad = sell_units * (sell_price_cad or Decimal("0"))
        sell_snap = sell_pool.dispose(sell_units, sell_proceeds_cad)
        check_acb_pool_invariants(sell_pool, conn=conn, user_id=user_id, context=f"swap-sell:{sell_leg.id}")
        sell_snap_id = self._persist_snapshot(
            conn=conn, user_id=user_id, symbol=sell_symbol, classification_id=sell_leg.id,
            block_timestamp=raw_ts, snap=sell_snap, proceeds_cad=sell_snap["net_proceeds_cad"],
            gain_loss_cad=sell_snap["gain_loss_cad"], price_usd=None, price_cad=sell_price_cad,
            is_estimated=sell_is_est, needs_review=sell_snap.get("needs_review", False),
        )
        stats["snapshots_written"] += 1

        if sell_snap_id is not None:
            gains.record_disposal(
                user_id=user_id, acb_snapshot_id=sell_snap_id, token_symbol=sell_symbol,
                block_timestamp=unix_ts, chain=chain, units_disposed=sell_snap["units_delta"],
                proceeds_cad=sell_snap["net_proceeds_cad"], acb_used_cad=sell_snap["acb_used_cad"],
                fees_cad=Decimal("0"), gain_loss_cad=sell_snap["gain_loss_cad"],
                needs_review=sell_snap.get("needs_review", False),
            )
            stats["gains_recorded"] += 1

        # --- Fee leg (added to buy ACB) ---
        fee_cad = Decimal("0")
        if fee_leg is not None:
            fee_symbol = resolve_token_symbol(fee_leg.token_id, chain, asset=fee_leg.asset)
            _, fee_price_cad, _ = self._resolve_fmv_cad(fee_leg, unix_ts, fee_symbol)
            if fee_leg.exchange_transaction_id is not None and fee_leg.quantity is not None:
                fee_units = Decimal(str(fee_leg.quantity))
            elif fee_leg.amount is not None:
                fee_units = to_human_units(int(fee_leg.amount), chain)
            else:
                fee_units = Decimal("0")
            fee_cad = fee_units * (fee_price_cad or Decimal("0"))

        # --- Buy leg ---
        buy_symbol = resolve_token_symbol(buy_leg.token_id, chain, asset=buy_leg.asset)
        buy_pool = self._get_pool(pools, buy_symbol)
        if buy_leg.exchange_transaction_id is not None and buy_leg.quantity is not None:
            buy_units = Decimal(str(buy_leg.quantity))
        elif buy_leg.amount is not None:
            buy_units = to_human_units(int(buy_leg.amount), chain)
        else:
            buy_units = Decimal("0")

        _, buy_price_cad, buy_is_est = self._resolve_fmv_cad(buy_leg, unix_ts, buy_symbol)
        buy_cost_cad = buy_units * (buy_price_cad or Decimal("0"))
        buy_snap = buy_pool.acquire(buy_units, buy_cost_cad, fee_cad=fee_cad)
        check_acb_pool_invariants(buy_pool, conn=conn, user_id=user_id, context=f"swap-buy:{buy_leg.id}")
        self._persist_snapshot(
            conn=conn, user_id=user_id, symbol=buy_symbol, classification_id=buy_leg.id,
            block_timestamp=raw_ts, snap=buy_snap, proceeds_cad=None, gain_loss_cad=None,
            price_usd=None, price_cad=buy_price_cad, is_estimated=buy_is_est,
        )
        stats["snapshots_written"] += 1
        stats["tokens_processed"].add(sell_symbol)
        stats["tokens_processed"].add(buy_symbol)

    def _persist_snapshot(self, conn, user_id, symbol, classification_id, block_timestamp,
                          snap, proceeds_cad, gain_loss_cad, price_usd, price_cad,
                          is_estimated=False, needs_review=False) -> Optional[int]:
        """INSERT acb_snapshots row (ON CONFLICT DO UPDATE). Returns snapshot id."""
        try:
            with conn.cursor() as cur:
                cur.execute(
                    _SNAPSHOT_UPSERT_SQL,
                    (
                        user_id, symbol, classification_id, block_timestamp,
                        snap["event_type"], snap["units_delta"], snap["total_units"],
                        snap.get("cost_cad_delta") or snap.get("acb_used_cad") or Decimal("0"),
                        snap["total_cost_cad"], snap["acb_per_unit"],
                        proceeds_cad, gain_loss_cad, price_usd, price_cad,
                        is_estimated, needs_review,
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
