---
phase: 03-transaction-classification
plan: 04
subsystem: classification
tags: [python, postgresql, psycopg2, tax-classification, tdd, near, evm, exchange]

requires:
  - phase: 03-01
    provides: classification schema (transaction_classifications, classification_rules, classification_audit_log, spam_rules)
  - phase: 03-02
    provides: WalletGraph.is_internal_transfer(), SpamDetector.check_spam()
  - phase: 03-03
    provides: EVMDecoder.detect_swap(), rule_seeder with 56 rules

provides:
  - TransactionClassifier class in engine/classifier.py
  - Rule-based NEAR/EVM/exchange classification via priority-ordered DB rules
  - Staking reward linkage to staking_events (CLASS-03)
  - Lockup vest linkage to lockup_events (CLASS-04)
  - DEX swap multi-leg decomposition (parent + sell_leg + buy_leg + fee_leg)
  - Spam pre-check and internal transfer detection before rule matching
  - Audit log write for every classification change

affects:
  - 04-cost-basis-engine
  - 05-verification
  - 06-reporting

tech-stack:
  added: []
  patterns:
    - "Priority-ordered rule matching: rules loaded from classification_rules ORDER BY priority DESC, first match wins"
    - "Staking linkage: tx_hash exact match first, then 60-second timestamp window fallback"
    - "Lockup linkage: same tx_hash-first, 60s-window pattern as staking"
    - "Swap decomposition: _decompose_swap() returns list[dict] with leg_type + leg_index"
    - "confidence < 0.90 always sets needs_review=True"
    - "Specialist-confirmed records preserved via ON CONFLICT WHERE specialist_confirmed = FALSE"

key-files:
  created: []
  modified:
    - engine/classifier.py
    - tests/test_classifier.py

key-decisions:
  - "Rules provided pre-sorted (priority DESC) to _match_rules — no re-sort inside matching loop"
  - "Internal transfer check uses counterparty field; direction determines TRANSFER_IN vs TRANSFER_OUT"
  - "Lockup linkage triggers for INCOME, REWARD, or DEPOSIT categories with .lockup.near counterparty"
  - "EVM swap decomposition uses EVMDecoder.detect_swap() on primary tx of group; fee_leg only emitted when tx.fee is truthy"
  - "REVIEW_THRESHOLD = 0.90 (not 0.70): plan says confidence < 0.90 -> needs_review"

patterns-established:
  - "TDD: RED (failing tests) -> GREEN (implementation) -> verify all pass"
  - "_classify_near_tx returns list[dict] for both single and multi-leg results"
  - "_make_record is the single factory for classification record dicts"
  - "_decompose_swap is a pure function (no DB calls), safe to test in isolation"

requirements-completed: [CLASS-01, CLASS-03, CLASS-04, CLASS-05]

duration: 25min
completed: 2026-03-12
---

# Phase 03 Plan 04: Transaction Classification Engine Summary

**PostgreSQL-backed TransactionClassifier with rule priority matching, WalletGraph internal transfer detection, staking/lockup event linkage, EVM swap decomposition, and audit logging — 15 tests, 151 total pass**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-03-12T21:30:00Z
- **Completed:** 2026-03-12T21:55:00Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- Rewrote `engine/classifier.py` completely: removed all SQLite/get_connection() legacy code, implemented PostgreSQL-backed `TransactionClassifier` class
- Rule engine: loads `classification_rules` sorted by priority DESC, matches NEAR/EVM/exchange transactions via 9 pattern fields (method_name, action_type, counterparty_suffix, counterparty_in, tx_type, input_selector, direction, amount_gt, is_own_wallet)
- Staking reward linkage (CLASS-03): `_find_staking_event()` tries exact tx_hash match then 60-second timestamp window, sets `staking_event_id` on REWARD classifications from staking pools
- Lockup vest linkage (CLASS-04): same tx_hash-first/60s-window pattern, sets `lockup_event_id` for income events from `.lockup.near` counterparties
- EVM swap decomposition (CLASS-05): `EVMDecoder.detect_swap()` + `group_by_base_tx_hash()`, decomposed swaps produce 4 rows: parent + sell_leg (index 0) + buy_leg (index 1) + fee_leg (index 2, only when fee present)
- Spam pre-check (SpamDetector.check_spam) + internal transfer check (WalletGraph.is_internal_transfer) before rule matching

## Task Commits

1. **Task 1: TransactionClassifier core** - `b2e60c7` (feat)

## Files Created/Modified

- `/home/vitalpointai/projects/Axiom/engine/classifier.py` - Full rewrite: TransactionClassifier with rule matching, staking/lockup linkage, swap decomposition, audit log
- `/home/vitalpointai/projects/Axiom/tests/test_classifier.py` - 15 real tests replacing all 16 pytest.skip() stubs

## Decisions Made

- Rules provided to `_match_rules` must be pre-sorted by caller (priority DESC). `_load_rules()` returns them sorted; tests sort `_near_rules()` when mixing priorities.
- `REVIEW_THRESHOLD = 0.90` per plan spec (not 0.70 from original categories.py). Any rule with confidence < 0.90 sets needs_review.
- `_decompose_swap` is a pure function (no DB calls) accepting a dict from `_classify_near_tx`. The parent_classification_id linking of legs is deferred to `_upsert_classification` (DB assigns IDs at write time).
- `fee_leg` only emitted when `tx.get("fee")` is truthy — tests for 4-row decomposition pass a `fee` field in the tx dict.
- EVM plain transfer classification uses `input_selector: None` rule pattern to match transactions with empty calldata.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Initial test suite had EVM plain-transfer test failing because `_near_rules()` fixture lacked EVM rules. Fixed by adding EVM DEX swap and plain-transfer rules to the fixture (not a code bug — test setup issue).
- Lockup test rule ordering: appending lockup rule to `_near_rules()` without sorting produced wrong match order. Fixed by sorting the combined list by priority DESC in the test.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- TransactionClassifier complete and tested. Ready for Phase 4 (Cost Basis Engine) to consume `transaction_classifications` records.
- `classify_user_transactions(user_id)` is the main entry point for batch classification.
- Staking and lockup event linkage ensures income events have FK references, preventing double-counting in cost basis calculations.

## Self-Check: PASSED

All artifacts verified:
- FOUND: engine/classifier.py
- FOUND: tests/test_classifier.py
- FOUND: 03-04-SUMMARY.md
- FOUND: commit b2e60c7

---
*Phase: 03-transaction-classification*
*Completed: 2026-03-12*
