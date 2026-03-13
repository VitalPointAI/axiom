---
phase: 05-verification
plan: 01
subsystem: database, verification
tags: [alembic, postgresql, sqlalchemy, verification, reconciliation, pipeline]

# Dependency graph
requires:
  - phase: 04-cost-basis-engine
    provides: ACBHandler pipeline chaining pattern, acb_snapshots table
provides:
  - verification_results and account_verification_status tables (migration 005)
  - VerificationResult and AccountVerificationStatus SQLAlchemy models
  - VerifyHandler skeleton registered in IndexerService
  - ACB -> verify_balances pipeline chaining
  - RECONCILIATION_TOLERANCES config dict
affects: [05-02-balance-reconciler, 05-03-duplicate-detector, 05-04-gap-finder, 07-web-ui]

# Tech tracking
tech-stack:
  added: []
  patterns: [verify_balances job type in pipeline, upsert pattern for account status rollup]

key-files:
  created:
    - db/migrations/versions/005_verification_schema.py
    - indexers/verify_handler.py
  modified:
    - db/models.py
    - indexers/service.py
    - indexers/acb_handler.py
    - config.py

key-decisions:
  - "UniqueConstraint(wallet_id, token_symbol) on verification_results for upsert-per-run pattern"
  - "verify_balances priority=4 (lower than ACB at 5) -- runs last in pipeline"
  - "RECONCILIATION_TOLERANCES as string values for clean Decimal conversion"
  - "VerifyHandler takes pool only (no price_service) -- verification reads existing data"

patterns-established:
  - "Pipeline chain: classify -> ACB -> verify_balances (3-stage post-indexing)"
  - "Account status rollup via INSERT ON CONFLICT upsert pattern"

requirements-completed: [VER-01, VER-02]

# Metrics
duration: 3min
completed: 2026-03-13
---

# Phase 5 Plan 01: Verification Schema + Handler Wiring Summary

**Migration 005 with verification_results/account_verification_status tables, VerifyHandler skeleton registered in IndexerService, ACBHandler auto-queues verify_balances after ACB completes, RECONCILIATION_TOLERANCES configurable per chain**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-13T12:04:44Z
- **Completed:** 2026-03-13T12:07:22Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Migration 005 creates verification_results (balance components, NEAR decomposed, diagnosis, status) and account_verification_status (per-wallet rollup) tables
- VerifyHandler skeleton with run_verify() orchestration and _update_account_status() upsert logic
- Full pipeline wiring: ACBHandler auto-queues verify_balances -> IndexerService dispatches to VerifyHandler
- RECONCILIATION_TOLERANCES dict in config.py with 5 chain entries (string values for Decimal precision)

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration 005 + SQLAlchemy models** - `dc9d5fb` (feat)
2. **Task 2: VerifyHandler + service wiring + ACB chaining + config** - `50fdd2e` (feat)

## Files Created/Modified
- `db/migrations/versions/005_verification_schema.py` - Alembic migration creating verification_results and account_verification_status tables
- `db/models.py` - Added VerificationResult and AccountVerificationStatus SQLAlchemy models
- `indexers/verify_handler.py` - VerifyHandler job handler skeleton with run_verify() and _update_account_status()
- `indexers/service.py` - Registered verify_balances handler and dispatch
- `indexers/acb_handler.py` - Added pipeline chaining to queue verify_balances after ACB completes
- `config.py` - Added RECONCILIATION_TOLERANCES dict with per-chain thresholds

## Decisions Made
- UniqueConstraint(wallet_id, token_symbol) on verification_results enables upsert-per-run pattern (one active result per wallet+token)
- verify_balances priority=4 (lower than ACB at 5) ensures verification runs last in the pipeline
- RECONCILIATION_TOLERANCES stored as string values to convert cleanly to Decimal without float precision issues
- VerifyHandler takes pool only (no price_service needed) since verification reads existing computed data

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Schema foundation ready for Plans 02-04 to implement reconciler, duplicate detector, and gap finder
- VerifyHandler skeleton has placeholder steps for each module -- Plans 02-04 will add imports and calls
- Pipeline fully wired: classify -> ACB -> verify_balances chain operational

## Self-Check: PASSED

All 6 files verified present. Both task commits (dc9d5fb, 50fdd2e) confirmed in git log.

---
*Phase: 05-verification*
*Completed: 2026-03-13*
