---
phase: 08-cicd-deployment
plan: 01
subsystem: infra
tags: [docker, docker-compose, deployment, ssh, bash, health-check]

# Dependency graph
requires:
  - phase: 01-near-indexer
    provides: "Dockerfile for indexer, docker-compose.yml base config"
provides:
  - "Production Docker Compose with postgres, migrate, web, indexer services"
  - "SSH-based deployment script with rolling restart and rollback"
  - "Post-deploy health check script with retry logic"
affects: [08-cicd-deployment]

# Tech tracking
tech-stack:
  added: []
  patterns: [docker-compose-prod-config, ssh-deploy, rolling-restart, one-shot-migration]

key-files:
  created:
    - docker-compose.prod.yml
    - scripts/deploy.sh
    - scripts/healthcheck.sh
  modified:
    - .env.example

key-decisions:
  - "Removed obsolete version field from docker-compose.prod.yml"
  - "Deploy script runs locally and SSHs to server (no Docker registry needed)"
  - "Rolling restart: web first, wait 30s, then indexer — postgres never restarts"
  - "Rollback via git checkout of specific commit SHA"

patterns-established:
  - "Production compose: axiom-net bridge network, json-file logging with rotation"
  - "One-shot migrate service runs Alembic before app services start"
  - "Resource limits on all app services (256-512MB memory, 0.5 CPU)"

requirements-completed: [CICD-02, CICD-03]

# Metrics
duration: 3min
completed: 2026-03-12
---

# Phase 8 Plan 1: Production Docker Compose + Deployment Scripts Summary

**Production Docker Compose with 4 services (postgres, migrate, web, indexer), SSH deployment script with rolling restart and rollback, and health check verification**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-12T10:21:09Z
- **Completed:** 2026-03-12T10:24:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Production-hardened Docker Compose with resource limits, health checks, logging, and bridge networking
- Alembic migration service runs before app services start (one-shot)
- SSH deployment script with rolling restart strategy and --rollback flag
- Health check script verifies all services with retry logic

## Task Commits

Each task was committed atomically:

1. **Task 1: Create production Docker Compose and update .env.example** - `56f5ff5` (feat)
2. **Task 2: Create deployment and health check scripts** - `d67aa15` (feat)

## Files Created/Modified
- `docker-compose.prod.yml` - Production Docker Compose with 4 services, bridge network, resource limits, health checks
- `scripts/deploy.sh` - SSH-based deployment with git pull, build, migrate, rolling restart, rollback
- `scripts/healthcheck.sh` - Post-deploy verification for postgres, web, indexer with retry logic
- `.env.example` - Added CRYPTOCOMPARE_API_KEY, indexer config, deployment vars

## Decisions Made
- Removed obsolete `version: '3.8'` field from compose file (Docker Compose V2 no longer needs it)
- Deploy script runs locally/in CI and SSHs to server -- no Docker registry needed for single-server setup
- Rolling restart order: web first (user-facing), wait 30s for health, then indexer. Postgres never restarts during deploy.
- Rollback mechanism: re-deploy specific git commit SHA via `--rollback` flag

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. Deployment env vars (DEPLOY_HOST, DEPLOY_USER, DEPLOY_PATH) documented in .env.example.

## Next Phase Readiness
- docker-compose.prod.yml and deployment scripts ready for GitHub Actions workflow (08-02)
- deploy.sh expects DEPLOY_HOST, DEPLOY_USER, DEPLOY_PATH env vars (to be set as GitHub Secrets)
- healthcheck.sh is called by deploy.sh on the remote server after restart

---
*Phase: 08-cicd-deployment*
*Completed: 2026-03-12*
