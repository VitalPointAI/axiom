---
phase: 03-transaction-classification
verified: 2026-03-12T21:50:00Z
status: passed
score: 11/11 must-haves verified
re_verification: false
---

# Phase 03: Transaction Classification Verification Report

**Phase Goal:** Build a rule-based + AI-assisted classification engine that classifies all transactions (NEAR, EVM, exchange) by tax treatment, with multi-leg decomposition, internal transfer detection, spam filtering, staking/lockup linkage, and full audit trail.
**Verified:** 2026-03-12T21:50:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Migration 003 creates 4 tables: transaction_classifications, classification_rules, spam_rules, classification_audit_log | VERIFIED | File exists (229 lines), revision=003, down_revision=002b, all 4 tables confirmed in file |
| 2 | SQLAlchemy models for all 4 tables exist in db/models.py | VERIFIED | All 4 models import cleanly; ClassificationRule has UniqueConstraint uq_cr_name; TransactionClassification has staking_event_id and lockup_event_id FKs |
| 3 | WalletGraph detects internal transfers and cross-chain pairs, scoped by user_id | VERIFIED | engine/wallet_graph.py (248 lines); 7 unit tests pass; all queries use user_id filter; no SQLite references |
| 4 | SpamDetector flags dust/contracts, requires 2+ signals for auto-spam, supports user learning | VERIFIED | engine/spam_detector.py (247 lines); 6 unit tests pass; multi-signal threshold enforced |
| 5 | EVMDecoder detects all 10 Uniswap V2/V3 swap signatures and groups related logs by base tx_hash | VERIFIED | engine/evm_decoder.py (189 lines); 16 unit tests pass covering all signatures and grouping |
| 6 | Rule seeder produces 56 rules (23 NEAR + 23 EVM + 10 exchange) covering all tax categories | VERIFIED | engine/rule_seeder.py (665 lines); python3 import confirmed 56 rules; categories include stake, unstake, reward, trade, liquidity_in/out, collateral, loan, etc. |
| 7 | TransactionClassifier classifies NEAR/EVM/exchange transactions via rule matching, with spam check, internal transfer check, staking/lockup linkage, multi-leg decomposition, and audit logging | VERIFIED | engine/classifier.py (1114 lines); 15 unit tests pass; INSERT INTO transaction_classifications and classification_audit_log both present; _find_staking_event/_find_lockup_event wired; _decompose_swap creates parent + sell_leg + buy_leg + fee_leg |
| 8 | Low-confidence results (< 0.90) flagged needs_review=True | VERIFIED | REVIEW_THRESHOLD = 0.90 defined; applied in _classify_near_tx, _classify_exchange_tx, _classify_evm_tx_group |
| 9 | AI fallback via Claude API for rule misses or confidence < 0.70 | VERIFIED | AI_CONFIDENCE_THRESHOLD=0.70 exported; _classify_with_ai() uses claude-sonnet-4-20250514; lazy ai_client property; graceful degradation to UNKNOWN when SDK unavailable |
| 10 | ClassifierHandler registered in IndexerService as classify_transactions job type | VERIFIED | indexers/classifier_handler.py (89 lines); service.py imports ClassifierHandler; handler dict has "classify_transactions" key; dispatch case elif job_type == "classify_transactions": handler.run_classify(job) |
| 11 | Full test suite passes with no regressions (151 tests) | VERIFIED | pytest tests/ -q: 151 passed, 1 skipped in 1.76s |

**Score:** 11/11 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db/migrations/versions/003_classification_schema.py` | Alembic migration creating 4 classification tables | VERIFIED | 229 lines; revision=003, down_revision=002b; all 4 tables with correct columns, indexes, and partial unique constraints via op.execute() |
| `db/models.py` | SQLAlchemy models for 4 new tables | VERIFIED | 457 lines total; TransactionClassification, ClassificationRule (UniqueConstraint uq_cr_name), SpamRule, ClassificationAuditLog all importable |
| `tests/test_classifier.py` | 15 unit tests for classifier behaviors | VERIFIED | 15 tests pass covering CLASS-01 through CLASS-05 including multi-leg, staking/lockup linkage |
| `tests/test_wallet_graph.py` | 7 unit tests for WalletGraph | VERIFIED | 7 tests pass including internal transfer, cross-chain matching, false-positive prevention, wallet discovery |
| `tests/test_evm_decoder.py` | 16 unit tests for EVMDecoder | VERIFIED | 16 tests pass covering all V2/V3 signatures, defi type detection, multi-token grouping |
| `tests/test_spam_detector.py` | 6 unit tests for SpamDetector | VERIFIED | 6 tests pass: dust detection, contract detection, multi-signal threshold, user learning, global propagation |
| `engine/wallet_graph.py` | PostgreSQL-backed WalletGraph class | VERIFIED | 248 lines; WalletGraph with get_owned_wallets, is_internal_transfer, find_cross_chain_transfer_pairs, suggest_wallet_discovery |
| `engine/spam_detector.py` | SpamDetector with multi-signal detection and user learning | VERIFIED | 247 lines; SpamDetector with check_spam, tag_as_spam, find_similar_spam, load_rules |
| `engine/evm_decoder.py` | EVMDecoder with swap detection and log grouping | VERIFIED | 189 lines; EVMDecoder with detect_swap, detect_defi_type, group_by_base_tx_hash; 10 DEX signatures |
| `engine/rule_seeder.py` | Seeds 56 classification rules from existing patterns | VERIFIED | 665 lines; get_near_rules() = 23, get_evm_rules() = 23, get_exchange_rules() = 10; seed_classification_rules() uses ON CONFLICT (name) DO UPDATE |
| `engine/classifier.py` | TransactionClassifier — core engine with AI fallback | VERIFIED | 1114 lines; all methods implemented; Decimal used for amounts; AI_CONFIDENCE_THRESHOLD and CLASSIFICATION_SYSTEM_PROMPT exported |
| `indexers/classifier_handler.py` | ClassifierHandler job handler | VERIFIED | 89 lines; ClassifierHandler with _ensure_rules_seeded and run_classify |
| `indexers/service.py` | Updated service with classify_transactions handler | VERIFIED | ClassifierHandler imported; "classify_transactions" key in handlers dict; dispatch case present |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `db/models.py` | `003_classification_schema.py` | Model definitions match migration columns | VERIFIED | TransactionClassification, ClassificationRule, SpamRule, ClassificationAuditLog all present in both |
| `engine/wallet_graph.py` | wallets table | SELECT...FROM wallets WHERE user_id | VERIFIED | Line 54: `WHERE user_id = %s AND is_owned = TRUE` |
| `engine/spam_detector.py` | spam_rules table | SELECT...FROM spam_rules WHERE is_active | VERIFIED | Line 66: `WHERE is_active = TRUE` |
| `engine/evm_decoder.py` | raw_data JSONB on transactions | Reads input field from raw_data | VERIFIED | Line 102: `raw_data.get("input", "")` |
| `engine/rule_seeder.py` | classification_rules table | INSERT INTO classification_rules | VERIFIED | Line 641: `INSERT INTO classification_rules...ON CONFLICT (name) DO UPDATE` |
| `engine/classifier.py` | classification_rules table | SELECT...ORDER BY priority DESC | VERIFIED | Line 83: `SELECT * FROM classification_rules WHERE is_active=TRUE ORDER BY priority DESC` |
| `engine/classifier.py` | transaction_classifications table | INSERT...ON CONFLICT DO UPDATE WHERE specialist_confirmed = FALSE | VERIFIED | Line 887: `INSERT INTO transaction_classifications` with upsert |
| `engine/classifier.py` | classification_audit_log table | INSERT for every classification write | VERIFIED | Line 952: `INSERT INTO classification_audit_log` |
| `engine/classifier.py` | engine/wallet_graph.py | WalletGraph.is_internal_transfer() | VERIFIED | Line 295 and 462: `self.wallet_graph.is_internal_transfer(...)` |
| `engine/classifier.py` | engine/evm_decoder.py | EVMDecoder.detect_swap() | VERIFIED | Line 427: `self.evm_decoder.detect_swap(primary_tx)` |
| `engine/classifier.py` | engine/spam_detector.py | SpamDetector.check_spam() before rule matching | VERIFIED | Lines 271 and 444: `self.spam_detector.check_spam(user_id, tx)` |
| `engine/classifier.py` | anthropic API | client.messages.create | VERIFIED | Line 1008: `self.ai_client.messages.create(model="claude-sonnet-4-20250514", ...)` |
| `indexers/classifier_handler.py` | engine/classifier.py | TransactionClassifier.classify_user_transactions() | VERIFIED | Line 81: `stats = self.classifier.classify_user_transactions(user_id)` |
| `indexers/service.py` | indexers/classifier_handler.py | Handler registration | VERIFIED | Line 79: `"classify_transactions": ClassifierHandler(...)` + line 154-155: dispatch |

---

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|------------|-------------|-------------|--------|----------|
| CLASS-01 | 03-01, 03-03, 03-04, 03-05 | System classifies transactions as income, capital_gain, capital_loss, transfer, fee | SATISFIED | TransactionClassifier classifies NEAR/EVM/exchange transactions; TaxCategory enum with 35+ categories; rule seeder with 56 rules; AI fallback for unmatched cases |
| CLASS-02 | 03-01, 03-02, 03-04, 03-05 | System detects internal transfers (between owned wallets) and marks as non-taxable | SATISFIED | WalletGraph.is_internal_transfer() integrated into classifier; TRANSFER_IN/TRANSFER_OUT assigned; 7 tests verify behavior |
| CLASS-03 | 03-01, 03-04, 03-05 | System identifies staking reward distributions and marks as income | SATISFIED | _find_staking_event() in classifier; staking_event_id FK on transaction_classifications; REWARD category; test_links_to_staking_event passes |
| CLASS-04 | 03-01, 03-04, 03-05 | System identifies lockup vesting events and marks as income | SATISFIED | _find_lockup_event() in classifier; lockup_event_id FK on transaction_classifications; test_links_to_lockup_event passes |
| CLASS-05 | 03-01, 03-03, 03-04, 03-05 | System identifies token swaps/trades and calculates gain/loss | SATISFIED | EVMDecoder with 10 Uniswap V2/V3 signatures; _decompose_swap() creates parent + sell_leg + buy_leg + fee_leg; 3-leg decomposition tested |

**Note:** REQUIREMENTS.md status table shows "Not Started" for CLASS-01, CLASS-03, CLASS-04, CLASS-05 and "Complete" for CLASS-02. This is stale — the actual implementation satisfies all five requirements. The status table was not updated after phase completion.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `engine/classifier.py` | 423 | `return []` | INFO | Valid early return guard: `if not txs: return []` — not a stub |
| `engine/spam_detector.py` | 220, 225, 241 | `return []` | INFO | Valid early returns in error/edge case handling — not stubs |

No blockers or warnings found. The `return []` instances are all properly guarded early-returns, not placeholder stubs.

---

## Human Verification Required

### 1. Live Database Integration

**Test:** Run `classify_transactions` job against a database with actual NEAR/EVM/exchange transactions.
**Expected:** Transactions are classified with correct TaxCategory values; staking_events and lockup_events are linked where applicable; audit log entries are created.
**Why human:** No live database was available during verification. All tests use mocked DB connections.

### 2. AI Fallback with Real Anthropic API

**Test:** Trigger classification of an unrecognized NEAR transaction (one that matches no rules) with a live ANTHROPIC_API_KEY set.
**Expected:** Claude API is called, response is parsed, classification_source='ai' is set, result is stored with needs_review=True if confidence < 0.70.
**Why human:** All AI calls are mocked in tests. Cannot verify real API integration without live credentials.

### 3. Rule Seeder Against Live Database

**Test:** Run `seed_classification_rules(pool)` against the actual PostgreSQL database.
**Expected:** 56 rules inserted; re-running is idempotent (ON CONFLICT DO UPDATE); no errors on second run.
**Why human:** Requires live PostgreSQL connection with migration 003 applied.

### 4. REQUIREMENTS.md Status Table Staleness

**Test:** Update the status table in `.planning/REQUIREMENTS.md` to reflect completion.
**Expected:** CLASS-01 through CLASS-05 all show "Complete" (currently shows "Not Started" for 4 of 5).
**Why human:** Documentation cleanup decision requires human judgment on which status values to use.

---

## Summary

Phase 03 goal is fully achieved. All 11 observable truths are verified:

- The classification schema (4 tables, migration 003) and SQLAlchemy models are in place and production-ready.
- WalletGraph, SpamDetector, and EVMDecoder are implemented as standalone, testable modules with PostgreSQL integration.
- The rule seeder contains 56 rules ported from existing tax/categories.py patterns, covering all major NEAR, EVM, and exchange transaction types.
- TransactionClassifier is the complete core engine: rule loading, spam check, internal transfer detection, rule matching, staking/lockup linkage, multi-leg swap decomposition, audit logging, and AI fallback via Claude API.
- ClassifierHandler is registered in IndexerService as the `classify_transactions` job type, with automatic rule seeding on first run.
- 151 tests pass with no regressions. 44 new tests cover all phase-3 behaviors.

The only gap is a stale status table in REQUIREMENTS.md (documentation only, not a code issue).

---

_Verified: 2026-03-12T21:50:00Z_
_Verifier: Claude (gsd-verifier)_
