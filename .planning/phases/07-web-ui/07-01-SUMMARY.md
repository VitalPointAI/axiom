---
phase: 07-web-ui
plan: 01
subsystem: api
tags: [fastapi, webauthn, psycopg2, alembic, postgresql, pytest, pydantic]

# Dependency graph
requires:
  - phase: 05-verification
    provides: "verification_results and account_verification_status tables"
  - phase: 01-near-indexer
    provides: "indexers/db.py psycopg2 connection pool, users table"

provides:
  - "Migration 006: passkeys, sessions, challenges, magic_link_tokens, accountant_access tables"
  - "FastAPI app factory (api/main.py) with CORS, lifespan, router mounts, GET /health"
  - "Auth dependencies: get_current_user, get_effective_user, require_admin, get_pool_dep"
  - "Pydantic schemas: auth (Register/Login/MagicLink/OAuth/Session/User) + common (Error/Paginated/JobStatus)"
  - "Stub routers for wallets, transactions, portfolio, reports, verification, jobs (all auth-enforced)"
  - "Test fixtures: api_client, auth_client, admin_client, mock_pool, mock_user, mock_conn"

affects:
  - 07-02-passkey-auth
  - 07-03-magic-link-oauth
  - 07-04-wallet-transaction-routers
  - 07-05-portfolio-router
  - 07-06-reports-verification-routers
  - 07-07-job-status-router

# Tech tracking
tech-stack:
  added:
    - fastapi>=0.111.0
    - uvicorn[standard]>=0.29.0
    - python-multipart>=0.0.9
    - webauthn>=2.0.0 (PyPI name; plan spec said py_webauthn which does not exist at >=2.0.0)
    - itsdangerous>=2.1.0
    - boto3>=1.34.0
    - httpx>=0.27.0
    - aiofiles>=24.0.0
    - slowapi>=0.1.9
  patterns:
    - "FastAPI dependency injection via Depends() for pool and auth"
    - "lifespan asynccontextmanager for DB pool init/teardown"
    - "dependency_overrides + patch('indexers.db.get_pool') for test isolation"
    - "get_effective_user wraps get_current_user for accountant delegation"

key-files:
  created:
    - db/migrations/versions/006_auth_schema.py
    - api/__init__.py
    - api/main.py
    - api/dependencies.py
    - api/auth/__init__.py
    - api/routers/__init__.py
    - api/schemas/__init__.py
    - api/schemas/auth.py
    - api/schemas/common.py
    - tests/conftest.py
    - tests/test_api_auth.py
  modified:
    - db/models.py (User extended; Passkey, Session, Challenge, MagicLinkToken, AccountantAccess added)
    - requirements.txt (9 new packages)

key-decisions:
  - "webauthn (not py_webauthn) is the correct PyPI package name for WebAuthn v2 — py_webauthn only has v0.x"
  - "Challenge.metadata mapped as challenge_metadata column to avoid SQLAlchemy reserved attribute name"
  - "Stub routers require get_effective_user on all GET endpoints so unauthenticated requests return 401 not 404"
  - "lifespan db.get_pool() patched in test fixtures to avoid requiring DATABASE_URL during testing"
  - "User.near_account_id made nullable=True to support email-only users (no NEAR wallet required)"
  - "ALLOWED_ORIGINS defaults to localhost:3000 when env var absent (safe for dev, explicit for prod)"

patterns-established:
  - "All data routers use Depends(get_effective_user) not Depends(get_current_user) to support accountant mode"
  - "TestClient fixtures patch both dependency_overrides[get_pool_dep] and indexers.db.get_pool for lifespan"
  - "Pool putconn() always in finally block to prevent connection leaks"

requirements-completed:
  - UI-08

# Metrics
duration: 7min
completed: 2026-03-13
---

# Phase 7 Plan 01: FastAPI Foundation Summary

**FastAPI app factory with psycopg2 pool injection, WebAuthn-ready auth dependencies, Pydantic schemas, and migration 006 formalizing passkeys/sessions/challenges/magic_link_tokens/accountant_access tables**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-03-13T21:31:54Z
- **Completed:** 2026-03-13T21:38:54Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments

- Alembic migration 006 created with all 6 auth table changes (users ALTER + 5 new tables), all idempotent via IF NOT EXISTS
- FastAPI app factory with CORS middleware, lifespan-managed psycopg2 pool, 7 mounted routers, GET /health
- Auth dependency chain: get_pool_dep → get_current_user → get_effective_user → require_admin
- Accountant delegation in get_effective_user: checks accountant_access table, returns client context with permission_level
- Pydantic schemas for WebAuthn register/login, magic link, OAuth callback, session and user responses
- Test infrastructure with 3 TestClient fixtures (api_client, auth_client, admin_client) all using dependency_overrides + lifespan patching — 8 tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Alembic migration 006 + auth SQLAlchemy models** - `bebbf2b` (feat)
2. **Task 2: FastAPI app skeleton + dependencies + schemas + test infrastructure** - `76a3099` (feat)

## Files Created/Modified

- `db/migrations/versions/006_auth_schema.py` - Idempotent migration for passkeys, sessions, challenges, magic_link_tokens, accountant_access + ALTER users
- `db/models.py` - User extended with username/email/is_admin/codename; 5 new models: Passkey, Session, Challenge, MagicLinkToken, AccountantAccess
- `requirements.txt` - 9 new packages including fastapi, uvicorn, webauthn, itsdangerous, boto3, httpx, aiofiles, slowapi
- `api/main.py` - FastAPI app factory with CORS, lifespan, router mounts, GET /health
- `api/dependencies.py` - get_pool_dep, get_db_conn, get_current_user, get_effective_user, require_admin
- `api/auth/__init__.py` - Auth APIRouter stub (WebAuthn handlers added in 07-02)
- `api/routers/__init__.py` - 6 stub routers with auth-enforcing GET endpoints
- `api/schemas/auth.py` - Register/Login Start/Finish, MagicLink, OAuthCallback, Session/UserResponse
- `api/schemas/common.py` - ErrorResponse, PaginatedResponse[T], JobStatusResponse
- `tests/conftest.py` - api_client, auth_client, admin_client, mock_pool, mock_conn, mock_user, mock_admin fixtures
- `tests/test_api_auth.py` - 8 passing tests for health endpoint, 401 guards, accountant mode

## Decisions Made

- **webauthn vs py_webauthn:** Plan spec said `py_webauthn>=2.0.0` but that package only has v0.x on PyPI. Correct package is `webauthn>=2.0.0` — installed webauthn 2.7.1.
- **Challenge.metadata:** SQLAlchemy reserves `metadata` as a class attribute on DeclarativeBase. Mapped as `challenge_metadata` Python attribute pointing to the `metadata` DB column via `mapped_column("metadata", ...)`.
- **Stub router endpoints:** Plan said stub routers are empty packages. Empty packages produce 404 for unauthenticated requests which breaks the `test_unauthenticated_returns_401` requirement. Added stub GET endpoints with `Depends(get_effective_user)` to enforce 401.
- **User.near_account_id nullable:** Context says email-only users (no NEAR wallet) must be supported. Made nullable=True on the SQLAlchemy model (DB column has no NOT NULL constraint in migration 006).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] py_webauthn package name incorrect in plan**
- **Found during:** Task 2 (install dependencies)
- **Issue:** `py_webauthn>=2.0.0` does not exist on PyPI (only v0.x). Correct package is `webauthn`.
- **Fix:** Installed `webauthn>=2.0.0` and updated requirements.txt accordingly
- **Files modified:** requirements.txt
- **Verification:** `import webauthn` succeeds with version 2.7.1
- **Committed in:** 76a3099

**2. [Rule 1 - Bug] Challenge.metadata conflicts with SQLAlchemy reserved name**
- **Found during:** Task 1 (model import verification)
- **Issue:** `metadata` is a reserved attribute on SQLAlchemy DeclarativeBase; declaring a column with that name raises InvalidRequestError
- **Fix:** Mapped as `challenge_metadata` Python attribute pointing to `metadata` DB column via `mapped_column("metadata", JSONB, ...)`
- **Files modified:** db/models.py
- **Verification:** `from db.models import Challenge; print('OK')` succeeds
- **Committed in:** bebbf2b

**3. [Rule 2 - Missing Critical] Stub routers need auth-enforcing endpoints**
- **Found during:** Task 2 (running tests)
- **Issue:** Empty stub routers return 404 for unauthenticated requests; plan requires 401. Empty APIRouter has no routes to enforce auth.
- **Fix:** Added stub GET "" handlers with `Depends(get_effective_user)` on each router
- **Files modified:** api/routers/__init__.py
- **Verification:** `test_unauthenticated_wallets_returns_401` passes (401 not 404)
- **Committed in:** 76a3099

**4. [Rule 3 - Blocking] lifespan calls db.get_pool() which fails without DATABASE_URL**
- **Found during:** Task 2 (first test run)
- **Issue:** TestClient triggers the lifespan event which calls `_db.get_pool()`, raising EnvironmentError when DATABASE_URL is unset
- **Fix:** Added `patch("indexers.db.get_pool", return_value=mock_pool)` and `patch("indexers.db.close_pool")` in all TestClient fixtures
- **Files modified:** tests/conftest.py
- **Verification:** All 8 tests pass without DATABASE_URL
- **Committed in:** 76a3099

---

**Total deviations:** 4 auto-fixed (1 bug, 1 bug, 1 missing critical, 1 blocking)
**Impact on plan:** All fixes necessary for correctness and testability. No scope creep.

## Issues Encountered

None beyond the deviations documented above.

## Next Phase Readiness

- FastAPI foundation is fully in place — 07-02 can implement WebAuthn register/login handlers on the `auth_router`
- `get_current_user` and `get_effective_user` are ready for all data routers (07-04 through 07-07)
- Test fixtures (api_client, auth_client) are reusable across all subsequent plan test files
- Migration 006 needs to run against the production DB before Phase 7 deployment

---
*Phase: 07-web-ui*
*Completed: 2026-03-13*
