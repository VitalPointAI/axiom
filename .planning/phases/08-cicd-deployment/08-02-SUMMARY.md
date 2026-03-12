---
phase: 08-cicd-deployment
plan: 02
subsystem: infra
tags: [github-actions, ci-cd, deployment, ssh, workflow-dispatch, rollback]

# Dependency graph
requires:
  - phase: 08-cicd-deployment
    provides: "Production Docker Compose, deploy.sh, healthcheck.sh from plan 08-01"
provides:
  - "GitHub Actions workflow for automated deploy on push to main"
  - "Manual rollback via workflow_dispatch with commit SHA"
  - "Hardened .gitignore preventing accidental secret commits"
affects: []

# Tech tracking
tech-stack:
  added: [github-actions]
  patterns: [github-actions-deploy, ssh-key-in-workflow, env-from-secrets, concurrency-control]

key-files:
  created:
    - .github/workflows/deploy.yml
  modified:
    - .gitignore

key-decisions:
  - "SSH key written to temp file in runner, cleaned up in always() step"
  - ".env created on server via SSH heredoc from GitHub Secrets -- never in repo"
  - "Concurrency group prevents overlapping deployments (cancel-in-progress: false)"

patterns-established:
  - "GitHub Actions: checkout, SSH setup, remote .env write, deploy script, health check, cleanup"
  - "Secrets flow: GitHub Secrets -> workflow env vars -> SSH to server -> .env file"

requirements-completed: [CICD-01, CICD-02, CICD-03]

# Metrics
duration: 3min
completed: 2026-03-12
---

# Phase 8 Plan 2: GitHub Actions Deploy Workflow + .gitignore Hardening Summary

**GitHub Actions CI/CD workflow with auto-deploy on push to main, manual rollback via workflow_dispatch, and .gitignore hardened for deployment secrets**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-12T10:25:37Z
- **Completed:** 2026-03-12T10:28:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- GitHub Actions workflow auto-deploys on push to main using SSH + deploy.sh from 08-01
- Manual rollback supported via workflow_dispatch input with commit SHA
- All sensitive values use GitHub Secrets -- no hardcoded credentials in workflow
- .gitignore hardened with .env variants, SSH key patterns, Docker volume exclusion

## Task Commits

Each task was committed atomically:

1. **Task 1: Create GitHub Actions deploy workflow** - `311452a` (feat)
2. **Task 2: Update .gitignore and add deployment documentation** - `5566829` (chore)

## Files Created/Modified
- `.github/workflows/deploy.yml` - Full CI/CD pipeline: checkout, SSH setup, .env creation, deploy, health check, failure logging, cleanup
- `.gitignore` - Added .env.local, .env.production, deploy_key, id_rsa, postgres_data/ exclusions

## Decisions Made
- SSH key written to `~/.ssh/deploy_key` temp file, cleaned up in `if: always()` step for security
- .env file created on remote server via SSH heredoc rather than scp -- avoids temp file on runner
- Concurrency group `deploy` with `cancel-in-progress: false` -- queues deployments rather than canceling

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

Before the workflow can run, configure these GitHub Secrets in the repository settings:

**Required:**
- `DEPLOY_HOST` - Server IP or hostname
- `DEPLOY_USER` - SSH username on server
- `DEPLOY_SSH_KEY` - Private SSH key content (full key, not file path)
- `DEPLOY_PATH` - Absolute path to project on server (e.g., /home/deploy/Axiom)
- `POSTGRES_PASSWORD` - Database password

**API Keys:**
- `NEARBLOCKS_API_KEY` - NearBlocks API key
- `COINGECKO_API_KEY` - CoinGecko API key
- `CRYPTOCOMPARE_API_KEY` - CryptoCompare API key

**Optional:**
- `ALCHEMY_API_KEY` - Alchemy API key
- `ETHERSCAN_API_KEY` - Etherscan API key
- `FASTNEAR_API_KEY` - FastNEAR API key

Also create a GitHub Environment named `production` in repository settings.

## Next Phase Readiness
- CI/CD pipeline is complete -- Phase 8 fully done
- Push to main will auto-deploy once GitHub Secrets are configured
- Manual rollback available via Actions UI > "Run workflow" > enter commit SHA

---
*Phase: 08-cicd-deployment*
*Completed: 2026-03-12*
