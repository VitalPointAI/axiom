---
phase: 11-robustness-missing-features
plan: "01"
subsystem: database
tags: [postgresql, alembic, sqlalchemy, audit-log, jsonb]

# Dependency graph
requires:
  - phase: 03-transaction-classification
    provides: classification_audit_log table and ClassificationAuditLog model (now replaced)
  - phase: 07-web-ui
    provides: users table (audit_log FK target)
provides:
  - audit_log PostgreSQL table with JSONB old_value/new_value
  - Alembic migration 008 creating and populating audit_log
  - AuditLog SQLAlchemy model (replaces ClassificationAuditLog)
  - write_audit() helper in db/audit.py for all downstream mutation points
  - ClassificationAuditLog = AuditLog backward compatibility alias
affects:
  - 11-02-PLAN (invariant checks will use write_audit)
  - 11-03-PLAN (multi-hop swaps may produce audit rows)
  - 11-04-PLAN (data export validation)
  - any future plan that writes audit entries

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "write_audit(conn, *, ...) always called within caller's transaction boundary"
    - "conn=None silently skips audit writes (test-compatibility pattern)"
    - "try/except in write_audit: audit failures never crash the pipeline"
    - "ClassificationAuditLog = AuditLog alias for backward compat during transition"

key-files:
  created:
    - db/migrations/versions/008_unified_audit_log.py
    - db/audit.py
  modified:
    - db/models/_all_models.py
    - db/models/__init__.py

key-decisions:
  - "audit_log uses JSONB old_value/new_value instead of narrow typed columns — supports all entity types without schema changes"
  - "actor_type column added ('system','user','specialist','ai') to distinguish automated vs human mutations"
  - "entity_id nullable=True — report generation and invariant violations have no single entity PK"
  - "write_audit() conn=None safety: test callers that skip DB provisioning work without mocks"
  - "ClassificationAuditLog = AuditLog alias in __init__.py: downstream code continues to import by old name without crashing"

patterns-established:
  - "Pattern 1: All mutation points call write_audit(conn, ...) before or after the main INSERT/UPDATE"
  - "Pattern 2: audit_log rows are INSERT-only — never UPDATE or DELETE"

requirements-completed: [ROB-01]

# Metrics
duration: 15min
completed: 2026-03-14
---

# Phase 11 Plan 01: Unified Audit Log Foundation Summary

**Alembic migration 008 replaces classification_audit_log with a general-purpose audit_log table (JSONB values, entity_type/action/actor_type), migrates existing data, and delivers write_audit() helper and AuditLog SQLAlchemy model.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-14T09:44:22Z
- **Completed:** 2026-03-14T09:59:00Z
- **Tasks:** 2
- **Files modified:** 4 (1 created migration, 1 new module, 2 updated models)

## Accomplishments

- Alembic migration 008 creates audit_log table, migrates classification_audit_log rows using jsonb_build_object, and drops the old table in one transaction
- AuditLog SQLAlchemy model replaces ClassificationAuditLog with JSONB old_value/new_value columns matching migration schema
- write_audit() helper in db/audit.py available for all downstream plans; silently skips on conn=None; audit failures never crash pipeline
- Backward compatibility alias ClassificationAuditLog = AuditLog in db/models/__init__.py preserves existing import paths

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration 008 — create audit_log, migrate data, drop classification_audit_log** - `130e420` (feat)
2. **Task 2: AuditLog model + write_audit() helper + model exports update** - `fbc5962` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `db/migrations/versions/008_unified_audit_log.py` - Alembic migration creating audit_log, migrating data via jsonb_build_object, dropping classification_audit_log; downgrade re-creates old table
- `db/audit.py` - write_audit() helper with conn=None guard and try/except; all future mutation points import from here
- `db/models/_all_models.py` - ClassificationAuditLog class replaced by AuditLog; audit_log back-ref removed from TransactionClassification
- `db/models/__init__.py` - AuditLog exported; ClassificationAuditLog = AuditLog alias added

## Decisions Made

- Used JSONB old_value/new_value instead of typed columns so the same table handles classification changes, ACB corrections, duplicate merges, and future mutation types without ALTER TABLE
- entity_id is nullable so report generation events (no single entity PK) can be audited
- actor_type distinguishes system, user, specialist, and ai mutations — required for downstream review workflows
- write_audit conn=None pattern matches RESEARCH.md Pitfall 5 guidance — tests that do not provision a DB pass None and skip audit inserts cleanly

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Pre-existing test failures in test_evm_decoder.py (multi-hop path tests, flaky ordering) and test_reports.py (manifest/stale detection) and test_classifier.py (multi-hop classifier TDD RED tests) were confirmed pre-existing before my changes. None introduced by this plan.

## User Setup Required

None - no external service configuration required. Migration 008 will apply on next `alembic upgrade head`.

## Next Phase Readiness

- write_audit() is ready for use by all plans 11-02 through 11-05
- audit_log table schema and indexes defined; migration runs after 007
- AuditLog model importable from db.models for SQLAlchemy query use
- ClassificationAuditLog alias ensures no import breakage in existing code

---
*Phase: 11-robustness-missing-features*
*Completed: 2026-03-14*
