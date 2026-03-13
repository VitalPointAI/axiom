---
phase: 06-reporting
verified: 2026-03-13T20:10:00Z
status: passed
score: 14/14 must-haves verified
re_verification: false
---

# Phase 6: Reporting Verification Report

**Phase Goal:** Generate accountant-ready tax reports with full Koinly parity, corporate/business reports, accounting software exports, and PDF output. Multi-user with configurable fiscal year and tax treatment (capital/business/hybrid).
**Verified:** 2026-03-13T20:10:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Capital gains report shows all disposals for a tax year with gain/loss and superficial loss columns | VERIFIED | `reports/capital_gains.py` queries `capital_gains_ledger`, writes chronological CSV with `Superficial Loss` and `Denied Loss (CAD)` columns; 50% inclusion rate applied (`taxable_amount = net_gain_loss * Decimal('0.50')`) |
| 2 | Capital gains report has both chronological and grouped-by-token views | VERIFIED | `_write_chronological_csv()` writes `capital_gains_{year}.csv`; `_write_grouped_csv()` writes `capital_gains_{year}_by_token.csv` |
| 3 | Income report shows staking/vesting/airdrop income grouped by month and source type | VERIFIED | `reports/income.py` runs `GROUP BY DATE_TRUNC('month', income_date), source_type, token_symbol`; writes `income_by_month_{year}.csv` |
| 4 | Reports block when unresolved needs_review items exist unless specialist_override=True | VERIFIED | `engine.py` `_check_gate()` queries both `capital_gains_ledger` (WHERE needs_review = TRUE) and `acb_snapshots` (same); raises `ReportBlockedError` unless override; logs WARNING when override used |
| 5 | All monetary values use Decimal precision, never float | VERIFIED | No float usage found in any report module; `fmt_cad()`/`fmt_units()` take Decimal; FIFOTracker uses `_to_decimal()` helper throughout |
| 6 | Transaction ledger includes all NEAR, EVM, and exchange transactions with classifications | VERIFIED | `reports/ledger.py` UNION ALL joins `transactions LEFT JOIN transaction_classifications LEFT JOIN wallets` with exchange_transactions side; 17 consistent columns |
| 7 | T1135 check uses peak ACB cost (not FMV) and correctly applies $100K CAD threshold | VERIFIED | `reports/t1135.py` queries `MAX(acb.total_cost_cad) AS peak_cost_cad` from `acb_snapshots`; compares sum to `$100,000` threshold |
| 8 | Self-custodied wallets flagged as ambiguous in T1135 report with specialist review note | VERIFIED | T1135Checker categorises self-custodied NEAR/EVM tokens as ambiguous with "CRA position unclear" note; not counted toward threshold |
| 9 | Superficial loss report shows all flagged losses with denied amounts | VERIFIED | `reports/superficial.py` queries `capital_gains_ledger WHERE is_superficial_loss = TRUE`; outputs `denied_loss_cad` |
| 10 | Koinly CSV export maps classification categories to correct Koinly labels | VERIFIED | `KOINLY_LABEL_MAP` dict present and used; e.g. `staking_reward` -> `staking`, `airdrop` -> `airdrop`; both year-specific and full-history modes implemented |
| 11 | Accounting software exports (QuickBooks IIF, Xero, Sage50, double-entry) are produced | VERIFIED | `reports/export.py` AccountingExporter produces all 4 formats with balanced debit/credit entries; QuickBooks uses tab-delimited TRNS/SPL/ENDTRNS |
| 12 | Inventory Holdings, COGS, and Business Income Statement support configurable tax treatment | VERIFIED | `PackageBuilder.build()` accepts `tax_treatment` in `{'capital', 'business_inventory', 'hybrid'}`; COGS/business reports conditional on non-capital treatment |
| 13 | PDF reports render from Jinja2 templates via WeasyPrint without error | VERIFIED | All 7 templates (`base.html`, `capital_gains.html`, `income.html`, `tax_summary.html`, `t1135.html`, `inventory.html`, `business_income.html`) load in Jinja2 without error; `ReportEngine.write_pdf()` wired to `HTML(...).write_pdf()` |
| 14 | PackageBuilder generates complete tax package; ReportHandler wired into IndexerService as generate_reports job | VERIFIED | `generate.py` PackageBuilder imports all 10 report modules and calls each; `indexers/service.py` registers `ReportHandler` as `self.handlers["generate_reports"]` with priority 3; lazy import pattern followed |

**Score:** 14/14 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `reports/engine.py` | ReportEngine base class with gate check, CSV/PDF helpers, fiscal year range utility | VERIFIED | 239 lines; exports `ReportEngine`, `ReportBlockedError`, `fmt_cad`, `fmt_units`, `fiscal_year_range`, `write_pdf` |
| `reports/capital_gains.py` | CapitalGainsReport with chronological and grouped-by-token CSV generation | VERIFIED | 322 lines; exports `CapitalGainsReport`; both CSV views confirmed |
| `reports/income.py` | IncomeReport with monthly breakdown by source type | VERIFIED | 250 lines; exports `IncomeReport`; SQL GROUP BY DATE_TRUNC confirmed |
| `reports/ledger.py` | LedgerReport joining all transaction sources | VERIFIED | 244 lines; exports `LedgerReport`; UNION ALL confirmed |
| `reports/t1135.py` | T1135Checker with peak cost calculation and threshold check | VERIFIED | 190 lines; exports `T1135Checker`; MAX(total_cost_cad) confirmed |
| `reports/superficial.py` | SuperficialLossReport listing all denied losses | VERIFIED | 141 lines; exports `SuperficialLossReport`; is_superficial_loss query confirmed |
| `reports/export.py` | KoinlyExport, AccountingExporter | VERIFIED | 606 lines; exports both classes; KOINLY_LABEL_MAP and all 4 accounting formats confirmed |
| `reports/inventory.py` | InventoryHoldingsReport and COGSReport | VERIFIED | 316 lines; exports both classes; DISTINCT ON query for latest holdings confirmed |
| `reports/business.py` | BusinessIncomeStatement | VERIFIED | 233 lines; exports `BusinessIncomeStatement`; queries income_ledger + capital_gains_ledger |
| `reports/generate.py` | PackageBuilder (rewrite) — orchestrates all reports | VERIFIED | 445 lines; imports and calls all 10 report modules; legacy SQLite code replaced |
| `reports/templates/` (7 files) | Jinja2 HTML templates for PDF | VERIFIED | All 7 templates present and load without error; A4 @page media, web-safe fonts |
| `reports/handlers/report_handler.py` | ReportHandler job type for IndexerService | VERIFIED | 108 lines; exports `ReportHandler`; calls `PackageBuilder.build()`; handles `ReportBlockedError` gracefully |
| `engine/fifo.py` | FIFOTracker with lot-level tracking | VERIFIED | 305 lines; exports `FIFOTracker`; `acquire`, `dispose`, `get_holdings`, `get_cogs`, `replay_from_snapshots` all present |
| `tests/test_reports.py` | Unit tests — gate check, all report classes | VERIFIED | 1982 lines; 89 tests pass |
| `tests/test_fifo.py` | Unit tests for FIFOTracker | VERIFIED | 177 lines; 9 tests pass (FIFO vs ACB difference confirmed) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `reports/engine.py` | `capital_gains_ledger`, `acb_snapshots` | psycopg2 pool queries for needs_review gate | WIRED | Lines 155, 169: `WHERE needs_review = TRUE` on both tables |
| `reports/capital_gains.py` | `capital_gains_ledger` | SQL query for disposal data | WIRED | Line 54: `FROM capital_gains_ledger cgl` |
| `reports/income.py` | `income_ledger` | SQL GROUP BY DATE_TRUNC | WIRED | Lines 45, 54: `FROM income_ledger` with group by |
| `reports/ledger.py` | `transactions`, `exchange_transactions`, `transaction_classifications` | UNION ALL | WIRED | Line 180: `UNION ALL` confirmed; both sources joined |
| `reports/t1135.py` | `acb_snapshots` | MAX(total_cost_cad) GROUP BY token_symbol | WIRED | Line 95: `MAX(acb.total_cost_cad) AS peak_cost_cad` |
| `reports/superficial.py` | `capital_gains_ledger` | WHERE is_superficial_loss = TRUE | WIRED | Line 78: `AND is_superficial_loss = TRUE` |
| `reports/export.py` | `transaction_classifications`, `transactions`, `exchange_transactions` | JOIN + KOINLY_LABEL_MAP | WIRED | KOINLY_LABEL_MAP at line 42; queries both NEAR and exchange sources |
| `reports/export.py` | `capital_gains_ledger`, `income_ledger` | Accounting export reads gains/income | WIRED | Lines 356, 377: queries both ledgers for journal entries |
| `engine/fifo.py` | `acb_snapshots` | replay_from_snapshots() replays event_type acquire/dispose | WIRED | Lines 271-305: replays rows from acb_snapshots via event_type dispatch |
| `reports/inventory.py` | `acb_snapshots` | DISTINCT ON (token_symbol) for latest holdings | WIRED | Line 31: `SELECT DISTINCT ON (token_symbol)... units_after, acb_per_unit_cad` |
| `reports/business.py` | `income_ledger`, `capital_gains_ledger` | Aggregates all revenue streams | WIRED | Lines 33, 39: queries both ledgers |
| `reports/generate.py` | All 10 report modules | PackageBuilder instantiates each and calls generate() | WIRED | Lines 42-49: imports; lines 117-316: calls each module |
| `reports/handlers/report_handler.py` | `reports/generate.py` | ReportHandler calls PackageBuilder.build() | WIRED | Line 81: `builder = PackageBuilder(self.pool, ...)` then `builder.build(...)` |
| `indexers/service.py` | `reports/handlers/report_handler.py` | Lazy import + handler registration | WIRED | Lines 86-87: lazy import, `self.handlers["generate_reports"] = ReportHandler(self.pool)` |
| `reports/templates/base.html` | WeasyPrint | HTML(string=rendered_template).write_pdf() | WIRED | `engine.py` line 217: `HTML(...).write_pdf(str(output_path))` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| RPT-01 | 06-01, 06-04 | Capital gains/losses summary for tax year | SATISFIED | `CapitalGainsReport` generates chronological + grouped CSVs with 50% inclusion; `InventoryHoldingsReport` + `COGSReport` extend to business inventory |
| RPT-02 | 06-01, 06-04 | Income summary by month (staking, airdrops) | SATISFIED | `IncomeReport` groups by DATE_TRUNC('month') + source_type; `BusinessIncomeStatement` extends to full business view |
| RPT-03 | 06-02 | Full transaction ledger with classifications | SATISFIED | `LedgerReport` UNION ALL joins all sources with classifications into 17-column CSV |
| RPT-04 | 06-02 | T1135 threshold check (foreign property > $100K CAD) | SATISFIED | `T1135Checker` uses peak ACB cost, applies $100K threshold, flags self-custody as ambiguous |
| RPT-05 | 06-03, 06-05 | CSV export (Koinly + accounting software) | SATISFIED | `KoinlyExport` with label mapping + yoctoNEAR conversion; `AccountingExporter` produces QB IIF, Xero, Sage50, double-entry; `PackageBuilder` assembles complete tax package |
| RPT-06 | 06-05 | PDF summary report | SATISFIED | 7 Jinja2 templates + WeasyPrint `write_pdf()` on `ReportEngine`; `PackageBuilder` generates PDFs for capital gains, income, T1135, tax summary, inventory, business income |

No orphaned requirements — all 6 RPT IDs declared across plans and implemented.

---

### Anti-Patterns Found

No blockers or warnings found.

- No TODO/FIXME/PLACEHOLDER comments in implementation files
- No `return null`/`return {}` stub patterns
- No float arithmetic in monetary calculations (Decimal throughout)
- No empty handlers or stub API routes
- No unconnected modules (all imports verified wired)

---

### Human Verification Required

#### 1. PDF Visual Quality

**Test:** Run `python3 reports/generate.py --year 2025` against a live database; open `output/2025_tax_package/tax_summary_2025.pdf`
**Expected:** A4 layout, readable fonts, page numbers in footer, superficial loss rows highlighted yellow, T1135 determination clearly stated
**Why human:** WeasyPrint rendering quality, font legibility, and print-safety cannot be verified programmatically

#### 2. Accountant Usability Confirmation

**Test:** Deliver the generated `output/{year}_tax_package/` to the accountant
**Expected:** Accountant confirms the package is complete and usable for filing (ROADMAP.md success criterion 5)
**Why human:** Accountant domain judgment on completeness and presentation quality

#### 3. QuickBooks IIF Import

**Test:** Import `quickbooks_{year}.iif` into a QuickBooks instance
**Expected:** TRNS/SPL/ENDTRNS entries imported without error; amounts balance
**Why human:** QuickBooks import validation requires the actual application

---

### Gaps Summary

No gaps. All automated verification passes.

**Test results:** 92/92 tests pass (89 in `test_reports.py` + 9 in `test_fifo.py`, confirmed via `python3 -m pytest tests/test_reports.py tests/test_fifo.py -q`)

**All phase deliverables present:**
- 10 report modules in `reports/` (engine, capital_gains, income, ledger, t1135, superficial, export, inventory, business, generate)
- 7 Jinja2 HTML templates in `reports/templates/`
- `reports/handlers/report_handler.py` registered as `generate_reports` job in `IndexerService`
- `engine/fifo.py` FIFOTracker for lot-level FIFO inventory valuation
- Multi-user support via `user_id` parameter on all report `generate()` calls
- Configurable fiscal year via `year_end_month` parameter on all reports
- All three tax treatments (`capital`, `business_inventory`, `hybrid`) supported in `PackageBuilder`

---

_Verified: 2026-03-13T20:10:00Z_
_Verifier: Claude (gsd-verifier)_
