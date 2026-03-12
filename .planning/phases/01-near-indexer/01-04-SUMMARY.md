---
phase: 01-near-indexer
plan: "04"
subsystem: integration
tags: [indexer, job-queue, web-api, staking, lockup, near]
dependency_graph:
  requires: [01-02, 01-03]
  provides: [end-to-end-pipeline]
  affects: [web-api, indexer-service]
tech_stack:
  added: []
  patterns: [job-type-dispatch, queue-decoupled-api]
key_files:
  created: []
  modified:
    - indexers/service.py
    - web/app/api/wallets/route.ts
    - web/app/api/sync/status/route.ts
decisions:
  - "Dispatch by job_type not chain — handlers map to operation not blockchain"
  - "Staking sync scheduled 4x less frequently than transaction incremental sync (hourly)"
  - "EVM spawn removed but job queue not yet wired — EVM job queue deferred to Phase 2"
  - "Sync status API reads from indexing_jobs table for job-level progress breakdown"
metrics:
  duration: "3 minutes"
  completed: "2026-03-12"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 1 Plan 4: Integration Wiring + Web API Job Queue Summary

**One-liner:** Wired StakingFetcher and LockupFetcher into IndexerService dispatch loop and replaced subprocess spawning in wallet API with three queued PostgreSQL jobs (full_sync, staking_sync, lockup_sync).

## What Was Built

End-to-end pipeline integration: wallet added in UI -> three jobs queued in PostgreSQL -> standalone IndexerService picks them up -> transactions, staking rewards, and lockup events all indexed by their respective handlers.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Register staking and lockup handlers in indexer service | a979941 | indexers/service.py |
| 2 | Update web APIs to use job queue instead of subprocess spawning | 00cd919 | web/app/api/wallets/route.ts, web/app/api/sync/status/route.ts |

## Key Changes

### indexers/service.py

- Added imports: `StakingFetcher`, `LockupFetcher`, `PriceService`
- `__init__` now instantiates `PriceService` and registers four handlers keyed by `job_type`:
  - `full_sync` -> `NearFetcher.sync_wallet()`
  - `incremental_sync` -> `NearFetcher.sync_wallet()`
  - `staking_sync` -> `StakingFetcher.sync_staking()`
  - `lockup_sync` -> `LockupFetcher.sync_lockup()`
- Dispatch logic changed from `handlers.get(chain)` to `handlers.get(job_type)` with method routing
- `check_incremental_syncs()` now also schedules periodic `staking_sync` jobs for NEAR wallets at 4x the transaction interval (~60 min)
- Incremental sync existence check now scopes to `full_sync`/`incremental_sync` job types so staking jobs don't block transaction scheduling

### web/app/api/wallets/route.ts

- Removed `import { spawn } from 'child_process'` and `import path from 'path'`
- Removed all `spawn()` subprocess calls for both NEAR (hybrid_indexer.py, sync-staking-pg.py) and EVM (evm_indexer.py)
- After NEAR wallet INSERT: creates three queued jobs via direct PostgreSQL INSERTs using the `db` async interface
- Returns `sync_status: 'queued'` immediately — API response is not blocked by indexing
- EVM wallet creation notes job queue integration as pending Phase 2 scope

### web/app/api/sync/status/route.ts

- Complete rewrite: reads from `indexing_jobs` JOIN `wallets` instead of `wallets.sync_status`
- Groups jobs by `wallet_id`, computes per-wallet aggregated status (syncing/synced/error/pending)
- Provides `wallet_details` array with per-wallet job breakdown by `job_type`
- Preserves existing response shape for UI compatibility: `status`, `progress`, `wallets` counts, `transactions`

## Decisions Made

1. **Dispatch by job_type not chain**: The handlers dict now maps operation names (full_sync, staking_sync) not blockchain names. This is the correct abstraction — you can have multiple job types per chain.

2. **Staking sync at 4x tx interval**: Staking rewards accrue once per ~12-hour epoch. Hourly polling (vs 15-min for transactions) is more appropriate. Defined as `SYNC_INTERVAL_MINUTES * 4`.

3. **EVM spawn removed, job queue deferred**: The EVM `evm_indexer.py` spawn was removed without replacement. EVM job queue integration is out of scope for Phase 1; the comment documents this clearly. EVM wallets can be indexed manually until Phase 2 adds EVM job queue support.

4. **Sync status reads indexing_jobs**: More accurate than `wallets.sync_status` (which was set by the old subprocess approach). Job-level breakdown lets the UI show per-operation progress.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] Scoped incremental sync existence check by job_type**
- **Found during:** Task 1 implementation
- **Issue:** Original existence check blocked ALL jobs for a wallet if any job was queued/running. This would prevent staking sync scheduling if a transaction job was running.
- **Fix:** Added `AND pending.job_type IN ('incremental_sync', 'full_sync')` to the incremental sync existence check. Staking sync has a separate existence check.
- **Files modified:** indexers/service.py
- **Commit:** a979941

**2. [Rule 1 - Bug] EVM spawn removal without job queue replacement**
- **Found during:** Task 2 — verification requires zero `spawn` references
- **Issue:** Removing EVM spawn without a replacement disables EVM auto-indexing. However, the verification check explicitly requires all spawns removed, and EVM job queue is not in scope.
- **Fix:** Removed EVM spawn, added documentation comment explaining Phase 2 will add job queue integration. EVM wallets still get created — indexing is deferred.
- **Files modified:** web/app/api/wallets/route.ts
- **Commit:** 00cd919

## Self-Check: PASSED

- SUMMARY.md: FOUND at .planning/phases/01-near-indexer/01-04-SUMMARY.md
- indexers/service.py: FOUND
- web/app/api/wallets/route.ts: FOUND
- web/app/api/sync/status/route.ts: FOUND
- Commit a979941: FOUND (Task 1)
- Commit 00cd919: FOUND (Task 2)
