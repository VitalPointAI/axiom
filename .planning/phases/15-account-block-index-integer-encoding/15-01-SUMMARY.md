---
phase: 15-account-block-index-integer-encoding
plan: "01"
subsystem: database

tags: [postgres, alembic, migration, integer-encoding, dictionary-encoding, account-block-index]

requires:
  - phase: 13-reliable-indexing
    provides: account_block_index + account_indexer_state tables (018 migration)
  - phase: 14-marketing-frontend
    provides: waitlist_signups table (019 migration, sets down_revision anchor)

provides:
  - "Alembic migration 020: account_dictionary table (SERIAL id + TEXT account_id UNIQUE)"
  - "Alembic migration 020: account_block_index_v2 table (INTEGER account_int + INTEGER segment_start)"
  - "Revision chain 019 -> 020 with clean downgrade"
  - "Named indexes ix_account_dictionary_account_id and ix_abiv2_account_segment"

affects:
  - 15-02
  - 15-03
  - 15-04
  - any plan that adds to account_block_index or queries wallet blocks

tech-stack:
  added: []
  patterns:
    - "Alembic migration with module-level docstring explaining schema change rationale"
    - "Explicit named index creation alongside unique constraint for drop-by-name support"
    - "Integer dictionary encoding: SERIAL primary key + TEXT UNIQUE = compact int IDs"
    - "Segment-based column naming (segment_start vs block_height) to clarify stored semantics"

key-files:
  created:
    - db/migrations/versions/020_integer_encoded_index.py
  modified: []

key-decisions:
  - "Use segment_start column name (not block_height) in account_block_index_v2 to reflect 1,000-block granule semantics"
  - "Create explicit named index ix_account_dictionary_account_id even though UNIQUE constraint creates its own index — enables named drop in downgrade"
  - "INTEGER (not BIGINT) for both columns: block heights at ~186M (8.7% of 2.1B max, 62 years headroom), account count at ~15M (0.7% of max)"
  - "Do NOT touch account_block_index or account_indexer_state — both old and new tables coexist during transition"

patterns-established:
  - "Migration 020 pattern: two tables created together, two indexes, clean reverse downgrade"

requirements-completed: [INT-01]

duration: 5min
completed: "2026-04-11"
---

# Phase 15 Plan 01: Integer-Encoded Index Migration Summary

**Alembic migration 020 creating account_dictionary (STRING->INTEGER mapping) and account_block_index_v2 (INTEGER account_int + INTEGER segment_start) alongside the existing account_block_index table**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-11T20:25:00Z
- **Completed:** 2026-04-11T20:30:46Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created migration 020 with correct revision chain (019 -> 020)
- account_dictionary table: SERIAL integer primary key + TEXT account_id UNIQUE NOT NULL, named B-tree index for string->int lookups
- account_block_index_v2 table: INTEGER account_int + INTEGER segment_start, composite PK prevents duplicates, named lookup index
- Original account_block_index and account_indexer_state tables completely untouched
- Clean downgrade drops both tables and both named indexes in reverse order

## Task Commits

1. **Task 1: Create Alembic migration 020** - `5701065` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `db/migrations/versions/020_integer_encoded_index.py` — Alembic migration 020 creating account_dictionary + account_block_index_v2 tables with INTEGER columns and named indexes

## Decisions Made

- Used `segment_start` column name (not `block_height`) as specified in the plan task action — the column stores the 1,000-block segment boundary (block_height // 1000 * 1000), not an exact block height
- Created explicit named index `ix_account_dictionary_account_id` in addition to the UNIQUE constraint's implicit index — this allows `op.drop_index("ix_account_dictionary_account_id")` in downgrade without needing to know the auto-generated constraint index name
- Chose INTEGER for both columns per research recommendation: 62 years headroom on block heights, effectively unlimited for account count

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. The migration applies via `alembic upgrade head` when the database is available.

## Next Phase Readiness

- Migration 020 is the foundation for all subsequent Phase 15 plans
- Plan 15-02 (Rust indexer changes) can proceed: account_dictionary and account_block_index_v2 tables are defined
- Plan 15-03 (Python lookup changes) can proceed: v2 table schema is established
- Plan 15-04 (data migration script) can proceed: both source (account_block_index) and target (account_block_index_v2 + account_dictionary) tables are defined

## Self-Check: PASSED

- `db/migrations/versions/020_integer_encoded_index.py` — FOUND
- Commit `5701065` — FOUND (git log confirmed)
- Verification check passed: revision chain, table names, column names all correct

---
*Phase: 15-account-block-index-integer-encoding*
*Completed: 2026-04-11*
