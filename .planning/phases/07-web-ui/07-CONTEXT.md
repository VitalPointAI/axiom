# Phase 7: Web UI - Context

**Gathered:** 2026-03-13 (updated from 2026-02-24)
**Status:** Ready for replanning

<domain>
## Phase Boundary

Wire the existing Next.js frontend to the Phase 1-6 PostgreSQL pipeline via a new FastAPI backend. The web UI already has 12 dashboard pages, 25+ API routes, WebAuthn auth, accountant mode, and sync status components. This phase replaces the Next.js API routes with a FastAPI backend, moves authentication to FastAPI, and ensures all pages work with the multi-user data layer (classification, ACB, verification, reports).

**What exists (do not rebuild):**
- Next.js App Router with Tailwind + shadcn/ui
- 12 dashboard pages (wallets, transactions, staking, DeFi, exchanges, reports, settings, admin, assets, prices, import, swap)
- Auth provider, sidebar, portfolio charts, sync status components
- Accountant access model with client switching and permission levels

**What this phase delivers:**
- FastAPI backend replacing all Next.js API routes
- Authentication moved to FastAPI (passkey, email magic link, Google OAuth)
- Full pipeline auto-chaining in UI (index → classify → ACB → verify)
- Verification dashboard with actionable issue resolution
- Report generation via job queue with inline previews + downloadable packages
- Transaction classification editing (inline + review queue)

</domain>

<decisions>
## Implementation Decisions

### API Architecture
- Build a **FastAPI backend** as the single API layer replacing all Next.js API routes
- Next.js becomes a pure frontend (SSR/CSR) calling FastAPI endpoints
- FastAPI runs as its own Docker container (separate from indexer), sharing PostgreSQL
- All business logic centralized in Python — no more dual JS/Python data access
- FastAPI interacts with the existing Python pipeline (IndexerService, ACBEngine, PackageBuilder, etc.)

### Authentication
- Move all auth to FastAPI — passkey/WebAuthn registration and login handled server-side in Python
- Three auth methods all active via `@vitalpoint/near-phantom-auth`:
  1. **Passkey/WebAuthn** — existing flow, migrated to Python
  2. **Email magic link** — signup and login via email
  3. **Google OAuth** — via near-phantom-auth OAuth flow
- All three methods are first-class and equal — email and NEAR passkey are both valid identity anchors
- NEAR wallet is just another tracked wallet, not the identity anchor
- Users can use the system without a NEAR wallet (email-only users track EVM/exchange data)
- Session management in PostgreSQL (existing sessions table pattern)
- Accountant access model preserved: `neartax_viewing_as` cookie + `accountant_access` table permission checks

### Wallet Sync UX
- **Full auto-chain pipeline:** add wallet → index → classify → ACB → verify (no manual triggers needed)
- Exchange CSV imports also auto-chain into classify → ACB → verify
- **Stage progress bar** showing pipeline stages: Indexing (45%) → Classifying → Cost Basis → Verifying → Done
  - Each stage lights up as it starts
  - Shows current stage details (e.g., "1,247 of 3,500 transactions fetched")
- **Incremental + selective recalc** when adding a new wallet after initial setup:
  - Index new wallet only
  - Re-classify only new transactions
  - Recalculate ACB only for affected tokens
  - Re-verify only affected wallets

### Report UI Integration
- **Inline data previews** for each report tab (first N rows from DB queries for quick review)
- **Plus "Generate Full Package"** button that creates the downloadable CSV+PDF bundle
- Report generation via **job queue + polling**: FastAPI creates `generate_reports` job → IndexerService processes via PackageBuilder → UI polls for completion → download links appear
- Generated reports **stored on server** (`output/{year}_tax_package/`) and served via FastAPI. Cached until data changes
- **Admin-only specialist override**: if `needs_review` items exist, show warning with count/summary. Override button only visible to admin users or accountants with readwrite access. Regular users must resolve flags first

### Verification & Flags UI
- **Issue-centric verification dashboard**: group by issue type (balance discrepancies, flagged classifications, superficial losses, potential duplicates). Each shows count + severity. Click into category for details
- **Actionable resolution guidance** per issue type: "Re-sync staking", "Mark as reviewed", "Merge duplicates", etc. One-click action buttons where possible. Leverages auto-diagnosis categories from BalanceReconciler
- **Transaction classification editing** — two modes:
  1. **Inline editing** from transaction ledger: flagged rows show yellow badge, click to expand editor (change category, add notes, mark reviewed)
  2. **Dedicated review queue**: separate page listing all `needs_review` items for focused bulk resolution
- **Batch recalc on save** for classification changes: edits are staged, user clicks "Apply Changes" to trigger ACB recalculation for affected tokens. Exception: intermediate recalc available when subsequent edits depend on updated ACB values

### Tech Stack (Updated)
- **Frontend:** Next.js 16+ with App Router, React 19, Tailwind CSS 4, shadcn/ui, Recharts
- **Backend:** FastAPI (new) replacing Next.js API routes
- **Database:** PostgreSQL only (multi-user, all tables have user_id FK)
- **Auth:** near-phantom-auth (passkey + email + Google OAuth) — moved to FastAPI
- **Deployment:** Separate Docker containers: web (Next.js), api (FastAPI), indexer (Python), postgres

### Claude's Discretion
- FastAPI route organization and middleware structure
- How to handle near-phantom-auth WebAuthn in Python (may need py_webauthn or similar)
- Polling interval and UX for job status updates
- Component refactoring needed to point at FastAPI instead of Next.js API routes
- State management approach for frontend
- Mobile responsiveness level
- Exact stage progress bar implementation

</decisions>

<specifics>
## Specific Ideas

- "Easy to use system to interact with and see the accounts, portfolios, reports"
- near-phantom-auth for user accounts (known working from Argus) — ensure passkey, email magic link, AND Google OAuth are all enabled
- Users should not need to understand the pipeline — add a wallet and everything just works
- Existing UX patterns from the current UI: clean card-based layouts, responsive sidebar navigation, action buttons with loading states, toast notifications
- The 16-tab reports page already has comprehensive report types — wire them to the Python PackageBuilder output
- Accountant client-switching with amber "viewing as" banner should continue working

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `web/components/` — 20+ components (sidebar, portfolio-summary, sync-status, auth-provider, client-switcher, staking-positions, etc.) — keep and rewire to FastAPI
- `web/app/dashboard/` — 12 dashboard pages fully built — keep layouts, rewire data fetching
- `web/lib/auth.ts` — Auth logic (182 lines) with accountant viewing mode — rewrite in FastAPI Python
- `web/lib/db.ts` — PostgreSQL connection pool — will be replaced by FastAPI's SQLAlchemy/psycopg2
- `web/app/api/phantom-auth/` — Full WebAuthn flow (register/login start/finish, OAuth, session) — rewrite as FastAPI endpoints
- `web/middleware.ts` — Rate limiting + auth middleware (121 lines) — rewrite in FastAPI middleware
- `indexers/service.py` — IndexerService with 12 job types, all user-scoped — FastAPI creates jobs, IndexerService processes them
- `reports/generate.py` — PackageBuilder orchestrating 10 report modules — called via job queue from FastAPI
- `reports/handlers/report_handler.py` — ReportHandler for generate_reports job type — already wired

### Established Patterns
- Multi-user isolation: all tables have `user_id` FK, all queries filter by `user_id` or `wallet_id IN (user's wallets)`
- Job queue: `indexing_jobs` table with FOR UPDATE SKIP LOCKED for concurrent processing
- Auto-chaining: ClassifierHandler already auto-queues ACB job after classification
- Session management: HTTP-only cookies, 7-day expiration, passkey counter validation
- Accountant mode: `neartax_viewing_as` cookie → `getAuthenticatedUser()` switches to client context

### Integration Points
- `docker-compose.prod.yml` — needs new `api` service for FastAPI container
- `.github/workflows/deploy.yml` — needs updated to build and deploy FastAPI container
- `config.py` — shared config between FastAPI and IndexerService
- `db/models.py` — SQLAlchemy models shared by FastAPI and pipeline
- `indexers/db.py` — PostgreSQL connection pool — FastAPI can use same pool pattern or SQLAlchemy async

</code_context>

<deferred>
## Deferred Ideas

- Real-time price updates via WebSocket (v2)
- Mobile app (v2)
- Multi-entity support for multiple corporations (v2)
- Automated exchange API sync (v2)
- WebSocket progress updates instead of polling (enhancement)
- Tax optimization suggestions (advisory feature, not reporting)
- General business accounting beyond crypto (future milestone)

</deferred>

---

*Phase: 07-web-ui*
*Context gathered: 2026-03-13*
