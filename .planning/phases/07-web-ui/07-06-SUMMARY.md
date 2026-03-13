---
phase: 07-web-ui
plan: 06
subsystem: frontend
tags: [nextjs, fastapi, apiClient, webauthn, passkey, oauth, magic-link, pipeline, sync-status, portfolio, transactions, reports]

# Dependency graph
requires:
  - phase: 07-02
    provides: WebAuthn /auth/register/start|finish /auth/login/start|finish, OAuth /auth/oauth/start, magic-link /auth/magic-link/request
  - phase: 07-03
    provides: /api/wallets CRUD, /api/wallets/{id}/status, /api/wallets/{id}/resync, /api/portfolio/summary, /api/jobs/active
  - phase: 07-04
    provides: /api/transactions, /api/verification/needs-review-count
  - phase: 07-05
    provides: /api/reports/preview/{type}, /api/reports/generate, /api/reports/download/{year}, /api/reports/status
provides:
  - web/lib/api.ts: centralized apiClient with credentials:include for all FastAPI calls
  - web/components/auth-provider.tsx: session via GET /auth/session, logout via POST /auth/logout
  - web/app/auth/page.tsx: passkey/OAuth/magic-link all calling FastAPI directly
  - web/components/sync-status.tsx: 4-stage pipeline progress bar (Indexing/Classifying/Cost Basis/Verifying)
  - web/components/portfolio-summary.tsx: holdings + staking positions from /api/portfolio/summary
  - web/app/dashboard/page.tsx: needs-review badge from /api/verification/needs-review-count
  - web/app/dashboard/wallets/page.tsx: full CRUD via apiClient FastAPI endpoints
  - web/app/dashboard/transactions/page.tsx: paginated list from /api/transactions
  - web/app/dashboard/reports/page.tsx: 6 inline previews + generate job + download list
affects:
  - 07-07

# Tech tracking
tech-stack:
  added:
    - "@simplewebauthn/browser (startRegistration, startAuthentication) — replaces AnonAuthProvider"
  patterns:
    - "Centralized apiClient with credentials:include on every request — single import for all fetch calls"
    - "ApiError class with status + body — typed error handling across all pages"
    - "SyncStatus optional walletId — wallet-specific or global header mode"
    - "4-stage pipeline dots with pulsing active stage and checkmark on complete"
    - "Poll /api/jobs/{id}/status every 3s for report generation progress"

key-files:
  created:
    - web/lib/api.ts
  modified:
    - web/components/auth-provider.tsx
    - web/app/auth/page.tsx
    - web/next.config.mjs
    - web/components/sync-status.tsx
    - web/components/portfolio-summary.tsx
    - web/app/dashboard/page.tsx
    - web/app/dashboard/wallets/page.tsx
    - web/app/dashboard/transactions/page.tsx
    - web/app/dashboard/reports/page.tsx

key-decisions:
  - "apiClient centralizes credentials:include — no per-page fetch() calls needed"
  - "User.nearAccountId kept as required string (computed fallback) for Sidebar/SwapWidget legacy compat"
  - "SyncStatus walletId made optional — undefined triggers global /api/jobs/active mode for header badge"
  - "Auth page replaced AnonAuthProvider wrapper with direct SimpleWebAuthn browser calls to FastAPI"
  - "Reports page rewired from 16-tab old API to 6 FastAPI preview tabs + Generate Package tab"
  - "Transactions export removed — not yet available via FastAPI (deferred to Plan 07-07 or post-launch)"

# Metrics
duration: 11min
completed: 2026-03-13
---

# Phase 7 Plan 06: Frontend FastAPI Rewiring Summary

**Centralized apiClient with credentials:include wires the entire Next.js frontend to FastAPI — auth, wallets, portfolio, transactions, reports, and verification all fetching from Python backend with 4-stage pipeline progress bar showing real-time sync status**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-13T22:05:35Z
- **Completed:** 2026-03-13T22:16:04Z
- **Tasks:** 2
- **Files modified:** 9 (1 created)

## Accomplishments

- `web/lib/api.ts`: `apiClient` with `get/post/patch/delete`, `credentials: 'include'` on all requests, typed `ApiError` class with `status + body`
- `auth-provider.tsx`: session check via `GET /auth/session`, logout via `POST /auth/logout`; User interface updated with required `nearAccountId` computed from best available field for legacy component compat
- `auth/page.tsx`: AnonAuthProvider wrapper removed; passkey uses `@simplewebauthn/browser` (`startRegistration`/`startAuthentication`) with FastAPI challenge endpoints; Google OAuth redirects via `GET /auth/oauth/start`; magic link via `POST /auth/magic-link/request`
- `sync-status.tsx`: 4-stage pipeline dots (Indexing → Classifying → Cost Basis → Verifying) with pulsing active dot, checkmarks for completed stages, 3-second polling; optional `walletId` prop — omitted triggers global mode via `/api/jobs/active`
- `portfolio-summary.tsx`: renders `HoldingResponse[]` and `StakingPositionResponse[]` from `/api/portfolio/summary`; cost basis total displayed as CAD ACB value
- `dashboard/page.tsx`: needs-review badge links to transactions page, count from `/api/verification/needs-review-count`
- `wallets/page.tsx`: list from `GET /api/wallets`, add via `POST /api/wallets`, delete via `DELETE /api/wallets/{id}`, resync via `POST /api/wallets/{id}/resync`; pipeline status inline on syncing cards
- `transactions/page.tsx`: paginated list from `GET /api/transactions`; filter params mapped to FastAPI query schema (`tx_type`, `tax_category`, `date_from`, `date_to`)
- `reports/page.tsx`: 6 inline preview tabs (capital-gains, income, ledger, t1135, superficial-losses, holdings) via `GET /api/reports/preview/{type}`; Generate Package queues job and polls `GET /api/jobs/{id}/status` every 3s; downloads listed from `GET /api/reports/download/{year}`

## Task Commits

1. **Task 1: Centralized API client + auth-provider + auth page rewiring** - `f124ec9` (feat)
2. **Task 2: Dashboard pages rewiring + pipeline progress bar** - `70b68e8` (feat)

## Files Created/Modified

- `web/lib/api.ts` — Created: `apiClient`, `ApiError`, `API_URL` export
- `web/components/auth-provider.tsx` — FastAPI session/logout, User type updated
- `web/app/auth/page.tsx` — Removed AnonAuthProvider, direct FastAPI + SimpleWebAuthn
- `web/next.config.mjs` — Added `NEXT_PUBLIC_API_URL` env exposure
- `web/components/sync-status.tsx` — 4-stage pipeline progress bar component
- `web/components/portfolio-summary.tsx` — FastAPI portfolio/summary shape
- `web/app/dashboard/page.tsx` — Needs-review badge
- `web/app/dashboard/wallets/page.tsx` — Full FastAPI CRUD
- `web/app/dashboard/transactions/page.tsx` — FastAPI paginated transactions
- `web/app/dashboard/reports/page.tsx` — 6 previews + generate + download

## Decisions Made

- `apiClient` centralizes `credentials: 'include'` — no per-page `fetch()` calls needed, single import for all communication
- `User.nearAccountId` kept as required string (computed fallback) for `Sidebar`/`SwapWidget`/`LoginButtons` legacy compat
- `SyncStatus walletId` made optional — `undefined` triggers global `/api/jobs/active` mode used in dashboard header
- Auth page replaced AnonAuthProvider wrapper with direct SimpleWebAuthn browser calls to FastAPI; removes the `@vitalpoint/near-phantom-auth` dependency from auth flow
- Reports page rewired from old 16-tab API to 6 FastAPI preview tabs + Generate Package tab with job polling
- CSV export from transactions deferred — FastAPI does not expose a raw CSV export endpoint; users directed to Reports tab

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] User.nearAccountId must remain required for legacy components**
- **Found during:** Task 1 (TypeScript check)
- **Issue:** Changed `nearAccountId` to optional, breaking `Sidebar`, `SwapWidget`, `LoginButtons` which expect `string` not `string | undefined`
- **Fix:** Made `nearAccountId` required in `User` interface — computed as `near_account_id ?? email ?? display_name ?? id` at session parse time
- **Files modified:** `web/components/auth-provider.tsx`
- **Commit:** f124ec9

**2. [Rule 1 - Bug] SyncStatus walletId must be optional for dashboard layout header usage**
- **Found during:** Task 2 (TypeScript check)
- **Issue:** Layout uses `<SyncStatus />` without props; new interface required `walletId: number`
- **Fix:** Made `walletId` optional; when omitted polls `/api/jobs/active` for global status; shows compact badge or nothing when all jobs done
- **Files modified:** `web/components/sync-status.tsx`
- **Commit:** 70b68e8

---

**Total deviations:** 2 auto-fixed (Rule 1 - Type bugs from TypeScript check)
**Impact on plan:** Minor type fixes. No scope creep.

## Issues Encountered

None beyond the auto-fixed TypeScript type errors above.

## User Setup Required

Set `NEXT_PUBLIC_API_URL` environment variable (default: `http://localhost:8000`) so the browser knows where FastAPI is running. Add to `.env.local` for development:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Next Phase Readiness

- Frontend fully wired to FastAPI — all data fetching goes through `apiClient`
- Ready for Plan 07-07: cleanup (remove old Next.js API routes in `web/app/api/`), E2E integration verification, and any remaining gap closures

## Self-Check: PASSED

- FOUND: web/lib/api.ts
- FOUND: web/components/auth-provider.tsx
- FOUND: web/components/sync-status.tsx
- FOUND: web/app/auth/page.tsx
- FOUND commit: f124ec9 (Task 1)
- FOUND commit: 70b68e8 (Task 2)

---
*Phase: 07-web-ui*
*Completed: 2026-03-13*
