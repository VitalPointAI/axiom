---
phase: 02-multichain-exchanges
plan: 07
subsystem: database
tags: [alembic, migration, postgresql, dedup, typescript, nextjs]

# Dependency graph
requires:
  - phase: 02-multichain-exchanges
    provides: "DedupHandler, file_handler, upload-file route, migration 002 tables"
provides:
  - "Migration 002b: updated_at TIMESTAMPTZ added to file_imports and exchange_transactions"
  - "DedupHandler block_timestamp BETWEEN query using epoch integers (BIGINT-safe)"
  - "Upload-file route wallet upsert uses correct ON CONFLICT (user_id, account_id, chain)"
affects: [03-classification, 04-cost-basis, 05-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Alembic additive migrations: 002b extends 002 without modifying original"
    - "Epoch integer conversion before BIGINT BETWEEN queries"
    - "ON CONFLICT clause must match exact UNIQUE constraint column set"

key-files:
  created:
    - db/migrations/versions/002b_add_updated_at.py
  modified:
    - indexers/dedup_handler.py
    - web/app/api/upload-file/route.ts

key-decisions:
  - "002b as separate migration from 002: preserves 002 for teams already migrated, additive approach"
  - "nullable=True for updated_at: existing rows get NULL, no backfill required at migration time"
  - "int(window.timestamp()) before BETWEEN: BIGINT block_timestamp requires integer operands not datetime"

patterns-established:
  - "Additive migrations (002b) when 002 is already in production"
  - "Always convert Python datetime to int epoch before BETWEEN on BIGINT columns"

requirements-completed: [DATA-04, DATA-05]

# Metrics
duration: 8min
completed: 2026-03-12
---

# Phase 2 Plan 07: Gap Closure — Runtime Bugs Summary

**Three one-line fixes closing the gap between passing unit tests and working runtime: updated_at migration (002b), BIGINT epoch conversion in DedupHandler, and correct ON CONFLICT columns in upload-file route**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-12T19:35:49Z
- **Completed:** 2026-03-12T19:43:00Z
- **Tasks:** 3
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- Created Alembic migration 002b adding `updated_at TIMESTAMPTZ` to both `file_imports` and `exchange_transactions` — resolves "column updated_at does not exist" runtime error in file_handler.py and dedup_handler.py
- Fixed DedupHandler to pass `int(window_start.timestamp())` / `int(window_end.timestamp())` to the `block_timestamp BETWEEN %s AND %s` query — resolves type mismatch between Python datetime objects and PostgreSQL BIGINT column
- Fixed upload-file route to use `ON CONFLICT (user_id, account_id, chain) DO NOTHING` matching the wallets table `UNIQUE(user_id, account_id, chain)` constraint — resolves constraint error during wallet upsert

## Task Commits

Each task was committed atomically:

1. **Task 1: Add updated_at columns via Alembic migration 002b** - `7f206e0` (feat)
2. **Task 2: Convert dedup window_start/window_end to epoch integers** - `e8b0189` (fix)
3. **Task 3: Fix ON CONFLICT clause in upload-file route** - `ed64baa` (fix)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `db/migrations/versions/002b_add_updated_at.py` - New Alembic migration 002b: adds updated_at TIMESTAMPTZ nullable to file_imports and exchange_transactions; down_revision='002'
- `indexers/dedup_handler.py` - Added window_start_epoch/window_end_epoch conversions; passes integers to BETWEEN block_timestamp query
- `web/app/api/upload-file/route.ts` - Corrected ON CONFLICT from `(account_id)` to `(user_id, account_id, chain)`

## Decisions Made
- Used `nullable=True` for updated_at columns — existing rows will have NULL until next update; no backfill required at migration time, handlers will SET updated_at = NOW() on next write
- Migration named 002b (not 003) because it's a gap fix for the 002 schema — semantically belongs with the same feature set

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None - all three fixes were straightforward one-line/one-file changes. All 54 existing tests continued to pass after changes.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three Phase 2 runtime blockers are resolved
- File import jobs can now run without `column updated_at does not exist` errors
- Dedup scans can now compare timestamps against BIGINT block_timestamp without type errors
- File uploads can now upsert exchange_imports wallets without ON CONFLICT constraint errors
- Phase 2 is complete and ready for Phase 3 (Transaction Classification)

---
*Phase: 02-multichain-exchanges*
*Completed: 2026-03-12*
