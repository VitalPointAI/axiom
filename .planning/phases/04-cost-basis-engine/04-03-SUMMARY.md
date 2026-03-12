---
phase: 04-cost-basis-engine
plan: 03
subsystem: engine
tags: [python, acb, superficial-loss, canadian-tax, psycopg2, job-queue]

# Dependency graph
requires:
  - phase: 04-cost-basis-engine/04-02
    provides: "ACBEngine.calculate_for_user(), GainsCalculator, acb_snapshots + capital_gains_ledger schema"
  - phase: 03-transaction-classification/03-05
    provides: "ClassifierHandler, IndexerService job dispatch pattern, classification pipeline"

provides:
  - "SuperficialLossDetector: CRA 30-day window detection with pro-rated partial rebuy denial"
  - "ACBHandler: job handler for 'calculate_acb' job type in IndexerService"
  - "IndexerService: 'calculate_acb' registered as 13th job type"
  - "ClassifierHandler: auto-queues calculate_acb after classification completes"
  - "ACBEngine.calculate_for_user(): superficial loss pass integrated at end of replay"

affects:
  - "05-verification"
  - "06-reporting"
  - "phase-07-web-ui"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SuperficialLossDetector injected with psycopg2 conn (not pool) — consistent with GainsCalculator pattern"
    - "Lazy import of engine.superficial in ACBEngine to avoid circular imports"
    - "Cross-source rebuy detection: JOIN transactions + exchange_transactions in window query"
    - "Dedup guard before job insert: SELECT existing job before INSERT INTO indexing_jobs"
    - "denied_ratio = min(1, rebought/sold) for partial rebuy pro-rating"

key-files:
  created:
    - engine/superficial.py
    - indexers/acb_handler.py
    - tests/test_superficial.py
  modified:
    - engine/acb.py
    - indexers/service.py
    - indexers/classifier_handler.py

key-decisions:
  - "SuperficialLossDetector takes conn not pool — ACBEngine owns the transaction boundary; detector is stateless helper"
  - "scan_for_user() returns list, apply_superficial_losses() separate step — allows dry-run inspection before persistence"
  - "needs_review=True on all superficial losses — specialist confirmation required before finalizing CRA submission"
  - "denied_loss quantized to 2 decimal places (Decimal('0.01')) — monetary precision for tax reporting"
  - "Dedup check on calculate_acb job insert — prevents duplicate ACB recalcs for concurrent classify_transactions jobs"
  - "ACBEngine.stats['superficial_losses'] added — ACBHandler log includes count for observability"

patterns-established:
  - "Token rebuy exclusion by parent_classification_id — swap legs never self-trigger superficial loss"
  - "Job auto-queue pattern: handler queues downstream job type after completing its own work"

requirements-completed: [ACB-05, ACB-01, ACB-02, ACB-03, ACB-04]

# Metrics
duration: 5min
completed: 2026-03-12
---

# Phase 4 Plan 3: Superficial Loss Detection + ACBHandler + Pipeline Wiring Summary

**SuperficialLossDetector with CRA 30-day cross-source rebuy detection and pro-rated denial, ACBHandler job type registered in IndexerService, ClassifierHandler auto-triggering ACB recalculation**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-12T23:42:11Z
- **Completed:** 2026-03-12T23:46:51Z
- **Tasks:** 2 (Task 1 TDD: 3 commits; Task 2: 1 commit)
- **Files modified:** 6

## Accomplishments
- SuperficialLossDetector detects CRA 30-day window rebuys (30 days before + 30 after disposal) across all on-chain wallets and exchange accounts, with pro-rated denial for partial rebuys
- ACBHandler wraps ACBEngine.calculate_for_user() as a job handler for the IndexerService queue; all stats logged including superficial_losses count
- ClassifierHandler now auto-queues a 'calculate_acb' job after classification completes, with dedup guard to avoid double-queueing when multiple wallets classify simultaneously

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for SuperficialLossDetector** - `59ecf9e` (test)
2. **Task 1 GREEN: SuperficialLossDetector implementation** - `d73143c` (feat)
3. **Task 2: ACBHandler + service wiring + classifier trigger** - `4d08a2d` (feat)

**Plan metadata:** _(docs commit follows)_

_Note: Task 1 used TDD: test commit then implementation commit._

## Files Created/Modified
- `engine/superficial.py` - SuperficialLossDetector with scan_for_user() and apply_superficial_losses(); 61-day window, pro-rated denial, needs_review=True
- `engine/acb.py` - Added superficial loss pass at end of calculate_for_user(); stats['superficial_losses'] count added
- `indexers/acb_handler.py` - ACBHandler.run_calculate_acb() delegates to ACBEngine; logs all stats
- `indexers/service.py` - Import ACBHandler, register 'calculate_acb' handler, add dispatch case
- `indexers/classifier_handler.py` - Queue calculate_acb job after classification with dedup check
- `tests/test_superficial.py` - 8 unit tests covering all superficial loss scenarios

## Decisions Made
- SuperficialLossDetector takes conn not pool — ACBEngine owns the transaction boundary; detector is a stateless persistence helper (consistent with GainsCalculator pattern)
- scan_for_user() returns list, apply_superficial_losses() is a separate method — allows dry-run inspection before persistence
- needs_review=True on all detected superficial losses — CRA ITA s.54 cases require specialist confirmation before finalizing tax submission
- denied_loss quantized to 2 decimal places — monetary precision appropriate for tax reporting
- Dedup check before calculate_acb job INSERT — prevents duplicate recalculations when classify_transactions jobs run for multiple wallets of same user

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 4 cost basis engine is complete: ACB snapshots, capital gains ledger, income ledger, superficial loss detection, and job queue integration all wired
- Phase 5 (Verification) can now read from capital_gains_ledger and income_ledger for reconciliation checks
- Phase 6 (Reporting) can read superficial loss flags (is_superficial_loss, denied_loss_cad) for CRA Schedule 3 output
- All 182 tests pass (1 skipped)

---
*Phase: 04-cost-basis-engine*
*Completed: 2026-03-12*
