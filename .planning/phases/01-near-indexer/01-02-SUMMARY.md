---
phase: 01-near-indexer
plan: "02"
subsystem: indexer
tags: [python, nearblocks, psycopg2, job-queue, cursor-resume, exponential-backoff, tdd, pytest]

# Dependency graph
requires:
  - phase: 01-near-indexer-01
    provides: "indexers/db.py connection pool, config.py with DATABASE_URL/NEARBLOCKS config, db/models.py with IndexingJob and Transaction models"
provides:
  - Standalone indexer service (indexers/service.py) with PostgreSQL job queue polling
  - NEAR transaction fetcher (indexers/near_fetcher.py) with cursor-based resume
  - Unit tests (tests/test_near_fetcher.py) covering all action types and resume logic
  - Updated Dockerfile to run as standalone service (not cron)
  - Updated docker-compose.yml with CRYPTOCOMPARE_API_KEY, FASTNEAR_API_KEY, JOB_POLL_INTERVAL, SYNC_INTERVAL_MINUTES
affects: [01-near-indexer-03, 01-near-indexer-04, all plans that add wallets or read transaction data]

# Tech tracking
tech-stack:
  added: [pytest (already installed), unittest.mock (stdlib)]
  patterns:
    - "FOR UPDATE SKIP LOCKED for multi-worker-safe job queue polling (PostgreSQL advisory lock pattern)"
    - "Cursor-based page resume: job.cursor persisted to DB after each page, survives restarts"
    - "ON CONFLICT (chain, tx_hash, receipt_id, wallet_id) DO NOTHING for idempotent inserts"
    - "Exponential backoff: min(300, 5 * 2^attempts) seconds, capped at 5 min, max 100 attempts"
    - "TDD: RED commit (failing tests) then GREEN commit (implementation) per task"

key-files:
  created:
    - indexers/near_fetcher.py
    - indexers/service.py
    - tests/test_near_fetcher.py
    - tests/__init__.py
  modified:
    - indexers/Dockerfile
    - docker-compose.yml

key-decisions:
  - "parse_transaction() is module-level (not a method) — allows direct import in tests without DB pool"
  - "Action priority list for multi-action txs: TRANSFER > FUNCTION_CALL > STAKE > CREATE > DELETE > DEPLOY > ADD_KEY > DELETE_KEY"
  - "COUNT_TOLERANCE_PCT = 5% — NearBlocks count can lag; tight tolerance still catches major gaps"
  - "Dockerfile build context changed from indexers/ to project root — enables COPY of config.py and db/ alongside indexers/"
  - "check_incremental_syncs() runs on every empty poll cycle — keeps sync latency at ~JOB_POLL_INTERVAL when queue empties"

patterns-established:
  - "All chain handlers implement sync_wallet(job_row: dict) — IndexerService dispatches via self.handlers[chain]"
  - "Job lifecycle: queued → running → completed | retrying → failed (100 attempt limit)"
  - "Per-page commit: cursor + progress_fetched updated to DB after every page insert for crash safety"
  - "verify_sync() runs after every full_sync completion — count check + RPC balance (non-blocking, warnings only)"

requirements-completed: [DATA-01]

# Metrics
duration: 5min
completed: 2026-03-12
---

# Phase 1 Plan 02: Standalone Indexer Service and NEAR Transaction Fetcher

**PostgreSQL job queue polling service with NearFetcher using cursor-based page resume, ON CONFLICT duplicate handling, and exponential backoff self-healing retry (20 unit tests, all passing)**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-12T00:15:14Z
- **Completed:** 2026-03-12T00:20:26Z
- **Tasks:** 2 (Task 1 TDD, Task 2 auto)
- **Files modified:** 6

## Accomplishments

- Built `NearFetcher` with `parse_transaction()` handling all 8 NEAR action types (TRANSFER, FUNCTION_CALL, STAKE, ADD_KEY, DELETE_KEY, CREATE_ACCOUNT, DELETE_ACCOUNT, DEPLOY_CONTRACT) — amounts stored in yoctoNEAR (Numeric) to match schema
- Built `IndexerService` with `FOR UPDATE SKIP LOCKED` job queue polling, chain handler dispatch, 5-minute-capped exponential backoff, graceful SIGTERM shutdown, and incremental sync scheduling
- 20 unit tests covering parse_transaction for all action types, cursor resume logic, empty wallet handling, ON CONFLICT verification, and verify_sync count tolerance

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests for NearFetcher** - `e8ae169` (test)
2. **Task 1 (GREEN): Implement NearFetcher with cursor-based resume** - `eb26ca3` (feat)
3. **Task 2: Build standalone indexer service** - `2d5bd4d` (feat)

**Plan metadata:** (docs commit — forthcoming)

## Files Created/Modified

- `indexers/near_fetcher.py` - NearFetcher class + parse_transaction() module-level function; 20 tests pass
- `indexers/service.py` - IndexerService with job queue polling, exponential backoff, graceful shutdown, incremental sync scheduling
- `tests/test_near_fetcher.py` - 20 pytest unit tests (all passing)
- `tests/__init__.py` - Empty package init
- `indexers/Dockerfile` - Changed CMD to `python -m indexers.service`; build context moved to project root
- `docker-compose.yml` - Added CRYPTOCOMPARE_API_KEY, FASTNEAR_API_KEY, JOB_POLL_INTERVAL, SYNC_INTERVAL_MINUTES env vars

## Decisions Made

- `parse_transaction()` is a module-level function (not a class method) — makes it directly testable without instantiating NearFetcher or its DB pool
- Action priority list determines primary `action_type` for multi-action transactions: TRANSFER takes precedence since it carries the amount
- Dockerfile build context changed from `./indexers` to `.` (project root) — required to COPY `config.py` and `db/` into the container alongside `indexers/`
- `check_incremental_syncs()` runs on every empty-queue poll cycle (not a timer thread) — simpler architecture, no threading needed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed cursor resume test assertion for keyword args**
- **Found during:** Task 1 GREEN (running tests after implementation)
- **Issue:** Test asserted `first_call[0][1] == "EXISTING_CURSOR"` but `fetch_transactions(account_id, cursor=cursor)` passes cursor as keyword arg, so `first_call[0]` only has 1 element, causing IndexError before `or` branch evaluated
- **Fix:** Changed assertion to safely check both positional (len guard) and keyword args
- **Files modified:** tests/test_near_fetcher.py
- **Verification:** All 20 tests pass
- **Committed in:** eb26ca3 (Task 1 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in test assertion)
**Impact on plan:** Test was correct in intent, just had a fragile assertion. Fix was minimal.

## Issues Encountered

None — implementation matched plan spec exactly.

## User Setup Required

None — no external service configuration required for this plan. Env vars added to docker-compose.yml will read from `.env` file.

## Next Phase Readiness

- IndexerService and NearFetcher ready for Plan 01-03 (price service + staking rewards)
- To run service locally: `DATABASE_URL=... python -m indexers.service`
- To run service once (for smoke testing): `DATABASE_URL=... python -m indexers.service --once`
- Docker container now runs `indexers.service` as main process (not cron)
- Incremental syncs auto-scheduled when queue empties and SYNC_INTERVAL_MINUTES has elapsed

## Self-Check: PASSED

All created files verified present on disk:
- indexers/near_fetcher.py: FOUND
- indexers/service.py: FOUND
- tests/test_near_fetcher.py: FOUND
- .planning/phases/01-near-indexer/01-02-SUMMARY.md: FOUND (this file)

Task commits verified:
- e8ae169 (Task 1 RED): FOUND
- eb26ca3 (Task 1 GREEN + fix): FOUND
- 2d5bd4d (Task 2): FOUND

---
*Phase: 01-near-indexer*
*Completed: 2026-03-12*
