---
phase: 05-verification
plan: 04
subsystem: verification
tags: [gap-detection, archival-rpc, discrepancy-report, near, reindex, pipeline-wiring]

# Dependency graph
requires:
  - phase: 05-verification/05-01
    provides: verification_results table, VerifyHandler skeleton, RECONCILIATION_TOLERANCES config
  - phase: 05-verification/05-02
    provides: BalanceReconciler class with reconcile_user()
  - phase: 05-verification/05-03
    provides: DuplicateDetector class with scan_user()
provides:
  - GapDetector class for missing transaction inference via archival NEAR RPC
  - DiscrepancyReporter class for DISCREPANCIES.md generation
  - VerifyHandler fully wired with all four verification modules
  - Full classify -> ACB -> verify pipeline operational end-to-end
affects: [06-reporting, 07-web-ui]

# Tech tracking
tech-stack:
  added: []
  patterns: [monthly balance checkpoint series for gap inference, archival RPC relative delta comparison, lazy imports in handler for module decoupling]

key-files:
  created:
    - verify/gaps.py
    - verify/report.py
  modified:
    - indexers/verify_handler.py

key-decisions:
  - "Archival balance is liquid only; compare relative deltas between checkpoints rather than absolute values"
  - "Gap threshold at 2x tolerance (confidence 0.60) since archival liquid balance is an approximation"
  - "Re-index job priority 3 (moderate -- below regular sync at 5, above background)"
  - "Lazy imports in VerifyHandler.run_verify() to match ACBHandler pattern and avoid circular imports"
  - "DISCREPANCIES.md report grouped by category: reconciliation, duplicates, gaps"

patterns-established:
  - "Monthly checkpoint balance series: group transactions by calendar month, compute running balance per month"
  - "Archival RPC relative delta comparison: delta_indexed vs delta_onchain catches gaps without absolute balance accuracy"
  - "Report generation from verification_results with category-based grouping"

requirements-completed: [VER-04, VER-01, VER-02, VER-03]

# Metrics
duration: 3min
completed: 2026-03-13
---

# Phase 5 Plan 04: Gap Finder + Report Summary

**GapDetector with monthly balance checkpoints vs archival NEAR RPC relative deltas, DiscrepancyReporter for DISCREPANCIES.md generation, and VerifyHandler fully wired with all four verification modules (reconciler + duplicates + gaps + report)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-13T12:18:08Z
- **Completed:** 2026-03-13T12:21:32Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- GapDetector (432 lines): builds monthly balance series from transactions, queries archival NEAR RPC at each checkpoint, identifies gaps where relative balance deltas diverge by >2x tolerance, queues targeted re-index jobs
- DiscrepancyReporter (350 lines): queries all open/flagged verification_results, generates structured DISCREPANCIES.md with summary table, reconciliation issues, duplicate merge log, gap detection results, and investigation notes section
- VerifyHandler.run_verify() fully wired with lazy imports: BalanceReconciler -> DuplicateDetector -> GapDetector -> _update_account_status -> DiscrepancyReporter
- Phase 5 verification pipeline complete: classify -> ACB -> verify_balances chain operational end-to-end

## Task Commits

Each task was committed atomically:

1. **Task 1: GapDetector -- balance series + archival RPC + re-index queuing** - `53e936c` (feat)
2. **Task 2: DiscrepancyReporter + VerifyHandler final wiring** - `d394aca` (feat)

## Files Created/Modified
- `verify/gaps.py` - GapDetector class: monthly checkpoint balance series, archival NEAR RPC comparison, targeted re-index job queuing (432 lines)
- `verify/report.py` - DiscrepancyReporter class: DISCREPANCIES.md generation from open verification_results with category grouping (350 lines)
- `indexers/verify_handler.py` - VerifyHandler.run_verify() fully wired with lazy imports for all four verification modules

## Decisions Made
- Compare relative balance deltas (checkpoint[N] - checkpoint[N-1]) rather than absolute values because archival RPC returns liquid balance only while indexed transactions include everything
- Gap diagnosis confidence set to 0.60 (archival balance is liquid only, not definitive)
- Re-index jobs queued at priority 3 (moderate) with cursor set to start_block for NearFetcher resume
- Lazy imports inside run_verify() avoid circular imports and match the ACBHandler pattern
- Report grouped into three sections by diagnosis_category for clear specialist review

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 5 verification pipeline fully operational
- All four modules (reconcile, duplicates, gaps, report) wired into VerifyHandler
- classify -> ACB -> verify_balances chain complete end-to-end
- DISCREPANCIES.md report ready for specialist review workflow
- Phase 6 (Reporting) can consume verification_results and account_verification_status data
- Phase 7 UI can display verification dashboard from account_verification_status table

---
*Phase: 05-verification*
*Completed: 2026-03-13*
