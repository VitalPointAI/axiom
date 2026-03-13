---
phase: 05-verification
plan: 03
subsystem: verification
tags: [duplicate-detection, multi-signal-scoring, balance-aware-merge, dedup, postgresql]

# Dependency graph
requires:
  - phase: 05-verification
    provides: verification_results table (migration 005), VerifyHandler skeleton
  - phase: 02-multi-chain-exchanges
    provides: DedupHandler pattern, ASSET_DECIMALS, cross-source dedup algorithm
provides:
  - DuplicateDetector class with multi-signal scoring (verify/duplicates.py)
  - Within-table exact tx_hash dedup (score=1.0, auto-merge)
  - Cross-chain bridge heuristic (score=0.60, flag only)
  - Exchange-vs-on-chain full re-scan (scores 0.85/0.80/0.60)
  - Balance-aware auto-merge decision logic
  - Audit trail via verification_results with 'duplicate_merged' category
affects: [05-04-gap-finder, 07-web-ui]

# Tech tracking
tech-stack:
  added: []
  patterns: [multi-signal scoring with threshold-based actions, balance-aware merge using on-chain ground truth, soft-delete via needs_review+notes]

key-files:
  created:
    - verify/duplicates.py
  modified: []

key-decisions:
  - "Imports ASSET_DECIMALS from dedup_handler as single source of truth for decimal conversions"
  - "Bridge window 30 minutes vs 10 minutes for same-chain (accounts for cross-chain confirmation)"
  - "Bridge duplicates never auto-merged (score=0.60 always flagged for specialist review)"
  - "Balance-aware merge returns False when no on-chain balance available (no merge without ground truth)"
  - "Each duplicate detection logged as separate verification_results row (not upsert) for full audit trail"

patterns-established:
  - "Multi-signal scoring: exact hash (1.0) > amount+time+asset (0.85) > exchange match (0.80) > amount+day (0.60)"
  - "Threshold actions: auto-merge >= 1.0, balance-aware 0.75-1.0, flag 0.50-0.75, log-only < 0.50"
  - "Soft-delete pattern: needs_review=TRUE + explanatory notes, never DELETE rows"

requirements-completed: [VER-03]

# Metrics
duration: 2min
completed: 2026-03-13
---

# Phase 5 Plan 03: Duplicate Detector Summary

**DuplicateDetector with 3-scan pipeline (hash dedup, bridge heuristic, exchange re-scan), multi-signal scoring (1.0/0.85/0.80/0.60), balance-aware auto-merge, and verification_results audit trail**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-13T12:10:46Z
- **Completed:** 2026-03-13T12:13:36Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- DuplicateDetector class with scan_user() orchestrating three scan types in order
- Within-table exact tx_hash duplicate detection using GROUP BY/HAVING, auto-merge with score=1.0, soft-delete pattern (needs_review + notes on duplicate rows and their transaction_classifications)
- Cross-chain bridge heuristic detecting same-amount transfers on different chains within 30 minutes, flagged at score=0.60, never auto-merged
- Exchange-vs-on-chain full re-scan with multi-signal scoring (Signal 2: 0.85, Signal 3: 0.60, Signal 4: 0.80) and threshold-based actions
- Balance-aware auto-merge at score>=0.75 that checks if removing the exchange duplicate brings calculated balance closer to on-chain ground truth
- Full audit trail: every detection logged in verification_results with diagnosis_category='duplicate_merged', JSONB detail, and confidence score

## Task Commits

Each task was committed atomically:

1. **Task 1: DuplicateDetector -- within-table hash dedup + multi-signal scoring** - `d12ea49` (feat)

## Files Created/Modified
- `verify/duplicates.py` - DuplicateDetector class with 3 scan types, multi-signal scoring, balance-aware merge, and audit logging (885 lines)

## Decisions Made
- Imports ASSET_DECIMALS from indexers.dedup_handler as single source of truth (no duplication)
- Bridge window set to 30 minutes (vs 10 for same-chain) to account for cross-chain confirmation times
- Bridge duplicates always flagged (never auto-merged) because specialist must verify bridge direction
- Balance-aware merge requires on-chain ground truth -- returns False without it to prevent incorrect merges
- Each duplicate detection is INSERT (not upsert) into verification_results for complete audit trail
- Helper functions (_resolve_token_symbol, _amounts_close, _convert_onchain_amount) extracted as module-level for testability

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- DuplicateDetector ready to be wired into VerifyHandler (Plan 05-01 skeleton has placeholder)
- verify/duplicates.py exports DuplicateDetector class for import by verify_handler.py
- All three scan types follow the same audit trail pattern (verification_results with duplicate_merged category)
- Plan 05-04 (Gap Finder) can proceed independently

## Self-Check: PASSED

All 1 file verified present. Task commit (d12ea49) confirmed in git log.

---
*Phase: 05-verification*
*Completed: 2026-03-13*
