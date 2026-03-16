---
phase: 12-user-onboarding
verified: 2026-03-16T16:00:00Z
status: passed
score: 26/26 must-haves verified
re_verification: false
---

# Phase 12: User Onboarding Verification Report

**Phase Goal:** Guide new users through setup — wallets, exchanges, reports, validation,
reconciliation, warning/error resolution. Backend preferences API + wallet suggestions,
5-step onboarding wizard with smart resume, contextual help banners on dashboard pages,
inline guidance for verification issues.

**Verified:** 2026-03-16
**Status:** passed
**Re-verification:** No — initial verification

---

## Requirements Coverage Note

The plan frontmatter references `ONBOARD-01` through `ONBOARD-07` across all three
plans. These IDs do not appear in `.planning/REQUIREMENTS.md` and have no traceability
table entry. Phase 12 was added as a UX experience layer after the main requirements
document was finalized. The ROADMAP overview row for phase 12 (`| 12 | 3/3 | Complete |
2026-03-16 | 2 days |`) has no name, goal text, or requirements column — the phase
detail section was never written into ROADMAP.md.

**Assessment:** The ONBOARD-xx IDs are self-contained within phase 12's own plan files
and are internally consistent. There are no orphaned requirements in REQUIREMENTS.md
pointing to phase 12. The absence of formal requirement entries in REQUIREMENTS.md is a
documentation gap, not a blocking implementation gap. All stated must-haves were
verified against the actual code.

---

## Goal Achievement

### Plan 12-01: Backend Foundation

**Observable Truths**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /api/preferences returns onboarding_completed_at and dismissed_banners | VERIFIED | `api/routers/preferences.py` line 37: `@router.get("")` queries both columns, returns typed dict with NULL handling |
| 2 | POST /api/preferences/complete-onboarding sets onboarding_completed_at idempotently | VERIFIED | Line 100: `COALESCE(onboarding_completed_at, NOW())` — second call leaves timestamp unchanged |
| 3 | PATCH /api/preferences/dismiss-banner merges banner key into dismissed_banners JSONB | VERIFIED | Line 154: `COALESCE(dismissed_banners, '{}') \|\| %s::jsonb` — atomic NULL-safe merge |
| 4 | GET /api/wallets/suggestions returns discovered linked wallets from WalletGraph | VERIFIED | `api/routers/wallets.py` line 354: `@router.get("/suggestions")` calls `graph.suggest_wallet_discovery(user_id, min_transfers=3)` |
| 5 | Existing users with wallets but NULL onboarding_completed_at are not broken | VERIFIED | GET endpoint returns `{}` for NULL dismissed_banners; columns use `ADD COLUMN IF NOT EXISTS` |

**Score: 5/5**

### Plan 12-01: Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `db/migrations/versions/010_onboarding_columns.py` | VERIFIED | 26 lines, revision="010", down_revision="009", IF NOT EXISTS idempotency, upgrade + downgrade |
| `api/routers/preferences.py` | VERIFIED | 176 lines (well above min), 3 endpoints, DismissBannerRequest model, run_in_threadpool, pool.getconn/putconn |
| `tests/test_api_preferences.py` | VERIFIED | 202 lines, 6 tests — all pass (confirmed: `6 passed` in pytest run) |

### Plan 12-01: Key Links

| From | To | Via | Status |
|------|----|-----|--------|
| `api/routers/preferences.py` | users table | SELECT/UPDATE onboarding_completed_at, dismissed_banners | WIRED — lines 53–56, 99–105, 151–158 all reference both columns directly |
| `api/routers/wallets.py` | engine/wallet_graph.py | WalletGraph.suggest_wallet_discovery() | WIRED — line 374: `graph.suggest_wallet_discovery(user_id, min_transfers=3)` |
| `api/main.py` | api/routers/preferences.py | include_router(preferences_router) | WIRED — `api/routers/__init__.py` line 24 exports `preferences_router`; `api/main.py` line 108 mounts it |

---

### Plan 12-02: Onboarding Wizard

**Observable Truths**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | New users (no wallets, onboarding_completed_at NULL) redirected to /onboarding | VERIFIED | `web/app/dashboard/layout.tsx` lines 44–60: two-part guard checks prefs then wallets; redirects only when both conditions true |
| 2 | Existing users with wallets never redirected to onboarding | VERIFIED | Line 63: explicit "Existing user with wallets but NULL onboarding_completed_at — allow dashboard access" |
| 3 | Wizard has 5 steps: Welcome, Add Wallets, Import Exchanges, Processing, Review | VERIFIED | `web/app/onboarding/page.tsx`: all 5 step components imported and rendered conditionally |
| 4 | Every step has a 'skip to dashboard' link that marks onboarding complete | VERIFIED | All 5 step components accept `onSkip` prop; `handleSkipToDashboard` in page.tsx calls POST /api/preferences/complete-onboarding then routes to /dashboard |
| 5 | Users can add multiple wallets in Step 2 before proceeding | VERIFIED | `web/app/onboarding/steps/wallets.tsx`: `pendingWallets` array state, add/remove UI, Continue POSTs sequentially |
| 6 | Step 2 shows contextual help per chain (format, where to find, what data pulled) | VERIFIED | `CHAIN_HELP` record in wallets.tsx maps NEAR, ETH, Polygon, Cronos, Optimism to format/whereToFind/whatsPulled/example |
| 7 | Step 3 is optional (skip available) with file upload zone | VERIFIED | `import.tsx`: drag-drop zone, `handleDrop`/`handleFileInput`, "Skip this step" button calls `onNext()` |
| 8 | Step 4 shows pipeline progress bar and auto-advances to Step 5 on completion | VERIFIED | `processing.tsx`: SyncStatus rendered, polls /api/jobs/active every 3s, `setTimeout(onNext, 1500)` on pipeline done |
| 9 | Step 4 surfaces discovered linked wallets with Add/Not Mine buttons | VERIFIED | `processing.tsx` lines 171–224: fetches /api/wallets/suggestions after classifying stage; Add (POST /api/wallets) and Not Mine (local dismiss) buttons |
| 10 | Step 5 shows import summary and orientation links, Go to Dashboard marks complete | VERIFIED | `review.tsx`: wallet/tx count stats, ORIENTATION_LINKS array, handleGoToDashboard calls POST /api/preferences/complete-onboarding |
| 11 | Smart resume routes returning users to correct step based on data state | VERIFIED | `page.tsx` lines 40–89: Promise.all(wallets, jobs, prefs) with branching logic for steps 1, 3, 4, 5 |

**Score: 11/11**

### Plan 12-02: Required Artifacts

| Artifact | Min Lines | Actual | Status |
|----------|-----------|--------|--------|
| `web/app/onboarding/layout.tsx` | 15 | 71 | VERIFIED — auth check, completed-onboarding redirect, full-page dark layout |
| `web/app/onboarding/page.tsx` | 40 | 186 | VERIFIED — smart resume Promise.all, 5-step orchestration, step indicator |
| `web/app/onboarding/steps/welcome.tsx` | 20 | 61 | VERIFIED — Get Started + skip, feature list, substantive content |
| `web/app/onboarding/steps/wallets.tsx` | 80 | 264 | VERIFIED — multi-wallet, chain help panel, sequential POST, error handling |
| `web/app/onboarding/steps/import.tsx` | 40 | 130 (approx) | VERIFIED — drag-drop, FormData upload, exchange badges |
| `web/app/onboarding/steps/processing.tsx` | 60 | 238 | VERIFIED — SyncStatus, 3s polling, wallet discovery suggestions |
| `web/app/onboarding/steps/review.tsx` | 40 | 164 | VERIFIED — stats, expectations note, orientation links, Go to Dashboard |

### Plan 12-02: Key Links

| From | To | Via | Status |
|------|----|-----|--------|
| `web/app/dashboard/layout.tsx` | /api/preferences | useEffect onboarding check | WIRED — line 45: `apiClient.get<PreferencesResponse>('/api/preferences')` |
| `web/app/onboarding/page.tsx` | /api/wallets, /api/jobs/active, /api/preferences | Promise.all smart resume | WIRED — lines 42–46: `Promise.all([...'/api/wallets'...'/api/jobs/active'...'/api/preferences'...])` |
| `web/app/onboarding/steps/processing.tsx` | web/components/sync-status.tsx | SyncStatus with onComplete | WIRED — line 166: `<SyncStatus />` rendered; SyncStatus has `onComplete` prop (added in plan 12-02 Task 2) |
| `web/app/onboarding/steps/wallets.tsx` | /api/wallets | POST for each added wallet | WIRED — line 91: `apiClient.post('/api/wallets', {...})` in sequential loop |
| `web/app/onboarding/steps/review.tsx` | /api/preferences/complete-onboarding | POST on Go to Dashboard | WIRED — line 50: `apiClient.post('/api/preferences/complete-onboarding')` |

**SyncStatus onComplete verification:**
`web/components/sync-status.tsx` lines 42, 55, 108–127: `onComplete?: () => void` prop added, `prevDoneRef` tracks prior done state, `onCompleteRef.current?.()` fires exactly once on transition.

---

### Plan 12-03: Banners and Inline Guidance

**Observable Truths**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Reports page shows a dismissible contextual banner | VERIFIED | `web/app/dashboard/reports/page.tsx` line 5: imports `OnboardingBanner`; line 389: renders with `bannerKey="reports_page"` |
| 2 | Transactions page shows a dismissible banner | VERIFIED | `transactions/page.tsx` line 5: imports OnboardingBanner; line 266: renders with `bannerKey="transactions_page"` |
| 3 | Wallets page shows a dismissible banner | VERIFIED | `wallets/page.tsx` line 4: imports OnboardingBanner; line 114: renders with `bannerKey="wallets_page"` |
| 4 | Main dashboard page shows a dismissible banner | VERIFIED | `dashboard/page.tsx` line 5: imports OnboardingBanner; line 30: renders with `bannerKey="verification_page"` |
| 5 | Banner dismissal persists via PATCH /api/preferences/dismiss-banner | VERIFIED | `onboarding-banner.tsx` line 48: `apiClient.patch('/api/preferences/dismiss-banner', { banner_key: bannerKey })` on X click |
| 6 | Dismissed banners never reappear | VERIFIED | On mount GET /api/preferences checks `dismissed_banners[bannerKey] === true`; renders null if dismissed |
| 7 | Verification issues display inline plain-English explanations per diagnosis category | VERIFIED | `inline-guidance.tsx`: `CATEGORY_GUIDANCE` record maps all 5 categories (missing_staking_rewards, unindexed_period, classification_error, duplicates, uncounted_fees) to explanations |
| 8 | Inline guidance shows action buttons per issue type | VERIFIED | Each category maps to resync/resolve/navigate action with label; button calls POST /api/verification/resync/{id} or /resolve/{id} |
| 9 | Transactions page renders InlineGuidance for needs_review items with expandable explanation | VERIFIED | `transactions/page.tsx` line 6: imports InlineGuidance; line 117: `expandedTxId` state; line 525: click toggles; line 576–582: `<InlineGuidance>` rendered for needs_review rows |

**Score: 9/9**

### Plan 12-03: Required Artifacts

| Artifact | Min Lines | Actual | Status |
|----------|-----------|--------|--------|
| `web/components/onboarding-banner.tsx` | 40 | 77 | VERIFIED — preferences check, dismiss PATCH, fail-open, X button |
| `web/components/inline-guidance.tsx` | 50 | 110 | VERIFIED — 5 category mappings, resync/resolve/navigate actions, done state |

### Plan 12-03: Key Links

| From | To | Via | Status |
|------|----|-----|--------|
| `web/components/onboarding-banner.tsx` | /api/preferences | GET dismissed_banners + PATCH dismiss-banner | WIRED — lines 25–36 GET on mount, line 48 PATCH on dismiss |
| `web/components/inline-guidance.tsx` | /api/verification/resync, /api/verification/resolve | Action button POST calls | WIRED — lines 73–76: POST `/api/verification/resync/${verificationId}` and `/api/verification/resolve/${verificationId}` |
| `web/app/dashboard/reports/page.tsx` | web/components/onboarding-banner.tsx | OnboardingBanner with bannerKey='reports_page' | WIRED — import confirmed + rendered at line 389 |
| `web/app/dashboard/page.tsx` | web/components/onboarding-banner.tsx | OnboardingBanner with bannerKey='verification_page' | WIRED — import confirmed + rendered at line 30 |
| `web/app/dashboard/transactions/page.tsx` | web/components/inline-guidance.tsx | InlineGuidance for needs_review transaction rows | WIRED — import at line 6, expandedTxId toggle at line 525, render at line 576 |

---

## Anti-Patterns Scan

No stubs, placeholders, empty implementations, or TODO comments found in any phase 12
files. All components have substantive implementations.

Pre-existing TypeScript errors noted in SUMMARY documents (3 errors in
`web/app/auth/page.tsx` related to NEAR wallet signing types) are unrelated to phase 12
and were present before this phase began. Phase 12 introduced no new TypeScript errors.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

---

## Test Results

```
6 passed, 2 warnings in 0.36s
```

All 6 preferences API tests pass: GET preferences (with data, with NULL dismissed_banners),
POST complete-onboarding (sets timestamp), POST complete-onboarding idempotency, PATCH
dismiss-banner (merges key), PATCH dismiss-banner with missing banner_key (returns 422).

Ruff lint: clean on all Python files (`api/routers/preferences.py`,
`db/migrations/versions/010_onboarding_columns.py`, `api/routers/wallets.py`).

---

## Requirements Coverage

The ONBOARD-xx IDs referenced in plan frontmatter are phase-internal identifiers not
registered in REQUIREMENTS.md. No orphaned requirements in REQUIREMENTS.md point to
phase 12. The phase 12 row in ROADMAP.md overview is incomplete (no name or goal text),
but this is a documentation-only gap.

| Req ID | Plan | Implementation Evidence | Status |
|--------|------|------------------------|--------|
| ONBOARD-01 | 12-01, 12-02 | Migration 010 + preferences API + dashboard redirect guard | SATISFIED |
| ONBOARD-02 | 12-02 | 5-step wizard at /onboarding, all step components present | SATISFIED |
| ONBOARD-03 | 12-02 | Smart resume page.tsx + step orchestration | SATISFIED |
| ONBOARD-04 | 12-02, 12-03 | Skip-to-dashboard on all steps + banner dismiss system | SATISFIED |
| ONBOARD-05 | 12-01, 12-03 | dismissed_banners JSONB column + PATCH endpoint + OnboardingBanner component | SATISFIED |
| ONBOARD-06 | 12-01, 12-03 | GET /api/preferences returns dismissed_banners; banners on 4 pages | SATISFIED |
| ONBOARD-07 | 12-03 | InlineGuidance component + wired into transactions page for needs_review rows | SATISFIED |

**Documentation gap (non-blocking):** ONBOARD-01 through ONBOARD-07 have no entries in
REQUIREMENTS.md and phase 12 has no detail section in ROADMAP.md. These IDs exist only
within the phase 12 plan files. Future work: add these to REQUIREMENTS.md traceability
table and write a phase 12 detail section in ROADMAP.md.

---

## Human Verification Required

Two flows require human testing to confirm end-to-end UX behavior (both were approved
during checkpoint tasks in the original plans, but are documented here for completeness):

### 1. New User Onboarding Redirect Flow

**Test:** Create or simulate a user with no wallets and NULL onboarding_completed_at.
Navigate to /dashboard.
**Expected:** Redirect to /onboarding. Complete wizard through all 5 steps. After "Go to
Dashboard" in Step 5, land on /dashboard and never see onboarding again on subsequent
visits.
**Why human:** Dashboard-to-onboarding redirect loop prevention requires runtime
rendering with auth state. Smart resume step routing depends on live API responses.

### 2. Banner Dismissal Persistence

**Test:** Log in as user who has not dismissed any banners. Navigate to /dashboard/reports.
Verify blue info banner appears. Click X. Refresh page.
**Expected:** Banner stays dismissed after refresh (persisted via PATCH to
/api/preferences/dismiss-banner and stored in dismissed_banners JSONB).
**Why human:** Requires live browser session to confirm LocalState + API + DB round-trip.

---

## Verification Summary

All 26 observable truths (5 + 11 + 9 + 1 SyncStatus callback) verified against actual
code. Every artifact exists and is substantive. All key links are wired — no orphaned
components, no stub implementations, no missing connections. Tests pass. Lint is clean.

Phase goal is achieved: new users have a guided setup experience (wizard + smart resume),
existing dashboard pages have dismissible contextual help banners (backed by JSONB
persistence), and verification issues have plain-English inline guidance with one-click
resolution actions.

The only gap is documentation-level: ONBOARD-xx requirement IDs are not registered in
REQUIREMENTS.md and the ROADMAP.md phase 12 detail section was never written. This does
not affect the working implementation.

---

_Verified: 2026-03-16_
_Verifier: Claude (gsd-verifier)_
