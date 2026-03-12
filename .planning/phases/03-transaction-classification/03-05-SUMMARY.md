---
phase: 03-transaction-classification
plan: 05
subsystem: classification
tags: [anthropic, claude-api, job-queue, classifier, ai-fallback, indexer]

requires:
  - phase: 03-04
    provides: TransactionClassifier with rule-based classification, WalletGraph, SpamDetector, EVMDecoder
  - phase: 03-03
    provides: seed_classification_rules (56 rules), EVMDecoder

provides:
  - "AI fallback in TransactionClassifier via Claude claude-sonnet-4-20250514 for ambiguous transactions"
  - "AI_CONFIDENCE_THRESHOLD=0.70 as importable module constant"
  - "CLASSIFICATION_SYSTEM_PROMPT for Canadian tax context"
  - "ClassifierHandler job handler wiring classification into IndexerService"
  - "'classify_transactions' job type fully operational in IndexerService"
  - "Rule auto-seeding on first classify_transactions job if rules table is empty"

affects:
  - "04-cost-basis-engine"
  - "06-reporting"

tech-stack:
  added: []
  patterns:
    - "Lazy Anthropic client via @property (same pattern as AIFileAgent)"
    - "AI fallback invoked when rule match confidence < 0.70 or no rule matched"
    - "classification_source='ai' for AI-classified transactions vs 'rule'"
    - "AI confidence < 0.70 always sets needs_review=True"
    - "ClassifierHandler._rules_seeded flag prevents repeated COUNT queries"

key-files:
  created:
    - indexers/classifier_handler.py
  modified:
    - engine/classifier.py
    - indexers/service.py

key-decisions:
  - "AI_CONFIDENCE_THRESHOLD=0.70 as module constant — below this triggers AI fallback even for rule matches"
  - "AI fallback uses more-confident result (rule vs AI) rather than always preferring one"
  - "classification_source='ai' distinguishes AI-classified rows from rule-matched in audit trail"
  - "ClassifierHandler._rules_seeded prevents repeated COUNT(*) queries across multiple jobs"
  - "AI error/unavailable falls back to UNKNOWN category with confidence=0.30 and needs_review=True"

patterns-established:
  - "AI fallback pattern: check if result is None or confidence < threshold, call AI, take higher-confidence result"
  - "_parse_json_response() with regex fallback for markdown-wrapped JSON (reused from AIFileAgent)"
  - "_build_ai_context() strips raw_data bulk to keep token count low"

requirements-completed: [CLASS-01, CLASS-02, CLASS-03, CLASS-04, CLASS-05]

duration: 9min
completed: 2026-03-12
---

# Phase 03 Plan 05: Classification Integration Summary

**Claude AI fallback (confidence < 0.70) + ClassifierHandler job type wiring full classification pipeline into IndexerService with auto rule seeding**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-12T21:26:38Z
- **Completed:** 2026-03-12T21:35:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added AI classification fallback to TransactionClassifier using Claude claude-sonnet-4-20250514 API
- Created ClassifierHandler that seeds rules, dispatches classification, and logs stats
- Registered 'classify_transactions' job type in IndexerService with full dispatch support
- All 151 existing tests continue to pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: AI classification fallback in TransactionClassifier** - `2d85441` (feat)
2. **Task 2: ClassifierHandler + IndexerService registration + rule seeding** - `ae97649` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `engine/classifier.py` - Added AI_CONFIDENCE_THRESHOLD, CLASSIFICATION_SYSTEM_PROMPT, ai_client property, _classify_with_ai(), _parse_json_response(), _build_ai_context(); integrated AI fallback into all three classify methods
- `indexers/classifier_handler.py` - New ClassifierHandler with _ensure_rules_seeded() and run_classify()
- `indexers/service.py` - Added ClassifierHandler import, 'classify_transactions' handler registration, dispatch case

## Decisions Made

- AI fallback takes the higher-confidence result between rule and AI (not always AI): ensures deterministic rules with confidence >= 0.70 are not overridden by uncertain AI responses
- classification_source set to 'ai' for AI-classified transactions — provides audit trail distinction
- _rules_seeded instance flag prevents repeated COUNT(*) queries across jobs on same handler instance
- AI errors/SDK unavailability degrade gracefully to UNKNOWN + needs_review=True (no crashes)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Anthropic SDK already installed (used by AIFileAgent in Phase 2).

## Next Phase Readiness

- Full classification pipeline operational: classify_transactions job can be queued via API or scheduler
- All 5 phases of Phase 3 complete (CLASS-01 through CLASS-05)
- Phase 4 (Cost Basis Engine) can now consume classified transactions from transaction_classifications table
- AI fallback ensures 100% of transactions receive a classification (no unhandled cases)

## Self-Check: PASSED

- `indexers/classifier_handler.py` — FOUND
- `engine/classifier.py` — FOUND
- `03-05-SUMMARY.md` — FOUND
- Commit `2d85441` (Task 1) — FOUND
- Commit `ae97649` (Task 2) — FOUND

---
*Phase: 03-transaction-classification*
*Completed: 2026-03-12*
