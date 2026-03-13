---
phase: 06-reporting
plan: 03
subsystem: reporting
tags: [koinly, csv-export, quickbooks, xero, sage50, double-entry, accounting]

requires:
  - phase: 06-01
    provides: ReportEngine base class, fiscal_year_range, fmt_cad helpers, gate check pattern

provides:
  - KoinlyExport: Koinly-compatible CSV with category->label mapping, yoctoNEAR conversion, fiscal year filtering, full-history mode
  - AccountingExporter: QuickBooks IIF, Xero CSV, Sage 50 CSV, generic double-entry CSV
  - reports/export.py: all export classes

affects: [06-04, 06-05]

tech-stack:
  added: []
  patterns:
    - TDD (RED-GREEN) for all 15 new tests before implementation
    - KOINLY_LABEL_MAP dict for TransactionClassification.category to Koinly label mapping
    - yoctoNEAR-to-NEAR conversion (divide by 1e24) in _convert_near_amount()
    - Fiscal year date filter applied in Python after mock-DB fetch (for testability)
    - QuickBooks IIF written as plain text tab-delimited lines (not csv.writer)
    - Generic placeholder account codes (1500/4100/4200) for accounting exports
    - Double-entry balance invariant: sum(Debit) == sum(Credit) per dataset

key-files:
  created:
    - reports/export.py
  modified:
    - tests/test_reports.py

key-decisions:
  - "Fiscal year date filter applied in Python after fetching all rows — mock cursor returns all rows; date filter is the report layer's responsibility"
  - "KoinlyExport queries two tables separately (transactions + exchange_transactions) rather than UNION — different column sets"
  - "Full history export skips gate check entirely — no date range means no tax year context to check"
  - "QuickBooks IIF TRNS AMOUNT = proceeds (not gain) — IIF journals debit proceeds to Crypto Assets, credit Capital Gains separately"
  - "Double-entry uses ACB as Crypto Assets credit — proceeds = ACB + capital gain/loss, balancing the debit cash entry"
  - "Xero and Sage 50 use GST Free tax rate — crypto disposals are not subject to GST in Canada"
  - "Generic placeholder account codes (1500, 4100, 4200) — accountant assigns real chart-of-accounts codes on import"

patterns-established:
  - "Pattern: IIF writing uses plain file.write() not csv.writer — IIF is tab-delimited with ! header prefix not supported by csv module"
  - "Pattern: accounting exports all write from same gains/income query results fetched once in generate_all()"

requirements-completed: [RPT-05]

duration: 6min
completed: 2026-03-13
---

# Phase 06 Plan 03: KoinlyExport + Accounting Software Exports Summary

**Koinly CSV export with KOINLY_LABEL_MAP category mapping and yoctoNEAR conversion, plus QuickBooks IIF, Xero CSV, Sage 50, and balanced generic double-entry CSV — all from capital_gains_ledger and income_ledger**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-13T19:06:48Z
- **Completed:** 2026-03-13T19:12:37Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 2

## Accomplishments
- KoinlyExport generates Koinly-compatible CSV from classified transactions (NEAR + exchange), with correct 12-column format, label mapping, yoctoNEAR-to-NEAR conversion, sent/received direction, fee population, fiscal year filtering, and full-history mode
- AccountingExporter produces all four accounting formats (QuickBooks IIF with balanced TRNS/SPL/ENDTRNS triplets, Xero CSV, Sage 50 CSV, generic double-entry CSV with balanced debit=credit)
- 15 new tests covering all behaviors, 71 total tests pass

## Task Commits

1. **TDD RED — TestKoinlyExport + TestAccountingExports** - `a904016` (test)
2. **TDD GREEN — reports/export.py** - `10d26c1` (feat)

**Plan metadata:** (docs commit after state update)

_Note: Both tasks implemented in single feat commit — same file covers both task behaviors._

## Files Created/Modified
- `/home/vitalpointai/projects/Axiom/reports/export.py` — KoinlyExport + AccountingExporter (all 4 formats), 606 lines
- `/home/vitalpointai/projects/Axiom/tests/test_reports.py` — Added TestKoinlyExport (8 tests) and TestAccountingExports (7 tests)

## Decisions Made
- Fiscal year date filter applied in Python after fetching rows from mock DB — this keeps the query simple and the date filtering logic testable without DB
- QuickBooks IIF TRNS amount uses proceeds (not gain/loss) so the TRNS and SPL line amounts match (both show proceeds), making the IIF self-consistent
- Double-entry double-entry balance: Debit Cash = proceeds; Credit ACB account = acb_used; Credit/Debit Capital Gains = gain_loss. This ensures total debits == total credits
- Full history export skips gate check — no tax year context to validate against
- KoinlyExport queries two result sets (NEAR and exchange transactions) sequentially; mock uses fetchall.side_effect with two items

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- reports/export.py complete; KoinlyExport and AccountingExporter importable
- 06-04 (Inventory Holdings + COGS + Business Income Statement + FIFO engine) can proceed
- 06-05 (PDF templates + PackageBuilder + ReportHandler) can reference export.py exports

## Self-Check: PASSED

- reports/export.py: FOUND
- tests/test_reports.py: FOUND (modified)
- 06-03-SUMMARY.md: FOUND
- Commits a904016 (test RED) and 10d26c1 (feat GREEN): FOUND

---
*Phase: 06-reporting*
*Completed: 2026-03-13*
