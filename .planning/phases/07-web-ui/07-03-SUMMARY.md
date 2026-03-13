---
phase: 07-web-ui
plan: 03
subsystem: api
tags: [fastapi, psycopg2, pydantic, postgresql, pytest, wallets, portfolio, jobs, pipeline]

# Dependency graph
requires:
  - phase: 07-web-ui
    plan: 01
    provides: "FastAPI app factory, get_effective_user/get_pool_dep dependencies, stub routers, conftest fixtures"
  - phase: 04-cost-basis
    provides: "acb_snapshots table (token_symbol, quantity, acb_per_unit, total_cost_cad, chain)"
  - phase: 05-verification
    provides: "indexing_jobs table (status, priority, progress_fetched, progress_total)"
  - phase: 01-near-indexer
    provides: "wallets table, staking_events table"

provides:
  - "POST/GET/DELETE /api/wallets — wallet CRUD + NEAR (3 jobs) and EVM (1 job) pipeline auto-chain"
  - "POST /api/wallets/{id}/resync — re-queue pipeline jobs for existing wallet"
  - "GET /api/wallets/{id}/status — SyncStatusResponse with stage (Indexing/Classifying/Cost Basis/Verifying/Done) and pct 0-100"
  - "GET /api/portfolio/summary — PortfolioSummary with ACB holdings (ROW_NUMBER window) + staking positions"
  - "GET /api/jobs/active — ActiveJobsResponse with pipeline_stage/pct derived from running jobs"
  - "GET /api/jobs/{id}/status — single job progress + error_message"
  - "api/schemas/wallets.py, api/schemas/portfolio.py, api/schemas/jobs.py Pydantic models"
  - "16 passing tests across test_api_wallets.py and test_api_portfolio.py"

affects:
  - 07-04-transaction-routers
  - 07-05-reports-verification-routers
  - 07-06-job-status-router
  - frontend-dashboard-wallet-management

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pipeline job queuing: NEAR wallet => [full_sync p=10, staking_sync p=8, lockup_sync p=7]; EVM => [evm_full_sync p=10]"
    - "Stage mapping: job_type -> (stage_name, pct_min, pct_max); prefers running jobs over queued for stage determination"
    - "User isolation: every query filters WHERE user_id = %s (from get_effective_user)"
    - "run_in_threadpool wraps all synchronous psycopg2 calls in async route handlers"
    - "fetchall called twice in list_wallets (wallets then jobs) — tests use side_effect=[..., ...] not return_value"
    - "Active jobs query 9-col row (wallet_id included) vs single job query 8-col — separate _row_to_job_status helpers"

key-files:
  created:
    - api/schemas/wallets.py
    - api/schemas/portfolio.py
    - api/schemas/jobs.py
    - api/routers/wallets.py
    - api/routers/portfolio.py
    - api/routers/jobs.py
    - tests/test_api_wallets.py
    - tests/test_api_portfolio.py
  modified:
    - api/routers/__init__.py (imports real routers replacing stubs for wallets/portfolio/jobs)

key-decisions:
  - "Pipeline stage prefers running jobs over queued/retrying — _pipeline_from_jobs checks running first, falls back to queued"
  - "Active jobs query returns 9-col rows (includes wallet_id); single job query returns 8-col — separate helper functions per shape"
  - "_compute_stage uses highest stage_priority among active jobs for wallets; _pipeline_from_jobs in jobs router uses running-first semantics"
  - "fetchall called twice in list_wallets — wallet test mocks use side_effect=[wallet_rows, job_rows] not return_value"
  - "portfolio/jobs stubs created first as importable placeholders, then replaced with full implementations"

patterns-established:
  - "Two-fetchall pattern in list_wallets: first for wallets (4-col), second for jobs (7-col indexed by wallet_id)"
  - "All data routers follow: pool.getconn() -> run_in_threadpool(_fn, conn) -> pool.putconn() in finally"
  - "Route ordering: /api/jobs/active MUST precede /api/jobs/{id}/status to prevent FastAPI treating 'active' as int param"

requirements-completed:
  - UI-02
  - UI-03

# Metrics
duration: 9min
completed: 2026-03-13
---

# Phase 7 Plan 03: Wallet + Portfolio + Jobs API Summary

**Wallet CRUD with NEAR/EVM pipeline auto-chain, portfolio ACB holdings summary, and job status with pipeline stage progress bar using psycopg2 + FastAPI run_in_threadpool**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-03-13T21:42:50Z
- **Completed:** 2026-03-13T21:51:50Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- POST /api/wallets creates wallet + queues NEAR pipeline (full_sync p=10, staking_sync p=8, lockup_sync p=7) or EVM (evm_full_sync p=10); ON CONFLICT returns 409
- GET /api/wallets/{id}/status returns SyncStatusResponse with stage (Indexing/Classifying/Cost Basis/Verifying/Done) and pct 0-100 derived from indexing_jobs
- GET /api/portfolio/summary uses ROW_NUMBER() window function to get latest ACB snapshot per token + staking positions from staking_events
- GET /api/jobs/active returns pipeline_stage and pipeline_pct — prefers running jobs over queued for stage determination
- All 16 tests pass (9 wallet + 7 portfolio/jobs); TDD: RED commits first, then GREEN implementation

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing wallet tests** - `21053b6` (test)
2. **Task 1 GREEN: Wallet CRUD + pipeline auto-chain + sync status** - `3c40c85` (feat)
3. **Task 2 RED: Failing portfolio/jobs tests** - `1826c4c` (test)
4. **Task 2 GREEN: Portfolio summary + job status endpoints** - `e0899e4` (feat)

## Files Created/Modified

- `api/schemas/wallets.py` - WalletCreate, WalletResponse, SyncStatusResponse, JobSummary
- `api/schemas/portfolio.py` - HoldingResponse, StakingPosition, PortfolioSummary
- `api/schemas/jobs.py` - JobStatusResponse, ActiveJobsResponse
- `api/routers/wallets.py` - POST/GET/DELETE/resync wallets, _compute_stage(), _derive_sync_status(), _jobs_for_chain()
- `api/routers/portfolio.py` - GET /api/portfolio/summary with ROW_NUMBER ACB window + staking positions
- `api/routers/jobs.py` - GET /api/jobs/active + GET /api/jobs/{id}/status, _pipeline_from_jobs() running-first semantics
- `api/routers/__init__.py` - Imports real wallets_router, portfolio_router, jobs_router; stubs remain for transactions/reports/verification
- `tests/test_api_wallets.py` - 9 tests: create NEAR/EVM, duplicate 409, list with sync_status, delete ownership, sync_status stage, user isolation, resync
- `tests/test_api_portfolio.py` - 7 tests: summary holdings, staking positions, empty state, job status, active jobs pipeline stage, user isolation, empty active jobs

## Decisions Made

- **Pipeline stage prefers running jobs:** `_pipeline_from_jobs` checks running jobs first; falls back to queued/retrying only when nothing is running — matches RESEARCH.md "find highest-priority running job type"
- **Two separate row-to-response helpers:** Active jobs query includes wallet_id (9-col); single job query omits it (8-col) — `_active_row_to_job_status` vs `_row_to_job_status` to prevent index errors
- **Route ordering for jobs router:** `/api/jobs/active` registered before `/{job_id}/status` — FastAPI matches routes in registration order, preventing "active" being parsed as integer
- **fetchall side_effect in tests:** list_wallets calls fetchall twice (wallets then jobs in same cursor); tests use `mock_cursor.fetchall.side_effect = [list1, list2]` not `return_value`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Row index mismatch between active-jobs query and single-job query**
- **Found during:** Task 2 GREEN (test_active_jobs failing with ValidationError)
- **Issue:** Active jobs SELECT returns 9 columns (id, wallet_id, job_type, status, ...) but `_row_to_job_status` expected 8-col format (id, job_type, status, ...) — `row[1]` was wallet_id (int) being assigned to `job_type` (str)
- **Fix:** Added `_active_row_to_job_status` helper with correct indices for 9-col active jobs rows
- **Files modified:** api/routers/jobs.py
- **Verification:** test_active_jobs passes with correct job_type values
- **Committed in:** e0899e4

**2. [Rule 1 - Bug] Pipeline stage logic picked queued over running**
- **Found during:** Task 2 GREEN (test_active_jobs asserting "Indexing" got "Classifying")
- **Issue:** `_pipeline_from_jobs` iterated all active_statuses={queued,running,retrying} — `classify_transactions` queued had higher stage priority (2) than `full_sync` running (1), so Classifying was returned even though full_sync was actively running
- **Fix:** Restructured logic to prefer `running` jobs first for stage determination, fall back to queued/retrying only if nothing is running
- **Files modified:** api/routers/jobs.py
- **Verification:** test_active_jobs passes asserting stage == "Indexing" when full_sync is running
- **Committed in:** e0899e4

**3. [Rule 1 - Bug] Mock fetchall.return_value shared across both fetchall calls in list_wallets**
- **Found during:** Task 1 GREEN (IndexError: tuple index out of range in list_wallets)
- **Issue:** Tests set `mock_cursor.fetchall.return_value` to wallet rows (5-tuple), but list_wallets calls fetchall twice — the second call (for jobs) received the same wallet rows, causing `job[6]` IndexError
- **Fix:** Changed test mocks to use `fetchall.side_effect = [wallet_rows, job_rows]` for proper per-call return values
- **Files modified:** tests/test_api_wallets.py
- **Verification:** All 9 wallet tests pass
- **Committed in:** 3c40c85

---

**Total deviations:** 3 auto-fixed (2 bugs in implementation, 1 bug in test mock)
**Impact on plan:** All fixes necessary for correctness. No scope creep.

## Issues Encountered

None beyond the deviations documented above.

## Next Phase Readiness

- Wallet CRUD + pipeline auto-chain: ready for frontend dashboard to POST /api/wallets and poll /api/wallets/{id}/status
- Portfolio summary: ready for frontend to display holdings table with ACB data
- Job status: ready for frontend pipeline progress bar consuming GET /api/jobs/active
- api/routers/__init__.py pattern established for replacing stub routers as plans complete
- 07-04 (transaction routers) and 07-05 (reports/verification routers) can follow same patterns

---
*Phase: 07-web-ui*
*Completed: 2026-03-13*
