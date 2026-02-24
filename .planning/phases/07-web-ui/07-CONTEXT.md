# Phase 7: Web UI - Context

**Gathered:** 2026-02-24
**Status:** Ready for planning
**Source:** User request

<domain>
## Phase Boundary

Build a user-friendly web interface for NearTax that allows users to:
- Sign in with their NEAR wallet (using near-phantom-auth)
- Manage their crypto wallets/accounts
- View portfolio summaries and holdings
- Browse and filter transaction history
- Generate and download tax reports

The UI should be clean, intuitive, and production-ready.

</domain>

<decisions>
## Implementation Decisions

### Authentication
- Use `@vitalpoint/near-phantom-auth` npm package (already proven in Argus)
- NEAR mainnet wallet login (passkey + MPC accounts supported)
- Store user session server-side, link to their NEAR account ID

### Tech Stack
- Next.js 14+ with App Router (consistent with Argus)
- Tailwind CSS for styling
- shadcn/ui component library
- SQLite initially, PostgreSQL for production multi-user

### Data Architecture
- Each user's wallets stored with their NEAR account ID as foreign key
- Transaction data scoped to user
- Reports generated on-demand, cached for download

### Claude's Discretion
- Specific component structure and file organization
- API route design (REST vs tRPC)
- State management approach
- Loading/error states
- Mobile responsiveness level

</decisions>

<specifics>
## Specific Ideas

### From Aaron's Request
- "easy to use system to interact with and see the accounts, portfolios, reports"
- near-phantom-auth for user accounts (known working from Argus)

### Key Views
1. **Dashboard** - Portfolio overview, total value, holdings breakdown
2. **Wallets** - List/add/edit wallets, show sync status
3. **Transactions** - Searchable ledger with filters
4. **Reports** - Generate tax reports for selected year

### UX Patterns from Argus
- Clean card-based layouts
- Responsive sidebar navigation
- Action buttons with loading states
- Toast notifications for feedback

</specifics>

<deferred>
## Deferred Ideas

- Real-time price updates (v2)
- Mobile app (v2)
- Multi-entity support for multiple corporations (v2)
- Automated exchange API sync (v2)
- Collaboration features for accountants (v2)

</deferred>

---

*Phase: 07-web-ui*
*Context gathered: 2026-02-24*
