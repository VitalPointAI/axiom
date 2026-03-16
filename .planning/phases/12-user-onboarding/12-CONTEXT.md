# Phase 12: User Onboarding - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Guide new users through initial setup after first sign-in — adding wallets and exchange data, watching the pipeline process their data, and understanding how to use reports, verification, and error resolution. This phase adds a post-signup onboarding wizard, contextual help banners across dashboard pages, and inline warning/error guidance with actionable resolution steps.

</domain>

<decisions>
## Implementation Decisions

### Onboarding Flow Structure
- **Step-by-step wizard** triggered on first login (full-page, not modal)
- Trigger condition: `onboarding_completed_at IS NULL` AND no wallets AND no exchange imports for the user
- **5 steps:** Welcome → Add Wallets → Import Exchanges → Processing → Review & Next Steps
- **Skip/offramp:** "I know what I'm doing — skip to dashboard" link on every step. Marks `onboarding_completed_at` and redirects to dashboard
- After completion or skip, wizard never shows again — existing dashboard pages cover all functionality
- **No re-access option** — all wizard actions are available on existing pages (Wallets, Import, Reports)

### Wallet Addition (Step 2)
- Users can **add multiple wallets** before proceeding — each appears as a card showing chain + address with remove button
- **Contextual help per chain:** when user selects NEAR/ETH/etc., show help panel with example address format, where to find address, and what data will be pulled
- "Add another" button + "Continue" button — pipeline starts for all wallets at once on Continue
- **Discovered wallet surfacing:** during processing (Step 4), if WalletGraph discovers linked addresses (frequent transfers to/from unregistered addresses), surface them inline: "We found wallets that might be yours" with Add/Not Mine buttons. Confirmed wallets get added and indexed automatically

### Exchange Import (Step 3)
- **Generic upload with auto-detect** — file upload zone with list of supported exchanges (Coinbase, Crypto.com, Wealthsimple, Uphold, Coinsquare)
- AI file agent auto-detects exchange format (already built in Phase 2)
- Step is **optional** — user can skip if they have no exchange data
- No exchange-specific export instructions in the wizard (keep it simple)

### Processing Step (Step 4)
- Shows the existing pipeline progress bar (auto-chain: index → classify → ACB → verify)
- Auto-advances to Step 5 when pipeline completes
- Discovered linked wallets surfaced here with Add/Not Mine actions
- "We're crunching your data..." messaging with stage details

### Review & Next Steps (Step 5)
- **Summary + quick orientation:** shows what was imported (X wallets, Y exchange files, Z transactions found, N items need review)
- Brief orientation section: "Here's where to find your reports, here's what flagged items mean" with links to each dashboard page
- "Go to Dashboard" button marks `onboarding_completed_at` and navigates to dashboard

### Progress Tracking & Resumability
- **DB column:** `onboarding_completed_at TIMESTAMPTZ NULL` on users table (new Alembic migration)
- **Smart resume:** no step tracking needed — on return, check data state (has wallets? has imports? pipeline running?) and route to appropriate step
- **JSONB preferences:** `dismissed_banners JSONB DEFAULT '{}'` on users table for tracking per-page banner dismissals (same migration)

### Education & Help Content
- **Contextual banners on each page:** dismissible info banners shown on first visit to Reports, Transactions, Wallets, Verification pages
- Each banner has plain-English explanation of what the page does and how to use it
- Dismissal tracked in `dismissed_banners` JSONB column on users table — survives device changes
- **Inline guidance per warning/error type:** each `needs_review` item type (superficial loss, balance discrepancy, classification uncertainty, etc.) has a plain-English explanation + suggested action shown inline next to the flagged item
- Action buttons where applicable: "Mark Reviewed", "Re-sync", "Learn More"

### Claude's Discretion
- Wizard step component implementation (layout, transitions, animations)
- Exact help text content per chain and per banner
- Warning/error explanation copy and categorization
- Processing step polling interval and progress display details
- How to integrate discovered wallet suggestions with WalletGraph data
- Mobile responsiveness of wizard steps

</decisions>

<specifics>
## Specific Ideas

- "Users should not need to understand the pipeline — add a wallet and everything just works" (carried from Phase 7)
- Discovered wallets during processing should show why they might be the user's (e.g., "47 transfers from your wallet vitalpointai.near")
- Step 5 orientation should set expectations about flagged items without alarming users
- Banners should be helpful but not annoying — one per page, easily dismissible, never return after dismissed
- Warning explanations should be in plain English, not technical jargon (e.g., "You sold NEAR at a loss and rebought within 30 days" not "Superficial loss per ITA s.54(f)")

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `web/components/sync-status.tsx`: Pipeline progress display — reuse in wizard Step 4
- `web/app/dashboard/wallets/`: Wallet add form — extract chain selector + address input for wizard Step 2
- `web/app/dashboard/import/`: File upload UI — reuse upload zone for wizard Step 3
- `engine/wallet_graph.py`: WalletGraph detects linked wallets — query during processing for discovered wallet suggestions
- `web/components/ui/`: shadcn/ui component library (buttons, cards, inputs, badges) — use for wizard steps
- `web/components/auth-provider.tsx`: Auth context with user object — extend with onboarding check
- `api/routers/wallets.py`: Wallet CRUD endpoints — reuse for wizard wallet addition
- `api/routers/reports.py`: Report endpoints — link from Step 5 orientation

### Established Patterns
- Auto-chain pipeline: add wallet → index → classify → ACB → verify (Phase 7)
- `needs_review=True` flag pattern across classifier, ACB, verification modules
- `_CATEGORY_META` dict in verification router maps diagnosis categories to severity/description/action
- Job queue polling from frontend via `apiClient.get('/api/jobs/...')`
- shadcn/ui + Tailwind CSS design system throughout

### Integration Points
- `db/migrations/versions/` — new migration for `onboarding_completed_at` and `dismissed_banners` columns on users table
- `web/app/dashboard/layout.tsx` — add onboarding redirect check (if not completed → `/onboarding`)
- `web/app/onboarding/` — new wizard pages (Step 1-5)
- `api/routers/auth.py` or new `api/routers/preferences.py` — endpoints for banner dismissal and onboarding completion
- `web/app/dashboard/*/page.tsx` — add contextual banner components to Reports, Transactions, Wallets, Verification pages

</code_context>

<deferred>
## Deferred Ideas

- Interactive product tour with highlighting/spotlight on UI elements (v2 enhancement)
- Video tutorials embedded in help sections (content creation task, not engineering)
- In-app chat/support widget for stuck users (v2)
- Onboarding analytics (funnel tracking, drop-off points) — future milestone

</deferred>

---

*Phase: 12-user-onboarding*
*Context gathered: 2026-03-16*
