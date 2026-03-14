---
phase: 09-code-quality-hardening
plan: "03"
subsystem: engine-performance
tags: [n+1-queries, rate-limiting, retry, backoff, classifier, nearblocks]
dependency_graph:
  requires: []
  provides: [batch-staking-event-index, batch-lockup-event-index, nearblocks-exponential-backoff]
  affects: [engine/classifier.py, indexers/nearblocks_client.py, indexers/balance_snapshot.py]
tech_stack:
  added: []
  patterns: [batch-select-per-wallet, exponential-backoff-jitter, in-memory-index-dict]
key_files:
  created: []
  modified:
    - engine/classifier.py
    - indexers/nearblocks_client.py
    - indexers/balance_snapshot.py
    - config.py
decisions:
  - "Per-wallet staking/lockup index scope keeps memory bounded (not per-user)"
  - "index=None fallback to DB query preserves backward compat for direct callers"
  - "2^attempt + uniform[0,1) jitter matches plan spec exactly"
  - "NearBlocksClient uses requests.Session for connection reuse"
  - "RATE_LIMIT_DELAY inter-request pacing is orthogonal to retry backoff"
metrics:
  duration_minutes: 6
  tasks_completed: 2
  files_modified: 4
  completed_date: "2026-03-14"
requirements: [QH-02, QH-03]
---

# Phase 9 Plan 03: N+1 Queries + NearBlocks Retry Hardening Summary

**One-liner:** Batch staking/lockup event loading eliminates per-tx DB queries; NearBlocks API now retries 429/Timeout/ConnectionError with 2^attempt+jitter exponential backoff.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix N+1 queries — batch staking/lockup event loading | 75458cf | engine/classifier.py, config.py |
| 2 | Harden NearBlocks API retry with exponential backoff + jitter | cf0872b | indexers/nearblocks_client.py, indexers/balance_snapshot.py |

## What Was Built

### Task 1: N+1 Elimination in Classifier

Added two batch loading methods to `TransactionClassifier`:

- `_load_staking_event_index(conn, user_id, wallet_id)` — single SELECT on `staking_events WHERE event_type='reward'`, builds `{by_hash, by_timestamp}` dict
- `_load_lockup_event_index(conn, user_id, wallet_id)` — single SELECT on `lockup_events`, builds same structure

`classify_user_transactions` now groups NEAR transactions by `wallet_id`, loads both indexes once per wallet, then passes them to `_classify_near_tx` via `staking_index`/`lockup_index` parameters.

`_find_staking_event` and `_find_lockup_event` check the index first (O(1) hash lookup, then linear timestamp scan), falling back to direct DB query only when `index=None` (backward compatibility preserved).

### Task 2: NearBlocks Exponential Backoff

`NearBlocksClient._request` was rewritten as `_nearblocks_request` with proper backoff:
- Pattern: `wait = (2 ** attempt) + random.uniform(0, 1)` for each retry
- Handles: 429 status, `requests.exceptions.Timeout`, `requests.exceptions.ConnectionError`
- Max 5 retries then `RuntimeError` — no silent data loss
- Uses `requests.Session` for connection reuse
- All `print()` replaced with `logger.warning()` with structured format strings
- Normal inter-request pacing (`RATE_LIMIT_DELAY`) preserved and orthogonal to retry backoff

`balance_snapshot.fetch_ft_balances_nearblocks` updated with same pattern (was using fixed 30s linear waits).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing `validate_env` in config.py**
- **Found during:** Task 1 (stash pop from previous plans included api/main.py changes that import `validate_env`)
- **Issue:** `api/main.py` (modified in prior uncommitted work) imports `validate_env` from `config` which didn't exist, causing conftest.py ImportError blocking all tests
- **Fix:** Added `validate_env()` function to `config.py` that raises RuntimeError if `DATABASE_URL` not set, with logger warnings for optional missing vars
- **Files modified:** config.py
- **Commit:** 75458cf

## Verification

- `grep "_load_staking_event_index" engine/classifier.py` — 4 matches (definition + call + docstring refs)
- `grep "_load_lockup_event_index" engine/classifier.py` — 4 matches
- `grep -c "backoff\|429\|retry" indexers/nearblocks_client.py` — 10 matches
- `pytest tests/test_classifier.py tests/test_near_fetcher.py -q` — 35/35 passed

## Self-Check: PASSED

- engine/classifier.py: FOUND
- indexers/nearblocks_client.py: FOUND
- indexers/balance_snapshot.py: FOUND
- Commit 75458cf: FOUND
- Commit cf0872b: FOUND
