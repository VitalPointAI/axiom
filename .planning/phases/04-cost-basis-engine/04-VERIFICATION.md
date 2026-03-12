---
phase: 04-cost-basis-engine
verified: 2026-03-12T23:55:00Z
status: passed
score: 18/18 must-haves verified
re_verification: null
gaps: []
human_verification: []
---

# Phase 4: Cost Basis Engine Verification Report

**Phase Goal:** Build the cost basis calculation engine — ACB tracking, capital gains/income ledgers, superficial loss detection, price service extensions, and job queue integration.
**Verified:** 2026-03-12T23:55:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Migration 004 creates acb_snapshots, capital_gains_ledger, income_ledger, and price_cache_minute tables | VERIFIED | `004_cost_basis_schema.py` lines 31–235; all 4 tables created with correct FKs, indexes, and constraints |
| 2 | PriceService can fetch closest-available price at a specific Unix timestamp via CoinGecko market_chart/range | VERIFIED | `price_service.py` line 208: `get_price_at_timestamp()` implements 2-hour window fetch and closest-timestamp selection |
| 3 | PriceService can fetch USD/CAD rate from Bank of Canada Valet API for any date | VERIFIED | `price_service.py` line 260: `get_boc_cad_rate()` calls `BOC_VALET_BASE` with FXUSDCAD series |
| 4 | Minute-level prices cached in price_cache_minute and reused on subsequent calls | VERIFIED | `get_price_at_timestamp()` checks `_get_cached_minute()` before API call; caches via `_cache_minute_price()` with INSERT ON CONFLICT DO NOTHING |
| 5 | Weekend/holiday BoC rate lookback returns most recent business day rate | VERIFIED | `get_boc_cad_rate()` loops `range(6)` days back; sets `source='bank_of_canada_fallback'` |
| 6 | ACB calculated using Canadian average cost method with Decimal precision | VERIFIED | `ACBPool.acb_per_unit` = `total_cost_cad / total_units` quantized to 8 places; no float arithmetic anywhere in `engine/acb.py` |
| 7 | ACB pooled per token across ALL user wallets (not per-wallet) | VERIFIED | `ACBEngine.calculate_for_user()` maintains `pools: dict[str, ACBPool]` keyed by token symbol; SQL query has no per-wallet grouping |
| 8 | Per-transaction ACB snapshots persisted in acb_snapshots table for audit trail | VERIFIED | `_SNAPSHOT_UPSERT_SQL` in `acb.py` lines 254–278; called after every acquire/dispose |
| 9 | Fees on acquisitions increase ACB pool; fees on disposals reduce proceeds | VERIFIED | `ACBPool.acquire()` adds `cost_cad + fee_cad` to `total_cost_cad`; `ACBPool.dispose()` computes `net_proceeds_cad = proceeds_cad - fee_cad` |
| 10 | Swap fee_leg adds to buy_leg ACB (CRA acquisition cost treatment) | VERIFIED | `_handle_swap()` computes `fee_cad` from fee_leg, passes it as `fee_cad=fee_cad` to `buy_pool.acquire()` |
| 11 | Capital gains ledger populated with one row per disposal event | VERIFIED | `GainsCalculator.record_disposal()` issues INSERT ON CONFLICT (acb_snapshot_id) DO UPDATE; called in `_handle_disposal()` and `_handle_swap()` |
| 12 | Income ledger populated with staking rewards and lockup vesting events using pre-captured FMV | VERIFIED | `_handle_income()` uses `se_fmv_cad` / `le_fmv_cad` directly; calls `gains.record_income()` with correct source_type |
| 13 | Transactions processed chronologically with deterministic tie-breaking (block_timestamp ASC, id ASC) | VERIFIED | `_CLASSIFY_SQL` ORDER BY: `COALESCE(t.block_timestamp, EXTRACT(EPOCH FROM et.timestamp)::BIGINT) ASC, tc.id ASC` |
| 14 | Overselling clamped and flagged needs_review | VERIFIED | `ACBPool.dispose()` lines 190–192: `if units > self.total_units: needs_review = True; units = self.total_units` |
| 15 | Superficial loss detected when same token rebought within 30 days before or after a loss disposal | VERIFIED | `SuperficialLossDetector.scan_for_user()` with `WINDOW_SECONDS = 30 * 86400`; queries both `transactions` and `exchange_transactions` |
| 16 | Denied loss amount pro-rated for partial rebuys | VERIFIED | `denied_ratio = min(Decimal("1"), total_rebought / units_disposed)` at `superficial.py` lines 279–286 |
| 17 | ACBHandler registered as calculate_acb job type in IndexerService | VERIFIED | `service.py` line 81: `"calculate_acb": ACBHandler(self.pool, self.price_service)`; dispatch case at line 158 |
| 18 | ClassifierHandler triggers calculate_acb job after classification completes | VERIFIED | `classifier_handler.py` queues `calculate_acb` job with dedup guard; confirmed by grep for `calculate_acb` pattern |

**Score:** 18/18 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db/migrations/versions/004_cost_basis_schema.py` | Alembic migration for 4 new cost basis tables | VERIFIED | revision="004", down_revision="003"; all 4 tables, FKs, indexes present |
| `db/models.py` | ACBSnapshot, CapitalGainsLedger, IncomeLedger, PriceCacheMinute SQLAlchemy models | VERIFIED | 4 classes at lines 461, 533, 588, 642; `python3 -c "from db.models import ACBSnapshot, CapitalGainsLedger, IncomeLedger, PriceCacheMinute"` succeeds |
| `indexers/price_service.py` | get_price_at_timestamp(), get_boc_cad_rate(), get_price_cad_at_timestamp() | VERIFIED | All 3 methods present at lines 208, 260, 302; BOC_VALET_BASE and STABLECOIN_MAP constants present |
| `engine/acb.py` | ACBPool + ACBEngine (min 150 lines) | VERIFIED | 857 lines; exports ACBPool, ACBEngine, TOKEN_SYMBOL_MAP, resolve_token_symbol, normalize_timestamp, to_human_units |
| `engine/gains.py` | GainsCalculator (min 80 lines) | VERIFIED | 214 lines; exports GainsCalculator with record_disposal(), record_income(), clear_for_user() |
| `engine/superficial.py` | SuperficialLossDetector (min 80 lines) | VERIFIED | 386 lines; exports SuperficialLossDetector with scan_for_user(), apply_superficial_losses() |
| `indexers/acb_handler.py` | ACBHandler job handler (min 30 lines) | VERIFIED | 59 lines; ACBHandler.run_calculate_acb() delegates to ACBEngine |
| `indexers/service.py` | calculate_acb registered | VERIFIED | Handler registered at line 81; dispatch case at line 158 |
| `tests/test_acb.py` | Unit tests for ACBPool, ACBEngine, GainsCalculator (min 100 lines) | VERIFIED | 419 lines; 13 tests: TestACBPool x6, TestACBEngine x4, TestGainsCalculator x3 |
| `tests/test_superficial.py` | Unit tests for SuperficialLossDetector (min 80 lines) | VERIFIED | 420 lines; 8 tests covering all superficial loss scenarios |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `004_cost_basis_schema.py` | `db/models.py` | Migration table names match model __tablename__ | VERIFIED | "acb_snapshots", "capital_gains_ledger", "income_ledger", "price_cache_minute" in both |
| `price_service.py` | `price_cache_minute` table | INSERT ON CONFLICT DO NOTHING | VERIFIED | `_cache_minute_price()` calls INSERT ON CONFLICT; `get_price_at_timestamp()` checks cache first |
| `engine/acb.py` | `acb_snapshots` table | INSERT ON CONFLICT DO UPDATE after each acquire/dispose | VERIFIED | `_SNAPSHOT_UPSERT_SQL` at lines 254–278; called in `_persist_snapshot()` |
| `engine/gains.py` | `capital_gains_ledger` table | INSERT ON CONFLICT for each disposal | VERIFIED | `_DISPOSAL_INSERT_SQL` with ON CONFLICT (acb_snapshot_id) DO UPDATE |
| `engine/gains.py` | `income_ledger` table | INSERT for staking/vesting income events | VERIFIED | `_INCOME_INSERT_SQL` called in `record_income()` |
| `engine/acb.py` | `transaction_classifications` table | SELECT chronological classifications for replay | VERIFIED | `_CLASSIFY_SQL` queries `transaction_classifications` with ORDER BY block_timestamp ASC, tc.id ASC |
| `engine/superficial.py` | `transactions + exchange_transactions` | SQL query for rebuys within 61-day window | VERIFIED | `_ONCHAIN_REBUYS_QUERY` joins transactions; `_EXCHANGE_REBUYS_QUERY` queries exchange_transactions |
| `engine/superficial.py` | `capital_gains_ledger` | UPDATE is_superficial_loss, denied_loss_cad | VERIFIED | `_UPDATE_LEDGER_SUPERFICIAL` SQL in `apply_superficial_losses()` |
| `indexers/acb_handler.py` | `engine/acb.py` | ACBEngine.calculate_for_user() | VERIFIED | Lazy import `from engine.acb import ACBEngine` in `run_calculate_acb()` |
| `indexers/service.py` | `indexers/acb_handler.py` | handler registration in self.handlers dict | VERIFIED | `"calculate_acb": ACBHandler(...)` at line 81; import at line 39 |
| `indexers/classifier_handler.py` | `indexers/service.py` | Queue calculate_acb job after classification | VERIFIED | INSERT INTO indexing_jobs with job_type='calculate_acb'; dedup SELECT guards against duplicates |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ACB-01 | 04-02, 04-03 | ACB using Canadian average cost method | SATISFIED | ACBPool implements average cost; REQUIREMENTS.md checkbox `[x]` |
| ACB-02 | 04-02, 04-03 | ACB tracked per token across all wallets (pooled) | SATISFIED | Single `pools` dict in ACBEngine; SQL does not filter by wallet |
| ACB-03 | 04-01 | Historical FMV prices fetched for income events | SATISFIED | PriceService.get_price_at_timestamp(), get_boc_cad_rate(); REQUIREMENTS.md checkbox `[x]` |
| ACB-04 | 04-02, 04-03 | Cost basis adjusted for fees | SATISFIED | ACBPool.acquire() adds fee_cad; ACBPool.dispose() subtracts fee from proceeds |
| ACB-05 | 04-03 | Superficial loss rules (30-day rule) — flag for manual review | SATISFIED | SuperficialLossDetector implemented; all losses flagged needs_review=True |

**Note on REQUIREMENTS.md:** ACB-05 is marked `[ ]` (incomplete) in `REQUIREMENTS.md` but is fully implemented. The checkbox was not updated when Phase 04-03 completed. This is a documentation inconsistency — the implementation is present and tested — but `REQUIREMENTS.md` should be updated to `[x]` for ACB-05.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None detected | — | — | — |

Scanned all 6 new/modified engine files and 2 test files. No stub returns, placeholder implementations, TODO/FIXME comments, or float arithmetic found in cost basis code.

---

### Human Verification Required

None. All behaviors are verifiable programmatically through the mock-based test suite.

Items that would normally need human verification but are covered by the test suite:
- ACB pooling across wallets: covered by TestACBEngine::test_cross_wallet_pool
- Staking FMV passthrough: covered by TestACBEngine::test_staking_income_fmv
- Swap fee_leg ACB treatment: covered by TestACBEngine::test_swap_fee_leg_acb
- Superficial loss pro-rating: covered by 8 tests in TestSuperficialLoss

---

### Test Suite Results

```
tests/test_acb.py       — 13 tests PASSED
tests/test_superficial.py — 8 tests PASSED
tests/test_price_service.py — target file tests PASSED (subset of 48)
Full suite: 182 passed, 1 skipped
```

---

### Summary

Phase 4 goal fully achieved. The cost basis engine is implemented end-to-end:

1. **Foundation (Plan 01):** Migration 004 creates 4 tables; 4 SQLAlchemy models; PriceService extended with minute-level timestamp pricing and Bank of Canada CAD rates.

2. **Engine (Plan 02):** ACBPool (Decimal-precise, average-cost) and ACBEngine (full user replay with acb_snapshots persistence) replace the legacy float-based ACBTracker. GainsCalculator writes capital_gains_ledger and income_ledger rows.

3. **Integration (Plan 03):** SuperficialLossDetector detects CRA 30-day window rebuys across all wallets and exchanges, pro-rates partial denials, and flags all detections needs_review=True. ACBHandler registered in IndexerService as 'calculate_acb'; ClassifierHandler auto-queues ACB recalculation after classification completes.

All 5 ACB requirements (ACB-01 through ACB-05) are implemented. The only outstanding item is updating `REQUIREMENTS.md` to mark `ACB-05` as `[x]`.

---

_Verified: 2026-03-12T23:55:00Z_
_Verifier: Claude (gsd-verifier)_
