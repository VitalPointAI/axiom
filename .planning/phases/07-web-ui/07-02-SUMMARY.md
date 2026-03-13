---
phase: 07-web-ui
plan: 02
subsystem: auth
tags: [fastapi, webauthn, passkey, oauth, magic-link, psycopg2, itsdangerous, boto3, httpx, ses]

# Dependency graph
requires:
  - phase: 07-web-ui-01
    provides: "Migration 006 (passkeys/sessions/challenges/magic_link_tokens), FastAPI app factory, auth dependencies, Pydantic schemas, test fixtures"

provides:
  - "api/auth/session.py: create_session (httponly cookie, 7-day expiry, sessions table) + destroy_session"
  - "api/auth/passkey.py: WebAuthn start/finish_registration + start/finish_authentication with PostgreSQL challenge storage"
  - "api/auth/oauth.py: Google OAuth PKCE flow — state stored in challenges table, user upsert by email"
  - "api/auth/magic_link.py: itsdangerous signed tokens, SES email dispatch, reuse + expiry prevention"
  - "api/auth/router.py: 10 /auth/* endpoints mounted at prefix /auth"
  - "api/auth/_user_helpers.py: shared load_user_by_id + get_session_expires_at helpers"
  - "25 passing tests for full auth lifecycle"

affects:
  - 07-03-wallet-transaction-routers
  - 07-04-portfolio-router
  - 07-05-reports-verification-routers
  - 07-06-job-status-router

# Tech tracking
tech-stack:
  added: []  # All dependencies from Plan 01 (webauthn, itsdangerous, boto3, httpx already in requirements.txt)
  patterns:
    - "WebAuthn challenges stored in PostgreSQL challenges table (not in-memory) — survives restarts"
    - "run_in_threadpool() wraps all psycopg2 synchronous calls in async FastAPI routes"
    - "Lazy import of auth sub-modules inside route handlers prevents circular import issues"
    - "itsdangerous.URLSafeTimedSerializer for magic link tokens — self-contained, no extra DB round-trip for decode"
    - "All user creation paths use upsert ON CONFLICT (email) DO UPDATE to prevent duplicate accounts"

key-files:
  created:
    - api/auth/session.py
    - api/auth/passkey.py
    - api/auth/oauth.py
    - api/auth/magic_link.py
    - api/auth/router.py
    - api/auth/_user_helpers.py
  modified:
    - api/auth/__init__.py (now imports from router.py instead of stub)
    - tests/test_api_auth.py (25 tests, was 8)

key-decisions:
  - "Challenges stored in PostgreSQL not in-memory — required for multi-process and restart safety"
  - "run_in_threadpool() for all psycopg2 calls in async routes — psycopg2 is synchronous only"
  - "load_user_by_id called after finish_registration/finish_authentication to return full user context in SessionResponse"
  - "itsdangerous token carries email claim — token IS the proof; DB row (magic_link_tokens) is used-at guard only"
  - "OAuth state stored as challenge.id (not challenge.challenge field) to allow string comparison without base64"
  - "_user_helpers.py extracted as shared module to avoid duplication across router endpoints"

patterns-established:
  - "Auth endpoints import sub-modules lazily inside route handlers (from api.auth import passkey) to avoid circular imports at startup"
  - "DB mock tests need side_effect list sized to total fetchone calls including load_user_by_id (one extra row per endpoint)"

requirements-completed:
  - UI-01

# Metrics
duration: 8min
completed: 2026-03-13
---

# Phase 7 Plan 02: WebAuthn Passkey + OAuth + Magic Link Auth Summary

**WebAuthn passkey register/login with PostgreSQL challenge storage, Google OAuth PKCE flow, and itsdangerous-signed email magic links — all three auth paths create sessions via HTTP-only cookies**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-13T21:43:20Z
- **Completed:** 2026-03-13T21:51:20Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 8

## Accomplishments

- Session management with HTTP-only cookie, 7-day expiry, and PostgreSQL `sessions` table — challenges also persisted in `challenges` table (not in-memory)
- WebAuthn passkey register + login using the `webauthn` library — challenge/response cycle fully PostgreSQL-backed
- Google OAuth PKCE flow with state in challenges table, httpx token exchange, and email-based user upsert
- Email magic link with itsdangerous signed tokens, SES dispatch (mocked in tests), expiry and reuse prevention
- 10 `/auth/*` endpoints all mounted and passing tests: register start/finish, login start/finish, session, logout, oauth start/callback, magic-link request/verify

## Task Commits

Each task was committed atomically (TDD pattern):

1. **Task 1 RED: Failing tests for session + passkey** - `7f54125` (test)
2. **Task 1 + 2 GREEN: All auth modules implemented** - `ebe6b10` (feat)

## Files Created/Modified

- `api/auth/session.py` — `create_session` (INSERT sessions, set_cookie httponly/samesite/max_age) + `destroy_session`
- `api/auth/passkey.py` — `start_registration`, `finish_registration`, `start_authentication`, `finish_authentication`; challenges in PostgreSQL
- `api/auth/oauth.py` — `start_google_oauth` (state in challenges), `finish_google_oauth` (httpx token exchange + user upsert)
- `api/auth/magic_link.py` — `request_magic_link` (SES + magic_link_tokens INSERT) + `verify_magic_link` (token decode, reuse guard, user upsert)
- `api/auth/router.py` — 10 `/auth/*` endpoints with `run_in_threadpool()` for all DB calls
- `api/auth/_user_helpers.py` — `load_user_by_id`, `get_session_expires_at` shared helpers
- `api/auth/__init__.py` — Updated to import `router` from `router.py`
- `tests/test_api_auth.py` — 25 tests (was 8): session create/destroy, register/login start/finish, get_session, logout, OAuth, magic link full lifecycle

## Decisions Made

- **PostgreSQL challenge storage:** In-memory storage would not survive server restarts or work in multi-process deployments. Challenges stored with TTL (60s WebAuthn, 600s OAuth state, 900s magic link) and DELETE on consumption.
- **run_in_threadpool for psycopg2:** psycopg2 is synchronous-only; all DB calls in async FastAPI route handlers wrapped with `run_in_threadpool()`.
- **Lazy module imports in routes:** `from api.auth import passkey` inside route handlers avoids circular import at app startup (router.py imports from dependencies.py which imports from main app context).
- **OAuth state as challenge.id:** The state string stored as both `challenges.id` AND `challenges.challenge` (bytes). This allows looking up by state string directly via `WHERE id = %s` without base64 encoding/decoding.
- **Mock test side_effect sizing:** `load_user_by_id` adds one extra `fetchone` call per endpoint. Tests updated to include the user SELECT row after each auth-flow row sequence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mock side_effect lists were undersized**
- **Found during:** Task 1 + 2 (running endpoint tests)
- **Issue:** Router endpoints call `load_user_by_id` after `finish_registration`/`finish_google_oauth`/`verify_magic_link`, requiring one additional `fetchone` mock row. Original test design only had the auth-flow rows.
- **Fix:** Added `(user_id, near_account_id, username, email, codename, is_admin)` row to each endpoint test's `side_effect` list.
- **Files modified:** `tests/test_api_auth.py`
- **Verification:** All 25 tests pass
- **Committed in:** `ebe6b10`

---

**Total deviations:** 1 auto-fixed (1 bug in test mock setup)
**Impact on plan:** Test design adjustment only — no scope creep, no architectural changes.

## Issues Encountered

- Linter repeatedly reverted `api/auth/__init__.py` to the stub from Plan 01. Required re-applying the import update twice during execution. Final committed state is correct.

## Next Phase Readiness

- All auth endpoints complete — Plan 07-03 (wallet/transaction routers) can use `Depends(get_current_user)` and `Depends(get_effective_user)` directly
- Session cookie `neartax_session` is set by all three auth paths; `get_current_user` in `api/dependencies.py` validates it
- Test fixtures (`auth_client`, `admin_client`) from Plan 01 work correctly with the new auth endpoints
- Environment variables needed in production: `RP_ID`, `RP_NAME`, `ORIGIN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OAUTH_REDIRECT_URI`, `SECRET_KEY`, `SES_FROM_EMAIL`, `SESSION_SECURE=true`

## Self-Check: PASSED

- `api/auth/session.py` — FOUND
- `api/auth/passkey.py` — FOUND
- `api/auth/oauth.py` — FOUND
- `api/auth/magic_link.py` — FOUND
- `api/auth/router.py` — FOUND
- `api/auth/_user_helpers.py` — FOUND
- `tests/test_api_auth.py` — FOUND (25 tests passing)
- Commit `7f54125` — FOUND (test RED)
- Commit `ebe6b10` — FOUND (feat GREEN)

---
*Phase: 07-web-ui*
*Completed: 2026-03-13*
