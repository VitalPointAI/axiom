---
phase: 01-near-indexer
plan: "06"
subsystem: web-api
tags: [wallet-api, schema-fix, indexing-jobs, gap-closure]
dependency_graph:
  requires: [01-01, 01-04]
  provides: [working-wallet-crud-api]
  affects: [web/app/api/wallets/route.ts]
tech_stack:
  added: []
  patterns: [postgres-db-import, indexing-jobs-status-derivation]
key_files:
  created: []
  modified:
    - web/app/api/wallets/route.ts
decisions:
  - Derive wallet sync_status from indexing_jobs via CASE subqueries (not stored column)
  - Unified wallets table for all chains (NEAR + EVM) with chain column filter
  - EVM wallet block wrapped in try/catch for graceful Phase 2 readiness
metrics:
  duration: "2 minutes"
  completed: "2026-03-12"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 1
---

# Phase 1 Plan 06: Wallet API Schema Fix Summary

Wallet API updated to use new Alembic schema: GET derives sync_status from indexing_jobs table via CASE subqueries; POST inserts NEAR wallets without the removed sync_status column.

## Tasks Completed

| Task | Description | Commit | Status |
|------|-------------|--------|--------|
| 1 | Update wallet GET and POST handlers to use indexing_jobs schema | e500c27 | Done |

## What Was Built

Fixed `web/app/api/wallets/route.ts` to be compatible with the new PostgreSQL schema from `001_initial_schema.py` (Plan 01-01). The file had two critical breakages:

**GET handler:** Was querying `indexing_progress` table (removed in new schema) and `wallets.sync_status` column (removed in new schema). Now uses correlated CASE subqueries against `indexing_jobs` to derive sync status per wallet: running → syncing, queued/retrying → pending, failed → error, completed → synced.

**POST handler:** Was inserting `sync_status = 'pending'` into wallets table (column no longer exists). Was also SELECTing `sync_status, last_synced_at` after insert (both columns removed). Now inserts without sync_status; SELECT hardcodes `'pending' as sync_status` since the wallet was just created.

**Pattern migration:** Removed the `getDb()` import and all `db.prepare().all/get/run()` calls. Now uses the async `db.all/get/run()` pattern consistently, matching `sync/status/route.ts`.

**EVM/XRP handling:** Removed separate `evm_wallets` and `xrp_wallets` table queries (old schema). Non-NEAR wallets now query the unified `wallets` table with `chain != 'near'` filter, wrapped in try/catch for graceful failure if needed.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

## Verification Results

1. `grep -c "indexing_progress" web/app/api/wallets/route.ts` = 0 (PASS)
2. `sync_status` appears only as SELECT aliases (`as sync_status`) and JS property assignments, never as column references (PASS)
3. `grep -c "getDb" web/app/api/wallets/route.ts` = 0 (PASS)
4. `indexing_jobs` used in correlated subqueries for status derivation (PASS)
5. NEAR wallet INSERT: `(account_id, chain, label, user_id)` — no sync_status (PASS)

## Self-Check: PASSED

- [x] `web/app/api/wallets/route.ts` modified and committed (e500c27)
- [x] `01-06-SUMMARY.md` created at `.planning/phases/01-near-indexer/`
- [x] No `indexing_progress` references remain
- [x] No `getDb` references remain
- [x] No `sync_status` column references (only aliases)
- [x] NEAR INSERT excludes sync_status column
- [x] STATE.md updated with plan completion
- [x] ROADMAP.md updated with plan progress (6/6 plans marked done)
