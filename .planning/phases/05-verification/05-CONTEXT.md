# Phase 5: Verification - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Ensure data accuracy by reconciling calculated balances against on-chain state for all indexed chains, detecting duplicate transactions across all source combinations, and finding missing transactions via balance-based inference. Produces per-account verification status with auto-diagnosis of discrepancies. Exchange accounts without API access support manual balance entry for reconciliation. Verification runs automatically after ACB calculation and is available on-demand.

</domain>

<decisions>
## Implementation Decisions

### Reconciliation Scope
- All indexed chains get full balance reconciliation: NEAR (RPC view_account), EVM (Etherscan balance API), XRP/Akash (when fetchers are functional)
- Exchange accounts: provide interface for manual balance entry (user enters current balance as of reconciliation date) since exchanges have no on-chain state to verify against
- Per-chain configurable tolerance thresholds: NEAR ±0.01 NEAR, EVM ±0.0001 ETH, configurable per chain for different dust/rounding characteristics
- NEAR reconciliation uses decomposed balance check: query liquid + staked + locked separately via RPC, compare each component against indexed data (catches staking reward gaps a total-balance check would miss)

### Balance Calculation Method
- Dual cross-check: compare ACB pool totals (Phase 4 ACBPool snapshots) AND raw transaction replay (sum all in/out from transactions table)
- If the two methods disagree, that disagreement is itself a discrepancy to flag — catches ACB engine bugs independently
- ACB pool provides Decimal-precise expected balance; raw replay provides independent verification

### Discrepancy Handling
- Diagnose + flag: system auto-investigates likely causes and attaches diagnosis to the discrepancy record. Specialist reviews diagnosis and marks resolved/unresolved
- Storage in database: new `verification_results` table (user_id, chain, account_id, expected_balance, actual_balance, difference, diagnosis, status: open/resolved/accepted, resolved_by, notes). Queryable by Phase 7 UI
- Auto-trigger: register `verify_balances` job type in IndexerService. ACBHandler auto-queues verification after ACB completes (same chain: classify → ACB → verify). Also available via API for manual trigger
- Four automatic diagnosis categories:
  1. Missing staking rewards — compare staking_events count/total vs expected epoch count for delegation period
  2. Uncounted fees/storage — NEAR storage deposits (0.00125 NEAR per key/contract), gas fees not in transaction amounts, EVM gas costs
  3. Unindexed time periods — gaps in transaction timestamps where account was active on-chain but no transactions indexed
  4. Classification errors — transactions classified as transfers-out that should be internal transfers (inflating outgoing balance)

### Duplicate Detection
- Final audit sweep: Phase 2 DedupHandler catches cross-source dupes at import, Phase 3 classifier catches during classification, Phase 5 does full-table scan as safety net
- Multi-signal scoring: exact tx_hash match (definite), same amount + timestamp within 10min + same asset (high confidence), same amount + same day + same asset (medium confidence). Threshold-based flagging with confidence score
- All source combinations checked: within-chain, cross-chain (bridge tx on both sides), cross-source (exchange record matching on-chain tx)
- Balance-aware auto-merge: if removing a duplicate brings calculated balance closer to on-chain AND confidence is high, auto-merge (keep earliest record). Any doubt → flag for specialist review
- Merged duplicates logged in verification_results for audit trail

### Missing Transaction Detection
- Balance-based inference: work backwards from balance mismatch to identify which time periods likely have missing transactions
- Auto re-index + full pipeline cascade: queue targeted re-index job for suspected gap period. If re-indexing finds new transactions, auto-trigger reclassification and ACB recalculation. Report what was found
- Exchange completeness: cross-reference exchange deposit/withdrawal records with on-chain transactions. Unmatched records flagged as potential gaps or duplicates

### Verification Status
- Per-account status roll-up: each wallet/exchange account gets status — verified (within tolerance), flagged (discrepancies found), unverified (not yet checked)
- User-level status is the worst of all their accounts (any flagged account = user flagged)
- Feeds into Phase 7 verification dashboard (VER requirement in UI-07)

### Claude's Discretion
- Database schema design for verification_results and related tables
- Balance-based inference algorithm for detecting missing transaction periods
- Auto-diagnosis heuristics and confidence thresholds for each diagnosis category
- Re-indexing job scope (full re-index vs targeted time window)
- How to handle tokens with no price data in balance comparison (count-based vs value-based)
- Exact multi-signal scoring weights for duplicate detection

</decisions>

<specifics>
## Specific Ideas

- "100% data accuracy" principle carries forward from Phase 1 — verification is the final quality gate before reporting
- Manual exchange balance entry enables reconciliation even without API access — user enters what they see on the exchange as of a specific date
- Balance-aware duplicate merging is unique: uses the reconciliation target as a guide for auto-merge decisions
- Dual balance calculation (ACB pools + raw replay) catches bugs in both the ACB engine and the transaction pipeline independently
- Decomposed NEAR balance (liquid/staked/locked) enables pinpointing exactly where mismatches originate

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `verify/reconcile.py`: Legacy NEAR-only reconciler with RPC balance query pattern (get_onchain_balance). SQLite-based, needs full PostgreSQL rewrite but RPC call pattern is reusable
- `indexers/dedup_handler.py`: Cross-source dedup with 1% amount tolerance + 10-min time window + direction alignment. Pattern reusable for Phase 5 final sweep
- `engine/acb.py`: ACBPool snapshots track total units per token after every event — provides expected balance for reconciliation
- `engine/gains.py`: GainsCalculator already populates capital_gains_ledger and income_ledger — verification can cross-check these
- `indexers/service.py`: IndexerService job queue with job_type dispatch — register `verify_balances` as new job type
- `indexers/acb_handler.py`: ACBHandler pattern for auto-queuing next pipeline step — reuse for verify trigger
- `indexers/staking_rewards.py`: FastNear RPC calls for validator pool balance — reusable for decomposed NEAR balance check
- `indexers/evm_fetcher.py`: Etherscan V2 API patterns — reusable for EVM balance queries

### Established Patterns
- Job queue pipeline chaining: classify → ACB → verify (same pattern as classify → ACB from Phase 4)
- `needs_review` boolean + confidence scoring throughout the system
- Multi-user isolation via user_id FK
- Decimal precision for all monetary calculations (NUMERIC types)
- `needs_review=True` for specialist confirmation (Phase 3/4 pattern)

### Integration Points
- `indexers/service.py`: Register `verify_balances` job handler
- `indexers/acb_handler.py`: Auto-queue verification after ACB completes
- `db/models.py`: New models for verification_results
- `db/migrations/`: Alembic migration 005 for verification schema
- Phase 7 UI-07: Verification status dashboard reads from verification_results

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-verification*
*Context gathered: 2026-03-12*
