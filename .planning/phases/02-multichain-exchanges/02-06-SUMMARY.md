---
phase: 02-multichain-exchanges
plan: 06
subsystem: indexer
tags: [deduplication, xrp, akash, cosmos-sdk, xrpl, ai-agent, exchange-import]

# Dependency graph
requires:
  - phase: 02-multichain-exchanges
    plan: 04
    provides: "IndexerService + FileImportHandler wiring"
  - phase: 02-multichain-exchanges
    plan: 05
    provides: "AIFileAgent with Claude API + confidence scoring"

provides:
  - DedupHandler: cross-source dedup (exchange vs on-chain) flagging via needs_review
  - XRPFetcher: ChainFetcher stub for xrp_full_sync and xrp_incremental job types
  - AkashFetcher: ChainFetcher stub for akash_full_sync and akash_incremental job types
  - FileImportHandler AI fallback: routes unknown formats to AIFileAgent
  - service.py: all Phase 2 job types registered and dispatched

affects: [phase-03-classification, phase-04-cost-basis, phase-05-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ChainFetcher stub pattern: inherit ABC, set chain_name + supported_job_types, implement sync_wallet + get_balance"
    - "XRPL JSON-RPC via requests.post with marker-based pagination and endpoint rotation"
    - "Cosmos LCD REST GET with events query + pagination.key and dual-query merge (sent + received)"
    - "Dedup via JOIN semantics: asset + 1% amount tolerance + 10-min timestamp window + direction alignment"
    - "conn=None guard pattern: release pool conn before calling AI agent to prevent pool exhaustion"

key-files:
  created:
    - indexers/dedup_handler.py
    - indexers/xrp_fetcher.py
    - indexers/akash_fetcher.py
    - tests/test_dedup_handler.py
  modified:
    - indexers/file_handler.py
    - indexers/service.py

key-decisions:
  - "DedupHandler uses needs_review+notes columns for flagging instead of schema changes (avoids ALTER TABLE)"
  - "1% amount tolerance for dedup matching (covers exchange rounding vs exact on-chain values)"
  - "10-minute timestamp window for dedup (covers network propagation + exchange recording lag)"
  - "Direction alignment: exchange send/withdrawal/sell -> on-chain out; receive/deposit/buy -> in"
  - "ASSET_DECIMALS lookup table in dedup_handler (ETH=18, NEAR=24, XRP=6, AKT=6) for unit conversion"
  - "XRP amounts stored as drops (NUMERIC 40,0), same as NEAR yocto — consistent raw integer storage"
  - "Akash dual tx-search: query sent (message.sender) AND received (transfer.recipient), merge by txhash"
  - "Sweat wallets handled by NearFetcher (Sweat is NEAR-based, no separate fetcher needed)"
  - "Release pool conn before AIFileAgent call in FileImportHandler (AI agent manages own connections)"

patterns-established:
  - "All new ChainFetcher subclasses: rate limiting + endpoint rotation + ON CONFLICT DO NOTHING upsert"
  - "Dedup check pattern: SQL WHERE notes NOT LIKE '%Potential duplicate%' to skip already-processed rows"

requirements-completed: [DATA-04, DATA-05]

# Metrics
duration: 7min
completed: 2026-03-12
---

# Phase 2 Plan 06: Phase 2 Integration Summary

**DedupHandler (cross-source dedup with 1% tolerance + 10-min window), XRP + Akash ChainFetcher stubs, AI fallback wired into FileImportHandler, all 8 Phase 2 job types registered in service.py**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-03-12T19:17:26Z
- **Completed:** 2026-03-12T19:24:27Z
- **Tasks:** 2 (Task 1 TDD: RED+GREEN; Task 2: auto)
- **Files modified:** 6

## Accomplishments

- DedupHandler detects cross-source duplicates between exchange_transactions and transactions tables using asset + 1% amount tolerance + 10-min timestamp window + direction alignment; flags matches with needs_review=True and notes referencing on-chain tx_hash
- XRPFetcher and AkashFetcher implemented as full ChainFetcher stubs with real API calls (XRPL JSON-RPC and Cosmos LCD REST), endpoint rotation, rate limiting, and cursor-based incremental sync
- FileImportHandler now calls AIFileAgent for unknown exchange formats instead of silently setting needs_ai status; properly handles conn lifecycle to prevent pool exhaustion
- service.py registers all 8 Phase 2 job types with correct dispatch: evm_full_sync, evm_incremental, file_import, xrp_full_sync, xrp_incremental, akash_full_sync, akash_incremental, dedup_scan

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for DedupHandler** - `1e8b2df` (test)
2. **Task 1 GREEN: DedupHandler implementation** - `e3f7a4d` (feat)
3. **Task 2: AI fallback + XRP/Akash stubs + service.py** - `4163139` (feat)

**Plan metadata:** (docs commit — see below)

_Note: Task 1 used TDD with separate RED (test) and GREEN (feat) commits._

## Files Created/Modified

- `indexers/dedup_handler.py` — DedupHandler class; run_scan(), _amounts_match(), _get_expected_direction(); ASSET_DECIMALS dict; 283 lines
- `tests/test_dedup_handler.py` — 10 unit tests covering matching, non-matching, direction, tolerance, connection safety
- `indexers/xrp_fetcher.py` — XRPFetcher(ChainFetcher): sync_wallet via account_tx, get_balance via account_info, _parse_to_unified to unified transactions schema
- `indexers/akash_fetcher.py` — AkashFetcher(ChainFetcher): sync_wallet via dual tx-search (sent+received), get_balance via bank balances, MsgSend/Delegate/Reward parsing
- `indexers/file_handler.py` — AI fallback wired: releases conn, calls AIFileAgent, handles exceptions; conn=None guard in except/finally
- `indexers/service.py` — 3 new imports + 5 new handler entries + 3 new dispatch elif branches

## Decisions Made

- DedupHandler uses existing `needs_review` and `notes` columns for flagging instead of adding schema columns (avoids ALTER TABLE, leverages already-present columns from migration 002)
- 1% amount tolerance covers exchange rounding (e.g. Coinbase truncates to 8 decimals vs exact wei)
- 10-minute timestamp window covers network propagation latency + exchange recording delay
- ASSET_DECIMALS lookup table handles unit conversion (ETH=18, NEAR=24, XRP=6, AKT=6 uakt)
- XRP and Akash amounts stored as raw integers matching NUMERIC(40,0) column convention established for yoctoNEAR
- Sweat wallets: no separate fetcher needed — Sweat is NEAR-based, NearFetcher handles them

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None. One minor implementation detail handled proactively: the `conn=None` guard in FileImportHandler's except/finally blocks was added because the AI fallback path releases the connection to the pool before calling AIFileAgent — without the guard the `finally` block would call `putconn(None)` causing a TypeError.

## User Setup Required

None — no external service configuration required. XRP and Akash use public API endpoints without API keys.

## Next Phase Readiness

- Phase 2 complete: all 8 job types (NEAR full/incremental/staking/lockup, EVM, file_import, XRP, Akash, dedup_scan) registered and dispatched
- DedupHandler ready to run after exchange imports populate exchange_transactions
- Phase 3 (Transaction Classification) can now rely on: transactions table (all chains), exchange_transactions (all exchanges), dedup flagging (needs_review for potential duplicates)
- XRP and Akash fetchers are production-ready stubs; real wallet data will work once wallets are added to the wallets table

---
*Phase: 02-multichain-exchanges*
*Completed: 2026-03-12*
