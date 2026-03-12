---
phase: 03-transaction-classification
plan: "01"
subsystem: classification-schema
tags: [schema, migration, models, test-scaffolds, classification]
dependency_graph:
  requires: [02-07]
  provides: [classification-schema, test-scaffolds-03]
  affects: [03-02, 03-03, 03-04, 03-05]
tech_stack:
  added: []
  patterns: [alembic-migration, sqlalchemy-declarative, partial-unique-index-via-execute, self-referential-relationship]
key_files:
  created:
    - db/migrations/versions/003_classification_schema.py
    - tests/test_classifier.py
    - tests/test_wallet_graph.py
    - tests/test_evm_decoder.py
    - tests/test_spam_detector.py
  modified:
    - db/models.py
decisions:
  - "Partial unique indexes via op.execute() — op.create_unique_constraint() does not support WHERE clause"
  - "classification_rules created before transaction_classifications in migration — FK dependency order"
  - "TransactionClassification partial indexes not redeclared in __table_args__ — avoids SQLAlchemy duplicate creation during metadata operations"
  - "Self-referential parent/child_legs relationship uses remote_side on id column"
metrics:
  duration_seconds: 169
  completed_date: "2026-03-12"
  tasks_completed: 2
  tasks_total: 2
  files_created: 5
  files_modified: 1
---

# Phase 03 Plan 01: Classification Schema and Test Scaffolds Summary

Alembic migration 003 + 4 SQLAlchemy models + 30 test stubs covering the full classification engine foundation.

## What Was Built

### Task 1: Alembic Migration 003

`db/migrations/versions/003_classification_schema.py` — revision `003`, down_revision `002b`.

Creates 4 tables in dependency order:

1. **classification_rules** — Rule definitions with JSONB pattern, chain, priority, confidence. `uq_cr_name` unique constraint on `name` enables idempotent `ON CONFLICT (name) DO UPDATE` by the rule seeder.

2. **transaction_classifications** — Per-transaction tax category assignments. Supports multi-leg decomposition via `parent_classification_id` (self-FK) and `leg_type` values: `parent`, `sell_leg`, `buy_leg`, `fee_leg`. Links to staking_events (CLASS-03) and lockup_events (CLASS-04). Two partial unique indexes created via `op.execute()`: `uq_tc_user_tx_leg` and `uq_tc_user_etx_leg`.

3. **spam_rules** — User-scoped and global (user_id=NULL) spam detection rules. Four rule types: `contract_address`, `dust_threshold`, `token_symbol`, `pattern`.

4. **classification_audit_log** — Immutable audit trail. Only ever inserted, never updated. old_category=NULL for initial classification.

### Task 2: SQLAlchemy Models + Test Scaffolds

**db/models.py** — 4 new model classes appended:
- `ClassificationRule`: UniqueConstraint uq_cr_name in `__table_args__`
- `TransactionClassification`: Self-referential `parent`/`child_legs` relationship, FK to classification_rules, staking_events, lockup_events
- `SpamRule`: Dual-FK to users (user_id and created_by)
- `ClassificationAuditLog`: Back-references TransactionClassification.audit_log

**Test scaffolds** — 30 stubs across 4 files (all pytest.skip):
- `tests/test_classifier.py`: 16 stubs (CLASS-01, CLASS-02, CLASS-03, CLASS-04, CLASS-05, multi-leg)
- `tests/test_wallet_graph.py`: 7 stubs (CLASS-02 internal transfer detection)
- `tests/test_evm_decoder.py`: 4 stubs (CLASS-05 EVM path)
- `tests/test_spam_detector.py`: 5 stubs (spam detection + learning)

## Verification Results

- `from db.models import TransactionClassification, ClassificationRule, SpamRule, ClassificationAuditLog` — OK
- Migration 003 parses: revision=003, down_revision=002b — OK
- 30 test stubs collected (all skipped) — OK
- 107 pre-existing tests pass, 0 regressions — OK

## Deviations from Plan

None — plan executed exactly as written.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Partial unique indexes via op.execute() | op.create_unique_constraint() has no WHERE clause support; op.execute() raw SQL is the Alembic-documented approach |
| classification_rules created first | transaction_classifications has FK to classification_rules.id; creation order must respect FK dependency |
| Partial indexes not redeclared in __table_args__ | SQLAlchemy would attempt to create them during metadata.create_all(); migration already creates them; comment added for clarity |
| remote_side="TransactionClassification.id" as string | Required for string-based forward reference in self-referential relationship with mapped_column() style |

## Self-Check: PASSED

- db/migrations/versions/003_classification_schema.py: FOUND
- db/models.py (TransactionClassification, ClassificationRule, SpamRule, ClassificationAuditLog): FOUND
- tests/test_classifier.py: FOUND
- tests/test_wallet_graph.py: FOUND
- tests/test_evm_decoder.py: FOUND
- tests/test_spam_detector.py: FOUND
- Commits e495e91, eb62ddf: FOUND
