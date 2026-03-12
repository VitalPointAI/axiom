---
phase: 01-near-indexer
plan: "01"
subsystem: database
tags: [postgresql, sqlalchemy, alembic, psycopg2, migrations, schema]

# Dependency graph
requires: []
provides:
  - PostgreSQL schema via Alembic with 8 tables (users, wallets, transactions, indexing_jobs, staking_events, epoch_snapshots, price_cache, lockup_events)
  - SQLAlchemy 2.0 ORM models in db/models.py
  - Alembic migration framework in db/migrations/
  - Shared psycopg2 connection helpers in indexers/db.py
  - Cleaned config.py with DATABASE_URL (no SQLite, no hardcoded credentials)
affects: [02-near-indexer, 03-near-indexer, all subsequent indexer plans]

# Tech tracking
tech-stack:
  added: [alembic>=1.13.0, sqlalchemy>=2.0.0, psycopg2-binary>=2.9.9]
  patterns: [SQLAlchemy 2.0 mapped_column declarative models, Alembic online/offline migration modes, psycopg2 SimpleConnectionPool singleton, db_cursor context manager with auto commit/rollback]

key-files:
  created:
    - db/models.py
    - db/migrations/alembic.ini
    - db/migrations/env.py
    - db/migrations/script.mako
    - db/migrations/versions/001_initial_schema.py
    - indexers/db.py
    - requirements.txt
  modified:
    - config.py

key-decisions:
  - "JSONB for raw_data column (not TEXT) — enables indexed JSON queries in PostgreSQL"
  - "NUMERIC(40,0) for yoctoNEAR/wei amounts — avoids floating point precision loss"
  - "DATABASE_URL with no hardcoded fallback — explicit failure prevents silent misconfiguration"
  - "user_id FK on all data tables — enforces multi-user isolation at schema level"
  - "chain column on wallets/transactions — schema is multi-chain extensible from day one"
  - "indexing_jobs table as DB-backed queue (not in-memory/Redis) — per architecture decision"

patterns-established:
  - "All indexer DB access via indexers/db.py — no direct psycopg2.connect() in indexer scripts"
  - "All config via config.py — no os.environ.get() scattered in indexer scripts"
  - "Alembic manages schema — no CREATE TABLE in application code or raw SQL files"
  - "Explicit failure on missing DATABASE_URL — warning printed, EnvironmentError on first use"

requirements-completed: [DATA-06]

# Metrics
duration: 4min
completed: 2026-03-12
---

# Phase 1 Plan 01: PostgreSQL Schema and Alembic Migration Framework

**SQLAlchemy 2.0 models + Alembic migration creating 8 PostgreSQL tables with NUMERIC/JSONB/TIMESTAMPTZ types and user_id FK multi-user isolation**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-12T00:08:40Z
- **Completed:** 2026-03-12T00:12:26Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Created 8 SQLAlchemy 2.0 models with proper PostgreSQL types (NUMERIC for yoctoNEAR, JSONB for raw_data, TIMESTAMPTZ everywhere)
- Configured Alembic migration framework with env.py that reads DATABASE_URL from environment and imports model metadata for autogenerate
- Created initial migration (001_initial_schema.py) using op.create_table() with all indexes and constraints
- Cleaned config.py: removed DATABASE_PATH/SQLite reference, added DATABASE_URL with explicit-failure pattern, added price API keys and job scheduling config
- Created indexers/db.py providing get_connection(), get_pool(), close_pool(), and db_cursor() context manager for all indexers

## Task Commits

Each task was committed atomically:

1. **Task 1: SQLAlchemy models and Alembic migration framework** - `bf95541` (feat)
2. **Task 2: Shared db module and clean up config.py** - `859f8a7` (feat)

**Plan metadata:** (docs commit — forthcoming)

## Files Created/Modified

- `db/models.py` - 8 SQLAlchemy 2.0 declarative models with PostgreSQL-specific types
- `db/migrations/alembic.ini` - Alembic config (sqlalchemy.url injected via env.py)
- `db/migrations/env.py` - Migration runner that reads DATABASE_URL, imports Base.metadata
- `db/migrations/script.mako` - Standard Alembic migration file template
- `db/migrations/versions/001_initial_schema.py` - Initial migration creating all 8 tables
- `indexers/db.py` - Shared psycopg2 connection helpers with pool and context manager
- `config.py` - Removed SQLite, added DATABASE_URL + new config keys
- `requirements.txt` - New project root deps file (alembic, sqlalchemy, psycopg2-binary)

## Decisions Made

- JSONB for raw_data: enables indexed queries on transaction data in PostgreSQL (not TEXT)
- NUMERIC(40,0) for yoctoNEAR values: prevents floating point precision loss on large integers
- No hardcoded DATABASE_URL fallback: explicit failure is safer than silent misconfiguration
- Alembic uses op.create_table() not CREATE TABLE IF NOT EXISTS: Alembic owns schema lifecycle

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required for this plan. DATABASE_URL must be set in .env or environment before running migrations or indexers.

## Next Phase Readiness

- Schema foundation complete; all Phase 1 indexer plans can proceed
- To apply schema to PostgreSQL: `cd db/migrations && alembic upgrade head`
- Alembic autogenerate works: `alembic revision --autogenerate -m "description"`
- All indexers should import from `indexers.db` and `config` (not create their own connections)

## Self-Check: PASSED

All created files verified present on disk:
- db/models.py: FOUND
- db/migrations/alembic.ini: FOUND
- db/migrations/env.py: FOUND
- db/migrations/versions/001_initial_schema.py: FOUND
- indexers/db.py: FOUND
- requirements.txt: FOUND
- .planning/phases/01-near-indexer/01-01-SUMMARY.md: FOUND

Task commits verified:
- bf95541 (Task 1): FOUND
- 859f8a7 (Task 2): FOUND

---
*Phase: 01-near-indexer*
*Completed: 2026-03-12*
