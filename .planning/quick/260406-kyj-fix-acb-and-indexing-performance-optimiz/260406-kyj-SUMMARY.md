---
phase: quick
plan: 260406-kyj
subsystem: acb-performance
tags: [performance, acb, price-service, progress-reporting, deduplication]
dependency_graph:
  requires: []
  provides: [bulk_minute_price_prewarm, acb_progress_reporting, smart_replay_flag, job_dedup]
  affects: [engine/acb/engine_acb.py, indexers/price_service.py, indexers/acb_handler.py, indexers/service.py, api/routers/wallets.py, api/routers/jobs.py]
tech_stack:
  added: []
  patterns: [batch-api-clustering, progress-callback, smart-flag-optimization]
key_files:
  created: []
  modified:
    - indexers/price_service.py
    - engine/acb/engine_acb.py
    - indexers/acb_handler.py
    - indexers/service.py
    - api/routers/wallets.py
    - api/routers/jobs.py
decisions:
  - "Cluster minute-level price requests by coin_id and 2-hour proximity to minimize CoinGecko API calls"
  - "Use daily price as proxy to identify large dispositions before minute-level pre-warm"
  - "Progress callback fires every 50 rows to balance DB write overhead vs UI responsiveness"
  - "Smart ACB replay flag: first wallet omits flag, subsequent wallets still trigger full replay"
  - "Downstream scheduler 60-second window prevents ClassifierHandler/scheduler race duplication"
metrics:
  duration: ~15 minutes
  completed: "2026-04-06"
  tasks: 2
  files_modified: 6
---

# Phase quick Plan 260406-kyj: ACB and Indexing Performance Optimization Summary

**One-liner:** Batch CoinGecko minute-price pre-warming via cluster-based range API calls, ACB progress reporting via progress_total/progress_fetched DB updates, and smart replay/dedup flags to eliminate pipeline bottlenecks causing ~4h estimates.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Batch minute-level price fetching and smart ACB replay | 7e25dde | engine/acb/engine_acb.py, indexers/price_service.py, api/routers/wallets.py |
| 2 | ACB progress reporting and pipeline job deduplication | 9ef0ad9 | indexers/acb_handler.py, indexers/service.py, api/routers/jobs.py |

## What Was Built

### Task 1: Batch Price Fetching and Smart Replay

**PriceService.bulk_fetch_minute_prices()** (`indexers/price_service.py`):
- Accepts a list of `(coin_id, unix_ts)` tuples
- Batch-checks price_cache_minute for already-cached entries via per-coin `ANY(%s)` queries
- Groups missing timestamps by coin_id, then clusters timestamps within 2 hours of each other
- One `market_chart/range` API call per cluster covers all timestamps in that window
- Respects `_COINGECKO_DELAY` rate limiting between calls
- Turns N per-transaction API calls into ceil(N/cluster_size) calls

**ACBEngine._pre_warm_minute_prices()** (`engine/acb/engine_acb.py`):
- Iterates all disposition/fee rows, skipping child legs
- Uses already-warmed daily price as proxy to identify transactions above `DISPOSITION_PRECISION_THRESHOLD_CAD` ($500)
- Collects `(coin_id, unix_ts)` pairs for likely-large dispositions
- Calls `bulk_fetch_minute_prices()` once for the whole batch
- Called from both `_full_replay()` and `_incremental()` after daily price pre-warm

**ACBEngine.calculate_for_user()** now accepts `progress_callback=None`.
Both `_full_replay()` and `_incremental()` forward it to the row-processing loops.

**Wallet creation smart flag** (`api/routers/wallets.py`):
- Changed `UPDATE users SET acb_full_replay_required = TRUE WHERE id = %s` to
  `UPDATE ... WHERE id = %s AND acb_high_water_mark IS NOT NULL`
- First wallet addition no longer triggers unnecessary full ACB replay
- Subsequent wallet additions (where ACB data already exists) still correctly force full replay

**Resync deduplication** (`api/routers/wallets.py`):
- Before inserting resync jobs, queries existing active jobs for that wallet
- Skips job types already in `queued/running/retrying` state

### Task 2: Progress Reporting and Downstream Deduplication

**ACBHandler progress reporting** (`indexers/acb_handler.py`):
- Before starting ACBEngine, queries `COUNT(*) FROM transaction_classifications WHERE user_id = %s`
- Writes result to `progress_total` on the job row
- `_make_progress_callback(job_id)` factory returns a closure that updates `progress_fetched` every 50 rows
- Callback is passed to `engine.calculate_for_user(user_id, progress_callback=cb)`
- UI can now compute accurate percentage: `progress_fetched / progress_total`

**Downstream scheduler dedup** (`indexers/service.py`):
- After existing queued/running check, adds a second check: was this job type completed in the last 60 seconds?
- Prevents the race where `ClassifierHandler` directly queues `calculate_acb` AND `_schedule_downstream_if_ready` also tries to queue it
- Uses `completed_at > NOW() - INTERVAL '60 seconds'`

**ACB time estimate** (`api/routers/jobs.py`):
- Replaced fixed `total_minutes += 15` heuristic for `calculate_acb`
- Now uses `progress_total` (classification count): `max(1, int(total / 100 / 60))` minutes
- Fallback for queued jobs with no count yet: 2 minutes (not 15)

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all data flows are wired.

## Threat Flags

None - no new network endpoints or auth paths introduced. The `progress_fetched` updates are job-scoped internal service calls (T-quick-01 accepted), and rate limiting is preserved across the new batch fetch path (T-quick-02 mitigated).

## Self-Check: PASSED

Files modified exist:
- engine/acb/engine_acb.py: FOUND
- indexers/price_service.py: FOUND
- indexers/acb_handler.py: FOUND
- indexers/service.py: FOUND
- api/routers/wallets.py: FOUND
- api/routers/jobs.py: FOUND

Commits verified:
- 7e25dde: Task 1 — batch minute-level price fetching and smart ACB replay
- 9ef0ad9: Task 2 — ACB progress reporting and pipeline job deduplication

Test suite: 577 passed, 1 skipped
