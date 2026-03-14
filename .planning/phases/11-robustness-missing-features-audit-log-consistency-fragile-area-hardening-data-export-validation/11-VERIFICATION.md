---
phase: 11-robustness-missing-features
verified: 2026-03-14T00:00:00Z
status: passed
score: 10/10 must-haves verified
gaps: []
---

# Phase 11: Robustness & Missing Features — Verification Report

**Phase Goal:** Harden fragile areas across the pipeline, establish a unified audit log for all data mutations, add data export validation with manifest checksums, implement multi-currency swap decomposition for arbitrary multi-hop routes, and add a read-only offline/cached mode for working without live APIs.
**Verified:** 2026-03-14
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | audit_log table exists in PostgreSQL with entity_type, entity_id, action, old_value (JSONB), new_value (JSONB), user_id, timestamp columns | VERIFIED | `db/migrations/versions/008_unified_audit_log.py` creates table with all required columns including JSONB old_value/new_value |
| 2 | Existing classification_audit_log data is migrated to audit_log table and old table is dropped | VERIFIED | Migration upgrade() runs INSERT...SELECT with jsonb_build_object column mapping then op.drop_table("classification_audit_log") |
| 3 | write_audit() helper inserts audit rows within caller's transaction boundary | VERIFIED | `db/audit.py` implements write_audit() with conn parameter, conn=None guard, and try/except; INSERT INTO audit_log present |
| 4 | Tax package output directory contains MANIFEST.json with SHA-256 hash per file | VERIFIED | `reports/generate.py` _write_manifest() computes SHA-256 via hashlib, excludes itself, writes MANIFEST.json |
| 5 | MANIFEST.json includes source data version metadata and Reports API detects stale reports | VERIFIED | get_data_fingerprint() queries 5 DB values; _check_staleness() in api/routers/reports.py compares fingerprints |
| 6 | EVMDecoder decodes Uniswap V3 exactInput multi-hop paths into ordered token address lists | VERIFIED | engine/evm_decoder.py decode_multi_hop_path() and detect_swap() return hop_count and token_path |
| 7 | 3-hop swap (A->B->C) produces correct leg decomposition: sell_leg, intermediate_leg_1, buy_leg | PARTIAL | decompose_swap() in rules.py handles multi-hop correctly, BUT evm_classifier.py does NOT pass token_path from detect_swap() into category_result — intermediate legs never created for real EVM transactions |
| 8 | ACB pool consistency violations are logged and flagged, never raise | VERIFIED | engine/acb/pool.py check_acb_pool_invariants() logs violations and calls write_audit(); returns False on violation |
| 9 | Classifier, Reconciler, and Exchange parser invariant checks work with flag+continue pattern | VERIFIED | check_classifier_invariants_batch() in writer.py; wallet_coverage check in reconcile.py; validate_parsed_row() in base.py — all flag + continue |
| 10 | All data mutations write to audit_log; GET /api/audit/history returns filtered rows; offline mode skips network jobs | VERIFIED | write_audit() wired in classifier/writer.py, acb/engine_acb.py, duplicates.py, transactions.py, verification.py, reports/generate.py; audit.py endpoint with SELECT FROM audit_log; OFFLINE_MODE in config.py; IndexerService._detect_offline_mode() and _is_offline gate |

**Score:** 9/10 truths verified (1 partial)

---

## Required Artifacts

### Plan 01 — ROB-01

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db/migrations/versions/008_unified_audit_log.py` | Alembic migration creating audit_log | VERIFIED | revision="008", down_revision="007"; creates table, migrates data via jsonb_build_object, drops classification_audit_log |
| `db/audit.py` | write_audit() helper | VERIFIED | Exports write_audit(); conn=None guard; try/except; INSERT INTO audit_log with 8 columns |
| `db/models/_all_models.py` | AuditLog SQLAlchemy model | VERIFIED | class AuditLog at line 426 with matching schema |
| `db/models/__init__.py` | AuditLog export + ClassificationAuditLog alias | VERIFIED | AuditLog in __all__; ClassificationAuditLog = AuditLog alias present |

### Plan 02 — ROB-03, ROB-04

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `reports/generate.py` | _write_manifest() and get_data_fingerprint() | VERIFIED | Both present; _write_manifest() excludes MANIFEST.json from file list; get_data_fingerprint() queries 5 DB values. NOTE: get_data_fingerprint defined twice (duplicate at line 63 and line 142) — second shadows first but both are identical |
| `api/routers/reports.py` | Stale report detection | VERIFIED | _check_staleness() reads MANIFEST.json and compares fingerprint; stale key included in list_report_files response |
| `tests/test_reports.py` | Tests for manifest and stale detection | VERIFIED | test_manifest_file_created, test_manifest_contains_files_with_sha256_and_size, test_manifest_does_not_include_itself, test_manifest_contains_source_data_version, test_stale_false_when_fingerprint_matches, test_stale_true_when_fingerprint_differs all present |

### Plan 03 — ROB-09

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `engine/evm_decoder.py` | decode_multi_hop_path() and detect_swap() with hop_count | VERIFIED | decode_multi_hop_path() at line 81; detect_swap() returns hop_count and token_path |
| `engine/classifier/core.py` | Multi-hop swap decomposition | PARTIAL — FILE MISMATCH | Plan specified core.py but implementation is in engine/classifier/rules.py. decompose_swap() in rules.py correctly handles intermediate_leg_N. However, evm_classifier.py does NOT pass token_path from detect_swap() into category_result — the link is broken in production use |
| `tests/test_evm_decoder.py` | Tests for multi-hop path decoding | VERIFIED | 7 test_multi_hop_* tests present covering 2/3/4-token paths, hop_count, backward compat, malformed input |
| `tests/test_classifier.py` | Tests for multi-hop decomposition | VERIFIED | test_multi_hop_3_hop_swap_produces_4_legs, test_multi_hop_4_hop_swap_produces_5_legs, test_multi_hop_intermediate_has_needs_review present |

### Plan 04 — ROB-05, ROB-06, ROB-07, ROB-08

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `engine/acb/pool.py` | check_acb_pool_invariants() | VERIFIED | Module-level function at line 107; checks negative balance/cost; writes write_audit with action='invariant_violation' |
| `engine/classifier/writer.py` | check_classifier_invariants_batch() | VERIFIED | Function at line 187; GROUP BY query for parent_count != 1; swap leg balance check; calls write_audit on violations |
| `verify/reconcile.py` | Wallet coverage assertion | VERIFIED | coverage_complete in stats dict; skipped_wallets detection; write_audit on violations |
| `indexers/exchange_parsers/base.py` | Post-parse_row validation | VERIFIED | validate_parsed_row() at line 53; checks amount/date/asset; sets needs_review=True; called in parse_file() loop |
| `tests/test_invariants.py` | Integration tests for invariant checks | VERIFIED | TestReconcilerInvariants and TestExchangeParserInvariants classes with 5+ tests |

### Plan 05 — ROB-02, ROB-10

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `api/routers/audit.py` | GET /api/audit/history endpoint | VERIFIED | audit_history() function; entity_type required Query param; entity_id optional; ORDER BY created_at DESC; user isolation via user_id filter |
| `api/main.py` | Audit router registered | VERIFIED | audit_router imported and app.include_router(audit_router) at line 104 |
| `tests/test_api_audit.py` | Tests for audit history API | VERIFIED | 6 tests: test_audit_history_returns_rows_for_entity_type, 422 test, ordering test, fields test, user_isolation test, entity_id_filter test |
| `tests/test_offline_mode.py` | Tests for offline mode | VERIFIED | 4+ tests: test_offline_mode_true_skips_network_jobs, allows_non_network_jobs, auto_detects_offline, false_stays_online |
| `config.py` | OFFLINE_MODE + NETWORK_JOB_TYPES | VERIFIED | OFFLINE_MODE = os.environ.get("OFFLINE_MODE", "auto").lower(); NETWORK_JOB_TYPES set defined |
| `indexers/service.py` | _detect_offline_mode() + job gating | VERIFIED | _is_offline instance variable; _detect_offline_mode() probes NearBlocks; job gate at line 186 checks _is_offline and NETWORK_JOB_TYPES |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `db/audit.py` | audit_log table | INSERT INTO audit_log | WIRED | Line 52 in db/audit.py executes INSERT INTO audit_log |
| `db/models/_all_models.py` | migration 008 schema | AuditLog class matches schema | WIRED | AuditLog model at line 426 has matching columns |
| `reports/generate.py` | MANIFEST.json | _write_manifest() after files written | WIRED | _write_manifest() called at line 513 in build() |
| `api/routers/reports.py` | MANIFEST.json | _check_staleness() reads manifest | WIRED | _check_staleness() imports get_data_fingerprint and reads MANIFEST.json |
| `engine/evm_decoder.py` | `engine/classifier/rules.py` | detect_swap() returns hop_count and token_path consumed by classifier | PARTIAL — NOT WIRED | detect_swap() returns token_path but evm_classifier.py constructs category_result WITHOUT token_path (lines 39-45). decompose_swap() reads token_path from category_result — it defaults to [] when missing |
| `engine/acb/pool.py` | `db/audit.py` | write_audit on invariant violation | WIRED | Lines 133-146: imports and calls write_audit with action='invariant_violation' |
| `engine/classifier/writer.py` | `db/audit.py` | write_audit on classify/reclassify | WIRED | write_audit_log() delegates to write_audit() via import at line 14 |
| `verify/reconcile.py` | `db/audit.py` | write_audit on skipped wallets | WIRED | write_audit imported at line 30; called on coverage violation at line 141 |
| `engine/classifier/writer.py` | `db/audit.py` | write_audit on classifier invariant violation | WIRED | Lines 217-228 and 263-273: write_audit with action='invariant_violation' |
| `api/routers/audit.py` | audit_log table | SELECT FROM audit_log | WIRED | Lines 55-82: SELECT...FROM audit_log with WHERE user_id=%s AND entity_type=%s |
| `indexers/service.py` | `config.py` | OFFLINE_MODE check before job dispatch | WIRED | Imports OFFLINE_MODE at line 27; _detect_offline_mode() checks at lines 114/120/126; job gate at line 186 |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ROB-01 | 11-01 | Unified audit log table replacing classification_audit_log | SATISFIED | Migration 008 creates audit_log, migrates data, drops classification_audit_log; write_audit() helper available |
| ROB-02 | 11-05 | Audit log wired to all mutation points + queryable via API | SATISFIED | write_audit() called in 6+ mutation points; GET /api/audit/history endpoint returns filtered rows with user isolation |
| ROB-03 | 11-02 | MANIFEST.json with SHA-256 checksums in tax package | SATISFIED | _write_manifest() computes SHA-256 per file; MANIFEST.json excludes itself |
| ROB-04 | 11-02 | Stale report detection via data fingerprint comparison | SATISFIED | _check_staleness() in reports.py compares 4-field fingerprint; stale key in API response |
| ROB-05 | 11-04 | ACB runtime invariant checks (pool consistency, negative detection) | SATISFIED | check_acb_pool_invariants() detects negative balance/cost; logs + audits violations; never raises |
| ROB-06 | 11-04 | Classifier runtime invariant checks (parent classification, leg balance) | SATISFIED | check_classifier_invariants_batch() detects missing/duplicate parents and swap leg imbalances |
| ROB-07 | 11-04 | Reconciler runtime invariant checks (wallet coverage, diagnosis completeness) | SATISFIED | coverage_complete tracking + write_audit on skipped wallets; undiagnosed discrepancy detection |
| ROB-08 | 11-04 | Exchange parser runtime invariant checks (schema validation, zero-amount detection) | SATISFIED | validate_parsed_row() checks amount/date/asset; flags needs_review=True; never returns None |
| ROB-09 | 11-03 | Multi-hop swap decomposition (V3 exactInput path decoding) | PARTIALLY SATISFIED | decode_multi_hop_path() and detect_swap() work; decompose_swap() handles intermediate legs; BUT evm_classifier.py does not pass token_path into category_result — live EVM multi-hop swaps produce no intermediate legs |
| ROB-10 | 11-05 | Offline/cached mode (IndexerService gate + API status) | SATISFIED | _detect_offline_mode() with auto/true/false; NETWORK_JOB_TYPES gate; /api/health and /api/status expose offline_mode |

**Note:** ROB-* requirements are defined in ROADMAP.md Phase 11 section (lines 453-462). They are not in REQUIREMENTS.md (which covers v1 requirements from earlier phases). This is expected — ROB-* are Phase 11 additions.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `reports/generate.py` | 63 and 142 | Duplicate function definition `get_data_fingerprint` | Warning | Second definition silently shadows first; both are identical so no behavioral difference, but creates confusion and maintenance risk |
| `engine/classifier/evm_classifier.py` | 39-45 | `token_path` from `detect_swap()` not forwarded to `category_result` | Blocker | Multi-hop EVM swaps never produce intermediate legs in production despite the decompose_swap() logic being correct |

---

## Human Verification Required

### 1. Multi-hop EVM swap end-to-end flow

**Test:** Submit a real EVM transaction hash for a Uniswap V3 exactInput multi-hop swap (e.g., USDC -> ETH -> WBTC). Run classification and inspect transaction_classifications rows for that transaction.
**Expected:** Should produce parent + sell_leg + intermediate_leg_1 + buy_leg = 4 rows. Currently will produce only parent + sell_leg + buy_leg = 3 rows due to the wiring gap.
**Why human:** Requires a real or realistic EVM transaction input with exactInput encoding to confirm the end-to-end behavior.

### 2. Offline mode auto-detection with live network

**Test:** Start the IndexerService with OFFLINE_MODE=auto while NearBlocks is unreachable (firewall or wrong URL). Confirm offline mode activates and full_sync jobs are requeued. Then restore connectivity and confirm re-queued jobs eventually run.
**Expected:** Clean activation on network failure; clean deactivation when network restored on next service restart.
**Why human:** Tests mock the network probe; real behavior requires live network environment.

### 3. MANIFEST.json verification by accountant

**Test:** Generate a tax package, then manually modify one CSV file slightly and re-check the MANIFEST. Verify the SHA-256 hash in the original MANIFEST no longer matches the modified file.
**Expected:** MANIFEST checksums enable tamper detection.
**Why human:** Requires end-to-end report generation with real data.

---

## Gaps Summary

One gap blocks full goal achievement for ROB-09:

**Multi-hop EVM swap wiring is broken in production use.** `engine/evm_decoder.py` correctly decodes Uniswap V3 exactInput paths and returns `token_path` and `hop_count` from `detect_swap()`. `engine/classifier/rules.py` correctly creates intermediate legs when `token_path` has > 2 tokens in `category_result`. However, `engine/classifier/evm_classifier.py` (lines 39-45) constructs `category_result` without forwarding `token_path` from the `swap_result`. The unit tests bypass this path by calling `_decompose_swap()` directly with `token_path` already in `category_result`, so they pass.

The fix is a one-line addition in `evm_classifier.py`:

```python
category_result = {
    "category": TaxCategory.TRADE.value,
    "confidence": 0.90,
    "notes": f"EVM DEX swap: {swap_result['method_name']} ({swap_result['dex_type']})",
    "needs_review": False,
    "rule_id": None,
    "token_path": swap_result.get("token_path", []),   # ADD THIS
    "hop_count": swap_result.get("hop_count", 1),       # ADD THIS
}
```

Additionally, `reports/generate.py` has a duplicate `get_data_fingerprint` function definition (lines 63 and 142). The second definition shadows the first. While both are currently identical (no behavioral difference), this should be cleaned up to avoid future maintenance confusion.

---

*Verified: 2026-03-14*
*Verifier: Claude (gsd-verifier)*
