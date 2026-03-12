---
phase: 04-cost-basis-engine
plan: "01"
subsystem: database
tags: [postgres, alembic, sqlalchemy, coingecko, bank-of-canada, acb, capital-gains]

# Dependency graph
requires:
  - phase: 03-transaction-classification
    provides: TransactionClassification rows that acb_snapshots.classification_id references
provides:
  - Alembic migration 004 with acb_snapshots, capital_gains_ledger, income_ledger, price_cache_minute tables
  - ACBSnapshot, CapitalGainsLedger, IncomeLedger, PriceCacheMinute SQLAlchemy models
  - PriceService.get_price_at_timestamp() with minute-level cache in price_cache_minute
  - PriceService.get_boc_cad_rate() via Bank of Canada Valet API with weekend fallback
  - PriceService.get_price_cad_at_timestamp() convenience method
  - Test scaffolds for ACBPool, ACBEngine, SuperficialLossDetector (Wave 2 plans)
affects:
  - 04-02-PLAN.md (ACBEngine + SuperficialLossDetector implementation)
  - 04-03-PLAN.md (reporting layer)

# Tech tracking
tech-stack:
  added:
    - Bank of Canada Valet API (FXUSDCAD series, no auth required)
    - CoinGecko market_chart/range endpoint (minute-level price data)
  patterns:
    - Minute-level price cache: INSERT ON CONFLICT DO NOTHING in price_cache_minute
    - BoC weekend/holiday fallback: look back up to 5 business days for most recent rate
    - Stablecoin shortcut: STABLECOIN_MAP returns Decimal("1") without API call
    - is_estimated flag: True when closest CoinGecko data point is >15 min (900s) from target

key-files:
  created:
    - db/migrations/versions/004_cost_basis_schema.py
    - tests/test_acb.py
    - tests/test_superficial.py
  modified:
    - db/models.py
    - indexers/price_service.py
    - tests/test_price_service.py

key-decisions:
  - "price_cache_minute as separate table from daily price_cache — different granularity, schema, and retention needs"
  - "INSERT ON CONFLICT DO NOTHING for minute cache — concurrent requests safely silenced, no overwrite"
  - "is_estimated=True when CoinGecko data point gap >15 min (900s) — tax-safe: flags prices needing review"
  - "BoC Valet API replaces CryptoCompare for CAD rates — authoritative Canadian source for tax purposes"
  - "5-day lookback for BoC weekend/holiday gaps — covers long weekends without excessive API calls"
  - "STABLECOIN_MAP shortcut avoids API calls for tether/usd-coin/dai — always 1:1 USD"
  - "get_price_cad_at_timestamp() convenience method — ACBEngine calls one method vs two"

patterns-established:
  - "ACB table pattern: user_id + token_symbol + classification_id UNIQUE — one snapshot per classification event"
  - "tax_year as SmallInteger — year fits in 2 bytes, enables efficient index scans for annual reports"
  - "acb_added_cad = fmv_cad in IncomeLedger — income FMV at receipt is cost basis for acquired units"
  - "CapitalGainsLedger.acb_snapshot_id UNIQUE — one ledger row per disposal snapshot"

requirements-completed: [ACB-03]

# Metrics
duration: 6min
completed: 2026-03-12
---

# Phase 4 Plan 01: Cost Basis Schema + Price Infrastructure Summary

**Alembic migration 004 with 4 ACB tables, 4 SQLAlchemy models, CoinGecko timestamp prices with minute cache, and Bank of Canada Valet API CAD rates with weekend fallback**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-12T23:21:11Z
- **Completed:** 2026-03-12T23:27:xx Z
- **Tasks:** 2 of 2
- **Files modified:** 5

## Accomplishments

- Migration 004 creates acb_snapshots (ACB state machine), capital_gains_ledger (one row per disposal), income_ledger (staking/vesting/airdrop), and price_cache_minute (minute-level cache) with correct FKs and indexes
- Four SQLAlchemy models (ACBSnapshot, CapitalGainsLedger, IncomeLedger, PriceCacheMinute) match migration schema exactly; ACBSnapshot.capital_gains_entry and CapitalGainsLedger.acb_snapshot relationship pair wired
- PriceService extended with three new methods: get_price_at_timestamp() using CoinGecko market_chart/range with minute-level DB cache, get_boc_cad_rate() using Bank of Canada Valet API with 5-day weekend/holiday fallback, get_price_cad_at_timestamp() combining both
- Test scaffolds created: 6 ACBPool tests + 4 ACBEngine tests in test_acb.py, 5 SuperficialLoss tests in test_superficial.py, 15 new tests in test_price_service.py (TestMinutePriceCache, TestBoCRate, TestCoinGeckoRange) — 176 total passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration 004 + SQLAlchemy models for cost basis schema** - `1b08425` (feat)
2. **Task 2: Extend PriceService with minute-level prices and Bank of Canada CAD rates + test scaffolds** - `70cbd35` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `db/migrations/versions/004_cost_basis_schema.py` - Alembic migration 004 creating 4 cost basis tables
- `db/models.py` - Added ACBSnapshot, CapitalGainsLedger, IncomeLedger, PriceCacheMinute models; added SmallInteger import
- `indexers/price_service.py` - Added BOC_VALET_BASE, STABLECOIN_MAP, _ESTIMATION_GAP_SECONDS constants; added 3 public methods and 4 private helpers
- `tests/test_price_service.py` - Added TestMinutePriceCache (3 tests), TestBoCRate (4 tests), TestCoinGeckoRange (3 tests)
- `tests/test_acb.py` - New file: TestACBPool (6 scaffolds), TestACBEngine (4 scaffolds)
- `tests/test_superficial.py` - New file: TestSuperficialLoss (5 scaffolds)

## Decisions Made

- Used Bank of Canada Valet API instead of CryptoCompare for CAD rates — BoC is the authoritative source for Canadian tax purposes; CryptoCompare approximation with USDT remains in existing get_cad_rate()
- price_cache_minute as a separate table from the daily price_cache — different schema (unix_ts BigInteger vs Date), different retention, different cardinality per query
- INSERT ON CONFLICT DO NOTHING for minute cache — simpler than DO UPDATE and prevents accidental overwrites when concurrent requests race to cache the same minute
- is_estimated threshold at 15 minutes (900 seconds) — matches plan spec; flags prices for review without being overly aggressive on markets with infrequent ticks

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Bank of Canada Valet API requires no authentication.

## Next Phase Readiness

- Migration 004 ready for `alembic upgrade head` when DB is available
- PriceService.get_price_at_timestamp() and get_boc_cad_rate() ready for ACBEngine to call in Plan 04-02
- Test scaffolds in test_acb.py and test_superficial.py ready for Wave 2 implementation to fill in

---
*Phase: 04-cost-basis-engine*
*Completed: 2026-03-12*
