---
phase: 12-user-onboarding
plan: "02"
subsystem: ui
tags: [nextjs, react, onboarding, wizard, typescript, tailwind]

# Dependency graph
requires:
  - phase: 12-01
    provides: GET/POST /api/preferences, GET /api/wallets/suggestions, onboarding_completed_at column

provides:
  - 5-step onboarding wizard at /onboarding/ with smart resume logic
  - Dashboard redirect guard (new users with no wallets redirected to onboarding)
  - SyncStatus onComplete callback prop for pipeline completion detection

affects:
  - 12-03 (inline guidance/banners — shares dashboard layout and preferences API patterns)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Smart resume: Promise.all to fetch wallets/jobs/prefs and route to correct step
    - Two-part redirect guard: NULL onboarding_completed_at AND zero wallets required before redirect
    - onCompleteRef pattern: avoids stale closure on callback updates
    - prevDoneRef: tracks previous done state to fire onComplete exactly once

key-files:
  created:
    - web/app/onboarding/layout.tsx
    - web/app/onboarding/page.tsx
    - web/app/onboarding/steps/welcome.tsx
    - web/app/onboarding/steps/wallets.tsx
    - web/app/onboarding/steps/import.tsx
    - web/app/onboarding/steps/processing.tsx
    - web/app/onboarding/steps/review.tsx
  modified:
    - web/app/dashboard/layout.tsx
    - web/components/sync-status.tsx

key-decisions:
  - "Two-part redirect guard (NULL onboarding_completed_at AND zero wallets) prevents redirecting existing users with wallets"
  - "Onboarding layout separate from dashboard layout tree prevents redirect loop"
  - "Smart resume uses Promise.all for parallel wallet/jobs/prefs check on mount"
  - "prevDoneRef in SyncStatus to fire onComplete exactly once on pipeline completion"
  - "Processing step polls /api/jobs/active independently (SyncStatus global mode returns null when done)"
  - "Sequential wallet POST loop to avoid race conditions in Step 2"
  - "Non-blocking onboarding check in dashboard layout — API failure allows dashboard access"

patterns-established:
  - "Onboarding step components: accept { onNext, onSkip } props, use 'use client', dark theme"
  - "Step indicator: numbered circles with green check for completed, blue for active, gray for future"

requirements-completed: [ONBOARD-01, ONBOARD-02, ONBOARD-03, ONBOARD-04]

# Metrics
duration: 8min
completed: 2026-03-16
---

# Phase 12 Plan 02: Onboarding Wizard Summary

**5-step onboarding wizard at /onboarding/ with smart resume, chain-specific wallet help, drag-drop file import, pipeline progress monitoring, and dashboard redirect guard**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-16T15:11:41Z
- **Completed:** 2026-03-16T15:19:24Z
- **Tasks:** 2 auto tasks complete, 1 checkpoint awaiting human verify
- **Files modified:** 9 (7 created, 2 modified)

## Accomplishments

- Full-page onboarding layout (no sidebar) separate from dashboard layout to prevent redirect loops
- Smart resume page using Promise.all(wallets, jobs, prefs) to route returning users to correct step
- 5 step components: Welcome, Wallets (multi-add with chain help), Import (drag-drop), Processing (pipeline monitor + wallet discovery), Review (summary + orientation)
- Dashboard layout onboarding check: two-part guard redirects only new users (NULL completed_at AND zero wallets)
- SyncStatus `onComplete` prop fires exactly once on pipeline completion via prevDoneRef

## Task Commits

Each task was committed atomically:

1. **Task 1: Onboarding layout, smart resume page, and all 5 step components** - `365e4ea` (feat)
2. **Task 2: Dashboard onboarding redirect guard + SyncStatus onComplete** - `2579f61` (feat)

## Files Created/Modified

- `web/app/onboarding/layout.tsx` — Full-page dark layout with auth check and completed-onboarding redirect
- `web/app/onboarding/page.tsx` — Smart resume orchestrator with step indicator (1/5 ... 5/5)
- `web/app/onboarding/steps/welcome.tsx` — Welcome screen with feature highlights, Get Started + skip
- `web/app/onboarding/steps/wallets.tsx` — Multi-wallet addition with chain dropdown + per-chain help panel (format/where-to-find/what-pulled/example)
- `web/app/onboarding/steps/import.tsx` — Drag-drop upload zone with supported exchange badges, POST /api/upload-file
- `web/app/onboarding/steps/processing.tsx` — Loader2 + SyncStatus global mode + 3s job polling + wallet discovery suggestions with Add/Not Mine buttons
- `web/app/onboarding/steps/review.tsx` — Wallet/tx count summary, amber review note, orientation links (Reports/Transactions/Verification), Go to Dashboard
- `web/app/dashboard/layout.tsx` — Added onboarding check useEffect, two-part guard, onboardingChecked state
- `web/components/sync-status.tsx` — Added onComplete prop, prevDoneRef, onCompleteRef (stable callback ref pattern)

## Decisions Made

- **Two-part redirect guard** — NULL onboarding_completed_at AND zero wallets required. This prevents redirecting existing users who have wallets but never completed onboarding wizard (per CONTEXT.md pitfall #2).
- **Onboarding layout separate from dashboard layout** — Prevents redirect loop. Onboarding layout checks if completed and redirects to dashboard; dashboard layout checks if not completed and redirects to onboarding. They can't conflict because they're in separate layout trees.
- **Processing step polls /api/jobs/active independently** — SyncStatus in global mode returns null when done, making it impossible to detect completion from the component alone. Independent polling detects the transition.
- **Sequential wallet POST** — Multiple wallets added one-by-one in sequence to avoid race conditions at the DB level.
- **prevDoneRef for onComplete** — Tracks previous done state to fire callback exactly once on transition, not on every re-render while in done state.
- **Non-blocking dashboard onboarding check** — try/catch around preferences fetch; failure allows dashboard access rather than blocking authenticated users.

## Deviations from Plan

None - plan executed exactly as written. TypeScript errors found in `app/auth/page.tsx` are pre-existing (3 errors unrelated to onboarding), not introduced by this plan.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Onboarding wizard complete and awaiting human verification (checkpoint)
- After verification, Phase 12 Plan 03 (inline guidance + banner system) can proceed
- SyncStatus onComplete callback is available for future use cases beyond onboarding

---
*Phase: 12-user-onboarding*
*Completed: 2026-03-16*
