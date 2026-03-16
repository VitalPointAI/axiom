# Phase 12: User Onboarding - Research

**Researched:** 2026-03-16
**Domain:** Next.js App Router wizard UI, FastAPI preferences endpoints, Alembic migration, React polling
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Step-by-step wizard** triggered on first login (full-page, not modal)
- Trigger condition: `onboarding_completed_at IS NULL` AND no wallets AND no exchange imports for the user
- **5 steps:** Welcome -> Add Wallets -> Import Exchanges -> Processing -> Review & Next Steps
- **Skip/offramp:** "I know what I'm doing — skip to dashboard" link on every step. Marks `onboarding_completed_at` and redirects to dashboard
- After completion or skip, wizard never shows again
- **No re-access option** — all wizard actions are available on existing pages (Wallets, Import, Reports)
- Users can **add multiple wallets** before proceeding — each appears as a card showing chain + address with remove button
- **Contextual help per chain** when user selects NEAR/ETH/etc.: help panel with example address format, where to find address, what data will be pulled
- "Add another" button + "Continue" button — pipeline starts for all wallets at once on Continue
- **Discovered wallet surfacing** during Step 4: if WalletGraph discovers linked addresses, surface inline with Add/Not Mine buttons
- **Generic upload with auto-detect** — file upload zone with list of supported exchanges (Coinbase, Crypto.com, Wealthsimple, Uphold, Coinsquare)
- Step 3 is **optional** — user can skip if no exchange data
- Step 4 shows the existing pipeline progress bar (auto-chain: index -> classify -> ACB -> verify), auto-advances when pipeline completes
- **Summary + quick orientation** in Step 5 with links to each dashboard page
- "Go to Dashboard" button marks `onboarding_completed_at` and navigates to dashboard
- **DB column:** `onboarding_completed_at TIMESTAMPTZ NULL` on users table (new Alembic migration)
- **Smart resume:** no step tracking — on return, check data state and route to appropriate step
- **JSONB preferences:** `dismissed_banners JSONB DEFAULT '{}'` on users table (same migration)
- **Contextual banners on each page:** dismissible info banners shown on first visit to Reports, Transactions, Wallets, Verification pages
- Dismissal tracked in `dismissed_banners` JSONB column
- **Inline guidance per warning/error type:** each `needs_review` item type has plain-English explanation + suggested action inline
- Action buttons where applicable: "Mark Reviewed", "Re-sync", "Learn More"

### Claude's Discretion
- Wizard step component implementation (layout, transitions, animations)
- Exact help text content per chain and per banner
- Warning/error explanation copy and categorization
- Processing step polling interval and progress display details
- How to integrate discovered wallet suggestions with WalletGraph data
- Mobile responsiveness of wizard steps

### Deferred Ideas (OUT OF SCOPE)
- Interactive product tour with highlighting/spotlight on UI elements (v2)
- Video tutorials embedded in help sections (content creation task)
- In-app chat/support widget for stuck users (v2)
- Onboarding analytics (funnel tracking, drop-off points) — future milestone
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ONBOARD-01 | Post-signup onboarding flow that walks users through initial setup | 5-step wizard at `/onboarding/*`, triggered by `onboarding_completed_at IS NULL` check in dashboard layout |
| ONBOARD-02 | Guided wallet addition (NEAR, EVM chains) with explanations | Reuse `AddWalletModal` logic from wallets page; chain-contextual help panel per chain ID |
| ONBOARD-03 | Guided exchange connection (CSV upload, AI auto-detect already built) | Reuse import page's drag-drop zone and `POST /api/upload-file` endpoint |
| ONBOARD-04 | Report overview — explain what reports are generated and how to read them | Step 5 orientation section + contextual banner on reports page |
| ONBOARD-05 | Validation walkthrough — show users how to review verification results | Step 5 link + contextual banner on verification page |
| ONBOARD-06 | Reconciliation guide — explain discrepancies and how to resolve them | Inline guidance per `diagnosis_category` in verification issues list |
| ONBOARD-07 | Warning/error resolution — actionable guidance for fixing flagged items | `_CATEGORY_META` dict already maps category to (severity, description, action); extend with plain-English copy |
</phase_requirements>

---

## Summary

Phase 12 is a pure UI/UX and data layer phase — no new pipeline logic or business rules. It builds a 5-step onboarding wizard at `/onboarding/` (new Next.js App Router directory), adds two columns to the users table via Alembic migration 009, creates a preferences API endpoint for banner dismissal and onboarding completion, adds dismissible contextual banners to four existing dashboard pages, and wires inline guidance to the existing verification issues display.

The project already has all building blocks: the `SyncStatus` component (Step 4 progress bar), the `AddWalletModal` logic (Step 2 wallet addition), the import wizard's drag-drop zone (Step 3 file upload), `WalletGraph.suggest_wallet_discovery()` (Step 4 wallet suggestions), and `_CATEGORY_META` in the verification router (ONBOARD-07 inline guidance). This phase assembles them into a cohesive first-run experience rather than building new core functionality.

The smart resume logic — routing returning users to the correct step by checking data state — is the most nuanced piece. It avoids storing step numbers in the DB; instead it examines `wallets` count, `file_imports` count, and `indexing_jobs` status to determine where to land.

**Primary recommendation:** Treat this as a composition phase. Extract sub-components from existing pages, assemble them into the wizard, add the preferences API, and add banners/inline guidance to existing pages. No new backend pipeline work needed.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js App Router | 16.x (project uses `^16.1.6`) | Wizard pages at `/onboarding/` | Already in use project-wide |
| React | 19.x | Component composition, `useState`/`useEffect` | Already in use |
| Tailwind CSS | 4.x | Styling wizard steps and banners | Already in use throughout |
| shadcn/ui primitives | local `web/components/ui/` | `Button`, `Card`, `Badge`, `Input`, `Label` | Already scaffolded (badge.tsx, button.tsx, card.tsx, input.tsx, label.tsx) |
| lucide-react | 0.469.0 | Icons: `CheckCircle`, `ChevronRight`, `X`, `Info`, `AlertTriangle` | Already in use |
| apiClient (`web/lib/api.ts`) | project | FastAPI calls with `credentials: include` | Standard fetch wrapper for all API calls |
| FastAPI | project | Preferences endpoints | All API routes already use FastAPI |
| Alembic | project | Migration 009 for `onboarding_completed_at` + `dismissed_banners` | All DB changes use Alembic |
| psycopg2 | project | DB queries in preferences router | Standard DB access pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `useRouter` (Next.js) | same | Navigate between wizard steps and to `/dashboard` | Step transitions and completion redirect |
| `useAuth` (`web/components/auth-provider.tsx`) | project | Get `user.id` for API calls | All wizard steps need user context |
| `run_in_threadpool` (FastAPI) | same | Wrap psycopg2 calls in async routes | All new API endpoints (same pattern as existing routers) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| URL-based step routing (`/onboarding/step-2`) | Single-page `useState` step | URL routing provides back-button support and deep links; but CONTEXT.md doesn't require back-button in wizard; single `useState` is simpler and matches import wizard pattern already used |
| Step tracking DB column | Smart resume from data state | DB column wastes a write per step; data state is always accurate and avoids sync issues |
| localStorage for banner dismissal | JSONB on users table | localStorage breaks across devices; JSONB survives device changes as required by CONTEXT.md |

**Installation:**
```bash
# No new packages required — all dependencies already installed
```

## Architecture Patterns

### Recommended Project Structure
```
web/app/onboarding/
├── layout.tsx               # Full-page layout (no sidebar), onboarding route guard
├── page.tsx                 # Smart resume logic — redirects to correct step
└── steps/
    ├── welcome.tsx          # Step 1: Welcome + skip link
    ├── wallets.tsx          # Step 2: Add wallets with chain help panels
    ├── import.tsx           # Step 3: File upload (optional, skip available)
    ├── processing.tsx       # Step 4: SyncStatus + wallet discovery suggestions
    └── review.tsx           # Step 5: Summary + orientation + "Go to Dashboard"

api/routers/
└── preferences.py           # New router: onboarding completion + banner dismissal

db/migrations/versions/
└── 009_onboarding_columns.py  # onboarding_completed_at + dismissed_banners

web/components/
├── onboarding-banner.tsx    # Reusable dismissible banner component
└── inline-guidance.tsx      # Inline warning/error explanation + action buttons
```

### Pattern 1: Onboarding Redirect Guard in Dashboard Layout

**What:** Check `onboarding_completed_at` in dashboard layout before rendering; redirect to `/onboarding` if null and no wallets/imports.
**When to use:** Must fire on every dashboard load for first-time users.

**Approach:** Add a `useEffect` to `web/app/dashboard/layout.tsx` that calls a new `GET /api/preferences` endpoint (returns `onboarding_completed_at`, `dismissed_banners`), and redirects to `/onboarding` if null and user has no wallets.

```typescript
// In web/app/dashboard/layout.tsx — add after existing auth check
useEffect(() => {
  if (!user || isLoading) return;
  const checkOnboarding = async () => {
    try {
      const prefs = await apiClient.get<{ onboarding_completed_at: string | null }>('/api/preferences');
      if (!prefs.onboarding_completed_at) {
        // Check if user has any wallets
        const walletData = await apiClient.get<{ wallets: unknown[] }>('/api/wallets');
        if (walletData.wallets.length === 0) {
          router.replace('/onboarding');
        }
      }
    } catch (e) {
      // Non-blocking — don't interrupt dashboard if preferences check fails
    }
  };
  checkOnboarding();
}, [user, isLoading]);
```

**Note:** Two-API-call approach (prefs then wallets) follows existing project patterns. If prefs endpoint returns 404 for users predating the column, treat as `null` (redirect to onboarding).

### Pattern 2: Smart Resume in Onboarding page.tsx

**What:** Route returning users mid-onboarding to the appropriate step based on data state.
**When to use:** User added wallets then closed browser; smart resume lands them at Step 4 (Processing).

```typescript
// web/app/onboarding/page.tsx
// Check: wallets count, file_imports count, active jobs
// - 0 wallets, 0 imports -> Step 1 (Welcome)
// - Has wallets, no active jobs, no imports -> Step 3 (Import) or 4 (Processing)
// - Has active jobs -> Step 4 (Processing)
// - All jobs done -> Step 5 (Review)
```

**Implementation note:** Call `/api/wallets`, `/api/jobs/active`, and `/api/preferences` in parallel (`Promise.all`) to minimize latency on resume.

### Pattern 3: Dismissible Banner Component

**What:** Single reusable `<OnboardingBanner>` component used on Reports, Transactions, Wallets, and Verification pages.
**When to use:** Once per page, checks `dismissed_banners` from preferences API, shows if not dismissed.

```typescript
// web/components/onboarding-banner.tsx
// Props: bannerKey (e.g., 'reports_page'), title, description
// On mount: GET /api/preferences -> check dismissed_banners[bannerKey]
// On dismiss: PATCH /api/preferences { dismiss_banner: bannerKey }
// Once dismissed, never re-renders (local state + DB update)
```

**Key pattern:** Cache preferences in a React context or single fetch per page load. Do not call `/api/preferences` once per banner if multiple banners could appear on a page (though each page has at most one).

### Pattern 4: Preferences API Endpoints

**What:** New `api/routers/preferences.py` with three endpoints.

```python
# GET /api/preferences — return onboarding_completed_at, dismissed_banners
# POST /api/preferences/complete-onboarding — set onboarding_completed_at = NOW()
# PATCH /api/preferences/dismiss-banner — add key to dismissed_banners JSONB
```

All use `get_effective_user` (accountant delegation consistent with other routers) and `run_in_threadpool` for psycopg2 calls.

**JSONB update pattern** (PostgreSQL jsonb_set):
```sql
UPDATE users
SET dismissed_banners = dismissed_banners || %s::jsonb
WHERE id = %s
```
Pass `json.dumps({banner_key: True})` as the parameter. This merges the key into existing JSONB without overwriting other dismissals.

### Pattern 5: Inline Guidance for Warning/Error Items

**What:** Extend the existing verification issues display with per-category plain-English explanations and action buttons.
**When to use:** Any `needs_review` item surfaced in the Verification dashboard.

The `_CATEGORY_META` dict in `api/routers/verification.py` already maps `diagnosis_category` to `(severity, description, suggested_action)`. The frontend receives these as part of `GET /api/verification/issues` response. The inline guidance component just needs to render them with better copy and action buttons.

**Action buttons mapping:**
- `missing_staking_rewards` -> "Re-sync Staking" -> `POST /api/verification/resync/{id}`
- `unindexed_period` -> "Re-index Wallet" -> `POST /api/verification/resync/{id}`
- `classification_error` -> "Review Transaction" -> link to `/dashboard/transactions?needs_review=true`
- `duplicates` -> "Mark Reviewed" -> `POST /api/verification/resolve/{id}`
- `uncounted_fees` -> "Mark Reviewed" -> `POST /api/verification/resolve/{id}`

### Pattern 6: Wallet Discovery in Step 4

**What:** After pipeline starts, query `GET /api/wallets/suggestions` to get WalletGraph results and show "We found wallets that might be yours" cards.

**New endpoint needed:** `GET /api/wallets/suggestions` wraps `WalletGraph.suggest_wallet_discovery(user_id, min_transfers=3)`. Returns list of `{address, chain, transfer_count, related_to}`.

**UI behavior:** Only show suggestions panel if response is non-empty. Each card: address (truncated), chain badge, transfer count context ("47 transfers from vitalpointai.near"), "Add" button (calls `POST /api/wallets` with the address), "Not Mine" button (hides card locally, no DB write — they can always add manually later).

### Anti-Patterns to Avoid

- **Re-fetching preferences on every render:** Use React state or a lightweight context. One fetch per page load is sufficient.
- **Storing wizard step in DB:** The smart resume from data state is more reliable and requires no write per step.
- **Blocking dashboard on preferences check:** The onboarding redirect check should be fire-and-forget — if it fails, log and continue (don't prevent dashboard access for existing users).
- **Showing banners on mobile in intrusive positions:** Banners should be below page header, dismissible with a single tap, and not block main content.
- **Adding onboarding redirect to the onboarding route itself:** Would create a redirect loop. The guard lives only in `dashboard/layout.tsx`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pipeline progress in Step 4 | Custom polling logic | `SyncStatus` component (`web/components/sync-status.tsx`) | Already polls `/api/jobs/active`, handles done state, stops polling automatically |
| Wallet addition form in Step 2 | New form component | Extract `AddWalletModal` from `web/app/dashboard/wallets/page.tsx` | Chain selector + address input + POST /api/wallets already built and tested |
| File upload zone in Step 3 | New drag-drop component | Extract upload zone from `web/app/dashboard/import/page.tsx` | Drag/drop, file list, parse feedback already implemented |
| JSONB merge update | Custom JSON string building | PostgreSQL `||` operator (`dismissed_banners || %s::jsonb`) | Atomic merge without race conditions, no full column rewrite |
| Wallet suggestion queries | New graph traversal logic | `WalletGraph.suggest_wallet_discovery()` in `engine/wallet_graph.py` | Already returns `{address, chain, transfer_count, related_to}` with confidence scores |
| Category descriptions for inline guidance | New metadata dict | `_CATEGORY_META` in `api/routers/verification.py` | Already maps all 5 diagnosis categories to severity + description + action |

**Key insight:** This phase is 80% composition of existing pieces. Custom implementation is limited to: the wizard shell/navigation, smart resume routing logic, the `preferences.py` router, the `OnboardingBanner` component, and Alembic migration 009.

## Common Pitfalls

### Pitfall 1: Redirect Loop Between Dashboard and Onboarding
**What goes wrong:** Onboarding pages import dashboard layout; dashboard layout redirects to onboarding; infinite redirect loop.
**Why it happens:** Guard in dashboard/layout.tsx triggers for `/onboarding` route if not scoped correctly.
**How to avoid:** Guard checks `pathname.startsWith('/dashboard')` before redirecting, OR onboarding lives outside the dashboard layout tree entirely (use `web/app/onboarding/layout.tsx` separate from `web/app/dashboard/layout.tsx`).
**Warning signs:** Browser shows "too many redirects" error on first load.

### Pitfall 2: Preferences Check Blocking Dashboard for Existing Users
**What goes wrong:** Existing users (many wallets, onboarding_completed_at NULL because column is new) get redirected to onboarding on every login.
**Why it happens:** New migration adds column with NULL default — all existing users start as NULL.
**How to avoid:** Two-part trigger condition: `onboarding_completed_at IS NULL` AND `wallets count = 0`. Existing users with wallets are never redirected. Migration 009 does NOT backfill `onboarding_completed_at` for existing users — that's intentional (no data loss), but the wallet count guard is essential.
**Warning signs:** Test with a user who has wallets and `onboarding_completed_at = NULL` — they should reach dashboard normally.

### Pitfall 3: SyncStatus Poll Not Stopping After Pipeline Completion
**What goes wrong:** Step 4 stays stuck showing "Verifying 100%" indefinitely without auto-advancing to Step 5.
**Why it happens:** `SyncStatus` stops polling when `pct >= 100` or `stage === 'done'` — parent wizard must observe that state and trigger step advance.
**How to avoid:** Pass an `onComplete` callback prop to `SyncStatus` (or wrap it and observe the status state), triggering auto-advance to Step 5. The existing `SyncStatus` component stops polling but does not emit a completion event — the wrapper needs to detect `isDone` state transition.
**Warning signs:** User stays on Step 4 after pipeline finishes; no auto-advance.

### Pitfall 4: JSONB Dismissed Banners Null Dereference
**What goes wrong:** `dismissed_banners->'reports_page'` returns NULL for users without that key; frontend throws on `prefs.dismissed_banners.reports_page`.
**Why it happens:** Default `'{}'` covers new rows but `->` operator returns `NULL` for missing keys.
**How to avoid:** Frontend uses `prefs.dismissed_banners?.['reports_page'] === true` (optional chaining). Backend PATCH endpoint uses `COALESCE(dismissed_banners, '{}'::jsonb) || %s::jsonb` to handle any remaining NULLs safely.
**Warning signs:** Banner shows on every page load for users who dismissed it.

### Pitfall 5: Wallet Suggestions API Called Before Pipeline Has Run
**What goes wrong:** `GET /api/wallets/suggestions` returns empty list (no transactions indexed yet) — blank suggestions panel appears briefly.
**Why it happens:** Step 4 starts pipeline and simultaneously queries suggestions; no data exists yet.
**How to avoid:** Only query suggestions after pipeline shows at least "Classifying" stage (pct > 45%). The `SyncStatus` stage/pct data can gate the suggestions query. Alternatively, only surface suggestions when pipeline reaches "done".
**Warning signs:** Empty "We found wallets" panel flashes at start of Step 4.

### Pitfall 6: Alembic Migration Idempotency
**What goes wrong:** Migration 009 fails on environments where `onboarding_completed_at` was manually added.
**Why it happens:** `ALTER TABLE ADD COLUMN` without `IF NOT EXISTS` raises `DuplicateColumn` in PostgreSQL.
**How to avoid:** Use `ADD COLUMN IF NOT EXISTS` pattern (same as migration 006 for auth columns).
**Warning signs:** `alembic upgrade head` fails with `column already exists`.

### Pitfall 7: `POST /api/preferences/complete-onboarding` Double-Call Race
**What goes wrong:** "Go to Dashboard" button fires twice (double-click); second call errors or logs duplicate audit event.
**Why it happens:** No guard on button re-click.
**How to avoid:** Use `UPDATE users SET onboarding_completed_at = COALESCE(onboarding_completed_at, NOW()) WHERE id = %s` — idempotent; does not overwrite an already-set timestamp. Frontend disables button after first click (standard `isLoading` state pattern used throughout).

## Code Examples

Verified patterns from existing project code:

### Alembic Migration Pattern (from migration 006)
```python
# db/migrations/versions/009_onboarding_columns.py
# Source: existing migration 006 pattern
def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS dismissed_banners JSONB DEFAULT '{}'
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE users
            DROP COLUMN IF EXISTS onboarding_completed_at,
            DROP COLUMN IF EXISTS dismissed_banners
    """)
```

### FastAPI Preferences Router Pattern (from existing routers)
```python
# api/routers/preferences.py
# Source: api/routers/verification.py pattern for Depends + run_in_threadpool
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from api.dependencies import get_effective_user, get_pool_dep
import json

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

@router.get("")
async def get_preferences(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    def _fetch(pool):
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT onboarding_completed_at, dismissed_banners FROM users WHERE id = %s",
                (user["user_id"],),
            )
            row = cur.fetchone()
            return {
                "onboarding_completed_at": row[0].isoformat() if row[0] else None,
                "dismissed_banners": row[1] or {},
            }
        finally:
            pool.putconn(conn)
    return await run_in_threadpool(_fetch, pool)
```

### JSONB Banner Dismissal Update
```python
# Source: PostgreSQL || operator for JSONB merge
cur.execute(
    """
    UPDATE users
    SET dismissed_banners = COALESCE(dismissed_banners, '{}'::jsonb) || %s::jsonb
    WHERE id = %s
    """,
    (json.dumps({banner_key: True}), user["user_id"]),
)
conn.commit()
```

### Smart Resume Logic (onboarding page.tsx)
```typescript
// Source: existing /api/wallets and /api/jobs/active endpoints
// (apiClient pattern from web/lib/api.ts)
const [wallets, jobs, prefs] = await Promise.all([
  apiClient.get<{ wallets: WalletData[] }>('/api/wallets'),
  apiClient.get<ActiveJobsResponse>('/api/jobs/active'),
  apiClient.get<PreferencesResponse>('/api/preferences'),
]);

if (prefs.onboarding_completed_at) {
  router.replace('/dashboard');
  return;
}

const hasWallets = wallets.wallets.length > 0;
const hasActiveJobs = jobs.jobs.length > 0;
// Route to appropriate step based on state
if (!hasWallets) setStep(1);           // Welcome
else if (hasActiveJobs) setStep(4);    // Processing
else setStep(5);                       // Review (pipeline done, no active jobs)
```

### Chain Help Panel Content (for Claude's discretion section)
```typescript
// Contextual help per chain (to be refined in planning)
const CHAIN_HELP: Record<string, ChainHelp> = {
  NEAR: {
    format: 'yourname.near or hex64chars.near',
    whereToFind: 'NEAR wallet app -> Copy Address',
    dataFetched: 'All NEAR transactions, staking rewards, lockup vesting',
    example: 'vitalpointai.near',
  },
  ETH: {
    format: '0x followed by 40 hex characters',
    whereToFind: 'MetaMask -> Account details -> Copy address',
    dataFetched: 'ETH transfers, ERC-20 token transactions, DeFi interactions',
    example: '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
  },
  // Polygon, Cronos, Optimism follow same 0x... format
};
```

### SyncStatus with Completion Callback
```typescript
// Extend SyncStatus for wizard Step 4 — observe isDone transition
// Source: web/components/sync-status.tsx existing polling logic
// Wrapper pattern:
function ProcessingStep({ onComplete }: { onComplete: () => void }) {
  const [prevDone, setPrevDone] = useState(false);
  // Poll /api/jobs/active via SyncStatus; when it shows "done", trigger onComplete
  // Use a wrapper that observes SyncStatus state via shared state lift
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| In-memory banner state (localStorage) | JSONB on users table | Phase 12 decision | Survives device changes |
| No onboarding tracking | `onboarding_completed_at` column | Phase 12 decision | Single source of truth, never nag returning users |
| Users figure out pipeline on their own | Step 4 guided processing with pipeline stages | Phase 12 new | "Add wallet -> everything just works" goal from Phase 7 |

**No deprecated patterns in this phase.** All existing components, API patterns, and DB conventions are used as-is.

## Open Questions

1. **SyncStatus "done" event propagation**
   - What we know: `SyncStatus` stops polling when `pct >= 100` but renders no callback mechanism
   - What's unclear: Should we add `onComplete?: () => void` prop to `SyncStatus`, or wrap it in a `ProcessingStep` that polls independently?
   - Recommendation: Add optional `onComplete` callback to `SyncStatus` — cleaner than duplicating polling logic. Planner should decide during task breakdown.

2. **Wallet suggestion "Not Mine" persistence**
   - What we know: CONTEXT.md says "Not Mine" hides the card locally, no DB write
   - What's unclear: If user dismisses "Not Mine" and returns to Step 4 (smart resume), the suggestion reappears
   - Recommendation: Accept this behavior — it's minor UX friction and avoids schema complexity. Or add suggestion dismissals to `dismissed_banners` JSONB (key: `suggestion_dismissed_{address}`). Planner can decide.

3. **Migration ordering vs Phase 11**
   - What we know: Phase 11 plans 11-02 through 11-05 are still pending (STATE.md shows 1/5 plans done)
   - What's unclear: Will migration 009 conflict if Phase 11 also adds migrations?
   - Recommendation: Phase 12 migration should be 009 (sequential after 008). If Phase 11 adds a migration between 008 and our 009, revision chain needs updating. Planner should note the dependency.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (pyproject.toml, tests/ directory) |
| Config file | pyproject.toml `[tool.ruff]` for lint; no pytest.ini found (pytest discovers tests/ automatically) |
| Quick run command | `pytest tests/test_api_wallets.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ONBOARD-01 | Preferences API: GET returns `onboarding_completed_at` | unit | `pytest tests/test_api_preferences.py -x -q` | Wave 0 |
| ONBOARD-01 | Preferences API: POST complete-onboarding sets timestamp | unit | `pytest tests/test_api_preferences.py -x -q` | Wave 0 |
| ONBOARD-01 | Migration 009 adds columns IF NOT EXISTS | unit | `pytest tests/test_migration_009.py -x -q` | Wave 0 |
| ONBOARD-02 | Wallet add in wizard: POST /api/wallets with chain help validation | unit | `pytest tests/test_api_wallets.py -x -q` | Exists |
| ONBOARD-03 | Exchange upload step: POST /api/upload-file accepts wizard context | unit | `pytest tests/test_api_wallets.py -x -q` (reuse pattern) | Exists |
| ONBOARD-04 | Report orientation links correct in Step 5 | manual | N/A — UI copy verification | manual-only |
| ONBOARD-05 | Verification page banner dismissed and tracked | unit | `pytest tests/test_api_preferences.py -x -q` | Wave 0 |
| ONBOARD-06 | Dismiss banner: PATCH stores key in dismissed_banners JSONB | unit | `pytest tests/test_api_preferences.py -x -q` | Wave 0 |
| ONBOARD-07 | Inline guidance: verification issues include description + action | unit | `pytest tests/test_api_verification.py -x -q` | Exists |
| ONBOARD-07 | "Mark Reviewed" calls POST /api/verification/resolve/{id} | unit | `pytest tests/test_api_verification.py -x -q` | Exists |

**Manual-only justifications:**
- ONBOARD-04: Report orientation is UI copy and link correctness — requires visual inspection or E2E test outside project scope.

### Sampling Rate
- **Per task commit:** `pytest tests/test_api_preferences.py tests/test_api_wallets.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_api_preferences.py` — covers ONBOARD-01, ONBOARD-05, ONBOARD-06 (GET/POST/PATCH preferences endpoints, JSONB merge, idempotent completion)
- [ ] `tests/test_migration_009.py` — covers migration 009 idempotency (IF NOT EXISTS columns)

*(All other test files already exist and cover the reused endpoints.)*

## Sources

### Primary (HIGH confidence)
- `/home/vitalpointai/projects/Axiom/web/components/sync-status.tsx` — SyncStatus props, polling interval (3s), done state detection
- `/home/vitalpointai/projects/Axiom/web/app/dashboard/wallets/page.tsx` — AddWalletModal implementation, CHAINS array, POST /api/wallets pattern
- `/home/vitalpointai/projects/Axiom/web/app/dashboard/import/page.tsx` — File upload zone, drag/drop handlers, exchange configs list
- `/home/vitalpointai/projects/Axiom/api/routers/verification.py` — `_CATEGORY_META` dict, all 5 diagnosis categories with descriptions and actions
- `/home/vitalpointai/projects/Axiom/engine/wallet_graph.py` — `suggest_wallet_discovery()` method signature and return format
- `/home/vitalpointai/projects/Axiom/web/app/dashboard/layout.tsx` — Dashboard guard pattern, `useAuth` usage
- `/home/vitalpointai/projects/Axiom/web/components/auth-provider.tsx` — User object shape, session API response
- `/home/vitalpointai/projects/Axiom/db/migrations/versions/006_auth_schema.py` — `ADD COLUMN IF NOT EXISTS` pattern for users table
- `/home/vitalpointai/projects/Axiom/db/migrations/versions/008_unified_audit_log.py` — Migration chaining (revision 008, down_revision 007); Phase 12 migration will be 009

### Secondary (MEDIUM confidence)
- `.planning/phases/12-user-onboarding/12-CONTEXT.md` — All locked decisions verified directly
- `.planning/STATE.md` — Phase 11 completion status (1/5 plans done); migration numbering context
- `web/package.json` — Next.js 16.x, React 19.x, Tailwind 4.x, lucide-react 0.469.0, shadcn/ui primitives confirmed

### Tertiary (LOW confidence)
- None — all claims verified against project source files.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies read directly from package.json and project source
- Architecture: HIGH — patterns derived from existing routers, components, and migrations (no speculation)
- Pitfalls: HIGH — derived from observed code patterns and explicit CONTEXT.md decisions (e.g., existing user NULL guard)
- Validation: HIGH — test framework confirmed from pyproject.toml and tests/ directory inspection

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (30 days — stable stack, no fast-moving dependencies)
