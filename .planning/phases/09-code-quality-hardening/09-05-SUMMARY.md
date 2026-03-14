---
phase: 09-code-quality-hardening
plan: "05"
subsystem: verify-reconcile
tags: [refactor, extraction, diagnosis, reconcile]
dependency_graph:
  requires: []
  provides: [diagnosis-module, slimmed-reconcile]
  affects: [verify/reconcile.py, verify/diagnosis.py]
tech_stack:
  added: []
  patterns: [delegation-pattern, extract-class]
key_files:
  created:
    - verify/diagnosis.py
  modified:
    - verify/reconcile.py
decisions:
  - "Extract to ReconcileDiagnoser class (not standalone functions) for pool access"
  - "Delegation via self.diagnoser preserves existing reconcile.py call sites"
  - "reconcile.py down from 1002 to 721 lines (~28% reduction)"
metrics:
  duration_minutes: 5
  tasks_completed: 1
  files_modified: 2
  completed_date: "2026-03-14"
requirements: [QH-13]
---

# Phase 9 Plan 05: Reconcile Refactor Summary

**One-liner:** Extracted 5 diagnosis methods (~280 lines) from reconcile.py into verify/diagnosis.py ReconcileDiagnoser class.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extract diagnosis helpers | 261d983 | verify/diagnosis.py, verify/reconcile.py |

## What Was Built

### Task 1: Diagnosis Extraction
- Created `verify/diagnosis.py` with `ReconcileDiagnoser` class (331 lines)
- Extracted methods: `auto_diagnose`, `diagnose_missing_staking`, `diagnose_uncounted_fees`, `diagnose_unindexed_period`, `diagnose_classification_error`
- `verify/reconcile.py` delegates via `self.diagnoser = ReconcileDiagnoser(pool)`
- reconcile.py reduced from 1002 to 721 lines

## Self-Check: PASSED

- verify/diagnosis.py: FOUND
- verify/reconcile.py: FOUND (721 lines)
- Commit 261d983: FOUND
