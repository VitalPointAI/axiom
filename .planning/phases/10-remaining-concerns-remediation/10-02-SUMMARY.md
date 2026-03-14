---
phase: 10-remaining-concerns-remediation
plan: "02"
subsystem: database
tags: [postgresql, alembic, psycopg2, connection-pool, migration, pyproject]

# Dependency graph
requires:
  - phase: 09-code-quality-hardening
    provides: validate_env() in config.py, db pool singleton in indexers/db.py
provides:
  - Alembic migration 007 adding ix_price_cache_coin_date_desc composite index
  - DB_POOL_MIN and DB_POOL_MAX configurable via env vars (default 1/10)
  - pool_stats() function in indexers/db.py returning pool utilisation dict
  - sanitize_for_log() in config.py for safe logging of env dicts
  - pyproject.toml [project] table with requires-python = ">=3.11"
affects: [indexers, api, deployment, ci-cd]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DB pool sizing via env vars DB_POOL_MIN/DB_POOL_MAX — tune without code changes"
    - "pool_stats() introspection pattern for operational observability"
    - "sanitize_for_log() substring matching on _SENSITIVE_KEY_PATTERNS for safe logging"
    - "pyproject.toml [project] table as canonical Python version constraint"

key-files:
  created:
    - db/migrations/versions/007_price_cache_index.py
  modified:
    - config.py
    - indexers/db.py
    - pyproject.toml
    - tests/test_config_validation.py

key-decisions:
  - "ix_price_cache_coin_date_desc on (coin_id, date DESC) matches ACB/report query ordering pattern"
  - "IF NOT EXISTS on both indexes makes migration 007 idempotent across environments"
  - "downgrade() only drops ix_price_cache_coin_date_desc — ix_pcm_coin_ts may predate this migration"
  - "DB_POOL_MIN/MAX defaults 1/10 match typical single-process indexer workload"
  - "validate_env() raises ValueError (not RuntimeError) for pool constraint violations — distinct from missing vars"
  - "sanitize_for_log() uses case-insensitive substring matching on _SENSITIVE_KEY_PATTERNS set"
  - "pyproject.toml [tool.setuptools] packages=[] declares non-installable project"

patterns-established:
  - "Pool configuration via env vars: import DB_POOL_MIN, DB_POOL_MAX from config in db.py"
  - "pool_stats(pool) as lightweight introspection helper — pass pool object, return dict"

requirements-completed: [RC-02, RC-06, RC-09]

# Metrics
duration: 4min
completed: 2026-03-14
---

# Phase 10 Plan 02: price_cache Index + Configurable Pool + pyproject.toml Summary

**Alembic migration 007 adds ix_price_cache_coin_date_desc on price_cache(coin_id, date DESC); DB_POOL_MIN/MAX configurable via env vars with pool_stats() introspection; pyproject.toml declares requires-python >= 3.11**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T03:25:12Z
- **Completed:** 2026-03-14T03:29:44Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments
- Migration 007 creates composite price_cache index (coin_id, date DESC) for efficient ACB and report range queries; IF NOT EXISTS makes it safe on all environments
- DB connection pool sizing is now fully configurable via DB_POOL_MIN/DB_POOL_MAX env vars (default 1/10); pool_stats() provides operational visibility into pool utilisation
- pyproject.toml has a complete [project] table with requires-python = ">=3.11", enforcing Python version constraint across all tooling
- sanitize_for_log() added to config.py for safe logging of env/config dicts without leaking secrets

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: failing tests for DB_POOL_MIN/MAX + pool_stats()** - `2e2535a` (test)
2. **Task 1 GREEN: migration 007, pool config, pool_stats, pyproject.toml** - `718f869` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD task — RED commit first, GREEN commit implements all features_

## Files Created/Modified
- `db/migrations/versions/007_price_cache_index.py` - Alembic migration adding ix_price_cache_coin_date_desc; IF NOT EXISTS on ix_pcm_coin_ts safety net
- `config.py` - DB_POOL_MIN/DB_POOL_MAX env vars (default 1/10); sanitize_for_log(); validate_env() pool constraint checks
- `indexers/db.py` - get_pool() defaults to DB_POOL_MIN/DB_POOL_MAX; pool_stats() introspection helper
- `pyproject.toml` - [build-system], [project] with requires-python >= 3.11, [tool.setuptools]
- `tests/test_config_validation.py` - TestDbPoolConfig (6 tests), TestPoolStats (2 tests), TestSanitizeForLog (7 tests)

## Decisions Made
- `ix_price_cache_coin_date_desc` on `(coin_id, date DESC)` matches the natural query pattern for ordered range lookups in ACB and report generation
- `IF NOT EXISTS` on both indexes makes migration idempotent — safe when run against environments that already have manual indexes
- downgrade() only drops `ix_price_cache_coin_date_desc` since `ix_pcm_coin_ts` may predate this migration
- `ValueError` for pool constraint violations (MIN > MAX, values <= 0) vs `RuntimeError` for missing required vars — distinct error types for distinct failure modes
- `sanitize_for_log()` uses case-insensitive substring matching against `_SENSITIVE_KEY_PATTERNS` to catch variants like `NEARBLOCKS_API_KEY`, `SESSION_TOKEN`, `DB_PASSWORD` without an exhaustive list

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added sanitize_for_log() to config.py**
- **Found during:** Task 1 GREEN (implementation)
- **Issue:** Linter added `TestSanitizeForLog` tests (RC-07) to the test file while the RED commit was in progress; these tests covered `sanitize_for_log()` which was not in the original plan
- **Fix:** Implemented `sanitize_for_log(env_dict)` with `_SENSITIVE_KEY_PATTERNS` set for case-insensitive substring redaction; all 7 TestSanitizeForLog tests pass
- **Files modified:** config.py, tests/test_config_validation.py
- **Verification:** `python3 -m pytest tests/test_config_validation.py -q` → 23 passed
- **Committed in:** `718f869` (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing critical functionality added by linter-driven test expansion)
**Impact on plan:** sanitize_for_log() is a correct addition aligned with RC-07 scope. No scope creep beyond plan requirements.

## Issues Encountered
- `git stash`/`git stash pop` during verification (checking pre-existing failures) reverted disk state of `indexers/db.py` and `pyproject.toml`; re-applied changes after stash drop. No data loss — changes were confirmed complete before stashing.

## User Setup Required
None - no external service configuration required. Pool sizing via DB_POOL_MIN/DB_POOL_MAX env vars in .env file.

## Next Phase Readiness
- Migration 007 ready to apply: `alembic upgrade 007`
- Pool observability available: `from indexers.db import pool_stats; pool_stats(get_pool())`
- Python version constraint enforced for tooling (ruff, pytest, mypy)

---
*Phase: 10-remaining-concerns-remediation*
*Completed: 2026-03-14*
