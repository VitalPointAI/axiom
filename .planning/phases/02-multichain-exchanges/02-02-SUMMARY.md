---
phase: 02-multichain-exchanges
plan: "02"
subsystem: evm-indexer
tags: [evm, etherscan, pagination, transactions, chain-fetcher, tdd]
dependency_graph:
  requires: [02-01]
  provides: [EVMFetcher, CHAIN_CONFIG, CHAIN_NAME_MAP]
  affects: [indexers/service.py, transactions table]
tech_stack:
  added: [psycopg2.extras.execute_values, requests, time.sleep rate-limiting]
  patterns: [ChainFetcher-ABC, TDD-RED-GREEN, paginated-API-fetch, ON-CONFLICT-DO-NOTHING]
key_files:
  created:
    - indexers/evm_fetcher.py
    - tests/test_evm_fetcher.py
    - tests/fixtures/etherscan_responses.py
    - tests/fixtures/__init__.py
  modified: []
decisions:
  - CHAIN_NAME_MAP for bidirectional resolution between config keys (ETH/Polygon) and DB values (ethereum/polygon)
  - ERC20/NFT tx_hash = hash-logIndex prevents unique constraint violation when parent tx has multiple token transfers
  - fee=None for internal/ERC20/NFT (gas already counted in parent normal tx)
  - Fix applied to NORMAL_TX fixture (from/to were swapped — wallet should be receiver for incoming test)
metrics:
  duration_minutes: 4
  completed_date: "2026-03-12"
  tasks_completed: 1
  tasks_total: 1
  files_created: 4
  files_modified: 0
---

# Phase 02 Plan 02: EVMFetcher — Etherscan V2 + PostgreSQL Summary

**One-liner:** EVMFetcher implementing ChainFetcher ABC with 10,000-item Etherscan V2 pagination, ERC20/NFT logIndex dedup, and PostgreSQL execute_values upsert for ETH/Polygon/Cronos/Optimism.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for EVMFetcher | cabbefe | tests/test_evm_fetcher.py, tests/fixtures/etherscan_responses.py |
| 1 (GREEN) | EVMFetcher implementation | eaca55f | indexers/evm_fetcher.py |

## What Was Built

**`indexers/evm_fetcher.py`** — Production-ready EVM chain fetcher:

- `EVMFetcher(ChainFetcher)` with `chain_name='evm'`, `supported_job_types=['evm_full_sync', 'evm_incremental']`
- `sync_wallet(job)` — processes job dict, fetches all 4 tx types, upserts to transactions table, updates cursor
- `_fetch_paginated(params, chain_config)` — loops through 10,000-item pages with 0.25s rate limit delay
- `_transform_tx(raw_tx, wallet_address, chain, tx_type, chain_config)` — maps Etherscan JSON to unified schema
- `_batch_upsert(rows)` — uses `psycopg2.extras.execute_values` with `ON CONFLICT (chain, tx_hash, receipt_id, wallet_id) DO NOTHING`
- `_update_job_cursor(job_id, cursor, progress_fetched)` — updates indexing_jobs after sync
- `CHAIN_CONFIG` — ETH (chainid=1), Polygon (137), Cronos (25, custom_api), Optimism (10)
- `CHAIN_NAME_MAP` / `CHAIN_KEY_MAP` — bidirectional mapping between config keys and DB lowercase values

**`tests/test_evm_fetcher.py`** — 23 unit tests across 7 test classes, all mocked (no DB required):
- `TestSyncWalletNormalTx` — execute_values called, 16-column row structure
- `TestERC20TxHash` — ERC20/NFT get hash-logIndex suffix, normal tx gets raw hash
- `TestPagination` — multi-page fetch (10000+500=10500), single-page stops after 1 request
- `TestCursorUpdate` — cursor=max(blockNumber) written to UPDATE indexing_jobs
- `TestDirectionDetection` — in/out based on to/from vs wallet; case-insensitive
- `TestFeeCalculation` — gasUsed*gasPrice for normal; None for internal/ERC20/NFT
- `TestCronosCustomAPI` / `TestInheritance` / `TestChainConfig`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed NORMAL_TX fixture from/to addresses swapped**
- **Found during:** TDD GREEN phase - test_incoming_tx_direction failing
- **Issue:** `NORMAL_TX` had `from = 0xWALLET`, `to = 0xCOUNTERPARTY` but test expected incoming direction (wallet is receiver). Comment said "NORMAL_TX has 'to' == WALLET_ADDRESS" but fixture was reversed.
- **Fix:** Swapped from/to in NORMAL_TX fixture so wallet is the receiver
- **Files modified:** tests/fixtures/etherscan_responses.py
- **Commit:** eaca55f (included in GREEN commit)

## Verification Results

All plan verification checks passed:
- `python3 -c "from indexers.evm_fetcher import EVMFetcher, CHAIN_CONFIG"` — import OK
- `EVMFetcher` inherits from `ChainFetcher` — confirmed
- No `?` SQL placeholders in evm_fetcher.py — confirmed (uses `%s`)
- No `db.init` references in evm_fetcher.py — confirmed (uses `indexers.chain_plugin`)
- `CHAIN_CONFIG` includes ETH (1), Polygon (137), Cronos (25), Optimism (10) — confirmed
- `pytest tests/test_evm_fetcher.py -x` — 23 passed in 0.44s

## Self-Check: PASSED
