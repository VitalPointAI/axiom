# Phase 4: Cost Basis Engine - Research

**Researched:** 2026-03-12
**Domain:** Canadian ACB calculation, capital gains engine, FMV pricing, superficial loss detection
**Confidence:** HIGH (core ACB math), MEDIUM (CoinGecko minute-level constraints), HIGH (Bank of Canada API)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**ACB Persistence & Recalculation**
- Hybrid approach: recalculate ACB from scratch by replaying all classified transactions chronologically, then cache the result. Re-run only when underlying data changes (new transactions, reclassifications)
- Per-transaction ACB snapshots stored in DB — full audit trail showing ACB-per-unit, total units, total cost, and gain/loss at every acquisition and disposal event (CRA defensible)
- Dual trigger: background job queue (`calculate_acb` job type in IndexerService, triggered after classification completes) + on-demand recalc via API (for specialist reclassification scenarios)
- Per-user scope: one job calculates ACB for all tokens a user holds (typical user has 5-15 tokens)

**FMV & Price Handling**
- Minute-level price granularity — fetch closest-minute price for each transaction timestamp, not daily
- On-demand with cache: fetch minute-level price from CoinGecko market_chart/range API when needed, cache in price_cache with minute granularity. Extends existing PriceService caching pattern
- Previous-period fallback: when no price available for exact minute, use most recent available price (last 1-2 minutes). Flag transaction as `price_estimated` for specialist review
- Stablecoin handling: configurable per token — default to 1:1 USD peg for USDT/USDC/DAI, but allow specialist to flag specific stablecoins for real price lookup (e.g., depeg events)
- CAD conversion: Bank of Canada daily rates (CRA-preferred). Fetch USD price from CoinGecko, convert using official BoC CAD/USD rate
- Income events (staking/vesting): use pre-captured FMV from StakingEvent/LockupEvent tables directly as acquisition cost. No re-derivation — ensures consistency with indexing-time values

**Superficial Loss Treatment**
- Auto-calculate + flag: engine detects 30-day window matches, calculates denied loss amount, proposes ACB adjustment to replacement property. Flags for specialist review but shows the proposed adjustment
- All wallets pooled: check across ALL user wallets for rebuys within 30 days of any disposal at a loss (CRA-correct — rule applies across all taxpayer accounts)
- All sources: check on-chain transactions AND exchange transactions for rebuys (retail often rebuys on exchanges)
- Pro-rate partial rebuys: if sold 100 NEAR at loss and rebought 50 within 30 days, deny 50% of loss and add denied portion to ACB of the 50 replacement units

**Multi-leg Disposal Mapping**
- FMV-based swap treatment: sell leg disposed at FMV of tokens sold (capital gain/loss), buy leg acquired at FMV of tokens received (= same value). CRA barter transaction treatment
- Gas/network fees on swaps: add to acquisition cost of the buy leg (increases ACB, reduces future gains). CRA treats transaction costs as part of acquisition cost
- Consume Phase 3's multi-leg decomposition: parent + sell_leg + buy_leg + fee_leg from TransactionClassification table

**Output Ledgers**
- Produce both capital gains ledger (all disposals with gain/loss calculations) and income ledger (staking rewards + lockup vesting with FMV at receipt)
- Both ledgers feed directly into Phase 6 (Reporting)

### Claude's Discretion
- Database schema design for ACB snapshot tables and income ledger tables
- Cache invalidation strategy (dirty flag, version counter, or timestamp comparison)
- Exact CoinGecko market_chart/range API pagination for minute-level data
- Bank of Canada rate API integration details
- ACB recalculation optimization (e.g., only replay from first changed transaction forward)
- How to handle zero-value or dust transactions in ACB calculation

### Deferred Ideas (OUT OF SCOPE)
- Tax-loss harvesting suggestions (optimization, not reporting) — future feature
- Multi-year ACB carryforward reporting — Phase 6 (Reporting)
- T1135 threshold calculation using ACB data — Phase 6 (Reporting)
- Affiliated persons superficial loss detection (beyond user's own wallets) — future enhancement
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ACB-01 | System calculates Adjusted Cost Base (ACB) using Canadian average cost method | Legacy `engine/acb.py` has correct math — needs PostgreSQL rewrite with Decimal precision; average cost formula is: new_ACB = (old_total_cost + acquisition_cost) / new_total_units |
| ACB-02 | System tracks ACB per token across all wallets (pooled, not per-wallet) | Must aggregate all wallets for a user_id into single pool per token symbol; transactions sorted by block_timestamp ASC across all chains |
| ACB-03 | System fetches historical FMV prices for income events (staking, vesting) | Income events already have fmv_usd/fmv_cad in StakingEvent + LockupEvent tables — use directly; for on-chain tx needing FMV, extend PriceService to minute-level via CoinGecko market_chart/range |
| ACB-04 | System adjusts cost basis for fees paid | For acquisitions: add fee to acquisition cost (increases ACB pool); for disposals: fees reduce proceeds (net_proceeds = proceeds - fee); for swap buy_leg: fee_leg adds to ACB of received tokens |
| ACB-05 | System handles superficial loss rules (30-day rule) — flag for manual review | 61-day window (30 days before + day of sale + 30 days after); pro-rated denial for partial rebuys; denied loss added to ACB of replacement property |
</phase_requirements>

---

## Summary

Phase 4 builds the ACB calculation engine on top of Phase 3's classified transactions. The domain is well-understood: Canadian tax law requires the average cost method for crypto, all units of the same token are a single pool regardless of wallet. The legacy `engine/acb.py` has the correct math but uses Python floats and in-memory state — it must be rewritten with `Decimal` precision and PostgreSQL persistence.

The main complexity in this phase is threefold. First, FMV price resolution: CoinGecko's free/paid tiers only provide hourly auto-granularity for historical data older than 1 day — "minute-level" will actually be hourly for most transactions (anything older than ~24 hours). This is a constraint to document clearly. Second, superficial loss detection requires a cross-wallet, cross-source scan of ALL acquisitions within a 61-day window around each loss disposal. Third, the Bank of Canada Valet API provides daily FXUSDCAD rates with no auth required — this is the CRA-preferred source for USD→CAD conversion and replaces the current CryptoCompare USDT→CAD fallback.

**Primary recommendation:** Rewrite `engine/acb.py` as a PostgreSQL-backed `ACBEngine` class with `Decimal` arithmetic throughout. Extend `PriceService` with a `get_price_at_timestamp()` method using CoinGecko `market_chart/range`. Add Bank of Canada Valet API integration for daily CAD rates. Implement `SuperficialLossDetector` scanning all user transactions across wallets/exchanges.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `decimal` (stdlib) | Python 3.x | Exact decimal arithmetic for ACB calculations | Eliminates float rounding; project already uses Decimal throughout (NUMERIC(40,0), NUMERIC(24,8)) |
| `psycopg2-binary` | >=2.9.9 | PostgreSQL pool operations | Already in requirements.txt; all handlers use this pattern |
| `sqlalchemy` | >=2.0.0 | ORM models for new DB tables | Already in requirements.txt; all models use SQLAlchemy declarative |
| `alembic` | >=1.13.0 | Schema migration (migration 004) | Already in requirements.txt; all schema changes use Alembic |
| `requests` | >=2.31.0 | HTTP calls to CoinGecko and BoC Valet API | Already in requirements.txt; PriceService already uses it |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `datetime` (stdlib) | Python 3.x | Timestamp arithmetic for 30-day superficial loss windows | Block_timestamp is BIGINT (nanoseconds for NEAR, seconds for EVM) |
| `collections.defaultdict` (stdlib) | Python 3.x | Group transactions by token symbol during replay | Used in legacy acb.py, correct pattern |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CoinGecko market_chart/range | CryptoCompare OHLCV | CoinGecko is already integrated and primary; CryptoCompare as fallback already exists |
| Bank of Canada Valet API | CryptoCompare USDT→CAD (existing) | BoC is CRA-preferred; deterministic daily rates; no API key; replaces the hardcoded 1.36 fallback |
| PostgreSQL ACB snapshots | In-memory replay only | DB snapshots give full audit trail and avoid full replay on every API call |

**Installation:** No new packages required — all dependencies are already in `requirements.txt`.

---

## Architecture Patterns

### Recommended Project Structure
```
engine/
├── acb.py           # ACBEngine — PostgreSQL-backed average cost calculator (replaces legacy)
├── gains.py         # GainsCalculator — produces capital_gains_ledger entries
├── superficial.py   # SuperficialLossDetector — 30-day window scan, pro-rated denial
└── prices.py        # (legacy, superseded — do not extend)

indexers/
├── price_service.py         # Extend: add get_price_at_timestamp() + BoC CAD rates
├── acb_handler.py           # NEW: job handler for 'calculate_acb' job type
└── service.py               # Register 'calculate_acb': ACBHandler(pool, price_service)

db/
├── models.py                # Add: ACBSnapshot, CapitalGainsLedger, IncomeLedger models
└── migrations/versions/
    └── 004_cost_basis_schema.py   # Alembic migration 004
```

### Pattern 1: ACB Chronological Replay

**What:** Load all classified transactions for a user in chronological order (block_timestamp ASC), then apply acquire/dispose operations to build per-token ACB pools, storing a snapshot after each operation.

**When to use:** Every `calculate_acb` job run. On dirty recalculation, replay from the first transaction timestamp that changed.

**Example:**
```python
# engine/acb.py
from decimal import Decimal, ROUND_HALF_UP

class ACBPool:
    """In-memory pool for a single token during chronological replay."""
    def __init__(self, symbol: str, user_id: int):
        self.symbol = symbol
        self.user_id = user_id
        self.total_units = Decimal("0")
        self.total_cost_cad = Decimal("0")  # Always CAD

    @property
    def acb_per_unit(self) -> Decimal:
        if self.total_units <= 0:
            return Decimal("0")
        return (self.total_cost_cad / self.total_units).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        )

    def acquire(self, units: Decimal, cost_cad: Decimal, fee_cad: Decimal = Decimal("0")) -> dict:
        self.total_cost_cad += cost_cad + fee_cad
        self.total_units += units
        return {
            "acb_per_unit": self.acb_per_unit,
            "total_units": self.total_units,
            "total_cost_cad": self.total_cost_cad,
        }

    def dispose(self, units: Decimal, proceeds_cad: Decimal, fee_cad: Decimal = Decimal("0")) -> dict:
        acb_used = (units * self.acb_per_unit).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        )
        net_proceeds = proceeds_cad - fee_cad
        gain_loss_cad = net_proceeds - acb_used
        # Reduce pool proportionally
        self.total_cost_cad -= acb_used
        self.total_units -= units
        if self.total_units < Decimal("0"):
            self.total_units = Decimal("0")
            self.total_cost_cad = Decimal("0")
        return {
            "acb_used_cad": acb_used,
            "net_proceeds_cad": net_proceeds,
            "gain_loss_cad": gain_loss_cad,
            "acb_per_unit": self.acb_per_unit,
            "total_units": self.total_units,
        }
```

### Pattern 2: CoinGecko market_chart/range for Historical Prices

**What:** Fetch 1-day window around a transaction timestamp to get hourly price data, return closest price by timestamp proximity.

**Important constraint:** CoinGecko auto-granularity rules:
- Data from the last 24 hours: 5-minute intervals (free tier)
- Data from 1-90 days ago: **hourly** intervals (free tier)
- Data older than 90 days: **daily** intervals (free tier)
- True minute-level (5-minute interval param): Enterprise plan only

For historical crypto transactions, nearly all will fall into hourly or daily granularity on free/paid-but-not-Enterprise tiers. "Closest-minute" becomes "closest-hour" in practice.

**Example:**
```python
# indexers/price_service.py — new method
def get_price_at_timestamp(
    self,
    coin_id: str,
    unix_ts: int,        # UNIX timestamp (seconds)
    currency: str = "usd",
) -> tuple[Optional[Decimal], bool]:
    """
    Return (price, is_estimated) for coin_id at unix_ts.

    Fetches 2-hour window around timestamp using market_chart/range.
    Returns closest price and is_estimated=True if not exact match.
    Caches at minute-level key: coin_id + unix_ts_rounded_to_minute + currency.
    """
    # Round to nearest minute for cache key
    ts_minute = (unix_ts // 60) * 60

    # 1. Check minute-level cache
    cached = self._get_cached_minute(coin_id, ts_minute, currency)
    if cached is not None:
        return cached, False

    # 2. Fetch 3-hour window: ts-1h to ts+1h (ensures hourly data includes target)
    from_ts = unix_ts - 3600
    to_ts = unix_ts + 3600
    base = COINGECKO_PRO_BASE if self.coingecko_api_key else COINGECKO_BASE
    url = f"{base}/coins/{coin_id}/market_chart/range"
    params = {"vs_currency": currency, "from": from_ts, "to": to_ts}
    # ... fetch and find closest timestamp
    # 3. Cache result
    # 4. Return (price, is_estimated)
```

### Pattern 3: Bank of Canada Valet API for CAD Rates

**What:** Fetch daily FXUSDCAD rates from BoC Valet API. No API key required. CRA-preferred source.

**Endpoint:**
```
GET https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
```

**Response structure:**
```json
{
  "observations": [
    {"d": "2025-01-15", "FXUSDCAD": {"v": "1.4389"}},
    ...
  ]
}
```

**Example:**
```python
# indexers/price_service.py — new method
BOC_VALET_BASE = "https://www.bankofcanada.ca/valet"

def get_boc_cad_rate(self, date_str: str) -> Optional[Decimal]:
    """
    Fetch USD/CAD rate from Bank of Canada Valet API for date_str.

    Falls back to previous business day if no rate found (weekends/holidays).
    Caches result in price_cache as coin_id='usd', currency='cad'.
    Source label: 'bank_of_canada'.
    """
    # Check cache first
    cached = self._get_cached("usd", date_str, "cad")
    if cached is not None:
        return cached

    # Fetch BoC Valet API (no auth required)
    url = f"{BOC_VALET_BASE}/observations/FXUSDCAD/json"
    params = {"start_date": date_str, "end_date": date_str}
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()

    observations = data.get("observations", [])
    if observations:
        rate = Decimal(observations[0]["FXUSDCAD"]["v"])
        self._cache_price("usd", date_str, "cad", rate, "bank_of_canada")
        return rate

    # Weekend/holiday: look back up to 5 business days
    # ...
    return None
```

### Pattern 4: Superficial Loss Detection

**What:** After full ACB replay is complete, scan capital gains ledger for losses. For each loss disposal, query all acquisitions of the same token within 61-day window across ALL user wallets and exchanges.

**Example:**
```python
# engine/superficial.py
class SuperficialLossDetector:
    def detect(self, user_id: int, disposal: dict) -> Optional[dict]:
        """
        For a disposal that resulted in a loss, check for rebuys in 61-day window.

        Returns superficial loss info if triggered, else None.

        Window: disposal_date - 30 days to disposal_date + 30 days (inclusive)
        Sources: transactions table + exchange_transactions table
        All wallets for user_id (pooled).
        """
        if disposal["gain_loss_cad"] >= 0:
            return None  # Not a loss

        token = disposal["token_symbol"]
        disposal_ts = disposal["block_timestamp"]
        window_start = disposal_ts - (30 * 86400)  # 30 days in seconds
        window_end = disposal_ts + (30 * 86400)

        # Query ALL acquisitions of same token in window, across wallets + exchanges
        # ...

        total_rebought = sum(acq["units"] for acq in rebuys)
        units_sold = disposal["units"]

        if total_rebought <= 0:
            return None

        # Pro-rated: denied_ratio = min(1, total_rebought / units_sold)
        denied_ratio = min(Decimal("1"), total_rebought / units_sold)
        denied_loss = abs(disposal["gain_loss_cad"]) * denied_ratio

        return {
            "denied_loss_cad": denied_loss,
            "denied_ratio": denied_ratio,
            "rebuys": rebuys,
            "acb_adjustment_cad": denied_loss,  # Add to ACB of replacement units
        }
```

### Pattern 5: ACBHandler Job Integration

**What:** Register `calculate_acb` in IndexerService. Trigger from ClassifierHandler after `classify_transactions` completes (same pattern as ClassifierHandler triggering dedup).

**Example:**
```python
# indexers/acb_handler.py
class ACBHandler:
    def __init__(self, pool, price_service):
        self.pool = pool
        self.price_service = price_service
        self.engine = ACBEngine(pool, price_service)

    def run_calculate_acb(self, job: dict) -> None:
        user_id = job["user_id"]
        stats = self.engine.calculate_for_user(user_id)
        logger.info("ACB complete: %d snapshots, %d gains, %d income events", ...)
```

### Anti-Patterns to Avoid

- **Float arithmetic for ACB:** Never use `float` for cost basis. One float rounding error compounds across thousands of transactions. Always `Decimal`.
- **Per-wallet ACB pools:** CRA requires pooling across all wallets. Never scope ACB to a single wallet.
- **Re-fetching FMV for staking/vesting:** StakingEvent and LockupEvent already have `fmv_usd`/`fmv_cad` captured at indexing time. Re-deriving from price service creates inconsistency.
- **Daily price for disposal events:** ACB disposal proceeds must use FMV at time of transaction, not end-of-day price.
- **Marking all superficial losses as final:** Superficial losses must be flagged for specialist review — the engine proposes the adjustment but does not apply it without confirmation.
- **Ignoring fee_leg in swap ACB:** The fee_leg from Phase 3's multi-leg decomposition adds to ACB of the buy_leg. Skipping this understates ACB and overstates future gains.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Decimal rounding for money | Custom rounding logic | `Decimal.quantize(Decimal("0.00000001"), ROUND_HALF_UP)` | Python stdlib; matches PostgreSQL NUMERIC behavior |
| HTTP retry with backoff | Custom retry loop | Use existing `requests` + the 3-attempt retry already in PriceService | Already tested; consistent with existing code |
| CAD/USD exchange rates | Scraping or approximation | Bank of Canada Valet API (`/valet/observations/FXUSDCAD/json`) | Free, no auth, CRA-preferred, daily published |
| PostgreSQL upsert | Custom INSERT+UPDATE | `INSERT ... ON CONFLICT DO UPDATE` | Same pattern used in price_cache, transaction_classifications |
| Job queue integration | New queue mechanism | Register in `IndexerService.handlers` dict | Same pattern as ClassifierHandler, DedupHandler |
| Chronological ordering | Application-level sort | `ORDER BY block_timestamp ASC` in SQL query | Block_timestamp is indexed; DB sort is more efficient |

**Key insight:** The project already has all the infrastructure needed. This phase is about wiring ACB math (from legacy `engine/acb.py`) into the PostgreSQL-backed, Decimal-precise, job-queue-driven pattern established in Phases 1-3.

---

## Common Pitfalls

### Pitfall 1: CoinGecko Granularity Mismatch

**What goes wrong:** Code requests minute-level prices but CoinGecko returns hourly data (or daily for old transactions), causing KeyError or wrong price lookup.

**Why it happens:** CoinGecko auto-granularity: data older than 1 day returns hourly; older than 90 days returns daily. "Minute-level" is only available for last 24 hours (5-min) or Enterprise plans.

**How to avoid:** When fetching `market_chart/range`, parse the returned timestamps array — don't assume intervals. Find the closest timestamp to the target. Set `price_estimated=True` when closest available timestamp is more than 15 minutes away from target.

**Warning signs:** `KeyError` on timestamp lookup; always getting identical prices for transactions in the same hour.

### Pitfall 2: NEAR Block Timestamp in Nanoseconds

**What goes wrong:** ACB engine uses NEAR block_timestamp directly as Unix seconds, producing dates in year 2262.

**Why it happens:** NEAR block timestamps are stored in nanoseconds (1e9 * Unix seconds). EVM chains use seconds. This is already documented in the project but easy to miss in new code.

**How to avoid:** When converting to datetime or Unix seconds, divide NEAR timestamps by 1e9. Check chain column on the transaction row.

**Warning signs:** Dates appearing 1000 years in the future; superficial loss window calculations spanning centuries.

### Pitfall 3: Overselling (units > pool)

**What goes wrong:** Dispose operation receives more units than are in the pool, producing negative total_units and negative total_cost.

**Why it happens:** Missing transactions (Phase 1 data gaps), internal transfers not correctly excluded, or transaction ordering errors.

**How to avoid:** Guard in dispose(): if `units > total_units`, clamp to `total_units` and set `needs_review=True` on the snapshot. Do not silently proceed with negative pool.

**Warning signs:** `total_units` going negative in ACB snapshots; very large losses on early transactions.

### Pitfall 4: BoC Rate Not Available for Weekends/Holidays

**What goes wrong:** Transactions on Saturday or Sunday have no BoC FXUSDCAD rate, causing None return and NULL CAD values.

**Why it happens:** Bank of Canada publishes rates only on business days.

**How to avoid:** When BoC returns no observation for a date, look back up to 5 calendar days for the most recent published rate. Use that rate with `price_estimated=True` flag.

**Warning signs:** NULL `fmv_cad` on weekend transactions; large gaps in income ledger.

### Pitfall 5: Duplicate Superficial Loss Detection on Multi-leg Swaps

**What goes wrong:** A swap (sell_leg + buy_leg) triggers superficial loss detection because the buy_leg looks like a rebuy of the token being sold.

**Why it happens:** The buy_leg of a NEAR/token swap is an acquisition of a different token, but if the same token is involved (e.g., unwrap NEAR), it could falsely trigger the 30-day rule.

**How to avoid:** Exclude buy_legs from the same parent transaction when scanning for rebuys. The rebuy check should only fire when a different transaction acquires the same token.

**Warning signs:** Every swap flagging superficial loss on the same token.

### Pitfall 6: Transaction Ordering Tie-Breaking

**What goes wrong:** Two transactions in the same block (same block_timestamp) are processed in wrong order, causing incorrect ACB at the end of the block.

**Why it happens:** SQL `ORDER BY block_timestamp ASC` is non-deterministic for ties; PostgreSQL returns rows in arbitrary order within same timestamp.

**How to avoid:** Secondary sort on transaction ID as tie-breaker: `ORDER BY block_timestamp ASC, id ASC`. This ensures stable, reproducible ordering.

**Warning signs:** ACB results differ between recalculation runs for the same user.

---

## Code Examples

Verified patterns from existing codebase:

### ACBSnapshot DB Write (upsert pattern from price_cache)
```python
# Source: indexers/price_service.py _cache_price() + migration 003 pattern
cur.execute(
    """
    INSERT INTO acb_snapshots (
        user_id, token_symbol, classification_id,
        block_timestamp, event_type,
        units_delta, units_after, cost_cad_delta, total_cost_cad,
        acb_per_unit_cad, proceeds_cad, gain_loss_cad,
        price_estimated, needs_review
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (user_id, token_symbol, classification_id)
    DO UPDATE SET
        acb_per_unit_cad = EXCLUDED.acb_per_unit_cad,
        gain_loss_cad = EXCLUDED.gain_loss_cad,
        updated_at = now()
    """,
    (user_id, symbol, classification_id, ...)
)
conn.commit()
```

### Chronological Transaction Query
```python
# Source: pattern from engine/classifier.py + TransactionClassification model
cur.execute(
    """
    SELECT
        tc.id,
        tc.category,
        tc.leg_type,
        tc.fmv_usd,
        tc.fmv_cad,
        tc.staking_event_id,
        tc.lockup_event_id,
        tc.parent_classification_id,
        t.block_timestamp,
        t.amount,
        t.fee,
        t.token_id,
        t.chain,
        et.asset,
        et.quantity,
        et.fee AS et_fee,
        et.timestamp AS et_timestamp
    FROM transaction_classifications tc
    LEFT JOIN transactions t ON tc.transaction_id = t.id
    LEFT JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
    WHERE tc.user_id = %s
      AND tc.leg_type IN ('parent', 'sell_leg', 'buy_leg', 'fee_leg')
      AND tc.category NOT IN ('spam', 'transfer')
    ORDER BY
        COALESCE(t.block_timestamp, EXTRACT(EPOCH FROM et.timestamp)::BIGINT) ASC,
        tc.id ASC
    """,
    (user_id,)
)
```

### Bank of Canada Valet API Call
```python
# Source: verified from BoC Valet API search results (MEDIUM confidence)
# URL confirmed: https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
import requests
from decimal import Decimal

BOC_VALET_BASE = "https://www.bankofcanada.ca/valet"

def fetch_boc_rate(date_str: str) -> Optional[Decimal]:
    url = f"{BOC_VALET_BASE}/observations/FXUSDCAD/json"
    resp = requests.get(url, params={"start_date": date_str, "end_date": date_str}, timeout=15)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    if observations:
        return Decimal(observations[0]["FXUSDCAD"]["v"])
    return None
```

### CoinGecko market_chart/range Call
```python
# Source: CoinGecko official docs (HIGH confidence)
# Endpoint: /coins/{id}/market_chart/range
# Returns: {"prices": [[timestamp_ms, price], ...], "market_caps": [...], "total_volumes": [...]}

def _fetch_coingecko_range(self, coin_id: str, from_ts: int, to_ts: int, currency: str):
    """
    Fetch price history in [from_ts, to_ts] window (UNIX seconds).
    Returns list of [timestamp_ms, price] pairs.
    Granularity is auto-determined by range size:
      <= 1 day: 5-minute (if recent), else hourly
      1-90 days: hourly
      > 90 days: daily
    """
    base = COINGECKO_PRO_BASE if self.coingecko_api_key else COINGECKO_BASE
    url = f"{base}/coins/{coin_id}/market_chart/range"
    params = {
        "vs_currency": currency,
        "from": from_ts,
        "to": to_ts,
    }
    headers = {}
    if self.coingecko_api_key:
        headers["x-cg-pro-api-key"] = self.coingecko_api_key

    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("prices", [])  # [[ts_ms, price], ...]
```

---

## Schema Design (Claude's Discretion)

### New Tables Required (Migration 004)

**`acb_snapshots`** — Per-transaction ACB state after each acquire/dispose event:
```sql
CREATE TABLE acb_snapshots (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    token_symbol        VARCHAR(32) NOT NULL,          -- e.g. 'NEAR', 'ETH'
    classification_id   INTEGER NOT NULL REFERENCES transaction_classifications(id),
    block_timestamp     BIGINT NOT NULL,               -- for ordering/replay
    event_type          VARCHAR(20) NOT NULL,           -- 'acquire', 'dispose'
    units_delta         NUMERIC(24, 8) NOT NULL,        -- positive=acquire, negative=dispose
    units_after         NUMERIC(24, 8) NOT NULL,        -- running total after event
    cost_cad_delta      NUMERIC(24, 8) NOT NULL,        -- change to ACB pool
    total_cost_cad      NUMERIC(24, 8) NOT NULL,        -- running total cost after event
    acb_per_unit_cad    NUMERIC(24, 8) NOT NULL,        -- snapshot of ACB/unit after event
    proceeds_cad        NUMERIC(24, 8) NULL,            -- for dispose events only
    gain_loss_cad       NUMERIC(24, 8) NULL,            -- for dispose events only
    price_usd           NUMERIC(18, 8) NULL,
    price_cad           NUMERIC(18, 8) NULL,
    price_estimated     BOOLEAN NOT NULL DEFAULT FALSE, -- True if closest-available, not exact
    needs_review        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, token_symbol, classification_id)
);
```

**`capital_gains_ledger`** — One row per disposal event with full gain/loss detail:
```sql
CREATE TABLE capital_gains_ledger (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    acb_snapshot_id     INTEGER NOT NULL REFERENCES acb_snapshots(id),
    token_symbol        VARCHAR(32) NOT NULL,
    disposal_date       DATE NOT NULL,
    block_timestamp     BIGINT NOT NULL,
    units_disposed      NUMERIC(24, 8) NOT NULL,
    proceeds_cad        NUMERIC(24, 8) NOT NULL,
    acb_used_cad        NUMERIC(24, 8) NOT NULL,
    fees_cad            NUMERIC(24, 8) NOT NULL DEFAULT 0,
    gain_loss_cad       NUMERIC(24, 8) NOT NULL,
    is_superficial_loss BOOLEAN NOT NULL DEFAULT FALSE,
    denied_loss_cad     NUMERIC(24, 8) NULL,           -- amount denied if superficial
    needs_review        BOOLEAN NOT NULL DEFAULT FALSE,
    tax_year            SMALLINT NOT NULL,              -- extracted from disposal_date
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (acb_snapshot_id)
);
```

**`income_ledger`** — One row per income event (staking reward, lockup vest):
```sql
CREATE TABLE income_ledger (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    source_type         VARCHAR(20) NOT NULL,           -- 'staking', 'vesting', 'airdrop', 'other'
    staking_event_id    INTEGER NULL REFERENCES staking_events(id),
    lockup_event_id     INTEGER NULL REFERENCES lockup_events(id),
    classification_id   INTEGER NULL REFERENCES transaction_classifications(id),
    token_symbol        VARCHAR(32) NOT NULL,
    income_date         DATE NOT NULL,
    block_timestamp     BIGINT NOT NULL,
    units_received      NUMERIC(24, 8) NOT NULL,
    fmv_usd             NUMERIC(18, 8) NOT NULL,
    fmv_cad             NUMERIC(18, 8) NOT NULL,
    acb_added_cad       NUMERIC(24, 8) NOT NULL,       -- = fmv_cad (income cost basis = FMV at receipt)
    tax_year            SMALLINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**`price_cache_minute`** — Separate table for minute/hourly price data (avoids collisions with daily `price_cache`):
```sql
CREATE TABLE price_cache_minute (
    id          SERIAL PRIMARY KEY,
    coin_id     VARCHAR(64) NOT NULL,
    unix_ts     BIGINT NOT NULL,                       -- UNIX seconds, rounded to minute
    currency    VARCHAR(10) NOT NULL,
    price       NUMERIC(24, 10) NOT NULL,
    source      VARCHAR(32) NULL,
    is_estimated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (coin_id, unix_ts, currency)
);
```

### Cache Invalidation Strategy (Claude's Discretion)

Recommendation: **dirty flag on user scope**. Add `acb_calculated_at TIMESTAMPTZ NULL` to users table (or a separate `acb_state` table). Set it to `NULL` when new transactions/classifications are inserted. ACBHandler checks this flag at job start; if NULL or older than last classification, runs full replay.

Alternative: version counter (`acb_version INTEGER`) that increments on any transaction change — simpler to check but requires additional UPDATE on every classification write.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `float`-based ACB (`engine/acb.py`) | `Decimal`-based with `ROUND_HALF_UP` | Phase 4 | Eliminates compounding float errors on 23,000+ transactions |
| Daily price lookup only | Hourly (auto-granularity from CoinGecko) for ACB | Phase 4 | Closer price to actual transaction time |
| CryptoCompare USDT→CAD fallback | Bank of Canada Valet API FXUSDCAD | Phase 4 | CRA-preferred authoritative source; no API key required |
| In-memory ACB (no persistence) | PostgreSQL `acb_snapshots` table | Phase 4 | Full audit trail; no re-replay on every API call |
| Superficial loss flagging only | Auto-calculate denied amount + ACB adjustment proposal | Phase 4 | Specialist gets proposed numbers, not just flags |

**Deprecated/outdated:**
- `engine/prices.py` (SQLite-based): already superseded by `indexers/price_service.py`. Do not extend.
- `engine/acb.py` (float-based): rewrite as `ACBEngine` class — do not add features to old version.

---

## Open Questions

1. **CoinGecko tier for this project**
   - What we know: The project has a `COINGECKO_API_KEY` config variable; free tier = 30 calls/min
   - What's unclear: Whether the key is a Pro/Enterprise key (affects whether 5-minute interval is available vs hourly only)
   - Recommendation: Design for hourly granularity as the minimum guarantee; use "closest price" lookup regardless of tier. If Enterprise key available, pass `interval=5m` param to get 5-minute data.

2. **Token symbol normalization for ACB pooling**
   - What we know: NEAR transactions use token_id (contract address), exchanges use asset string (e.g., "NEAR", "ETH")
   - What's unclear: How to reliably map `token_id = "wrap.near"` → symbol `NEAR`, or `token_id = "0xa0b86991c6218..."` → `USDC`
   - Recommendation: Build a token_symbol_map (config dict or DB table) mapping known contract addresses to canonical symbols. Flag unmapped tokens for specialist review.

3. **Stablecoin FMV for ACB acquisitions from exchanges**
   - What we know: Exchange transactions use fiat amounts (USDC used at ~$1); stablecoin flag is configurable
   - What's unclear: When an exchange TX acquires USDC, should ACB use $1 CAD equivalent or fetch real price?
   - Recommendation: Default to 1:1 for USDT/USDC/DAI as decided. Apply CAD/USD rate to get CAD ACB cost. Specialist can override per-token via stablecoin configuration.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (inferred from tests/ structure; no pytest.ini found — runs with `pytest tests/`) |
| Config file | none — pytest auto-discovers `tests/` directory |
| Quick run command | `cd /home/vitalpointai/projects/Axiom && python -m pytest tests/test_acb.py -x -q` |
| Full suite command | `cd /home/vitalpointai/projects/Axiom && python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACB-01 | Average cost method: acquire + dispose → correct ACB per unit | unit | `pytest tests/test_acb.py::TestACBPool -x` | ❌ Wave 0 |
| ACB-01 | Multi-acquisition: ACB pools across 3+ buys at different prices | unit | `pytest tests/test_acb.py::TestACBPool::test_multi_acquire -x` | ❌ Wave 0 |
| ACB-02 | Cross-wallet pooling: two wallets same token → single ACB pool | unit | `pytest tests/test_acb.py::TestACBEngine::test_cross_wallet_pool -x` | ❌ Wave 0 |
| ACB-03 | Staking FMV passthrough: uses pre-captured fmv_cad from StakingEvent | unit | `pytest tests/test_acb.py::TestACBEngine::test_staking_income_fmv -x` | ❌ Wave 0 |
| ACB-03 | PriceService.get_price_at_timestamp: cache hit returns (price, False) | unit | `pytest tests/test_price_service.py::TestMinutePriceCache -x` | ❌ Wave 0 |
| ACB-03 | PriceService.get_boc_cad_rate: BoC API fetched and cached | unit | `pytest tests/test_price_service.py::TestBoCRate -x` | ❌ Wave 0 |
| ACB-04 | Fee on acquisition: fee added to total_cost_cad pool | unit | `pytest tests/test_acb.py::TestACBPool::test_acquire_with_fee -x` | ❌ Wave 0 |
| ACB-04 | Fee on disposal: fee deducted from proceeds before gain/loss | unit | `pytest tests/test_acb.py::TestACBPool::test_dispose_with_fee -x` | ❌ Wave 0 |
| ACB-04 | Swap fee_leg adds to buy_leg ACB | unit | `pytest tests/test_acb.py::TestACBEngine::test_swap_fee_leg_acb -x` | ❌ Wave 0 |
| ACB-05 | Superficial loss: detect rebuy within 30 days → flag + calculate denied amount | unit | `pytest tests/test_superficial.py::TestSuperficialLoss::test_full_rebuy_denial -x` | ❌ Wave 0 |
| ACB-05 | Superficial loss pro-rate: partial rebuy → proportional denial | unit | `pytest tests/test_superficial.py::TestSuperficialLoss::test_partial_rebuy_prorated -x` | ❌ Wave 0 |
| ACB-05 | Superficial loss cross-exchange: exchange rebuy triggers detection | unit | `pytest tests/test_superficial.py::TestSuperficialLoss::test_exchange_rebuy -x` | ❌ Wave 0 |
| ACB-05 | No superficial loss when no rebuy in window | unit | `pytest tests/test_superficial.py::TestSuperficialLoss::test_no_rebuy_no_flag -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_acb.py tests/test_superficial.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_acb.py` — covers ACB-01, ACB-02, ACB-03, ACB-04; mocked psycopg2 pool
- [ ] `tests/test_superficial.py` — covers ACB-05; mocked pool with synthetic disposal + acquisition rows
- [ ] `tests/test_price_service.py` needs new test classes: `TestMinutePriceCache`, `TestBoCRate`, `TestCoinGeckoRange` — extends existing test file

---

## Sources

### Primary (HIGH confidence)
- `engine/acb.py` (project codebase) — existing ACB math logic, acquire/dispose/superficial_loss patterns
- `db/models.py` (project codebase) — all existing model patterns, NUMERIC precision conventions
- `indexers/price_service.py` (project codebase) — PriceService architecture, caching pattern
- `indexers/classifier_handler.py` (project codebase) — job handler registration pattern
- [CoinGecko market_chart/range docs](https://docs.coingecko.com/reference/coins-id-market-chart-range) — auto-granularity rules, endpoint format

### Secondary (MEDIUM confidence)
- [Bank of Canada Valet API endpoint](https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json) — URL pattern confirmed from multiple search results including actual example URLs
- [CRA crypto ACB rules (Koinly)](https://koinly.io/blog/calculating-crypto-taxes-canada/) — average cost method requirements, superficial loss 61-day window
- [CoinTracking superficial loss](https://cointracking.info/crypto-taxes-ca/superficial-loss-rule) — pro-rated partial rebuy treatment

### Tertiary (LOW confidence)
- CoinGecko Enterprise plan details — 5-minute granularity via `interval=5m` param; not directly verified from official API reference

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages already in requirements.txt
- ACB math/Canadian tax rules: HIGH — verified against multiple CRA-aligned sources + existing code
- CoinGecko API granularity: HIGH — verified from official docs
- Bank of Canada Valet API URL format: MEDIUM — confirmed from search result URLs + how-to guide, exact JSON structure needs runtime verification
- Architecture/schema: MEDIUM — follows established project patterns, discretionary design choices not yet reviewed by specialist

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (30-day window; CoinGecko API tier changes could affect granularity assumptions)
