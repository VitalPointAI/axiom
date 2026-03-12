---
phase: 03-transaction-classification
plan: "03"
subsystem: classification
tags: [evm, decoder, uniswap, aave, rule-seeder, classification-rules, near, defi]

# Dependency graph
requires:
  - phase: 03-01
    provides: classification_rules table with uq_cr_name unique constraint (migration 003)

provides:
  - EVMDecoder class with 4-byte method selector matching for 21 known DeFi signatures
  - group_by_base_tx_hash() grouping for ERC20/NFT multi-transfer deduplication
  - rule_seeder with 56 rules covering NEAR/EVM/exchange classification patterns
  - seed_classification_rules() idempotent upsert function ready for live DB

affects:
  - 03-04 (classifier engine will import EVMDecoder and load rules from DB)
  - 03-05 (spam detector may use grouping for multi-transfer spam detection)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - 4-byte method selector matching for EVM DeFi type detection
    - logIndex suffix stripping for multi-token tx grouping (hash-N -> hash)
    - Priority-ordered rule table (100 staking > 90 DEX > 80 lending > 70 LP > 60 misc > 50 basic > 40 exchange)
    - Idempotent DB seeding via INSERT ON CONFLICT (name) DO UPDATE

key-files:
  created:
    - engine/evm_decoder.py
    - engine/rule_seeder.py
  modified:
    - tests/test_evm_decoder.py

key-decisions:
  - "EVMDecoder is purely data-driven (no DB) — tested with synthetic tx dicts"
  - "LP_SIGNATURES extended to 6 entries (added removeLiquidityETHSupportingFeeOnTransferTokens and removeLiquidityWithPermit)"
  - "LENDING_SIGNATURES extended to 5 entries (added flashLoan for completeness)"
  - "get_evm_rules() generates EVM rules by iterating EVMDecoder signature dicts — single source of truth"
  - "chain='evm' for all EVM rules (covers ethereum/polygon/cronos/optimism uniformly)"
  - "chain='exchange' for exchange rules (matches exchange_transactions table records)"

patterns-established:
  - "EVM signature matching: raw_data.input[:10] compared against 4-byte hex selector dict"
  - "Multi-token grouping: tx_hash.split('-')[0] to extract base hash from hash-logIndex format"
  - "Rule pattern schema: {method_name, counterparty_suffix, direction, is_own_wallet, input_selector, tx_type}"
  - "Priority ordering: higher int = checked first in classifier"

requirements-completed: [CLASS-01, CLASS-05]

# Metrics
duration: 4min
completed: 2026-03-12
---

# Phase 03 Plan 03: EVM Decoder and Rule Seeder Summary

**EVMDecoder with 21 DeFi method selectors (Uniswap V2/V3, Aave V2, LP ops) and a 56-rule seeder porting all tax/categories.py NEAR patterns plus EVM/exchange patterns to the classification_rules table.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-12T21:11:00Z
- **Completed:** 2026-03-12T21:14:15Z
- **Tasks:** 2
- **Files modified:** 3 (2 created, 1 rewritten)

## Accomplishments

- EVMDecoder detects all 10 Uniswap V2/V3 swap selectors, 5 Aave V2 lending selectors, and 6 LP selectors; groups ERC20/NFT multi-transfers by base tx_hash to prevent Pitfall 3 (multiple SELL per swap)
- Rule seeder produces 56 rules (23 NEAR + 23 EVM + 10 exchange) with priority ordering 100-40, covering every pattern from tax/categories.py and engine/classifier.py
- 16 new passing tests in test_evm_decoder.py; all 136 tests pass (16 previously-skipped stubs replaced with real assertions)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: EVM decoder failing tests** - `52dce42` (test)
2. **Task 1 GREEN: EVMDecoder implementation** - `d8e91b0` (feat)
3. **Task 2: Rule seeder** - `05d0d8d` (feat)

**Plan metadata:** (docs commit — see below)

_Note: TDD tasks have multiple commits (test RED -> feat GREEN)_

## Files Created/Modified

- `engine/evm_decoder.py` - EVMDecoder class: detect_swap(), detect_defi_type(), group_by_base_tx_hash(), DEX/LENDING/LP signature dicts
- `engine/rule_seeder.py` - get_near_rules() (23), get_evm_rules() (23), get_exchange_rules() (10), seed_classification_rules(pool)
- `tests/test_evm_decoder.py` - 16 tests across TestSwapDetection, TestMethodSignatures, TestMultiTokenGrouping

## Decisions Made

- EVMDecoder is purely data-driven (no DB access) — makes it trivially testable with synthetic tx dicts, no fixtures required
- LP_SIGNATURES extended to 6 entries beyond the plan's 4 to cover additional Uniswap V2 variants (removeLiquidityETHSupportingFeeOnTransferTokens, removeLiquidityWithPermit)
- LENDING_SIGNATURES extended to 5 entries (added flashLoan) for more complete Aave V2 coverage
- get_evm_rules() iterates EVMDecoder signature dicts as single source of truth — adding a new selector to EVMDecoder automatically adds its DB rule
- chain='evm' for all EVM rules covers all four EVM chains (ethereum/polygon/cronos/optimism) uniformly
- chain='exchange' for exchange rules mirrors how exchange_transactions are stored

## Deviations from Plan

None - plan executed exactly as written. LP/LENDING signature table expansions are additive extensions within the same pattern (not architectural changes).

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 04 (classifier engine) can now: import EVMDecoder for on-the-fly swap detection, call seed_classification_rules() to populate DB rules at startup, query classification_rules by chain/priority for rule-based classification
- EVMDecoder.group_by_base_tx_hash() is ready for classifier to consolidate multi-leg swap events before classification
- All 56 rules are JSONB-pattern dicts with consistent schema ready for the classifier's rule-matching engine

---
*Phase: 03-transaction-classification*
*Completed: 2026-03-12*
