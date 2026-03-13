# Phase 5: Verification - Research

**Researched:** 2026-03-13
**Domain:** Data reconciliation, duplicate detection, missing transaction inference
**Confidence:** HIGH (based on full codebase analysis; no external libraries required)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- All indexed chains get full balance reconciliation: NEAR (RPC view_account), EVM (Etherscan balance API), XRP/Akash (when fetchers are functional)
- Exchange accounts: provide interface for manual balance entry (user enters current balance as of reconciliation date) since exchanges have no on-chain state to verify against
- Per-chain configurable tolerance thresholds: NEAR ±0.01 NEAR, EVM ±0.0001 ETH, configurable per chain for different dust/rounding characteristics
- NEAR reconciliation uses decomposed balance check: query liquid + staked + locked separately via RPC, compare each component against indexed data (catches staking reward gaps a total-balance check would miss)
- Dual cross-check: compare ACB pool totals (Phase 4 ACBPool snapshots) AND raw transaction replay (sum all in/out from transactions table)
- If the two methods disagree, that disagreement is itself a discrepancy to flag — catches ACB engine bugs independently
- ACB pool provides Decimal-precise expected balance; raw replay provides independent verification
- Diagnose + flag: system auto-investigates likely causes and attaches diagnosis to the discrepancy record
- Storage in database: new `verification_results` table (user_id, chain, account_id, expected_balance, actual_balance, difference, diagnosis, status: open/resolved/accepted, resolved_by, notes)
- Auto-trigger: register `verify_balances` job type in IndexerService. ACBHandler auto-queues verification after ACB completes (same chain: classify → ACB → verify). Also available via API for manual trigger
- Four automatic diagnosis categories: missing staking rewards, uncounted fees/storage, unindexed time periods, classification errors
- Final audit sweep: Phase 2 DedupHandler catches cross-source dupes at import, Phase 3 classifier catches during classification, Phase 5 does full-table scan as safety net
- Multi-signal scoring: exact tx_hash match (definite), same amount + timestamp within 10min + same asset (high confidence), same amount + same day + same asset (medium confidence). Threshold-based flagging with confidence score
- All source combinations checked: within-chain, cross-chain (bridge tx on both sides), cross-source (exchange record matching on-chain tx)
- Balance-aware auto-merge: if removing a duplicate brings calculated balance closer to on-chain AND confidence is high, auto-merge (keep earliest record). Any doubt → flag for specialist review
- Merged duplicates logged in verification_results for audit trail
- Balance-based inference: work backwards from balance mismatch to identify which time periods likely have missing transactions
- Auto re-index + full pipeline cascade: queue targeted re-index job for suspected gap period
- Exchange completeness: cross-reference exchange deposit/withdrawal records with on-chain transactions
- Per-account status roll-up: verified (within tolerance), flagged (discrepancies found), unverified (not yet checked)
- User-level status is the worst of all their accounts (any flagged account = user flagged)

### Claude's Discretion
- Database schema design for verification_results and related tables
- Balance-based inference algorithm for detecting missing transaction periods
- Auto-diagnosis heuristics and confidence thresholds for each diagnosis category
- Re-indexing job scope (full re-index vs targeted time window)
- How to handle tokens with no price data in balance comparison (count-based vs value-based)
- Exact multi-signal scoring weights for duplicate detection

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VER-01 | Reconcile calculated vs on-chain balances | Dual cross-check: ACBPool `units_after` (latest snapshot per token) + raw replay via `transactions` table; NEAR via `view_account` RPC, EVM via Etherscan V2 balance endpoint |
| VER-02 | Flag discrepancies | `verification_results` table with status/diagnosis fields; tolerance checks per chain; auto-diagnosis in 4 categories |
| VER-03 | Detect duplicates | Full-table multi-signal scan extending DedupHandler pattern; exact hash + amount/time/asset combos; balance-aware auto-merge |
| VER-04 | Detect missing transactions | Balance-based inference: find time windows where balance trajectory diverges from on-chain; queue targeted re-index |
</phase_requirements>

---

## Summary

Phase 5 builds on a fully operational Phase 4 pipeline (classify → ACB → verify). The codebase already contains almost all primitives needed: NEAR RPC balance calls (`verify/reconcile.py`), EVM Etherscan V2 balance queries (`indexers/evm_fetcher.py`), cross-source dedup logic (`indexers/dedup_handler.py`), ACBPool snapshots (`engine/acb.py`), and job queue pipeline chaining (`indexers/classifier_handler.py` auto-queuing `calculate_acb`). Phase 5 follows the exact same chain extension pattern.

The core reconciliation challenge is that `acb_snapshots.units_after` gives the final ACB pool state for any token after replaying all classified events, but this is a tax-entity view (all wallets pooled), whereas on-chain balance is per-address. The reconciliation must aggregate per token across all wallets, then compare to the sum of individual on-chain balances. NEAR balance requires three separate RPC calls per account (`amount`, `locked`, validator pools) because the NEAR protocol stores liquid, locked, and delegated separately.

The duplicate detection phase extends `DedupHandler` from a cross-source-only scan to a full-table scan covering within-chain duplicates (same tx_hash appearing twice from different fetcher runs), cross-chain bridge duplication (same value transferred on both source and destination chain), and the existing exchange-vs-on-chain pattern. The balance-aware auto-merge is the most novel part: it uses the on-chain balance as ground truth and merges when the merge brings the calculated balance closer to the on-chain target.

**Primary recommendation:** Implement as three separate modules (`verify/reconcile.py` rewrite, `verify/duplicates.py` new, `verify/gaps.py` new) with a shared `VerifyHandler` wiring them into the job queue, backed by a new `verification_results` table in migration 005.

---

## Codebase Analysis

### What Exists and Is Directly Reusable

**`verify/reconcile.py` (legacy):**
- `get_onchain_balance(account_id)` — exact NEAR RPC pattern to reuse. Uses FastNear `view_account`. Returns liquid `amount` field only (in yoctoNEAR). Need to extend for `locked` and staked (validator pools). File is SQLite-based and does a naive in/out sum — must be fully rewritten.
- Pattern: `requests.post(FASTNEAR_RPC, json={"method": "query", "params": {"request_type": "view_account", ...}})`. Use `FASTNEAR_RPC` from `config.py`.

**`indexers/staking_rewards.py`:**
- `get_pool_balance(account_id, pool_id)` — calls `get_account_staked_balance` on validator pool contract via RPC. Returns float. This is the exact call needed for NEAR staked balance component. Reuse directly.
- Note: the function silently returns 0 on error (by design for pool enumeration). For reconciliation, need to distinguish "not staked" from "RPC error" — add error tracking.

**`indexers/evm_fetcher.py`:**
- `get_balance(address)` — already implemented. Returns `{"native_balance": "<wei_string>", "tokens": []}`. Problem: it hardcodes ETH chain config. Need a chain-aware variant: `get_balance(address, chain)` that uses the correct `chainid`.
- Etherscan V2 `module=account, action=balance, address=..., tag=latest` is the pattern. Already working.

**`indexers/dedup_handler.py`:**
- Full dedup algorithm reusable: `AMOUNT_TOLERANCE = 0.01` (1%), `TIMESTAMP_WINDOW_MINUTES = 10`, `ASSET_DECIMALS` map. The `_amounts_match()` method uses Decimal arithmetic correctly.
- Phase 5 full scan extends this: (1) add within-table tx_hash duplicate check, (2) add cross-chain bridge duplicate heuristic, (3) keep the exchange-vs-on-chain check but make it a "final sweep" that re-checks all exchange txs.
- The `needs_review + notes` flagging pattern should continue for Phase 5 flagging.

**`indexers/classifier_handler.py` (pipeline chaining pattern):**
The exact pattern to copy for ACBHandler → VerifyHandler chaining:
```python
# Check if job already pending
cur.execute(
    "SELECT id FROM indexing_jobs WHERE user_id = %s AND job_type = %s AND status IN ('queued', 'running')",
    (user_id, 'verify_balances'),
)
existing = cur.fetchone()
if existing is None:
    cur.execute(
        "INSERT INTO indexing_jobs (user_id, wallet_id, job_type, chain, status, priority) VALUES (%s, %s, 'verify_balances', 'all', 'queued', 4)",
        (user_id, wallet_id),
    )
```
Priority 4 (lower than ACB priority 5, which is lower than classify at 5 — verify runs last).

**`engine/acb.py` — ACBPool snapshot state:**
The `acb_snapshots` table stores `units_after` (pool balance after each event) and `total_cost_cad`. For reconciliation:
- Latest snapshot per `(user_id, token_symbol)` ordered by `block_timestamp DESC, id DESC` gives the current ACB pool balance (expected holdings per the tax engine).
- SQL: `SELECT DISTINCT ON (token_symbol) token_symbol, units_after, total_cost_cad FROM acb_snapshots WHERE user_id = %s ORDER BY token_symbol, block_timestamp DESC, id DESC`

**`db/models.py` — existing schema patterns:**
- All financial columns use `Numeric(24, 8)` or `Numeric(40, 0)` (raw) or `Numeric(18, 8)` (prices)
- `needs_review = Boolean, default=True` pattern consistent throughout
- `JSONB` for flexible structured data (e.g., `raw_data` on transactions)
- Status columns use `CheckConstraint` with IN lists
- `updated_at = server_default + onupdate=func.now()`
- `user_id` FK on every data table
- Indexes: always add `ix_{table}_{column}` for user_id, status, timestamps

**`indexers/service.py` — job dispatch:**
Handler registration is in `__init__` dict. Dispatch is in the `run()` method's if/elif chain. Both need updating for `verify_balances`.

### Migration History
- 001: users, wallets, transactions, indexing_jobs
- 002/002b: exchange tables, updated_at columns
- 003: classification schema
- 004: acb_snapshots, capital_gains_ledger, income_ledger, price_cache_minute
- 005: Must create verification_results, account_verification_status (new, Phase 5)

---

## Technical Approach

### VER-01: Balance Reconciliation

**NEAR Decomposed Balance:**
Three components must be queried separately and summed:

1. **Liquid balance** — `view_account` RPC, field `amount` (yoctoNEAR). Already in `verify/reconcile.py`.
2. **Locked balance** — `view_account` RPC, field `locked` (yoctoNEAR). Not currently extracted but present in the same RPC response.
3. **Staked balance** — requires knowing which validator pools the account has stake in. Query active staking from `staking_events` table (distinct validators where net deposit > 0), then call `get_account_staked_balance` on each pool. Sum all.

The total on-chain NEAR holding = liquid + locked + staked (across all validators).

Expected balance from ACB = `acb_snapshots.units_after` for `token_symbol='NEAR'`, latest snapshot.

Dual cross-check: also compute raw replay = sum of all NEAR in - sum of all NEAR out - sum of all NEAR fees from `transactions` table for all wallets of this user.

**EVM Balance:**
Single call per address: Etherscan V2 `module=account, action=balance`. Need chain-aware version of `EVMFetcher.get_balance()`. The fix is trivial: pass `chain_config` from the wallet's chain field.

For ERC20 token balances: Etherscan `module=account, action=tokenbalance, contractaddress=...` — but the CONTEXT.md scope is native token (ETH/MATIC/etc.) reconciliation primarily. Token-level reconciliation would require iterating all known token contracts, which is complex. Recommend: reconcile native balance only in Phase 5; token reconciliation deferred or flagged as "count-based" (compare units in ACB pool to sum of classified token events).

**Exchange (Manual Entry):**
No on-chain state. The `verification_results` table should store a `manual_balance_entered_at` and `manual_balance` field. UI presents a form; user enters current exchange balance; system computes expected from classified exchange transactions.

**Tolerance Check:**
```python
TOLERANCE = {
    "near": Decimal("0.01"),       # ±0.01 NEAR
    "ethereum": Decimal("0.0001"), # ±0.0001 ETH
    "polygon": Decimal("0.0001"),
    "cronos": Decimal("0.0001"),
    "optimism": Decimal("0.0001"),
}
```
Config-driven: store in `config.py` as `RECONCILIATION_TOLERANCES` dict.

### VER-02: Flag Discrepancies + Auto-Diagnosis

**Discrepancy record:** Write to `verification_results` table (schema below). One row per (user_id, wallet_id, token_symbol, checked_at).

**Four auto-diagnosis heuristics:**

1. **Missing staking rewards** — Query: count `staking_events` of type `reward` for this wallet. Query: count expected epoch rewards = distinct epochs in `epoch_snapshots` where staked_balance > 0. If reward count is significantly less than epoch count, flag. Confidence: MEDIUM (epochs don't always produce rewards in precise 1:1 ratio).

2. **Uncounted fees/storage** — NEAR: query sum of `fee` from `transactions` table, compare to what's tracked in ACB. EVM: compare sum of gas costs (tx fee × gas price, from Etherscan `gasUsed × gasPrice` in `raw_data`) to ACB disposals with category='fee'. Large gap → flag.

3. **Unindexed time periods** — Query: find time gaps in `transactions.block_timestamp` for this wallet. If any gap > 7 days where the account was active before and after, flag. Detect activity around the gap by checking if on-chain balance changed between the first and last transaction in each candidate window.

4. **Classification errors** — Query: count transactions classified as `transfer` where counterparty is another of the user's own wallets. These should be `internal_transfer` (zero tax impact). If any are not, flag as potential misclassification inflating the outgoing balance.

### VER-03: Duplicate Detection

**Multi-signal scoring system:**

```
Signal 1: Exact tx_hash match within-table         → score = 1.0  (definite duplicate)
Signal 2: Same amount + timestamp ±10min + same asset → score = 0.85 (high confidence)
Signal 3: Same amount + same day + same asset       → score = 0.60 (medium confidence)
Signal 4: Exchange amount ≈ on-chain amount (±1%) + timestamp ±10min → score = 0.80
```

**Threshold actions:**
- score >= 1.0: auto-merge immediately (exact hash dupe from fetcher bug)
- 0.75 <= score < 1.0: balance-aware auto-merge if merge improves reconciliation, else flag
- 0.50 <= score < 0.75: flag for specialist review (needs_review=True)
- < 0.50: log only (low confidence)

**Within-table tx_hash duplicates** (extends DedupHandler scope):
```sql
SELECT tx_hash, chain, wallet_id, COUNT(*) as cnt, array_agg(id ORDER BY id) as ids
FROM transactions
WHERE user_id = %s AND tx_hash IS NOT NULL
GROUP BY tx_hash, chain, wallet_id
HAVING COUNT(*) > 1
```
Keep the row with the lowest id (earliest inserted), soft-delete or mark the others.

**Cross-chain bridge duplicates:**
A bridge transaction appears on both source chain (as an outgoing transfer) and destination chain (as an incoming transfer). Signal: same amount ± tolerance, within 30 minutes (cross-chain is slower), already classified as `transfer` on both sides. Flag with medium confidence (0.60); specialist verifies which is the bridge and which is the receipt.

**Balance-aware auto-merge:**
Before merging, compute: calculated_balance_before, calculated_balance_after_merge. If abs(calculated_balance_after_merge - onchain_balance) < abs(calculated_balance_before - onchain_balance): merge improves accuracy → auto-merge. Log the merge in `verification_results`.

### VER-04: Missing Transaction Detection

**Balance-based inference algorithm:**

1. Build a chronological balance series from `transactions` table: running sum of (in amounts) - (out amounts) - (fees) for each wallet, sampled at regular intervals (e.g., monthly checkpoints).
2. For each checkpoint, compare the running balance to what the on-chain balance would have been at that block height (via archival RPC — `FASTNEAR_ARCHIVAL_RPC` exists in `config.py`).
3. A gap is identified when the running balance diverges by more than 2× the tolerance threshold. The gap period is from the last matching checkpoint to the first diverging checkpoint.
4. For identified gap periods: queue a targeted re-index job. For NEAR: set `cursor` to the block height at gap start so `NearFetcher` re-indexes from there. Log the gap in `verification_results` with `diagnosis = 'unindexed_period'`.

**Archival balance query (NEAR):**
```python
requests.post(FASTNEAR_ARCHIVAL_RPC, json={
    "jsonrpc": "2.0", "id": "1",
    "method": "query",
    "params": {
        "request_type": "view_account",
        "block_id": block_height,  # specific block for historical check
        "account_id": account_id
    }
})
```

**Re-index cascade:**
After re-index finds new transactions: auto-queue `classify_transactions` → `calculate_acb` → `verify_balances` (the normal pipeline). This is already how the pipeline works; the targeted re-index job just sets a narrower cursor window.

---

## Schema Design

### `verification_results` table

One row per (user_id, wallet_id, token_symbol) per verification run. Upserted on each run.

```sql
CREATE TABLE verification_results (
    id                      SERIAL PRIMARY KEY,
    user_id                 INTEGER NOT NULL REFERENCES users(id),
    wallet_id               INTEGER NOT NULL REFERENCES wallets(id),
    chain                   VARCHAR(20) NOT NULL,
    token_symbol            VARCHAR(32) NOT NULL DEFAULT 'NEAR',

    -- Balance components (all in human units, Decimal precision)
    expected_balance_acb    NUMERIC(24, 8) NULL,    -- from ACBPool latest snapshot
    expected_balance_replay NUMERIC(24, 8) NULL,    -- from raw tx sum
    actual_balance          NUMERIC(24, 8) NULL,    -- from on-chain RPC/API
    manual_balance          NUMERIC(24, 8) NULL,    -- exchange: user-entered
    manual_balance_date     TIMESTAMPTZ NULL,       -- when user entered it
    difference              NUMERIC(24, 8) NULL,    -- actual - expected_acb
    tolerance               NUMERIC(24, 8) NOT NULL DEFAULT 0.01,

    -- NEAR decomposed components (NULL for non-NEAR)
    onchain_liquid          NUMERIC(24, 8) NULL,
    onchain_locked          NUMERIC(24, 8) NULL,
    onchain_staked          NUMERIC(24, 8) NULL,

    -- Status
    status                  VARCHAR(20) NOT NULL DEFAULT 'open',
    -- CHECK: status IN ('open', 'resolved', 'accepted', 'unverified')

    -- Diagnosis
    diagnosis_category      VARCHAR(50) NULL,
    -- Values: 'missing_staking_rewards', 'uncounted_fees', 'unindexed_period',
    --         'classification_error', 'duplicate_merged', 'within_tolerance', 'unknown'
    diagnosis_detail        JSONB NULL,             -- structured evidence for diagnosis
    diagnosis_confidence    NUMERIC(4, 3) NULL,     -- 0.000 to 1.000

    -- Resolution
    resolved_by             INTEGER REFERENCES users(id) NULL,
    resolved_at             TIMESTAMPTZ NULL,
    notes                   TEXT NULL,

    -- Verification run metadata
    verified_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rpc_error               TEXT NULL,              -- if on-chain query failed

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX ix_vr_user_id ON verification_results(user_id);
CREATE INDEX ix_vr_wallet_id ON verification_results(wallet_id);
CREATE INDEX ix_vr_status ON verification_results(status);
CREATE INDEX ix_vr_verified_at ON verification_results(verified_at);
-- One open result per wallet+token (latest run)
CREATE UNIQUE INDEX uq_vr_wallet_token_latest
    ON verification_results(wallet_id, token_symbol, verified_at DESC);
```

### `account_verification_status` table

Rollup view per account (updated after each verify run). Phase 7 UI reads this.

```sql
CREATE TABLE account_verification_status (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    wallet_id       INTEGER NOT NULL REFERENCES wallets(id),
    status          VARCHAR(20) NOT NULL DEFAULT 'unverified',
    -- CHECK: status IN ('verified', 'flagged', 'unverified')
    last_checked_at TIMESTAMPTZ NULL,
    open_issues     INTEGER NOT NULL DEFAULT 0,   -- count of open verification_results
    notes           TEXT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(wallet_id)
);
CREATE INDEX ix_avs_user_id ON account_verification_status(user_id);
CREATE INDEX ix_avs_status ON account_verification_status(status);
```

### Migration 005 scope

- Create `verification_results`
- Create `account_verification_status`
- Add `uq_vr_wallet_token_latest` partial unique index (see above)
- No changes to existing tables

### SQLAlchemy model additions (`db/models.py`)

Add `VerificationResult` and `AccountVerificationStatus` models following the exact patterns in the existing file (Numeric types, JSONB, DateTime with timezone, CheckConstraint, Index).

---

## Integration Points

### 1. `indexers/acb_handler.py` — Add verify_balances queuing

After `engine.calculate_for_user(user_id)` succeeds, add the same pipeline-chaining code as `ClassifierHandler` uses to queue `calculate_acb`, but for `verify_balances`:

```python
# In ACBHandler.run_calculate_acb(), after stats = engine.calculate_for_user(user_id):
cur.execute(
    "SELECT id FROM indexing_jobs WHERE user_id=%s AND job_type='verify_balances' AND status IN ('queued','running')",
    (user_id,),
)
if cur.fetchone() is None:
    cur.execute(
        "INSERT INTO indexing_jobs (user_id, wallet_id, job_type, chain, status, priority) VALUES (%s,%s,'verify_balances','all','queued',4)",
        (user_id, wallet_id),
    )
```

### 2. `indexers/service.py` — Register handler + dispatch

In `IndexerService.__init__()`:
```python
from indexers.verify_handler import VerifyHandler
# In self.handlers dict:
"verify_balances": VerifyHandler(self.pool),
```

In `run()` dispatch elif chain:
```python
elif job_type == "verify_balances":
    handler.run_verify(job)
```

### 3. New `indexers/verify_handler.py`

The VerifyHandler wires `verify/reconcile.py`, `verify/duplicates.py`, and `verify/gaps.py` into the job queue. Same class pattern as ACBHandler and ClassifierHandler.

### 4. `verify/reconcile.py` — Full rewrite

The existing file is SQLite-based with a naive balance formula. Rewrite to:
- Use PostgreSQL pool
- Query ACBPool latest snapshot
- Do raw replay cross-check
- Call NEAR RPC for decomposed balance
- Call EVM Etherscan for native balance
- Write results to `verification_results`

### 5. `verify/duplicates.py` — New file

Extends DedupHandler's patterns. Three scan types:
1. Within-table exact hash duplicates
2. Cross-chain bridge heuristic
3. Full exchange-vs-on-chain re-scan

### 6. `verify/gaps.py` — New file

Balance-based inference, archival RPC queries, targeted re-index queuing.

### 7. `db/migrations/versions/005_verification_schema.py` — New migration

Follows the 004 pattern exactly.

### 8. `db/models.py` — Add two new models

`VerificationResult` and `AccountVerificationStatus`.

### 9. `DISCREPANCIES.md` — Manual review output

Not a code file. Generated by the reconciler run as a formatted report. Consider a `verify/report.py` helper that queries `verification_results` with `status='open'` and formats markdown.

---

## Risks & Mitigations

### Risk 1: NEAR Validator Pool Enumeration
**Problem:** To get total staked balance, we need to query every validator pool the account has ever staked with. The `staking_events` table tracks this, but only for indexed staking events. If the user staked with a validator before Phase 1 indexing started, that pool won't be in our records.
**Mitigation:** Query `staking_events` for all distinct `validator_id` values per wallet. Additionally, use the NearBlocks `kitwallet/staking` endpoint (already used in `staking_rewards.py`) which returns historical staking deposits — this covers pre-indexing history. HIGH confidence mitigation.

### Risk 2: Archival NEAR RPC for Gap Detection
**Problem:** `FASTNEAR_ARCHIVAL_RPC` exists in config but archival queries are slower and occasionally rate-limited. Gap detection requires querying balance at multiple historical block heights.
**Mitigation:** Limit gap detection to monthly checkpoints (12-24 queries per year of history). Use `FASTNEAR_ARCHIVAL_RPC` only for gap verification, not the full run. Add timeout handling and cache results in `verification_results.diagnosis_detail` JSONB.

### Risk 3: EVM Token Balance Scope Creep
**Problem:** ERC20 token reconciliation would require iterating hundreds of token contracts. The CONTEXT.md locks in native token reconciliation for EVM chains.
**Mitigation:** Phase 5 reconciles native token balances (ETH, MATIC, CRO) only. Token-level EVM reconciliation is noted as out-of-scope. For the ACB cross-check, ERC20 tokens ARE included (units_after from acb_snapshots) but without an on-chain confirmation.

### Risk 4: Bridge Duplicate Detection False Positives
**Problem:** Cross-chain bridge transactions look identical in pattern to actual duplicates (same amount, same asset, similar time). A "receive" on Polygon after "send" on Ethereum is a legitimate bridge, not a duplicate.
**Mitigation:** Bridge duplicates get a medium confidence score (0.60) — never auto-merged. Always flagged for specialist review. The diagnosis detail includes both tx hashes and chains so the specialist can verify it's genuinely a bridge.

### Risk 5: Dual Cross-Check Disagreement is Common
**Problem:** ACB pool total and raw replay total will almost always disagree slightly because ACB skips `transfer` and `internal_transfer` categories (by design in the SQL filter), while raw replay sums all transactions. This is expected behavior, not a bug.
**Mitigation:** The "dual cross-check disagreement" discrepancy type should have its own diagnosis category: check if the disagreement matches the sum of skipped transfer categories. If it does, it's expected and within design; if it doesn't, it's a genuine ACB engine discrepancy. This distinction must be implemented in the auto-diagnosis logic.

### Risk 6: verify_balances Job Scope (per-user, not per-wallet)
**Problem:** ACBHandler queues one `verify_balances` job. But verification must check all wallets for the user. The job uses `wallet_id` as a FK requirement (indexing_jobs schema requires it), but the handler must iterate all wallets.
**Mitigation:** Same pattern as `calculate_acb` — job is user-scoped, wallet_id is just used to satisfy FK, handler queries all wallets for user_id. This is the established pattern (ACBHandler uses it, ClassifierHandler uses it).

---

## Suggested Plan Breakdown

Given `granularity: fine` and the complexity of the phase, recommend 4 plans:

### Plan 05-01: Schema + VerifyHandler Wiring (2-3 tasks)
- Task 1: Alembic migration 005 (`verification_results`, `account_verification_status`, SQLAlchemy models)
- Task 2: `indexers/verify_handler.py` skeleton + `indexers/service.py` registration + `indexers/acb_handler.py` pipeline chaining
- Self-check: migration applies cleanly, job type registered

### Plan 05-02: Balance Reconciler (3-4 tasks)
- Task 1: `verify/reconcile.py` rewrite — NEAR decomposed balance (liquid + locked + staked via validator pools)
- Task 2: EVM balance reconciliation (chain-aware Etherscan V2 call + write results)
- Task 3: Dual cross-check (ACBPool vs raw replay) + auto-diagnosis (4 categories)
- Task 4: Exchange manual entry path + account status rollup writer
- Self-check: all 64 NEAR accounts reconciled within tolerance, EVM accounts reconciled, results in DB

### Plan 05-03: Duplicate Detector (2-3 tasks)
- Task 1: Within-table exact hash duplicate scan + auto-merge
- Task 2: Cross-chain bridge heuristic + exchange full re-scan (multi-signal scoring)
- Task 3: Balance-aware merge decision + verification_results audit trail
- Self-check: no duplicate transactions in DB after scan, merge decisions logged

### Plan 05-04: Gap Finder + Report (2-3 tasks)
- Task 1: `verify/gaps.py` — balance series construction + monthly checkpoint comparison
- Task 2: Archival RPC gap confirmation + targeted re-index job queuing
- Task 3: `DISCREPANCIES.md` generator (queries open verification_results, formats report)
- Self-check: missing transaction report generated, re-index jobs queued for gaps, DISCREPANCIES.md produced

---

## Sources

### Primary (HIGH confidence)
- `/home/vitalpointai/projects/Axiom/verify/reconcile.py` — RPC pattern, balance query structure
- `/home/vitalpointai/projects/Axiom/indexers/dedup_handler.py` — Full dedup algorithm, scoring constants
- `/home/vitalpointai/projects/Axiom/indexers/service.py` — Job queue dispatch pattern
- `/home/vitalpointai/projects/Axiom/indexers/classifier_handler.py` — Pipeline chaining (classify → ACB pattern)
- `/home/vitalpointai/projects/Axiom/indexers/acb_handler.py` — Handler class pattern
- `/home/vitalpointai/projects/Axiom/engine/acb.py` — ACBPool structure, units_after semantics, Decimal precision
- `/home/vitalpointai/projects/Axiom/db/models.py` — All table schemas, naming conventions
- `/home/vitalpointai/projects/Axiom/db/migrations/versions/004_cost_basis_schema.py` — Migration pattern
- `/home/vitalpointai/projects/Axiom/indexers/evm_fetcher.py` — Etherscan V2 balance API
- `/home/vitalpointai/projects/Axiom/indexers/staking_rewards.py` — `get_pool_balance()` for staked NEAR
- `/home/vitalpointai/projects/Axiom/config.py` — FASTNEAR_RPC, FASTNEAR_ARCHIVAL_RPC constants

### Secondary (MEDIUM confidence)
- NEAR RPC `view_account` returns `amount` (liquid) AND `locked` fields in same response — confirmed via RPC response structure in existing code
- FastNear archival endpoint for historical block queries — present in config.py, consistent with NEAR protocol documentation

---

## Metadata

**Confidence breakdown:**
- Codebase analysis: HIGH — all source files read directly
- Schema design: HIGH — follows established project patterns exactly
- NEAR RPC patterns: HIGH — existing working code in reconcile.py and staking_rewards.py
- EVM Etherscan balance: HIGH — get_balance() method already implemented in EVMFetcher
- Algorithm design (gap detection, scoring): MEDIUM — logic is sound but confidence thresholds need tuning against real data
- Archival RPC reliability: MEDIUM — endpoint exists in config but no existing usage in codebase to validate

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable — no external library dependencies, all project-internal)
