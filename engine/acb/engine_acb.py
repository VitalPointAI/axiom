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

# Map uppercase token symbols to CoinGecko coin IDs for price lookups.
# Tokens not in this map are looked up as symbol.lower() (works for "NEAR" → "near").
_SYMBOL_TO_COINGECKO: dict[str, str] = {
    "NEAR": "near",
    "ETH": "ethereum",
    "BTC": "bitcoin",
    "MATIC": "matic-network",
    "OP": "optimism",
    "SOL": "solana",
    "AVAX": "avalanche-2",
    "XRP": "ripple",
    "AKT": "akash-network",
    "ATOM": "cosmos",
    "USDT": "tether",
    "USDC": "usd-coin",
    "DAI": "dai",
    "CRO": "crypto-com-chain",
    "WETH": "ethereum",
    "WBTC": "bitcoin",
    "WMATIC": "matic-network",
    "WNEAR": "near",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "AAVE": "aave",
    "SUSHI": "sushi",
    "GRT": "the-graph",
    "GTC": "gitcoin",
    "ALGO": "algorand",
    "MANA": "decentraland",
    "DOT": "polkadot",
    "ADA": "cardano",
    "LTC": "litecoin",
    "DOGE": "dogecoin",
    "SHIB": "shiba-inu",
    "FTM": "fantom",
    "SAND": "the-sandbox",
    "ENJ": "enjincoin",
    "BAT": "basic-attention-token",
    "COMP": "compound-governance-token",
    "MKR": "maker",
    "SNX": "havven",
    "YFI": "yearn-finance",
    "1INCH": "1inch",
    "CRV": "curve-dao-token",
    "LDO": "lido-dao",
    "APE": "apecoin",
    "IMX": "immutable-x",
    "LRC": "loopring",
    "AURORA": "aurora-near",
    "REF": "ref-finance",
    "OCT": "octopus-network",
    "PARAS": "paras",
    "LINEAR": "linear-protocol",
    "WOO": "woo-network",
    "CELO": "celo",
}

# Fiat currencies and tokens that shouldn't be price-looked-up
_SKIP_PRICE_LOOKUP: set[str] = {
    "CAD", "USD", "EUR", "GBP", "AUD", "JPY",  # Fiat
    "UNKNOWN",  # Unresolved tokens
}


def _symbol_to_coin_id(symbol: str) -> str | None:
    """Map a token symbol to a CoinGecko coin_id, or None if not priceable."""
    if symbol in _SKIP_PRICE_LOOKUP:
        return None
    return _SYMBOL_TO_COINGECKO.get(symbol, symbol.lower())


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
       t.direction,
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

        # Initialize dynamic token metadata resolver
        try:
            from indexers.token_metadata import TokenMetadataResolver
            from engine.acb.symbols import set_metadata_resolver
            set_metadata_resolver(TokenMetadataResolver(pool))
        except Exception:
            pass  # Graceful fallback to static map

    # Disposition threshold: transactions above this CAD value get minute-level
    # price precision. Below this, daily prices are used.
    DISPOSITION_PRECISION_THRESHOLD_CAD = Decimal("500")

    def _pre_warm_price_cache(self, rows) -> dict:
        """Pre-warm the price cache with bulk daily prices.

        Analyzes all transaction rows to find unique (coin_id, date_range) pairs,
        then fetches daily prices in bulk (1 CoinGecko call per token per year).

        This replaces thousands of individual API calls with a handful of bulk
        fetches. See docs/FMV_METHODOLOGY.md for the tiered pricing rationale.

        Returns:
            dict of coin_id -> set of cached date strings
        """
        from datetime import datetime as dt

        # Collect unique tokens and their date ranges
        token_dates: dict[str, set] = {}
        for row in rows:
            chain = row.chain or "near"
            symbol = resolve_token_symbol(row.token_id, chain, asset=row.asset)
            coin_id = _symbol_to_coin_id(symbol)
            if coin_id is None:
                continue  # Skip fiat currencies and unknown tokens

            raw_ts = row.t_block_timestamp
            if raw_ts is None and row.et_timestamp is not None:
                try:
                    unix_ts = int(row.et_timestamp.timestamp())
                except Exception:
                    continue
            else:
                unix_ts = normalize_timestamp(raw_ts or 0, chain)

            if unix_ts <= 0:
                continue

            date_str = dt.utcfromtimestamp(unix_ts).strftime("%Y-%m-%d")
            token_dates.setdefault(coin_id, set()).add(date_str)

        # Bulk fetch daily prices for each token's full date range
        for coin_id, dates in token_dates.items():
            if not dates:
                continue
            sorted_dates = sorted(dates)
            start_date = sorted_dates[0]
            end_date = sorted_dates[-1]
            logger.info(
                "Pre-warming price cache: %s (%s → %s, %d unique dates)",
                coin_id, start_date, end_date, len(dates),
            )
            self._price_service.bulk_fetch_daily_prices(
                coin_id, start_date, end_date, "usd"
            )

        # Bulk pre-warm BoC CAD rates for the full date range (single API call)
        all_dates = set()
        for dates in token_dates.values():
            all_dates.update(dates)
        if all_dates:
            sorted_all = sorted(all_dates)
            logger.info("Pre-warming BoC CAD rates: %s → %s (bulk)", sorted_all[0], sorted_all[-1])
            self._price_service.bulk_fetch_boc_cad_rates(sorted_all[0], sorted_all[-1])

        return {k: v for k, v in token_dates.items()}

    def _pre_warm_minute_prices(self, rows) -> None:
        """Pre-warm minute-level price cache for large dispositions.

        After daily prices are pre-warmed by _pre_warm_price_cache(), this
        method identifies disposition transactions likely above the precision
        threshold and batch-fetches their minute-level prices in one pass.

        Uses the already-warmed daily price as a proxy to decide if a
        transaction is "large" (units * daily_price > threshold).
        """
        from datetime import datetime as dt

        minute_requests: list[tuple[str, int]] = []

        for row in rows:
            # Only process dispositions and fees that might be large
            if row.category not in ("sell", "capital_gain", "capital_loss", "trade", "fee"):
                continue

            if row.parent_classification_id is not None:
                continue  # Skip child legs

            chain = row.chain or "near"
            from engine.acb.symbols import resolve_token_symbol, normalize_timestamp, to_human_units
            symbol = resolve_token_symbol(row.token_id, chain, asset=row.asset)
            coin_id = _symbol_to_coin_id(symbol)
            if coin_id is None:
                continue

            raw_ts = row.t_block_timestamp
            if raw_ts is None and row.et_timestamp is not None:
                try:
                    unix_ts = int(row.et_timestamp.timestamp())
                except Exception:
                    continue
            else:
                unix_ts = normalize_timestamp(raw_ts or 0, chain)

            if unix_ts <= 0:
                continue

            # Determine units
            if row.exchange_transaction_id is not None and row.quantity is not None:
                from decimal import Decimal as _D
                units = _D(str(row.quantity))
            elif row.amount is not None:
                units = to_human_units(int(row.amount), chain)
            else:
                continue

            # Use daily price to estimate if this is a large transaction
            date_str = dt.utcfromtimestamp(unix_ts).strftime("%Y-%m-%d")
            daily_result = self._price_service.get_daily_price_cad(coin_id, date_str)
            if daily_result and daily_result[0] is not None:
                from decimal import Decimal as _D
                estimated_value = abs(units) * daily_result[0]
                if estimated_value > self.DISPOSITION_PRECISION_THRESHOLD_CAD:
                    minute_requests.append((coin_id, unix_ts))

        if minute_requests:
            logger.info(
                "Pre-warming minute-level prices for %d large dispositions",
                len(minute_requests),
            )
            self._price_service.bulk_fetch_minute_prices(minute_requests)

    def calculate_for_user(self, user_id: int, progress_callback=None) -> dict:
        """Calculate ACB for a user — incremental when possible, full replay when needed.

        Incremental mode (fast path, <30s):
          - Restores ACB pool state from latest snapshots per token
          - Only processes classifications with id > high-water mark
          - Skips price pre-warming (new txs are recent, likely cached)

        Full replay mode (slow path, triggered by):
          - First-ever ACB run (no high-water mark)
          - New wallet added (acb_full_replay_required = true)
          - Reclassification of existing transactions
          - Explicit request via force_full_replay parameter

        Uses tiered FMV pricing (see docs/FMV_METHODOLOGY.md):
          - Tier 1: Staking/lockup FMV from on-chain data (exact, no API call)
          - Tier 2: Daily price for income, fees, small transactions (bulk-fetched)
          - Tier 3: Minute-level price for dispositions > $500 CAD (per-tx API call)
        """
        conn = self._pool.getconn()
        try:
            # Check incremental eligibility
            full_replay, high_water_mark = self._check_replay_mode(conn, user_id)

            if full_replay:
                logger.info("ACB full replay for user_id=%s (hwm=%s)", user_id, high_water_mark)
                return self._full_replay(conn, user_id, progress_callback=progress_callback)
            else:
                logger.info("ACB incremental for user_id=%s (hwm=%s)", user_id, high_water_mark)
                return self._incremental(conn, user_id, high_water_mark, progress_callback=progress_callback)
        finally:
            self._pool.putconn(conn)

    def _check_replay_mode(self, conn, user_id: int) -> tuple[bool, int | None]:
        """Determine if full replay is needed or incremental is safe.

        Returns (full_replay_needed, high_water_mark).
        """
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT acb_high_water_mark, acb_full_replay_required
                   FROM users WHERE id = %s""",
                (user_id,),
            )
            row = cur.fetchone()
        except Exception:
            # Columns may not exist yet (pre-migration 014) — full replay
            return True, None
        finally:
            cur.close()

        if row is None or len(row) < 2:
            return True, None

        hwm, replay_required = row

        # Full replay needed if:
        # 1. No high-water mark (first run)
        # 2. Explicitly flagged (new wallet, reclassification)
        if hwm is None or replay_required:
            return True, hwm

        # Check if any classifications were MODIFIED (not just added) since hwm.
        # If existing classifications were reclassified, their IDs stay the same
        # but updated_at changes. This catches reclassifications.
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT COUNT(*) FROM transaction_classifications
                   WHERE user_id = %s AND id <= %s
                     AND updated_at > (
                         SELECT COALESCE(MAX(updated_at), '1970-01-01')
                         FROM acb_snapshots WHERE user_id = %s
                     )""",
                (user_id, hwm, user_id),
            )
            modified_count = cur.fetchone()[0]
        finally:
            cur.close()

        if modified_count > 0:
            logger.info("ACB: %d classifications modified since last run, forcing full replay",
                        modified_count)
            return True, hwm

        return False, hwm

    def _restore_pools(self, conn, user_id: int) -> dict[str, ACBPool]:
        """Restore ACB pool state from the latest snapshot per token.

        For each token_symbol, finds the snapshot with the highest classification_id
        and restores total_units (units_after) and total_cost_cad.

        Returns dict of symbol -> ACBPool with restored state.
        """
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT DISTINCT ON (token_symbol)
                       token_symbol, units_after, total_cost_cad
                   FROM acb_snapshots
                   WHERE user_id = %s
                   ORDER BY token_symbol, classification_id DESC""",
                (user_id,),
            )
            rows = cur.fetchall()
        finally:
            cur.close()

        pools: dict[str, ACBPool] = {}
        for symbol, units_after, total_cost_cad in rows:
            pool = ACBPool(symbol)
            pool.total_units = Decimal(str(units_after))
            pool.total_cost_cad = Decimal(str(total_cost_cad))
            pools[symbol] = pool
            logger.debug("Restored pool %s: units=%s cost=%s",
                         symbol, pool.total_units, pool.total_cost_cad)

        return pools

    def _update_high_water_mark(self, conn, user_id: int, max_classification_id: int) -> None:
        """Update the user's ACB high-water mark after successful run."""
        cur = conn.cursor()
        try:
            cur.execute(
                """UPDATE users
                   SET acb_high_water_mark = %s,
                       acb_full_replay_required = FALSE
                   WHERE id = %s""",
                (max_classification_id, user_id),
            )
        finally:
            cur.close()

    def _incremental(self, conn, user_id: int, high_water_mark: int, progress_callback=None) -> dict:
        """Process only new classifications since the high-water mark.

        Restores pool state from snapshots, processes new rows, persists results.
        Much faster than full replay — typically <30s for incremental syncs.
        """
        import engine.acb as _acb_mod
        _GC = _acb_mod.GainsCalculator
        if _GC is None:
            from engine.gains import GainsCalculator as _GC
            _acb_mod.GainsCalculator = _GC
        gains = _GC(conn)
        # Don't clear gains — we're appending incrementally

        # Restore pool state from existing snapshots
        pools = self._restore_pools(conn, user_id)

        # Fetch only NEW classifications (id > high_water_mark)
        from psycopg2.extras import NamedTupleCursor
        incremental_sql = _CLASSIFY_SQL.replace(
            "WHERE tc.user_id = %s",
            "WHERE tc.user_id = %s AND tc.id > %s",
        )
        with conn.cursor(cursor_factory=NamedTupleCursor) as cur:
            cur.execute(incremental_sql, (user_id, high_water_mark))
            rows = cur.fetchall()

        if not rows:
            logger.info("ACB incremental: no new classifications for user_id=%s", user_id)
            conn.commit()
            return {"snapshots_written": 0, "gains_recorded": 0,
                    "income_recorded": 0, "tokens_processed": 0,
                    "superficial_losses": 0, "mode": "incremental_noop"}

        logger.info("ACB incremental: processing %d new classifications", len(rows))

        # Pre-warm prices only for the new rows
        self._pre_warm_price_cache(rows)

        # Pre-warm minute-level prices for large dispositions
        self._pre_warm_minute_prices(rows)

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

        max_id = high_water_mark
        for idx, row in enumerate(rows):
            if row.parent_classification_id is not None:
                continue
            self._process_row(
                row=row, child_map=child_map, pools=pools,
                conn=conn, gains=gains, user_id=user_id, stats=stats,
            )
            max_id = max(max_id, row.id)
            if progress_callback and idx % 50 == 0:
                progress_callback(idx)

        # Final progress callback
        if progress_callback:
            progress_callback(len(rows))

        # Update high-water mark
        self._update_high_water_mark(conn, user_id, max_id)

        conn.commit()
        stats["tokens_processed"] = len(stats["tokens_processed"])
        stats["mode"] = "incremental"
        return stats

    def _full_replay(self, conn, user_id: int, progress_callback=None) -> dict:
        """Full ACB replay — clears all snapshots and reprocesses everything.

        Triggered when:
          - First-ever ACB run
          - New wallet added
          - Classifications modified
        """
        import engine.acb as _acb_mod
        _GC = _acb_mod.GainsCalculator
        if _GC is None:
            from engine.gains import GainsCalculator as _GC
            _acb_mod.GainsCalculator = _GC
        gains = _GC(conn)
        gains.clear_for_user(user_id)

        with conn.cursor() as cur:
            cur.execute("DELETE FROM acb_snapshots WHERE user_id = %s", (user_id,))

        from psycopg2.extras import NamedTupleCursor
        with conn.cursor(cursor_factory=NamedTupleCursor) as cur:
            cur.execute(_CLASSIFY_SQL, (user_id,))
            rows = cur.fetchall()

        # Pre-warm price cache with bulk daily prices
        self._pre_warm_price_cache(rows)

        # Pre-warm minute-level prices for large dispositions
        self._pre_warm_minute_prices(rows)

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

        max_id = 0
        for idx, row in enumerate(rows):
            if row.parent_classification_id is not None:
                continue
            self._process_row(
                row=row, child_map=child_map, pools=pools,
                conn=conn, gains=gains, user_id=user_id, stats=stats,
            )
            max_id = max(max_id, row.id)
            if progress_callback and idx % 50 == 0:
                progress_callback(idx)

        # Final progress callback
        if progress_callback:
            progress_callback(len(rows))

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

        # Write audit row per token
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

        # Update high-water mark
        if max_id > 0:
            self._update_high_water_mark(conn, user_id, max_id)

        conn.commit()
        stats["tokens_processed"] = len(stats["tokens_processed"])
        stats["mode"] = "full_replay"
        return stats

    def _get_pool(self, pools: dict, symbol: str) -> ACBPool:
        if symbol not in pools:
            pools[symbol] = ACBPool(symbol)
        return pools[symbol]

    def _resolve_fmv_cad(
        self, row, unix_ts: int, symbol: str,
        require_precision: bool = False,
    ) -> tuple[Optional[Decimal], Optional[Decimal], bool]:
        """Resolve FMV in CAD for a transaction row.

        Uses tiered pricing (see docs/FMV_METHODOLOGY.md):
          - Tier 1: On-chain FMV from staking/lockup events (exact)
          - Tier 2: Daily price from pre-warmed cache (no API call)
          - Tier 3: Minute-level price from CoinGecko range API

        Args:
            row:                Transaction classification row (NamedTuple)
            unix_ts:            Unix timestamp in seconds
            symbol:             Resolved token symbol (e.g. "NEAR", "ETH")
            require_precision:  If True, use minute-level price (Tier 3).
                                Set for dispositions above the threshold.

        Returns:
            (fmv_usd, fmv_cad, is_estimated) tuple
        """
        # Tier 1: On-chain FMV (staking rewards, lockup events)
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

        coin_id = _symbol_to_coin_id(symbol)
        if coin_id is None:
            # Fiat currency — FMV is 1:1 in its own currency
            if symbol in ("CAD", "USD"):
                return None, Decimal("1"), False
            return None, None, True

        # Tier 3: Minute-level precision for large dispositions
        if require_precision:
            try:
                price_cad, is_estimated = self._price_service.get_price_cad_at_timestamp(
                    coin_id, unix_ts
                )
                return None, price_cad, is_estimated
            except Exception as exc:
                logger.warning("Minute-level FMV lookup failed for %s at %s: %s",
                               symbol, unix_ts, exc)
                # Fall through to daily price as fallback

        # Tier 2: Daily price from pre-warmed cache (no API call needed)
        try:
            from datetime import datetime as dt
            date_str = dt.utcfromtimestamp(unix_ts).strftime("%Y-%m-%d")
            price_cad, is_estimated = self._price_service.get_daily_price_cad(
                coin_id, date_str
            )
            if price_cad is not None:
                return None, price_cad, True  # Daily price = estimated
        except Exception as exc:
            logger.warning("Daily FMV lookup failed for %s at %s: %s",
                           symbol, unix_ts, exc)

        # Final fallback: minute-level API call
        try:
            price_cad, is_estimated = self._price_service.get_price_cad_at_timestamp(
                coin_id, unix_ts
            )
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

        # -----------------------------------------------------------
        # ACQUISITIONS — add units to pool with cost basis at FMV
        # -----------------------------------------------------------
        if category in ("income", "reward", "airdrop", "interest", "buy",
                         "nft_sale"):
            self._handle_income(row=row, pool=pool, symbol=symbol, units=units,
                                unix_ts=unix_ts, raw_ts=raw_ts or 0, chain=chain,
                                conn=conn, gains=gains, user_id=user_id, stats=stats)

        # -----------------------------------------------------------
        # DISPOSITIONS — remove units from pool, realize gains/losses
        # -----------------------------------------------------------
        elif category in ("sell", "capital_gain", "capital_loss"):
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

        # -----------------------------------------------------------
        # TRADES — decomposed swaps with buy/sell child legs
        # -----------------------------------------------------------
        elif category == "trade":
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
                # Trade without decomposed legs — treat as acquisition if direction=in,
                # disposal if direction=out
                direction = getattr(row, "direction", None)
                if direction == "out" or (row.amount and int(row.amount) < 0):
                    self._handle_disposal(row=row, pool=pool, symbol=symbol, units=abs(units),
                                          fee_human=fee_human, unix_ts=unix_ts, raw_ts=raw_ts or 0,
                                          chain=chain, conn=conn, gains=gains, user_id=user_id, stats=stats)
                else:
                    self._handle_income(row=row, pool=pool, symbol=symbol, units=units,
                                        unix_ts=unix_ts, raw_ts=raw_ts or 0, chain=chain,
                                        conn=conn, gains=gains, user_id=user_id, stats=stats)

        # -----------------------------------------------------------
        # FEES — disposal at zero proceeds (cost of doing business)
        # -----------------------------------------------------------
        elif category == "fee":
            self._handle_disposal(row=row, pool=pool, symbol=symbol,
                                  units=fee_human if fee_human > 0 else units,
                                  fee_human=Decimal("0"), unix_ts=unix_ts, raw_ts=raw_ts or 0,
                                  chain=chain, conn=conn, gains=gains, user_id=user_id, stats=stats,
                                  proceeds_override=Decimal("0"))

        # -----------------------------------------------------------
        # NON-TAXABLE MOVEMENTS — track units but no cost basis change
        # deposit/withdrawal/transfer_in/transfer_out/stake/unstake
        # These don't affect ACB per CRA rules — they move crypto
        # between wallets/platforms without triggering a taxable event.
        # We still record a snapshot so portfolio units_after is accurate.
        # -----------------------------------------------------------
        elif category in ("deposit", "transfer_in", "unstake",
                           "collateral_out", "liquidity_out", "loan_borrow"):
            # Incoming non-taxable: add units, zero cost delta
            in_units = abs(units)
            pool.total_units += in_units
            snap = {
                "event_type": category,
                "units_delta": in_units,
                "total_units": pool.total_units,
                "cost_cad_delta": Decimal("0"),
                "total_cost_cad": pool.total_cost_cad,
                "acb_per_unit": pool.acb_per_unit,
            }
            self._persist_snapshot(
                conn=conn, user_id=user_id, symbol=symbol,
                classification_id=row.id, block_timestamp=raw_ts or 0,
                snap=snap, proceeds_cad=None, gain_loss_cad=None,
                price_usd=None, price_cad=None,
            )
            stats["snapshots_written"] += 1

        elif category in ("withdrawal", "transfer_out", "stake",
                           "collateral_in", "liquidity_in", "loan_repay"):
            # Outgoing non-taxable: remove units, zero cost delta
            out_units = abs(units)
            pool.total_units = max(Decimal("0"), pool.total_units - out_units)
            snap = {
                "event_type": category,
                "units_delta": -out_units,
                "total_units": pool.total_units,
                "cost_cad_delta": Decimal("0"),
                "total_cost_cad": pool.total_cost_cad,
                "acb_per_unit": pool.acb_per_unit,
            }
            self._persist_snapshot(
                conn=conn, user_id=user_id, symbol=symbol,
                classification_id=row.id, block_timestamp=raw_ts or 0,
                snap=snap, proceeds_cad=None, gain_loss_cad=None,
                price_usd=None, price_cad=None,
            )
            stats["snapshots_written"] += 1

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
        # First get daily price to estimate value; upgrade to minute-level if large
        price_usd, price_cad, is_estimated = self._resolve_fmv_cad(row, unix_ts, symbol)
        if (price_cad is not None
                and units * price_cad > self.DISPOSITION_PRECISION_THRESHOLD_CAD
                and is_estimated
                and proceeds_override is None):
            # Large disposition — upgrade to minute-level precision
            price_usd, price_cad, is_estimated = self._resolve_fmv_cad(
                row, unix_ts, symbol, require_precision=True
            )
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

        # Swaps are always dispositions — use daily first, upgrade if large
        _, sell_price_cad, sell_is_est = self._resolve_fmv_cad(sell_leg, unix_ts, sell_symbol)
        sell_proceeds_cad = sell_units * (sell_price_cad or Decimal("0"))
        if sell_proceeds_cad > self.DISPOSITION_PRECISION_THRESHOLD_CAD and sell_is_est:
            _, sell_price_cad, sell_is_est = self._resolve_fmv_cad(
                sell_leg, unix_ts, sell_symbol, require_precision=True
            )
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
