---
phase: 12-user-onboarding
plan: "03"
subsystem: ui
tags: [react, nextjs, onboarding, ux, components, typescript]

# Dependency graph
requires:
  - phase: 12-01
    provides: GET /api/preferences + PATCH /api/preferences/dismiss-banner endpoints

provides:
  - OnboardingBanner component (dismissible, persists via API, graceful fallback on error)
  - InlineGuidance component (5 diagnosis categories, resync/resolve/navigate actions)
  - Contextual banners on Reports, Transactions, Wallets, and Dashboard pages
  - Expandable InlineGuidance rows for needs_review transactions in the transaction ledger

affects: [12-user-onboarding, web-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Dismissible banner pattern using preferences JSONB + PATCH endpoint
    - Expandable table rows via React.Fragment + expandedTxId state toggle
    - Diagnosis category -> explanation mapping in a single CATEGORY_GUIDANCE record

key-files:
  created:
    - web/components/onboarding-banner.tsx
    - web/components/inline-guidance.tsx
  modified:
    - web/app/dashboard/reports/page.tsx
    - web/app/dashboard/transactions/page.tsx
    - web/app/dashboard/wallets/page.tsx
    - web/app/dashboard/page.tsx

key-decisions:
  - "OnboardingBanner shows banner on preferences fetch error (fail open) — better to show than silently hide"
  - "React.Fragment with key for transaction rows to support expandable InlineGuidance without breaking tbody structure"
  - "InlineGuidance uses optimistic done state on API error — user sees feedback regardless"
  - "diagnosisCategory maps to tx.tax_category since verification_results diagnosis_category mirrors classification categories"

patterns-established:
  - "Dismissible banner pattern: useState(false) until preferences loaded, show if not dismissed, PATCH on close"
  - "InlineGuidance action types: resync (POST /api/verification/resync/{id}), resolve (POST /api/verification/resolve/{id}), navigate (href)"

requirements-completed: [ONBOARD-04, ONBOARD-05, ONBOARD-06, ONBOARD-07]

# Metrics
duration: 6min
completed: 2026-03-16
---

# Phase 12 Plan 03: Inline Guidance + Banner System Summary

**Dismissible contextual banners on 4 dashboard pages + expandable InlineGuidance rows for flagged transactions, backed by preferences API persistence**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-16T15:11:32Z
- **Completed:** 2026-03-16T15:17:33Z
- **Tasks:** 3/3 complete (Task 3 human-verify checkpoint approved)
- **Files modified:** 6

## Accomplishments

- OnboardingBanner component: dismissible info banner, fetches dismissed_banners from GET /api/preferences on mount, persists dismissal via PATCH /api/preferences/dismiss-banner, shows banner if fetch fails (fail-open)
- InlineGuidance component: maps all 5 diagnosis categories to plain-English explanations with action buttons (Re-sync Staking, Re-index Wallet, Review Transaction, Mark Reviewed)
- All 4 dashboard pages (Reports, Transactions, Wallets, Dashboard) show contextual banners above page content
- Transactions page renders expandable InlineGuidance rows beneath needs_review=true transaction rows; clicking a flagged row toggles the guidance panel

## Task Commits

Each task was committed atomically:

1. **Task 1: OnboardingBanner + InlineGuidance components** - `3b8b522` (feat)
2. **Task 2: Integrate banners into 4 pages + wire InlineGuidance** - `bcfd57b` (feat)

## Files Created/Modified

- `web/components/onboarding-banner.tsx` - Reusable dismissible banner; fetches preferences on mount, PATCH on dismiss, fail-open on error
- `web/components/inline-guidance.tsx` - Inline warning/error card; maps 5 diagnosis categories to explanations + action buttons
- `web/app/dashboard/reports/page.tsx` - Added OnboardingBanner (bannerKey='reports_page') before header
- `web/app/dashboard/transactions/page.tsx` - Added OnboardingBanner + React.Fragment rows with expandable InlineGuidance for needs_review items
- `web/app/dashboard/wallets/page.tsx` - Added OnboardingBanner (bannerKey='wallets_page') before header
- `web/app/dashboard/page.tsx` - Added OnboardingBanner (bannerKey='verification_page') before header

## Decisions Made

- OnboardingBanner shows on preferences fetch error (fail open) — better to show than silently hide, per plan spec
- React.Fragment with key prop used for transaction rows to allow InlineGuidance expansion row without breaking tbody structure
- InlineGuidance uses optimistic done state even on API error — user sees feedback regardless of transient failures
- diagnosisCategory prop maps to tx.tax_category since verification diagnosis categories mirror classification categories

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added React.Fragment with key for expandable transaction rows**
- **Found during:** Task 2 (wiring InlineGuidance into transactions table)
- **Issue:** Plan specified expanding rows in tbody; React requires Fragment key when used in .map() — plain `<>` produces key warning
- **Fix:** Used `<React.Fragment key={tx.id}>` instead of keyless `<>` and added `import React` to the imports
- **Files modified:** web/app/dashboard/transactions/page.tsx
- **Verification:** TypeScript compiles clean; no new errors introduced
- **Committed in:** bcfd57b (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical / correctness)
**Impact on plan:** Minor correctness fix required by React's key reconciliation rules. No scope creep.

## Issues Encountered

- Pre-existing TypeScript errors in `app/auth/page.tsx` (3 errors in NEAR wallet signing types) — out of scope, not introduced by this plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- OnboardingBanner and InlineGuidance components are ready and integrated
- Banners are dismissible and persist across sessions via the preferences API built in Plan 12-01
- Human verification checkpoint (Task 3) approved — banners confirmed to render correctly and dismissal persists on refresh

---
*Phase: 12-user-onboarding*
*Completed: 2026-03-16*
