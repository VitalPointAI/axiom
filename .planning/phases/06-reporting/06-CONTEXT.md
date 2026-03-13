# Phase 6: Reporting - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Generate accountant-ready tax reports from verified capital gains ledger, income ledger, ACB snapshots, and transaction data. Replicate full Koinly report set, add inventory/COGS/corporate reports, support multiple output formats (CSV + PDF + accounting software exports), and produce a deliverable tax package. Multi-user: any user can generate reports with configurable tax treatment and fiscal year. Reports block on unresolved verification flags unless specialist override is applied.

</domain>

<decisions>
## Implementation Decisions

### Report Catalog
- Full Koinly parity: Capital Gains, Income Summary, Holdings/Balances, Complete Transaction Ledger, T1135 Foreign Property Check, Tax Summary
- Additional reports beyond Koinly:
  - **Inventory Holdings** — current token holdings with ACB per unit, total cost basis, current FMV, unrealized gain/loss per asset
  - **Cost of Goods Sold (COGS)** — opening inventory + acquisitions - closing inventory = COGS, for users treating crypto as business inventory
  - **Business Income Statement** — crypto revenue (staking/vesting) + capital gains + COGS + fiat from exchange records. Designed with extensibility for future non-crypto business accounting
  - **Superficial Loss Report** — all flagged superficial losses with 61-day window details, denied amounts, ACB adjustments
- Capital Gains report: generate BOTH chronological view and grouped-by-token view
- Income Summary: broken down by month + source type (staking, vesting, airdrops, etc.)

### Output Formats & Packaging
- Every report gets both CSV and formatted PDF versions
- Accounting software export formats: QuickBooks (IIF/CSV), Xero-compatible CSV, Sage 50 import format, Generic double-entry CSV (Date/Account/Debit/Credit/Memo)
- Koinly-compatible CSV export: both tax-year-specific AND full-history versions, with configurable date range
- All files in single flat folder: `output/{year}_tax_package/` with clear naming convention (e.g., `capital_gains_2025.csv`, `income_summary_2025.pdf`)
- Report engine accepts configurable tax year parameter — not hardcoded to 2025. Maintain historical records across years

### Corporate Tax Treatment
- Per-user setting for tax treatment: capital property (50% inclusion) vs business inventory (100% inclusion, COGS applies) vs hybrid (both views generated)
- Inventory valuation methods: average cost (reuses existing ACBEngine) + FIFO (requires lot tracking — new engine capability)
- Business Income Statement includes fiat from exchange records (deposits/withdrawals as cash flow items)
- Architecture designed for future expansion beyond crypto to general business accounting

### Data Scoping & Filtering
- Reports BLOCK on unresolved needs_review flags by default — prevents incomplete/inaccurate reports from being generated
- Specialist override capability: can force report generation with warnings on flagged items (asterisks/footnotes + summary of flagged items)
- Configurable fiscal year — user sets fiscal year-end (Dec 31, March 31, etc.), reports generate for that period
- All user wallets/exchanges included by default, with optional wallet exclusion filter (e.g., exclude test wallets, dust accounts)
- Prior-year ACB carryforward: each report period starts with opening ACB balances carried from prior year for full audit trail

### Claude's Discretion
- PDF generation library choice (ReportLab, WeasyPrint, or similar)
- FIFO lot tracking implementation details for the inventory method
- Exact QuickBooks/Xero/Sage export format specifications
- Report file naming convention specifics
- How to calculate T1135 peak foreign property value during the year
- Koinly CSV column mapping details
- Performance optimization for large transaction sets

</decisions>

<specifics>
## Specific Ideas

- "At minimum, need to replicate the entire set of reports that Koinly provides" — Koinly parity is the baseline
- "Focus on inventory holdings, cost of goods sold, and other business and corporate related reporting" — this is a product, not just VitalPoint AI's internal tool
- "This isn't just for Vital Point AI — need to build all of these features for any business or individual" — multi-user product mindset
- "Set conditions for connections and exports to popular business and accounting software" — QuickBooks, Xero, Sage integration from day one
- "Setting conditions for possible expansion beyond crypto at some point to include other business accounting system requirements" — future-proofing for general business accounting
- "Maintain historical records" — system preserves all report data across years
- "Prevent report generation until all flagged items are dealt with; however, provide a specialist capability to override" — data quality gate with escape hatch

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `reports/generate.py`: Legacy stub with correct report structure (capital gains, income, ledger, T1135, Koinly export) but uses SQLite and hardcoded queries — needs full PostgreSQL rewrite
- `engine/gains.py`: GainsCalculator already populates `capital_gains_ledger` and `income_ledger` tables — reports read directly from these
- `engine/acb.py`: ACBEngine with ACBPool snapshots in `acb_snapshots` table — provides per-token holdings, ACB per unit, total cost basis
- `engine/superficial.py`: SuperficialLossDetector results in `capital_gains_ledger.is_superficial_loss` + `denied_loss_cad` + `acb_adjustment_cad` fields
- `verify/report.py`: DiscrepancyReporter generates markdown reports from `verification_results` — pattern reusable for tax report generation
- `indexers/price_service.py`: PriceService with get_price_cad_at_timestamp() and get_boc_cad_rate() — needed for current FMV in holdings report

### Established Patterns
- PostgreSQL-backed data: all report data lives in `capital_gains_ledger`, `income_ledger`, `acb_snapshots`, `transaction_classifications`, `verification_results` tables
- Multi-user isolation via `user_id` FK on all data tables
- `needs_review` boolean + confidence scoring throughout the pipeline
- Decimal precision for all monetary values (NUMERIC types)
- Job queue pattern in IndexerService for async operations

### Integration Points
- `db/models.py`: CapitalGainsLedger, IncomeLedger, ACBSnapshot, TransactionClassification, VerificationResult models
- `indexers/price_service.py`: Current FMV lookups for holdings report
- `config.py`: User settings (fiscal year, tax treatment) — may need schema extension
- Phase 7 UI-06: Report generation UI will call these report generators
- `output/` directory: Final deliverable location

</code_context>

<deferred>
## Deferred Ideas

- General business accounting beyond crypto (full P&L, balance sheet, A/R, A/P) — future milestone
- Automated accountant portal / direct sharing — future feature
- Tax optimization suggestions (tax-loss harvesting, timing) — advisory feature, not reporting
- Multi-jurisdiction support (US, UK, EU) — Canada only for now
- Wallet grouping / business lines — beyond simple wallet filtering

</deferred>

---

*Phase: 06-reporting*
*Context gathered: 2026-03-13*
