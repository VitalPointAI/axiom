---
phase: 07-web-ui
plan: "07"
subsystem: infra
tags: [docker, fastapi, uvicorn, next.js, deployment, github-actions]

requires:
  - phase: 07-web-ui
    provides: FastAPI backend (api/), Next.js frontend rewired to FastAPI (07-06)

provides:
  - api/Dockerfile for FastAPI container (python:3.11-slim, project root context)
  - docker-compose.prod.yml with 4 services (postgres, migrate, web, api, indexer)
  - Updated deploy.yml with SECRET_KEY secret and NEXT_PUBLIC_API_URL
  - Updated scripts/deploy.sh with api in rolling restart (api -> web -> indexer)
  - Updated scripts/healthcheck.sh with FastAPI /health check on port 8000
  - web/app/api/ deleted (75 Next.js API routes removed)
  - web/lib/db.ts, auth-db.ts, auth.ts deleted (server-side DB libs no longer needed)
  - web/middleware.ts simplified (rate limiting + auth removed, FastAPI handles those)

affects: [deployment, ci-cd, phase-08]

tech-stack:
  added: []
  patterns:
    - "api service depends_on: postgres (healthy) + migrate (completed_successfully)"
    - "web service depends_on: api (healthy) ensuring FastAPI ready before Next.js starts"
    - "Rolling restart order: api first (backend), then web (frontend), then indexer (background)"
    - "FastAPI healthcheck via curl -f http://localhost:8000/health"

key-files:
  created:
    - api/Dockerfile
  modified:
    - docker-compose.prod.yml
    - .github/workflows/deploy.yml
    - scripts/deploy.sh
    - scripts/healthcheck.sh
    - web/middleware.ts
  deleted:
    - web/app/api/ (entire directory, 75 route files)
    - web/lib/db.ts
    - web/lib/auth-db.ts
    - web/lib/auth.ts

key-decisions:
  - "api Dockerfile uses project root as build context (same as indexers/Dockerfile) so all Python packages are available"
  - "web service depends_on api (healthy) to ensure FastAPI is ready before Next.js starts serving"
  - "Rolling restart order: api -> web -> indexer (backend ready before frontend, then background worker last)"
  - "DATABASE_URL removed from web service env (Next.js no longer talks to DB directly)"
  - "NEXT_PUBLIC_API_URL=http://api:8000 added to web service for container-to-container communication"
  - "web/middleware.ts stripped of rate limiting and API auth checks (FastAPI handles those)"
  - "Checkpoint: human verification required to confirm end-to-end flow works in production Docker stack"

patterns-established:
  - "4-service Docker stack: postgres -> migrate -> (api, web in parallel, api first) -> indexer"

requirements-completed: [UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, UI-08]

duration: 8min
completed: 2026-03-13
---

# Phase 7 Plan 7: Docker Deployment + Next.js API Route Removal Summary

**FastAPI Docker container added as 4th service alongside postgres/web/indexer; all 75 Next.js API route files deleted after FastAPI rewiring confirmed complete in Plan 06**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-13T22:20:34Z
- **Completed:** 2026-03-13T22:28:00Z
- **Tasks:** 1 of 2 (Task 2 is checkpoint:human-verify)
- **Files modified:** 7 modified, 1 created, 78 deleted

## Accomplishments
- FastAPI container (api/Dockerfile) created with project-root build context so all Python packages (db, engine, reports, api) are accessible
- docker-compose.prod.yml updated to 4-service stack with health checks, resource limits, and proper depends_on ordering
- Rolling restart in deploy.sh updated: api starts first (20s wait), then web, then indexer
- healthcheck.sh updated to verify FastAPI /health on port 8000
- All 75 Next.js API route files deleted (web/app/api/) - these were all server-side routes that duplicated FastAPI
- web/lib/db.ts, auth-db.ts, auth.ts deleted (server-side DB access removed from Next.js)
- web/middleware.ts simplified: only handles dashboard redirects + security headers (rate limiting + auth moved to FastAPI)

## Task Commits

Each task was committed atomically:

1. **Task 1: FastAPI Dockerfile + docker-compose update + deploy workflow** - `1cb2ab5` (feat)

**Plan metadata:** (docs commit after verification checkpoint)

## Files Created/Modified
- `api/Dockerfile` - FastAPI container: python:3.11-slim, project root context, 2 uvicorn workers
- `docker-compose.prod.yml` - 4-service stack: postgres, migrate, web (depends on api), api (port 8000), indexer
- `.github/workflows/deploy.yml` - Added SECRET_KEY secret, NEXT_PUBLIC_API_URL, RP_ID/RP_NAME/ORIGIN env vars
- `scripts/deploy.sh` - Rolling restart: api -> web -> indexer; api health wait 20s before starting web
- `scripts/healthcheck.sh` - Added FastAPI /health check on port 8000 (curl -sf)
- `web/middleware.ts` - Simplified: removed rate limiting + API auth (FastAPI handles); kept dashboard redirect + security headers
- `web/app/api/` - DELETED (75 Next.js API routes: all auth, wallets, transactions, reports, portfolio routes)
- `web/lib/db.ts` - DELETED (PostgreSQL pool for Next.js server components, no longer needed)
- `web/lib/auth-db.ts` - DELETED (auth DB helpers for Next.js, no longer needed)
- `web/lib/auth.ts` - DELETED (session management for Next.js API routes, no longer needed)

## Decisions Made
- api Dockerfile uses project root as build context so `from db.models import ...`, `from engine.acb import ...` all work without path manipulation
- web service `depends_on: api: condition: service_healthy` ensures FastAPI is up before Next.js starts (prevents 502s on cold start)
- Rolling restart order: api first, then web depends on api being healthy, indexer last (background worker)
- DATABASE_URL removed from web service env — Next.js no longer has any direct DB access
- web/middleware.ts stripped to bare minimum — FastAPI handles rate limiting, session validation, and auth

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added healthcheck.sh update for api service**
- **Found during:** Task 1 (deploy workflow + scripts)
- **Issue:** Plan specified updating deploy.sh but did not mention healthcheck.sh needing api check
- **Fix:** Added curl -sf http://localhost:8000/health check to healthcheck.sh alongside existing checks
- **Files modified:** scripts/healthcheck.sh
- **Verification:** Script logic checks api before web and indexer
- **Committed in:** 1cb2ab5 (Task 1 commit)

**2. [Rule 2 - Missing Critical] web depends_on api condition: service_healthy**
- **Found during:** Task 1 (docker-compose update)
- **Issue:** Plan said web needs NEXT_PUBLIC_API_URL but didn't specify depends_on ordering
- **Fix:** Added api: condition: service_healthy to web depends_on so Next.js starts only after FastAPI is healthy
- **Files modified:** docker-compose.prod.yml
- **Verification:** docker compose config validates without error
- **Committed in:** 1cb2ab5 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (Rule 2 - missing critical)
**Impact on plan:** Both fixes are essential for production correctness. No scope creep.

## Issues Encountered
- web/app/api/health/route.ts existed (old Next.js health endpoint); deleted as part of api/ removal. healthcheck.sh updated to check FastAPI on port 8000 instead of Next.js /api/health.

## User Setup Required
Before deploying to production, add these GitHub Secrets:
- `SECRET_KEY` — random 64+ char string for FastAPI session signing (new, required)
- `RP_ID` — WebAuthn relying party ID (e.g., axiom.vitalpoint.ai)
- `ORIGIN` — WebAuthn origin URL (e.g., https://axiom.vitalpoint.ai)
- `ALLOWED_ORIGINS` — CORS allowed origins (e.g., https://axiom.vitalpoint.ai)

## Next Phase Readiness
- Phase 7 complete pending human verification of end-to-end Docker stack
- Checkpoint awaits: start `docker compose -f docker-compose.prod.yml up --build -d`, verify health checks pass, test login -> wallet add -> pipeline -> reports flow
- After checkpoint approval, Phase 7 Web UI is COMPLETE

---
*Phase: 07-web-ui*
*Completed: 2026-03-13*
