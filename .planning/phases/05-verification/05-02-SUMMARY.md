---
phase: 05-verification
plan: 02
subsystem: verification, reconciliation
tags: [near-rpc, etherscan, balance-reconciliation, auto-diagnosis, decimal]

# Dependency graph
requires:
  - phase: 05-verification/05-01
    provides: verification_results table, VerifyHandler skeleton, RECONCILIATION_TOLERANCES config
provides:
  - BalanceReconciler class with full reconciliation engine
  - NEAR decomposed balance queries (liquid + locked + staked)
  - EVM native balance via Etherscan V2
  - Dual cross-check (ACBPool vs raw tx replay)
  - Four auto-diagnosis categories with confidence scoring
  - VerifyHandler Step 1 wired to BalanceReconciler
affects: [05-03-duplicate-detector, 05-04-gap-finder, 07-web-ui]

# Tech tracking
tech-stack:
  added: []
  patterns: [NEAR decomposed balance RPC, Etherscan V2 chain-aware balance query, per-wallet raw replay vs user-level ACBPool cross-check]

key-files:
  created: []
  modified:
    - verify/reconcile.py
    - indexers/verify_handler.py

key-decisions:
  - "Per-wallet raw replay (expected_balance_replay) used for on-chain comparison; ACBPool (expected_balance_acb) is user-level cross-check"
  - "NearBlocks kitwallet staking endpoint as optional fallback for pre-indexing validator discovery"
  - "Auto-diagnosis runs 4 heuristics in priority order; first match with confidence > 0.5 wins"
  - "Exchange wallets use manual_balance from previous verification_results if available; otherwise marked unverified"

patterns-established:
  - "Decimal(str(value)) pattern throughout for financial precision"
  - "CHAIN_DIVISORS dict for yoctoNEAR/wei to human unit conversion"
  - "try/except per-RPC with rpc_error field recording failures"

requirements-completed: [VER-01, VER-02]

# Metrics
duration: 4min
completed: 2026-03-13
---

# Phase 5 Plan 02: Balance Reconciler Summary

**Full BalanceReconciler rewrite with NEAR decomposed balance (liquid+locked+staked via RPC), EVM Etherscan V2 native balance, dual cross-check (ACBPool snapshot vs raw tx replay), 4-category auto-diagnosis with confidence scoring, and exchange manual balance path**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-13T12:10:46Z
- **Completed:** 2026-03-13T12:15:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Complete rewrite of verify/reconcile.py from legacy SQLite (130 lines) to PostgreSQL-backed BalanceReconciler (1002 lines)
- NEAR decomposed balance via 3 RPC call types: view_account (liquid+locked), staking_events DB query + NearBlocks kitwallet fallback (validator enumeration), get_account_staked_balance per validator pool
- EVM native balance via Etherscan V2 with chain-aware chainid parameter (ETH/Polygon/Cronos/Optimism)
- Dual cross-check: ACBPool latest snapshot (user-level per token) + raw transaction replay (per-wallet sum of in - out - fees)
- Four auto-diagnosis categories: missing_staking_rewards (epoch gap detection), uncounted_fees (fee gap ratio), unindexed_period (7-day timestamp gap), classification_error (misclassified own-wallet transfers)
- Results upserted to verification_results via INSERT ON CONFLICT (wallet_id, token_symbol) DO UPDATE
- Exchange wallet path: looks up manual_balance from previous results, marks unverified if none
- VerifyHandler Step 1 placeholder replaced with BalanceReconciler.reconcile_user() call

## Task Commits

Each task was committed atomically:

1. **Task 1: BalanceReconciler full rewrite + VerifyHandler wiring** - `e86b69e` (feat)

## Files Created/Modified
- `verify/reconcile.py` - Full rewrite: BalanceReconciler class (1002 lines) replacing legacy SQLite reconciler
- `indexers/verify_handler.py` - Wired BalanceReconciler into Step 1 of run_verify()

## Decisions Made
- Per-wallet raw replay (expected_balance_replay) is used for direct on-chain comparison since ACBPool is user-scoped (all wallets pooled); ACBPool expected_balance_acb stored as cross-check
- NearBlocks kitwallet staking endpoint used as optional fallback (try/except) for discovering validators from before indexing started
- Auto-diagnosis heuristics run in priority order; first match with confidence > 0.5 is returned
- Exchange wallets check for existing manual_balance in verification_results; no on-chain query attempted

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no new external service configuration required (Etherscan API key already in env from Phase 2).

## Next Phase Readiness
- BalanceReconciler fully operational for Plans 05-03 and 05-04
- VerifyHandler Step 1 complete; Steps 2 (duplicates) and 3 (gaps) remain as placeholders for Plans 05-03 and 05-04
- verification_results table being populated enables duplicate detection and gap analysis

## Self-Check: PASSED

All files verified present. Task commit (e86b69e) confirmed in git log.

---
*Phase: 05-verification*
*Completed: 2026-03-13*
