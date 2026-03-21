---
phase: 13-reliable-indexing
plan: 04
status: complete
started: 2026-03-21
completed: 2026-03-21
---

# Plan 13-04 Summary: StreamingWorker + Gap Reindex

## What was built
- `StreamingWorker` class managing asyncio tasks for multi-chain streaming
- NEAR streaming via NearStreamFetcher.stream_blocks() with tx upsert + pg_notify
- EVM streaming via EVMStreamFetcher.watch_blocks() with incremental sync job queuing
- Periodic wallet refresh (60s interval)
- Chain config loading from chain_sync_config with hardcoded fallback
- `gap_reindex` module with 3/day retry cap and manual_review_required fallback
- `--streaming` flag in service.py to launch worker alongside job queue

## Key files

### Created
- `indexers/streaming_worker.py` — StreamingWorker + run_streaming_worker entry point
- `indexers/gap_reindex.py` — queue_reindex_if_needed + get_reindex_count_today
- `tests/test_streaming_worker.py` — 14 tests
- `tests/test_gap_reindex.py` — 6 tests

### Modified
- `indexers/service.py` — added --streaming CLI flag

## Test results
20 tests passed

## Self-Check: PASSED
- [x] StreamingWorker starts/stops asyncio tasks
- [x] NEAR transactions upserted with ON CONFLICT DO NOTHING
- [x] pg_notify called on new transaction insert
- [x] EVM new block queues incremental sync jobs
- [x] Wallet refresh every 60 seconds
- [x] Gap reindex caps at 3 retries/day/wallet
- [x] manual_review_required set after cap
- [x] service.py --streaming flag launches background thread

## Deviations
None.
