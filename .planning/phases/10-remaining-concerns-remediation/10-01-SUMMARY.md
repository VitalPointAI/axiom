---
phase: 10-remaining-concerns-remediation
plan: "01"
subsystem: architecture
tags: [refactoring, modules, classifier, acb, models]

# Dependency graph
requires:
  - phase: 09-code-quality-hardening
    provides: stable classifier, acb, and models implementations
provides:
  - engine/classifier/ sub-package with 7 focused modules
  - engine/acb/ sub-package with 3 focused modules
  - db/models/ sub-package with base + re-export facade
affects: [engine, db, tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin __init__.py facade with delegation to sub-modules"
    - "Sub-module functions accept classifier/engine instance as first arg"
    - "SQLAlchemy models share Base from dedicated base.py"

key-files:
  created:
    - engine/classifier/__init__.py
    - engine/classifier/near_classifier.py
    - engine/classifier/evm_classifier.py
    - engine/classifier/exchange_classifier.py
    - engine/classifier/writer.py
    - engine/classifier/rules.py
    - engine/classifier/ai_fallback.py
    - engine/acb/__init__.py
    - engine/acb/pool.py
    - engine/acb/engine_acb.py
    - engine/acb/symbols.py
    - db/models/__init__.py
    - db/models/base.py
    - db/models/_all_models.py
  modified: []

key-decisions:
  - "Classifier __init__.py retains TransactionClassifier class as thin facade"
  - "Sub-module functions take classifier instance as first arg for method delegation"
  - "ACBEngine placed in engine_acb.py to avoid name clash with engine/ directory"
  - "db/models uses _all_models.py single file with re-export __init__.py"

patterns-established:
  - "Module-to-package conversion: git mv + mkdir + __init__.py re-exports"
  - "Delegation pattern: method body in sub-module, thin wrapper in __init__"

requirements-completed: [RC-01]

# Metrics
duration: 20min
completed: 2026-03-14
---

# Phase 10 Plan 01: Module Splitting Summary

**Split classifier.py (1246 lines), acb.py (857 lines), and models.py (961 lines) into focused sub-packages with backward-compatible re-exports**

## Performance

- **Duration:** 20 min
- **Tasks:** 2
- **Files created:** 14

## Accomplishments
- engine/classifier/ split into 7 sub-modules: near_classifier, evm_classifier, exchange_classifier, writer, rules, ai_fallback, __init__.py facade (390 lines)
- engine/acb/ split into 3 sub-modules: symbols (token resolution), pool (ACBPool), engine_acb (ACBEngine)
- db/models/ converted to package with base.py (shared Base) and re-export __init__.py
- All existing import paths preserved via __init__.py re-exports
- 420 tests pass with zero import errors

## Task Commits

1. **Task 1: classifier split** - `5356923`
2. **Task 2: acb + models split** - `5ccb78f`
3. **Cleanup tmp files** - `7805764`

## Deviations from Plan
- db/models/_all_models.py remains 959 lines (not split into 7 sub-files) — SQLAlchemy relationship cross-references make fine-grained splitting complex. Package structure established; further splitting can be done incrementally.

## Issues Encountered
- Initial agent hit sandbox write permission limits after creating classifier sub-modules; orchestrator completed remaining work directly.

---
*Phase: 10-remaining-concerns-remediation*
*Completed: 2026-03-14*
