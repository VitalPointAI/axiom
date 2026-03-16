---
phase: 12-user-onboarding
plan: 01
subsystem: api
tags: [fastapi, postgres, alembic, psycopg2, onboarding, preferences, jsonb]

# Dependency graph
requires:
  - phase: 07-web-ui
    provides: FastAPI app factory, get_effective_user/get_pool_dep dependencies, router mount pattern
  - phase: 03-classification
    provides: WalletGraph.suggest_wallet_discovery() used by wallet suggestions endpoint
  - phase: 11-robustness
    provides: migration 009 (down_revision for migration 010)

provides:
  - Alembic migration 010: onboarding_completed_at TIMESTAMPTZ + dismissed_banners JSONB on users table
  - GET /api/preferences: returns onboarding state + dismissed banners for authenticated user
  - POST /api/preferences/complete-onboarding: idempotently sets onboarding_completed_at via COALESCE
  - PATCH /api/preferences/dismiss-banner: atomically merges banner key into dismissed_banners JSONB
  - GET /api/wallets/suggestions: returns WalletGraph discovery results (high-frequency counterparties)
  - 6-test suite covering all endpoints + JSONB merge + idempotency + 422 validation

affects: [12-user-onboarding frontend, any future onboarding wizard or banner components]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - JSONB merge via || operator with COALESCE(dismissed_banners, '{}') for safe NULL handling
    - COALESCE(col, NOW()) pattern for idempotent timestamp assignment
    - WalletGraph instantiated per-request with pool; no extra getconn() wrapper needed
    - Suggestions route registered before /{wallet_id} param routes (FastAPI order-matching rule)

key-files:
  created:
    - db/migrations/versions/010_onboarding_columns.py
    - api/routers/preferences.py
    - tests/test_api_preferences.py
  modified:
    - api/routers/__init__.py
    - api/main.py
    - api/routers/wallets.py

key-decisions:
  - "COALESCE(onboarding_completed_at, NOW()) in UPDATE makes complete-onboarding idempotent without SELECT first"
  - "COALESCE(dismissed_banners, '{}') || patch::jsonb for NULL-safe atomic JSONB merge in dismiss-banner"
  - "GET /api/wallets/suggestions registered before /{wallet_id} routes; WalletGraph manages its own pool connections"
  - "json.dumps({banner_key: True}) passed as %s::jsonb cast; avoids psycopg2 JSONB adapter dependency"

patterns-established:
  - "Idempotent timestamp pattern: UPDATE SET col = COALESCE(col, NOW()) WHERE id = %s RETURNING col"
  - "JSONB merge pattern: SET jsonb_col = COALESCE(jsonb_col, '{}') || %s::jsonb"

requirements-completed: [ONBOARD-01, ONBOARD-05, ONBOARD-06]

# Metrics
duration: 2min
completed: 2026-03-16
---

# Phase 12 Plan 01: User Onboarding Backend Foundation Summary

**Alembic migration 010 + preferences API (GET/POST/PATCH) + wallet discovery suggestions endpoint using WalletGraph, with idempotent COALESCE pattern and atomic JSONB merge**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-16T15:05:21Z
- **Completed:** 2026-03-16T15:07:37Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments
- Migration 010 adds `onboarding_completed_at TIMESTAMPTZ` and `dismissed_banners JSONB DEFAULT '{}'` to users table with IF NOT EXISTS idempotency
- Preferences API router with 3 endpoints: GET (read state), POST (idempotent completion via COALESCE), PATCH (atomic JSONB merge for banner dismissals)
- Wallet suggestions endpoint wrapping `WalletGraph.suggest_wallet_discovery()` registered before `/{wallet_id}` routes to prevent path param collision
- 6 tests passing covering all endpoints, NULL handling, idempotency, JSONB merge, and 422 validation

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration 010 + preferences router + wallet suggestions + tests** - `1567718` (feat)

**Plan metadata:** (docs commit — see final commit)

## Files Created/Modified
- `db/migrations/versions/010_onboarding_columns.py` - Alembic migration adding onboarding columns to users table
- `api/routers/preferences.py` - Preferences CRUD endpoints (GET/POST/PATCH) with run_in_threadpool + get_effective_user
- `api/routers/__init__.py` - Added preferences_router export
- `api/main.py` - Mounted preferences_router in create_app()
- `api/routers/wallets.py` - Added GET /api/wallets/suggestions before /{wallet_id} routes
- `tests/test_api_preferences.py` - 6 tests for preferences endpoints

## Decisions Made
- Used `COALESCE(onboarding_completed_at, NOW())` in the UPDATE to make complete-onboarding idempotent — no SELECT needed before the UPDATE
- Used `COALESCE(dismissed_banners, '{}') || %s::jsonb` for the JSONB merge to handle NULL dismissed_banners gracefully in existing rows
- WalletGraph manages its own pool connections internally; the suggestions endpoint calls `run_in_threadpool` on a no-arg lambda rather than passing a connection
- Wallet suggestions route registered before `/{wallet_id}` routes (same pattern as `/api/jobs/active` before `/{job_id}/status`) to prevent "suggestions" being parsed as an integer path param

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Backend foundation complete: migration 010 applies on next deploy, all 3 preferences endpoints operational
- Frontend onboarding wizard (plan 12-02) can call GET /api/preferences to check onboarding_completed_at and POST /complete-onboarding to mark completion
- Banner components can call PATCH /dismiss-banner with any banner_key string
- GET /api/wallets/suggestions available for "Add more wallets?" onboarding step

---
*Phase: 12-user-onboarding*
*Completed: 2026-03-16*
