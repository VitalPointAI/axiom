---
phase: 10-remaining-concerns-remediation
plan: "05"
subsystem: testing
tags: [tests, classifier, acb, edge-cases, priority, idempotency]

# Dependency graph
requires:
  - phase: 10-remaining-concerns-remediation
    plan: "01"
    provides: split engine/classifier and engine/acb packages
provides:
  - 7 classifier tests for rule priority, chain filter, unknown, specialist, idempotency
  - 4 ACB tests for missing price, None amount, estimated price, oversell
affects: [tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mock pool pattern for classifier tests — no real DB needed"
    - "Direct ACBPool unit tests for edge case verification"

key-files:
  created: []
  modified:
    - tests/test_classifier.py
    - tests/test_acb.py

key-decisions:
  - "Test _match_rules directly for rule priority/chain filter isolation"
  - "Use mock cursor with fetchone side_effect for upsert specialist test"
  - "ACBPool tested directly (not through ACBEngine) for edge case clarity"

requirements-completed: [RC-10, RC-11, RC-12]

# Metrics
duration: 8min
completed: 2026-03-14
---

# Phase 10 Plan 05: Classifier & ACB Edge Case Tests Summary

**11 new tests covering classification rule interactions, ACB gap data handling, and concurrent classification idempotency**

## Performance

- **Duration:** 8 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- 7 new classifier tests: priority resolution, equal priority tie-breaking, conflicting categories, chain filter, unknown fallthrough, specialist_confirmed preservation, idempotency
- 4 new ACB tests: missing price graceful handling, None amount no-crash, estimated price flagging, oversell clamp with needs_review
- All 435 tests pass (11 new + 424 existing)

## Task Commits

1. **Task 1: classifier tests** - `865bbb4`
2. **Task 2: ACB tests** - `c3cc5ca`

## Deviations from Plan
None

---
*Phase: 10-remaining-concerns-remediation*
*Completed: 2026-03-14*
