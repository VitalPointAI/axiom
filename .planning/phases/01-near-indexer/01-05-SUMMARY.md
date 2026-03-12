---
phase: 01-near-indexer
plan: 05
subsystem: database
tags: [postgresql, near, staking, lockup, job-queue, logging]

# Dependency graph
requires:
  - phase: 01-near-indexer
    plan: 04
    provides: "IndexerService job dispatch, StakingFetcher + LockupFetcher registered as handlers"

provides:
  - "_claim_next_job() JOINs wallets table so job dict contains account_id"
  - "StakingFetcher and LockupFetcher can read job_row['account_id'] without KeyError"
  - "_get_first_stake_timestamp() falls back to transactions table when staking_events is empty"
  - "All logging in staking_fetcher.py and lockup_fetcher.py uses Python logging module"

affects:
  - staking_sync jobs
  - lockup_sync jobs

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FOR UPDATE OF ij SKIP LOCKED — required PostgreSQL syntax when SELECT JOINs multiple tables"
    - "Transactions table as fallback for stake timestamp discovery when staking_events is unpopulated"
    - "Python logging module (logger.info/warning/error) instead of print() for all indexer output"

key-files:
  created: []
  modified:
    - indexers/service.py
    - indexers/staking_fetcher.py
    - indexers/lockup_fetcher.py

key-decisions:
  - "FOR UPDATE OF ij SKIP LOCKED instead of FOR UPDATE SKIP LOCKED — PostgreSQL requires specifying locked table when JOIN is present"
  - "transactions fallback queries action_type='STAKE' OR (action_type='FUNCTION_CALL' AND counterparty = validator_id) — covers both direct stake and pool function calls"

patterns-established:
  - "Timestamp fallback pattern: check primary table first, fall back to transactions for initial history"
  - "Structured logging: logger.info('msg %s', var) format throughout indexer pipeline"

requirements-completed: [DATA-01, DATA-02, DATA-03]

# Metrics
duration: 3min
completed: 2026-03-12
---

# Phase 01 Plan 05: Gap Closure — Job Dispatch account_id + Staking Timestamp Fallback Summary

**Fixed KeyError on staking/lockup job dispatch by JOINing wallets in _claim_next_job(), added transactions table fallback for first-stake timestamp discovery, replaced all print() with logger in both fetchers**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-12T00:46:38Z
- **Completed:** 2026-03-12T00:49:43Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `_claim_next_job()` now JOINs the wallets table and includes `w.account_id` in the returned job dict — eliminates KeyError in StakingFetcher.sync_staking() and LockupFetcher.sync_lockup()
- `_get_first_stake_timestamp()` falls back to the transactions table when staking_events has no deposit rows, enabling backfill to start for fresh wallets
- All print() statements in staking_fetcher.py and lockup_fetcher.py replaced with structured logger.info/warning/error calls

## Task Commits

Each task was committed atomically:

1. **Task 1: Add account_id to job dispatch via JOIN in _claim_next_job()** - `7cb7d08` (fix)
2. **Task 2: Fix _get_first_stake_timestamp() fallback + replace print() with logger** - `cbf06bd` (fix)

**Plan metadata:** (final docs commit below)

## Files Created/Modified

- `indexers/service.py` - Changed SELECT to JOIN wallets, added account_id column, changed FOR UPDATE OF ij SKIP LOCKED
- `indexers/staking_fetcher.py` - Added logging import + logger, fixed _get_first_stake_timestamp() with transactions fallback, replaced all print()
- `indexers/lockup_fetcher.py` - Added logging import + logger, replaced all print()

## Decisions Made

- Used `FOR UPDATE OF ij SKIP LOCKED` (not `FOR UPDATE SKIP LOCKED`) — PostgreSQL requires specifying the locked table when a JOIN is present; without `OF ij`, the query would fail or lock both tables incorrectly
- Transactions fallback queries both `action_type = 'STAKE'` and `action_type = 'FUNCTION_CALL' AND counterparty = validator_id` to cover both old-style direct STAKE actions and function calls to staking pools

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Staking sync and lockup sync jobs can now be dispatched without KeyError
- Staking backfill can start for wallets with zero staking_events by reading first transaction timestamp from the transactions table
- Ready for live staking data collection once DATABASE_URL is configured and indexer service is running

---
*Phase: 01-near-indexer*
*Completed: 2026-03-12*
