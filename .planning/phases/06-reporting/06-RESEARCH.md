# Phase 6: Reporting - Research

**Researched:** 2026-03-13
**Domain:** Python tax report generation — CSV/PDF output, Canadian crypto tax rules, accounting software exports
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Report Catalog**
- Full Koinly parity: Capital Gains, Income Summary, Holdings/Balances, Complete Transaction Ledger, T1135 Foreign Property Check, Tax Summary
- Additional reports beyond Koinly:
  - **Inventory Holdings** — current token holdings with ACB per unit, total cost basis, current FMV, unrealized gain/loss per asset
  - **Cost of Goods Sold (COGS)** — opening inventory + acquisitions - closing inventory = COGS, for users treating crypto as business inventory
  - **Business Income Statement** — crypto revenue (staking/vesting) + capital gains + COGS + fiat from exchange records. Designed with extensibility for future non-crypto business accounting
  - **Superficial Loss Report** — all flagged superficial losses with 61-day window details, denied amounts, ACB adjustments
- Capital Gains report: generate BOTH chronological view and grouped-by-token view
- Income Summary: broken down by month + source type (staking, vesting, airdrops, etc.)

**Output Formats and Packaging**
- Every report gets both CSV and formatted PDF versions
- Accounting software export formats: QuickBooks (IIF/CSV), Xero-compatible CSV, Sage 50 import format, Generic double-entry CSV (Date/Account/Debit/Credit/Memo)
- Koinly-compatible CSV export: both tax-year-specific AND full-history versions, with configurable date range
- All files in single flat folder: `output/{year}_tax_package/` with clear naming convention (e.g., `capital_gains_2025.csv`, `income_summary_2025.pdf`)
- Report engine accepts configurable tax year parameter — not hardcoded to 2025. Maintain historical records across years

**Corporate Tax Treatment**
- Per-user setting for tax treatment: capital property (50% inclusion) vs business inventory (100% inclusion, COGS applies) vs hybrid (both views generated)
- Inventory valuation methods: average cost (reuses existing ACBEngine) + FIFO (requires lot tracking — new engine capability)
- Business Income Statement includes fiat from exchange records (deposits/withdrawals as cash flow items)
- Architecture designed for future expansion beyond crypto to general business accounting

**Data Scoping and Filtering**
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

### Deferred Ideas (OUT OF SCOPE)
- General business accounting beyond crypto (full P&L, balance sheet, A/R, A/P) — future milestone
- Automated accountant portal / direct sharing — future feature
- Tax optimization suggestions (tax-loss harvesting, timing) — advisory feature, not reporting
- Multi-jurisdiction support (US, UK, EU) — Canada only for now
- Wallet grouping / business lines — beyond simple wallet filtering
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| RPT-01 | Capital gains/losses summary for tax year | `capital_gains_ledger` table populated by GainsCalculator; query by tax_year + user_id; include superficial loss fields from SuperficialLossDetector |
| RPT-02 | Income summary by month (staking, airdrops) | `income_ledger` table; GROUP BY DATE_TRUNC('month', income_date) + source_type; FMV already stored in fmv_cad |
| RPT-03 | Full transaction ledger with classifications | JOIN transactions + exchange_transactions + transaction_classifications; all chains, all sources |
| RPT-04 | T1135 foreign property threshold check | Query acb_snapshots for peak cost basis during year; aggregate tokens on non-Canadian exchanges |
| RPT-05 | CSV export package | Python csv module; one file per report; output/{year}_tax_package/ flat folder |
| RPT-06 | PDF summary report | WeasyPrint 68.0 (already installed); HTML template → write_pdf() |
</phase_requirements>

---

## Summary

Phase 6 builds the reporting layer on top of fully-populated PostgreSQL tables from Phases 3-5. The `capital_gains_ledger`, `income_ledger`, and `acb_snapshots` tables already contain all computed values — the reporting engine is primarily a query + format layer, not a computation layer.

The key architectural challenge is the report gate: before generating any report, the system must check for unresolved `needs_review` flags in the pipeline tables and either block generation or apply a specialist override with inline footnotes. This pattern mirrors how `DiscrepancyReporter` in `verify/report.py` works and should reuse its query-then-format approach.

PDF generation uses WeasyPrint 68.0 (already installed on the system). The HTML-to-PDF approach (render Jinja2 template → write_pdf()) is strongly preferred over direct ReportLab API calls because it allows the same HTML template to produce both browser-preview and PDF output, and CSS paged media handles headers/footers declaratively.

**Primary recommendation:** Build a `ReportEngine` base class with the gate-check + pool-connection pattern, then implement each report module (`capital_gains.py`, `income.py`, `ledger.py`, `t1135.py`, `export.py`) as a subclass. Add a `PackageBuilder` (`generate.py` rewrite) that orchestrates all modules and writes to `output/{year}_tax_package/`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg2 | already installed | PostgreSQL queries | All prior phases use this; connection pool pattern established |
| Python csv | stdlib | CSV file writing | Zero dependencies; project already uses it in reports/generate.py stub |
| WeasyPrint | 68.0 (installed) | HTML → PDF generation | Already installed; HTML/CSS approach is maintainable; handles @page, headers, footers |
| Decimal | stdlib | Monetary arithmetic | All prior phases use Decimal; never float for CAD values |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Jinja2 | Available (web/ uses it) | HTML templates for PDF | When generating PDF via WeasyPrint to keep layout in HTML/CSS |
| pathlib.Path | stdlib | Output directory creation | Consistent with existing generate.py stub |
| datetime | stdlib | Date arithmetic for fiscal year ranges | Month grouping, year boundary calculations |
| logging | stdlib | Consistent with all prior phase modules | Replace any print() calls |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| WeasyPrint | ReportLab | ReportLab is not installed; WeasyPrint is installed and provides HTML/CSS approach |
| WeasyPrint | fpdf2 | fpdf2 not installed; WeasyPrint already present |
| Jinja2 HTML templates | Python string formatting | Templates are maintainable, allow CSS styling, reusable for UI preview |

**Installation (only if Jinja2 not already present):**
```bash
pip install jinja2
```

Note: WeasyPrint 68.0 is already installed. No new PDF library installation needed.

---

## Architecture Patterns

### Recommended Project Structure
```
reports/
├── __init__.py          # exports ReportEngine, PackageBuilder
├── engine.py            # ReportEngine base class (gate check, pool wiring)
├── capital_gains.py     # RPT-01: CapitalGainsReport (chronological + grouped)
├── income.py            # RPT-02: IncomeReport (by month + source type)
├── ledger.py            # RPT-03: LedgerReport (full transaction ledger)
├── t1135.py             # RPT-04: T1135Checker (peak foreign property value)
├── export.py            # RPT-05/accounting: KoinlyExport + accounting exports
├── generate.py          # PackageBuilder (rewrite of existing stub)
├── templates/           # Jinja2 HTML templates for WeasyPrint
│   ├── base.html        # shared layout: @page CSS, header, footer
│   ├── capital_gains.html
│   ├── income.html
│   ├── tax_summary.html
│   └── t1135.html
└── handlers/
    └── report_handler.py  # IndexerService job type: generate_reports
```

### Pattern 1: ReportEngine Base Class with Gate Check
**What:** A base class that checks `needs_review` flags before allowing report generation. All report modules inherit from this.
**When to use:** Every report module — gates are always applied unless specialist_override=True.

```python
# Source: pattern from verify/report.py + engine/acb.py design
class ReportEngine:
    """Base class for all report generators."""

    def __init__(self, pool, specialist_override: bool = False):
        self.pool = pool
        self.specialist_override = specialist_override

    def _check_gate(self, user_id: int, tax_year: int) -> dict:
        """
        Returns {'blocked': bool, 'flagged_items': list}.
        If specialist_override=False and flagged_items, raises ReportBlockedError.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            # Check capital_gains_ledger
            cur.execute(
                """
                SELECT COUNT(*) FROM capital_gains_ledger
                WHERE user_id = %s AND tax_year = %s AND needs_review = TRUE
                """,
                (user_id, tax_year),
            )
            cgl_flagged = cur.fetchone()[0]

            # Check income_ledger
            cur.execute(
                """
                SELECT COUNT(*) FROM income_ledger
                WHERE user_id = %s AND tax_year = %s
                """,
                (user_id, tax_year),
            )
            # Check acb_snapshots for needs_review
            cur.execute(
                """
                SELECT COUNT(*) FROM acb_snapshots
                WHERE user_id = %s AND needs_review = TRUE
                AND DATE_PART('year', TO_TIMESTAMP(block_timestamp)) = %s
                """,
                (user_id, tax_year),
            )
            acb_flagged = cur.fetchone()[0]
            cur.close()
            total_flagged = cgl_flagged + acb_flagged
            if total_flagged > 0 and not self.specialist_override:
                raise ReportBlockedError(
                    f"{total_flagged} unresolved items require specialist review. "
                    "Use specialist_override=True to generate with warnings."
                )
            return {'blocked': False, 'flagged_count': total_flagged}
        finally:
            self.pool.putconn(conn)
```

### Pattern 2: CSV Generation (stdlib csv module)
**What:** Each report class has a `write_csv(path, rows, headers)` method.
**When to use:** All CSV outputs. Never use f-strings for CSV — always use the `csv.writer` to handle quoting.

```python
# Source: stdlib csv documentation + existing reports/generate.py pattern
import csv
from pathlib import Path

def write_csv(self, output_path: Path, headers: list, rows: list) -> Path:
    """Write CSV file. Returns path written."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return output_path
```

### Pattern 3: PDF Generation via WeasyPrint
**What:** Render a Jinja2 HTML template, then call `HTML(string=html).write_pdf(path)`.
**When to use:** All PDF outputs. WeasyPrint 68.0 is already installed.

```python
# Source: WeasyPrint official docs https://weasyprint.org/
from weasyprint import HTML

def write_pdf(self, output_path: Path, template_name: str, context: dict) -> Path:
    """Render HTML template and write PDF."""
    from jinja2 import Environment, FileSystemLoader
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    template = env.get_template(template_name)
    html_content = template.render(**context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_content, base_url=str(templates_dir)).write_pdf(str(output_path))
    return output_path
```

### Pattern 4: Decimal-safe Formatting
**What:** Format Decimal values for CSV/HTML output without losing precision or producing scientific notation.
**When to use:** All monetary values in CAD or units.

```python
# Consistent with all prior phases using Decimal for NUMERIC columns
from decimal import Decimal

def fmt_cad(value) -> str:
    """Format Decimal as CAD string to 2 decimal places."""
    if value is None:
        return ""
    return f"{Decimal(str(value)):.2f}"

def fmt_units(value) -> str:
    """Format Decimal as token units to 8 decimal places."""
    if value is None:
        return ""
    return f"{Decimal(str(value)):.8f}"
```

### Pattern 5: Fiscal Year Date Range
**What:** Convert a fiscal year and year-end month into a start/end date range for WHERE clauses.
**When to use:** All report queries that need to scope by fiscal year.

```python
from datetime import date

def fiscal_year_range(tax_year: int, year_end_month: int = 12):
    """
    Returns (start_date, end_date) for a fiscal year.
    Default: calendar year (Jan 1 - Dec 31).
    For Mar 31 year-end: (Apr 1 YYYY-1) to (Mar 31 YYYY).
    """
    if year_end_month == 12:
        return date(tax_year, 1, 1), date(tax_year, 12, 31)
    else:
        start = date(tax_year - 1, year_end_month + 1, 1)
        end = date(tax_year, year_end_month, 31)  # adjust for month
        return start, end
```

### Anti-Patterns to Avoid
- **Float arithmetic for monetary values:** All CAD, FMV, and unit values must stay as `Decimal`. Never `float(row[x])` for monetary fields.
- **Hardcoded tax year 2025:** The entire report engine must be parameterized on `tax_year`. The legacy `generate.py` stub hardcodes 2025 — discard this pattern.
- **SQLite queries in generate.py:** The existing stub uses SQLite (`get_connection()` from old `db/init.py`). All new code must use the psycopg2 pool from `db/__init__.py`.
- **Generating reports without the gate check:** Never skip `_check_gate()`. The specialist override must be explicit.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML to PDF | Custom PDF layout engine | WeasyPrint (already installed) | WeasyPrint handles pagination, headers, @page media, page numbers |
| CSV writing with commas in values | Manual string concatenation | stdlib csv.writer | csv.writer handles quoting, special characters, newlines in fields |
| Decimal formatting for financial display | Custom rounding logic | Python Decimal quantize() | Avoids banker's rounding surprises; matches CRA precision expectations |
| FIFO lot tracking | Complex in-memory sort | Sorted list of (timestamp, units, cost) lots, pop from front | Standard FIFO: maintain chronological lot queue per token per user |
| Month grouping for income | Python date math loops | PostgreSQL DATE_TRUNC('month', income_date) | Single GROUP BY in SQL is faster than Python loops over thousands of rows |
| T1135 peak value calculation | Scanning all transactions | Query acb_snapshots for max total_cost_cad per token during year window | acb_snapshots already has per-event total_cost_cad — find the max value row within the fiscal year |

**Key insight:** The computation is already done by Phases 3-5. Reporting is a read + format layer. Do not recompute ACB, gains, or income in report code — read from the ledger tables.

---

## Common Pitfalls

### Pitfall 1: Decimal to String Precision Loss in CSV
**What goes wrong:** `str(Decimal('1234.56789012'))` can produce unexpected trailing zeros or truncate in some contexts. `float(decimal_value)` loses precision for large numbers.
**Why it happens:** psycopg2 returns `Decimal` for NUMERIC columns. Python's default str() on Decimal does not zero-pad to consistent precision.
**How to avoid:** Always use explicit `quantize()` or f-string formatting: `f"{value:.8f}"` for units, `f"{value:.2f}"` for CAD.
**Warning signs:** CSV values showing `1.2E+3` or truncated decimal places.

### Pitfall 2: Report Gate Bypassed by Default Parameter
**What goes wrong:** `specialist_override=False` is the safe default but calling code may accidentally pass `True` in tests or for convenience, leaving gates open in production.
**Why it happens:** Easy to set override=True during development and forget to revert.
**How to avoid:** Gate check logs a WARNING when specialist_override=True is used. Log includes user_id, flagged count, and caller context. Never silently skip.
**Warning signs:** Reports generated for users with open verification_results.

### Pitfall 3: WeasyPrint Missing System Font or CSS
**What goes wrong:** WeasyPrint requires system fonts and may fail silently on missing CSS features in some environments.
**Why it happens:** WeasyPrint uses Cairo/Pango for rendering; Docker containers may not have full font sets.
**How to avoid:** Use CSS-safe web-safe fonts (Arial, Helvetica, sans-serif) in templates. Test PDF generation in the Docker container, not just locally.
**Warning signs:** PDF renders with boxes instead of characters, or WeasyPrint raises `PermissionError` or font-related warnings.

### Pitfall 4: T1135 Calculation — Cost vs FMV
**What goes wrong:** T1135 threshold is based on **cost** (ACB), not current FMV. Using current price × units gives wrong result.
**Why it happens:** Intuitive to think about "how much is it worth" but CRA defines threshold as "cost of specified foreign property."
**How to avoid:** Query `acb_snapshots.total_cost_cad` (the running cost basis) for peak value during the year, not price × units.
**Warning signs:** T1135 threshold incorrectly reported as not triggered when large price appreciation occurred.

### Pitfall 5: FIFO Lot Tracking vs ACB Engine Mismatch
**What goes wrong:** FIFO inventory method generates different gain/loss values than the Canadian average-cost ACB method. If FIFO report reads from `capital_gains_ledger` (which is ACB-based), it produces wrong numbers.
**Why it happens:** The existing ACBEngine uses average cost exclusively. FIFO requires separate lot-level tracking.
**How to avoid:** FIFO inventory report must be computed separately from a lot-level replay of `acb_snapshots` ordered by acquisition timestamp. It is NOT a read from `capital_gains_ledger`. Clearly label FIFO reports as "for inventory/COGS purposes" not "for Schedule 3."
**Warning signs:** FIFO and ACB capital gains numbers match exactly (they should differ for most users).

### Pitfall 6: Koinly CSV — Sent/Received Direction
**What goes wrong:** The existing `reports/generate.py` stub sets sent/received based on the raw `direction` column, but classified transactions have a defined `category` that determines the Koinly label (e.g., a `direction='out'` transaction categorized as `staking` should map to Koinly label `staking`, not generic `send`).
**Why it happens:** Old stub predates the classification engine.
**How to avoid:** Koinly export must JOIN `transaction_classifications` and map `category` → Koinly label. See mapping table in Code Examples section.

### Pitfall 7: Superficial Loss ACB Adjustment in Reports
**What goes wrong:** The denied loss amount from a superficial loss does not reduce taxable capital gains — it increases the ACB of the reacquired position. Reports must show the denied loss separately (it's not a deductible loss) and the ACB adjustment separately.
**Why it happens:** Accountants need to see both the denied amount and the ACB carryforward to reconcile with future disposal.
**How to avoid:** Capital gains report includes columns: `gain_loss_cad`, `is_superficial_loss`, `denied_loss_cad`, `acb_adjustment_cad`. The `gain_loss_cad` on a superficial loss row should already be $0 loss (loss denied) — the `denied_loss_cad` shows what was denied.

---

## Code Examples

Verified patterns from official sources and codebase inspection:

### Capital Gains Query (RPT-01)
```python
# Source: db/models.py CapitalGainsLedger + engine/gains.py
CAPITAL_GAINS_SQL = """
SELECT
    cgl.disposal_date,
    cgl.token_symbol,
    cgl.units_disposed,
    cgl.proceeds_cad,
    cgl.acb_used_cad,
    cgl.fees_cad,
    cgl.gain_loss_cad,
    cgl.is_superficial_loss,
    cgl.denied_loss_cad,
    cgl.needs_review,
    -- link to tx for audit trail
    snap.block_timestamp,
    tc.category AS classification_category
FROM capital_gains_ledger cgl
JOIN acb_snapshots snap ON cgl.acb_snapshot_id = snap.id
LEFT JOIN transaction_classifications tc ON snap.classification_id = tc.id
WHERE cgl.user_id = %s AND cgl.tax_year = %s
ORDER BY cgl.disposal_date, cgl.id
"""
```

### Income Query by Month (RPT-02)
```python
# Source: db/models.py IncomeLedger
INCOME_MONTHLY_SQL = """
SELECT
    DATE_TRUNC('month', income_date) AS month,
    source_type,
    token_symbol,
    SUM(units_received)    AS total_units,
    SUM(fmv_cad)           AS total_fmv_cad,
    COUNT(*)               AS event_count
FROM income_ledger
WHERE user_id = %s AND tax_year = %s
GROUP BY DATE_TRUNC('month', income_date), source_type, token_symbol
ORDER BY month, source_type, token_symbol
"""
```

### T1135 Peak Cost Query (RPT-04)
```python
# Source: db/models.py ACBSnapshot + CRA T1135 guidance (cost basis, not FMV)
T1135_PEAK_SQL = """
SELECT
    token_symbol,
    MAX(total_cost_cad) AS peak_cost_cad
FROM acb_snapshots
WHERE user_id = %s
  AND TO_TIMESTAMP(block_timestamp) >= %s
  AND TO_TIMESTAMP(block_timestamp) <= %s
GROUP BY token_symbol
"""
# Sum peak_cost_cad across all foreign-held tokens.
# Foreign = tokens held on non-Canadian exchanges (Coinbase, Crypto.com, etc.)
# Domestic = tokens in self-custodied NEAR wallets (debatable — flag for specialist review)
```

### Koinly Category Label Mapping
```python
# Source: Koinly help docs (support.koinly.io) + existing generate.py
# Maps TransactionClassification.category → Koinly label
KOINLY_LABEL_MAP = {
    'income':         'reward',
    'staking_reward': 'staking',
    'capital_gain':   '',          # no label needed — Koinly infers from sent/received
    'capital_loss':   '',
    'transfer':       '',          # internal transfer
    'fee':            '',
    'airdrop':        'airdrop',
    'vesting':        'income',
}

# Koinly CSV columns (universal import format)
KOINLY_HEADERS = [
    'Date',
    'Sent Amount', 'Sent Currency',
    'Received Amount', 'Received Currency',
    'Fee Amount', 'Fee Currency',
    'Net Worth Amount', 'Net Worth Currency',
    'Label',
    'Description',
    'TxHash',
]
```

### WeasyPrint PDF Generation
```python
# Source: WeasyPrint docs https://weasyprint.org/
from weasyprint import HTML
from pathlib import Path

def generate_pdf(html_string: str, output_path: Path) -> None:
    """Generate PDF from HTML string. WeasyPrint 68.0."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_string).write_pdf(str(output_path))
```

### Report Naming Convention
```
output/{year}_tax_package/
├── capital_gains_{year}.csv
├── capital_gains_{year}.pdf
├── capital_gains_{year}_by_token.csv      # grouped view
├── income_summary_{year}.csv
├── income_summary_{year}.pdf
├── transaction_ledger_{year}.csv
├── t1135_check_{year}.csv
├── t1135_check_{year}.pdf
├── tax_summary_{year}.pdf                 # combined summary
├── koinly_export_{year}.csv              # tax-year Koinly
├── koinly_export_full.csv                # full history Koinly
├── quickbooks_{year}.iif                 # QB Desktop IIF
├── xero_{year}.csv
├── sage50_{year}.csv
├── double_entry_{year}.csv               # generic accounting
├── inventory_holdings_{year}.csv
├── inventory_holdings_{year}.pdf
├── cogs_{year}.csv                       # if business inventory treatment
├── business_income_{year}.csv
├── business_income_{year}.pdf
└── superficial_losses_{year}.csv
```

### Accounting Software Export Formats

**QuickBooks IIF (Desktop):**
```
!TRNS  DATE  ACCNT  NAME  AMOUNT  DOCNUM  MEMO
!SPL   DATE  ACCNT  NAME  AMOUNT  DOCNUM  MEMO
!ENDTRNS
TRNS   01/15/2025  Crypto Assets  NEAR Sale  1500.00  TX001  Disposal
SPL    01/15/2025  Capital Gains  NEAR Sale  -1500.00  TX001  ...
ENDTRNS
```

**Xero CSV (journal import):**
```
Date, Description, Reference, Debit, Credit, Account Code, Tax Rate
2025-01-15, NEAR Disposal, TX001, , 1500.00, 200, GST Free
```

**Generic Double-Entry CSV:**
```
Date, Account, Debit, Credit, Memo, Reference
2025-01-15, Crypto Assets - NEAR, , 500.00, Disposal proceeds, TX001
2025-01-15, Capital Gains, , 200.00, Gain on disposal, TX001
2025-01-15, ACB - NEAR, 300.00, , Cost basis used, TX001
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQLite `get_connection()` in generate.py stub | psycopg2 pool from `db/__init__.py` | Phase 1 (2026-03-12) | Must rewrite generate.py entirely — no SQL reuse |
| PortfolioACB (float) in generate.py | ACBEngine with Decimal in `engine/acb.py` | Phase 4 (2026-03-12) | Reports read from ledger tables, not recompute |
| Single `generate.py` monolith | Module-per-report in `reports/` directory | This phase | Each report is independently testable and callable |
| No report gate | needs_review gate with specialist override | This phase | Prevents inaccurate tax reports being submitted |

**Deprecated/outdated:**
- `reports/generate.py` current content: Uses `db.init.get_connection()` (SQLite), `engine.acb.PortfolioACB` (deleted), hardcoded 2025, returns empty stubs. Discard all logic, keep the file as the new `PackageBuilder` entry point.
- `PortfolioACB` class: Was removed in Phase 4. Do not reference it anywhere in reporting code.

---

## Canadian Tax Rules (Verified)

### Capital Gains Inclusion Rate (2025 tax year)
- **50% inclusion rate** applies to all capital gains realized before January 1, 2026.
- Taxable capital gain = `gain_loss_cad * 0.50`
- Reported on T1 Schedule 3, Line 7 (crypto-assets, added 2021).
- Source: CRA announcement (canada.ca), confirmed by Kraken Canada crypto tax guide 2025.

### T1135 Foreign Property Threshold
- Required if **cost** (not FMV) of specified foreign property exceeds $100,000 CAD **at any time during the year**.
- Crypto held on non-Canadian exchanges (Coinbase, Crypto.com) = specified foreign property.
- Crypto in self-custodied NEAR wallets = **ambiguous** — CRA has not issued definitive guidance on situs. Flag for specialist review in T1135 report.
- T1135 threshold uses **ACB (cost basis)**, not current market value.
- Penalty for late filing: $25/day up to $2,500.
- Source: CRA T1135 FAQ (canada.ca), Metrics CPA blog.
- Confidence: HIGH for exchange-held crypto; MEDIUM for self-custodied wallet treatment.

### Business Income vs Capital Property
- If user trades frequently, CRA may reclassify gains as business income (100% inclusion, no 50% deduction).
- Per-user `tax_treatment` setting in config determines which calculation the report uses.
- Hybrid treatment: generate both Schedule 3 view (50%) and business income view (100%), let accountant decide.
- COGS formula: `opening_inventory_cost + acquisitions_cost - closing_inventory_cost`

### Superficial Loss Rules
- A capital loss is denied if the same or identical property is reacquired within 30 days before or after the disposition (61-day window total).
- Denied loss is added to ACB of the reacquired property (not permanently lost).
- `SuperficialLossDetector` in `engine/superficial.py` already populated `is_superficial_loss`, `denied_loss_cad`, `acb_adjustment_cad` in `capital_gains_ledger`.
- Reports must surface these separately — denied losses are NOT deductible in the reporting year.

---

## Open Questions

1. **User config schema for fiscal year and tax treatment**
   - What we know: `config.py` exists but has no user-level fiscal year or tax treatment fields.
   - What's unclear: Do these settings live in a `users` table column, a separate `user_settings` table, or are they passed as report generation parameters?
   - Recommendation: Add them as parameters to the report generation API call (not stored in DB for now). The handler can accept `fiscal_year_end_month=12` and `tax_treatment='capital'` as defaults. This avoids a schema migration for Phase 6.

2. **T1135 exchange vs self-custody classification**
   - What we know: Exchange-held crypto (Coinbase, Crypto.com) = foreign property. Self-custodied NEAR wallets = ambiguous.
   - What's unclear: CRA has not issued a definitive position on NEAR wallet situs.
   - Recommendation: T1135 report should include exchange-held tokens in the calculation, and list self-custodied tokens separately with a "CRA position unclear — consult specialist" footnote.

3. **Wallet exclusion filter mechanism**
   - What we know: CONTEXT.md says "optional wallet exclusion filter."
   - What's unclear: Is this a list of wallet IDs, account IDs, or a label-based filter?
   - Recommendation: Accept `excluded_wallet_ids: list[int]` as a report generation parameter. Adds a `AND cgl.user_id = %s AND wallet_id NOT IN (...)` clause via the join through acb_snapshots → transaction_classifications → transactions → wallet_id.

4. **Jinja2 availability**
   - What we know: `web/` directory has a Next.js app. Python Jinja2 may or may not be installed.
   - What's unclear: `requirements.txt` does not list Jinja2 explicitly.
   - Recommendation: Check at plan time with `pip show jinja2`. If missing, add to requirements.txt. Alternatively, use Python's stdlib string.Template for simple HTML — but Jinja2 is strongly preferred for maintainable templates.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (used in all prior phases) |
| Config file | none — pytest discovered from project root |
| Quick run command | `python3 -m pytest tests/test_reports.py -x -q` |
| Full suite command | `python3 -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RPT-01 | Capital gains rows queried, formatted with superficial loss fields | unit | `pytest tests/test_reports.py::TestCapitalGainsReport -x` | Wave 0 |
| RPT-02 | Income grouped by month + source type, FMV summed correctly | unit | `pytest tests/test_reports.py::TestIncomeReport -x` | Wave 0 |
| RPT-03 | Ledger joins all sources (NEAR + EVM + exchange), classifications included | unit | `pytest tests/test_reports.py::TestLedgerReport -x` | Wave 0 |
| RPT-04 | T1135 peak cost calculation uses ACB not FMV; $100K threshold correct | unit | `pytest tests/test_reports.py::TestT1135Checker -x` | Wave 0 |
| RPT-05 | CSV files written with correct headers and Decimal formatting | unit | `pytest tests/test_reports.py::TestCSVExport -x` | Wave 0 |
| RPT-06 | PDF generated via WeasyPrint from HTML template without error | integration | `pytest tests/test_reports.py::TestPDFGeneration -x` | Wave 0 |
| gate | Report blocked when needs_review=True items exist | unit | `pytest tests/test_reports.py::TestReportGate -x` | Wave 0 |
| gate | Specialist override generates with footnotes | unit | `pytest tests/test_reports.py::TestReportGate::test_override_generates_with_warnings -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_reports.py -x -q`
- **Per wave merge:** `python3 -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_reports.py` — covers all RPT requirements + gate check
- [ ] `reports/templates/` directory with base HTML template
- [ ] Confirm Jinja2 installed: `pip show jinja2` — if missing, add to `requirements.txt`

---

## Sources

### Primary (HIGH confidence)
- `db/models.py` — CapitalGainsLedger, IncomeLedger, ACBSnapshot, VerificationResult schemas
- `engine/gains.py` — GainsCalculator INSERT parameters; confirms field names in capital_gains_ledger and income_ledger
- `verify/report.py` — DiscrepancyReporter pattern (pool-based query + markdown format); directly reusable for report base class
- `engine/acb.py` (via test file) — ACBPool Decimal precision patterns
- WeasyPrint official site (weasyprint.org) — `HTML(string=html).write_pdf(path)` API confirmed
- CRA canada.ca T1135 FAQ — confirmed $100K cost threshold, not FMV

### Secondary (MEDIUM confidence)
- Koinly support docs (support.koinly.io/articles/9490074) — Koinly report types and CSV column names; site returned 403 but column structure confirmed via docs.stake.tax/export-csv-formats/koinly
- CRA capital gains 2025 update (canada.ca/en/revenue-agency/news) — 50% inclusion rate confirmed for 2025 tax year
- cryptact.com Canada crypto capital gains 2025 — cross-verification of inclusion rate

### Tertiary (LOW confidence)
- QuickBooks IIF structure (dancingnumbers.com/intuit-interchange-format-iif) — IIF format column structure; verify against actual QB import docs before implementation
- Xero CSV import format — not officially verified; recommend testing against a Xero sandbox account during implementation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — WeasyPrint installed (confirmed), psycopg2 installed (confirmed), stdlib csv always available
- Architecture: HIGH — based directly on existing codebase patterns (verify/report.py, engine/gains.py)
- Pitfalls: HIGH — Decimal precision and T1135 cost-not-FMV issues confirmed by reviewing existing models; FIFO vs ACB mismatch is mathematically certain
- Canadian tax rules: HIGH for 50% inclusion + T1135 threshold; MEDIUM for self-custody T1135 situs question
- Accounting software export formats: MEDIUM for IIF structure; LOW for exact Xero/Sage field names (need official docs)

**Research date:** 2026-03-13
**Valid until:** 2026-06-13 (stable domain — Canadian tax rules and WeasyPrint API are stable; accounting software export formats may need re-verification)
