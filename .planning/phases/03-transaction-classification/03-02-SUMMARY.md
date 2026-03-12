---
phase: 03-transaction-classification
plan: 02
subsystem: classification
tags: [wallet-graph, spam-detection, postgresql, psycopg2, internal-transfer, cross-chain, multi-signal]

requires:
  - phase: 03-01
    provides: classification schema — spam_rules table, SpamRule model, transaction_classifications table

provides:
  - WalletGraph class: PostgreSQL-backed internal transfer detection, cross-chain bridge matching, wallet discovery
  - SpamDetector class: multi-signal confidence scoring with user learning and global propagation

affects: [03-04, 04-cost-basis, 05-verification]

tech-stack:
  added: []
  patterns:
    - "Pool acquire/release: pool.getconn() + pool.putconn(conn) in try/finally blocks (consistent with all Phase 2 handlers)"
    - "user_id isolation: every query filtered by user_id to prevent cross-user data leakage"
    - "Decimal math for currency: Decimal(str(amount)) to prevent floating-point precision loss"
    - "Case-insensitive address matching: LOWER() in SQL and LOWER(%s) in params"
    - "Multi-signal confidence: per-signal weight accumulation capped at 1.0; single signal < 0.90"

key-files:
  created:
    - engine/spam_detector.py
  modified:
    - engine/wallet_graph.py
    - tests/test_wallet_graph.py
    - tests/test_spam_detector.py

key-decisions:
  - "Signal weight 0.46 per signal: 1 signal = 0.46 (not spam), 2 signals = 0.92 (auto-spam) — enforces 2-signal minimum for auto-spam threshold of 0.90"
  - "known_spam_contract returns 0.99 immediately: explicit curated rules bypass signal accumulation — high-precision human-confirmed data"
  - "Cross-chain matching uses 5% amount tolerance + 30-min window: wider than DedupHandler's 1%/10-min to cover bridge fees and settlement latency"
  - "Decimal for cross-chain amount comparison: prevents floating-point errors on large yoctoNEAR/wei values"
  - "WalletGraph.find_cross_chain_transfer_pairs() always filters both queries by user_id: prevents false-positive cross-user bridge matches"
  - "suggest_wallet_discovery() excludes already-owned wallets via NOT IN subquery: avoids suggesting wallets user already tracks"

patterns-established:
  - "TDD pattern: RED (failing test import) -> GREEN (implementation passes) -> commit per task"
  - "Mock pool pattern: MagicMock pool + conn + cursor with fetchall.side_effect for multi-call tests"

requirements-completed: [CLASS-02]

duration: 4min
completed: 2026-03-12
---

# Phase 03 Plan 02: WalletGraph + SpamDetector Summary

**PostgreSQL WalletGraph rewrite with user-scoped internal transfer detection, 5%/30-min cross-chain matching, and multi-signal SpamDetector requiring 2+ signals for auto-spam classification.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-12T21:10:53Z
- **Completed:** 2026-03-12T21:14:55Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Rewrote `engine/wallet_graph.py` as a class-based PostgreSQL module with 4 methods, eliminating all SQLite references
- Created `engine/spam_detector.py` with multi-signal confidence scoring, user tag learning, and global rule propagation
- 13 unit tests passing across both modules with fully mocked DB (no live database required)
- Maintained all 136 pre-existing tests passing (16 pre-existing scaffolds skipped)

## Task Commits

Each task was committed atomically:

1. **Task 1: WalletGraph PostgreSQL rewrite** - `194600b` (feat)
2. **Task 2: SpamDetector with multi-signal detection** - `25c00a0` (feat)

_Note: TDD tasks — tests written first, implementation second, single combined commit per task._

## Files Created/Modified

- `engine/wallet_graph.py` - Complete rewrite: WalletGraph class with get_owned_wallets(), is_internal_transfer(), find_cross_chain_transfer_pairs(), suggest_wallet_discovery()
- `engine/spam_detector.py` - New: SpamDetector class with check_spam(), tag_as_spam(), find_similar_spam(), load_rules()
- `tests/test_wallet_graph.py` - Replaced stubs with 7 real unit tests (mocked pool)
- `tests/test_spam_detector.py` - Replaced stubs with 6 real unit tests (mocked pool)

## Decisions Made

- Signal weight 0.46 per signal so that 1 signal stays below 0.90 (single-signal false positive prevention) while 2 signals reach 0.92 (auto-spam)
- Known spam contract rules short-circuit with 0.99 confidence — human-curated rules are high-precision and bypass accumulation
- Cross-chain bridge matching uses wider tolerances than same-chain dedup (5% vs 1%, 30-min vs 10-min) to account for bridge fees and network settlement latency
- WalletGraph returns `list` (not typed `list[dict]`) to stay compatible with Python 3.8 while still being clear

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion for global propagation was overly strict**
- **Found during:** Task 2 (SpamDetector — test_global_propagation)
- **Issue:** Test asserted `"user_id" not in sql` but the SELECT returns `user_id` as a column, not a filter
- **Fix:** Changed assertion to check `WHERE` clause specifically for `USER_ID =` pattern, not presence of `user_id` anywhere in SQL
- **Files modified:** tests/test_spam_detector.py
- **Verification:** 6/6 spam detector tests pass
- **Committed in:** 25c00a0 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 logic bug in test assertion)
**Impact on plan:** Test was testing the right thing but with wrong assertion logic. Fix makes the test accurately verify global propagation without false failures.

## Issues Encountered

None beyond the test assertion fix above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- WalletGraph and SpamDetector are ready for use by the classifier (Plan 03-04)
- Both modules accept the same pool pattern used throughout the codebase
- CLASS-02 requirement fully satisfied: internal transfer detection scoped by user_id
- Spam detection requires 2+ signals to prevent false positives (Pitfall 4 addressed)

## Self-Check: PASSED

- FOUND: engine/wallet_graph.py
- FOUND: engine/spam_detector.py
- FOUND: tests/test_wallet_graph.py
- FOUND: tests/test_spam_detector.py
- FOUND: .planning/phases/03-transaction-classification/03-02-SUMMARY.md
- FOUND commit: 194600b (WalletGraph PostgreSQL rewrite)
- FOUND commit: 25c00a0 (SpamDetector with multi-signal detection)

---
*Phase: 03-transaction-classification*
*Completed: 2026-03-12*
