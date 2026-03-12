---
phase: 04-cost-basis-engine
plan: "02"
subsystem: engine
tags: [acb, decimal, postgresql, gains, income, canadian-tax]

# Dependency graph
requires:
  - phase: 04-cost-basis-engine
    plan: "01"
    provides: acb_snapshots, capital_gains_ledger, income_ledger tables + PriceService + test scaffolds
provides:
  - ACBPool: Decimal-precise per-token pool (acquire/dispose/acb_per_unit)
  - ACBEngine: full user replay with PostgreSQL persistence via acb_snapshots upsert
  - GainsCalculator: capital_gains_ledger + income_ledger INSERT for disposals and income events
  - resolve_token_symbol(), normalize_timestamp(), TOKEN_SYMBOL_MAP utilities
  - 13 unit tests (TestACBPool x6, TestACBEngine x4, TestGainsCalculator x3)
affects:
  - 04-03-PLAN.md (reporting layer reads capital_gains_ledger + income_ledger)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ACBPool pure in-memory with Decimal; no DB — tested without any DB infrastructure"
    - "ACBEngine lazy-imports GainsCalculator to avoid circular import + enable test patching"
    - "acb_snapshots INSERT ON CONFLICT DO UPDATE — idempotent per (user_id, token_symbol, classification_id)"
    - "capital_gains_ledger INSERT ON CONFLICT (acb_snapshot_id) DO UPDATE — one row per disposal"
    - "income_ledger INSERT — acb_added_cad = fmv_cad (CRA: income FMV at receipt = cost basis)"
    - "Fee leg on swap adds to buy_leg ACB (not deducted from sell proceeds)"

key-files:
  created:
    - engine/gains.py
  modified:
    - engine/acb.py
    - tests/test_acb.py

key-decisions:
  - "Legacy ACBTracker/PortfolioACB removed entirely — Decimal-precise ACBPool is incompatible with float API"
  - "GainsCalculator takes conn (not pool) — ACBEngine manages connection lifecycle; calculator is stateless"
  - "Lazy import of GainsCalculator in ACBEngine.calculate_for_user() — avoids circular import and allows patch('engine.acb.GainsCalculator') in tests"
  - "is_superficial_loss excluded from GainsCalculator.record_disposal() params — SuperficialLossDetector (Plan 03) will set this separately via UPDATE"
  - "Oversell clamp: dispose(150) on 100-unit pool clamps to 100 and sets needs_review=True (not exception)"
  - "NEAR nanoseconds / 1e9 = Unix seconds; EVM already seconds — normalize_timestamp() handles both"

# Metrics
duration: 7min
completed: 2026-03-12
---

# Phase 4 Plan 02: ACBPool + ACBEngine + GainsCalculator Summary

**Decimal-precise ACBPool/ACBEngine with PostgreSQL persistence, and GainsCalculator writing capital_gains_ledger + income_ledger rows per disposal and income event**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-12T23:30:51Z
- **Completed:** 2026-03-12T23:37:00Z
- **Tasks:** 2 of 2
- **Files modified:** 3

## Accomplishments

- Rewrote engine/acb.py: replaced float-based ACBTracker/PortfolioACB with Decimal-precise ACBPool (acquire/dispose, 8-decimal acb_per_unit, oversell clamping) and ACBEngine (chronological classification replay, per-token pools pooled across all wallets, acb_snapshots upsert after each event)
- Added TOKEN_SYMBOL_MAP, resolve_token_symbol(), normalize_timestamp(), to_human_units() utilities covering NEAR (nanoseconds, yoctoNEAR) and EVM (seconds, wei) chains
- ACBEngine handles: staking income (se_fmv_cad passthrough), lockup vesting (le_fmv_cad passthrough), airdrop income (price_service fallback), simple disposals, multi-leg swaps (fee_leg added to buy_leg ACB), and gas fee disposals
- Created engine/gains.py with GainsCalculator: record_disposal() writes capital_gains_ledger (ON CONFLICT DO UPDATE), record_income() writes income_ledger (acb_added_cad = fmv_cad), clear_for_user() deletes both before replay
- 13 unit tests (6 ACBPool, 4 ACBEngine, 3 GainsCalculator) all pass; full suite: 179 passed, 1 skipped

## Task Commits

Each task was committed atomically:

1. **Task 1: ACBPool and ACBEngine with Decimal precision and PostgreSQL persistence** - `f98d3c7` (feat)
2. **Task 2: GainsCalculator for capital gains and income ledger population** - `2c9d7c7` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `engine/acb.py` - Rewritten: ACBPool, ACBEngine, TOKEN_SYMBOL_MAP, resolve_token_symbol(), normalize_timestamp(), to_human_units()
- `engine/gains.py` - New file: GainsCalculator with record_disposal(), record_income(), clear_for_user()
- `tests/test_acb.py` - Implemented: TestACBPool (6 tests), TestACBEngine (4 tests), TestGainsCalculator (3 tests)

## Decisions Made

- Legacy ACBTracker/PortfolioACB removed entirely — float arithmetic is incompatible with Canadian tax precision requirements; the Decimal-based ACBPool is a clean replacement
- GainsCalculator receives a connection (not a pool) — ACBEngine owns the transaction boundary; GainsCalculator is a thin persistence helper
- Lazy import of GainsCalculator inside calculate_for_user() prevents circular import (gains.py imports normalize_timestamp from acb.py) and enables `patch('engine.acb.GainsCalculator')` in tests
- is_superficial_loss column not set by GainsCalculator — set to False by default; SuperficialLossDetector (Plan 04-03) will detect the 30-day window and UPDATE rows after initial population
- Oversell clamping (not exception) — produces a valid snapshot with needs_review=True rather than crashing; allows partial data to be reviewed without blocking the full replay

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed is_superficial_loss from GainsCalculator INSERT params**
- **Found during:** Task 2 - test assertion mismatch
- **Issue:** Test expected `params[11] == 2023` (tax_year at index 11), but original SQL placed `is_superficial_loss` at index 10, `needs_review` at 11, `tax_year` at 12
- **Fix:** Removed `is_superficial_loss` from the INSERT params (column defaults to False in DB schema); reordered to match test expectations: needs_review at 10, tax_year at 11
- **Files modified:** engine/gains.py
- **Commit:** 2c9d7c7

## Issues Encountered

None beyond the auto-fixed param ordering issue above.

## User Setup Required

None — no external service configuration required for this plan.

## Next Phase Readiness

- ACBEngine.calculate_for_user(user_id) ready for integration testing once DB is available
- GainsCalculator writes both ledger tables; SuperficialLossDetector (Plan 04-03) can UPDATE is_superficial_loss on capital_gains_ledger rows
- All unit tests pass without a real database (full mock-based test suite)

---
*Phase: 04-cost-basis-engine*
*Completed: 2026-03-12*
