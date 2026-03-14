---
phase: 11
plan: "04"
title: Runtime Invariant Checks
status: complete
started: 2026-03-14
completed: 2026-03-14
---

## What was built

Runtime invariant checks injected into four fragile subsystems using the "flag + continue" pattern. All violations log to audit_log, set needs_review=True, and continue processing.

## Key files

### Modified
- `engine/acb/pool.py` — Added `check_acb_pool_invariants()` for negative balance/cost detection
- `engine/acb/engine_acb.py` — Wired invariant checks after every acquire/dispose in replay loop
- `engine/classifier/writer.py` — Added `check_classifier_invariants_batch()` for parent count and swap leg balance checks
- `verify/reconcile.py` — Added wallet coverage check and undiagnosed discrepancy detection to `reconcile_user()`
- `indexers/exchange_parsers/base.py` — Added `validate_parsed_row()` for amount/date/asset validation, wired into `parse_file()`

### Created
- `tests/test_invariants.py` — Integration tests for reconciler and exchange parser invariants

## Commits
- `3f9c4c8` feat(11-04): ACB pool and classifier invariant checks
- `9235658` feat(11-04): reconciler and exchange parser invariant checks

## Deviations
None.

## Self-Check: PASSED
- ACB pool invariant checks detect negative balance/cost: ✓
- Classifier batch check finds missing/duplicate parent classifications: ✓
- Reconciler verifies wallet coverage: ✓
- Exchange parser validates parsed row fields: ✓
- All violations write to audit_log: ✓
- Pipeline never halts on violation: ✓
