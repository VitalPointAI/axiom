---
phase: 06-reporting
plan: 05
subsystem: reporting
tags: [weasyprint, jinja2, pdf, tax-reports, package-builder, indexer-service]

# Dependency graph
requires:
  - phase: 06-01
    provides: ReportEngine base class, CapitalGainsReport, IncomeReport
  - phase: 06-02
    provides: LedgerReport, T1135Checker, SuperficialLossReport
  - phase: 06-03
    provides: KoinlyExport, AccountingExporter
  - phase: 06-04
    provides: InventoryHoldingsReport, COGSReport, BusinessIncomeStatement, FIFOTracker
provides:
  - 7 Jinja2 HTML templates for PDF rendering (A4, web-safe fonts, @page paged media)
  - write_pdf() method on ReportEngine using WeasyPrint 68.0
  - PackageBuilder class: orchestrates all reports into output/{year}_tax_package/
  - ReportHandler job type: async report generation via IndexerService generate_reports queue
  - generate_reports wired into IndexerService handler map
affects: [07-web-ui, phase-7]

# Tech tracking
tech-stack:
  added: [jinja2 (templates), weasyprint (PDF rendering)]
  patterns:
    - PackageBuilder runs gate check once, passes specialist_override to sub-reports to skip re-checks
    - Lazy import of ReportHandler in IndexerService.__init__ (matches ACBHandler/VerifyHandler pattern)
    - ReportHandler returns error dict on ReportBlockedError instead of raising (job marked failed with message)

key-files:
  created:
    - reports/templates/base.html
    - reports/templates/capital_gains.html
    - reports/templates/income.html
    - reports/templates/tax_summary.html
    - reports/templates/t1135.html
    - reports/templates/inventory.html
    - reports/templates/business_income.html
    - reports/handlers/__init__.py
    - reports/handlers/report_handler.py
  modified:
    - reports/engine.py (write_pdf() added)
    - reports/generate.py (full rewrite — PackageBuilder replaces legacy SQLite functions)
    - reports/__init__.py (PackageBuilder exported)
    - indexers/service.py (generate_reports handler registered)
    - tests/test_reports.py (TestPackageBuilder 9 tests + TestReportHandler 3 tests added)

key-decisions:
  - "Gate check runs once in PackageBuilder at top level; sub-reports set specialist_override=True to skip re-check"
  - "PackageBuilder._run_generate() temporarily sets specialist_override=True on each sub-report instance to bypass redundant gate re-runs"
  - "ReportHandler uses top-level imports (not lazy) for PackageBuilder and ReportBlockedError — no circular dep since reports/ doesn't import from indexers/"
  - "Lazy import of ReportHandler in IndexerService.__init__ matches existing ACBHandler/VerifyHandler pattern"
  - "PDF write uses base_url=templates_dir to handle any relative asset references in WeasyPrint"
  - "Tax summary PDF is a combined one-pager assembled from all sub-report summaries — generated last"

patterns-established:
  - "PackageBuilder pattern: single gate check + loop over report modules + PDF per report + manifest return"
  - "Handler error containment: ReportBlockedError returned as {error, blocked: True} not raised"

requirements-completed: [RPT-05, RPT-06]

# Metrics
duration: 25min
completed: 2026-03-13
---

# Phase 6 Plan 05: PDF Templates + PackageBuilder + ReportHandler Summary

**Jinja2/WeasyPrint PDF templates (7 templates, A4 @page), PackageBuilder orchestrator assembling complete tax packages, and ReportHandler async job wiring for IndexerService**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-03-13T19:23:38Z
- **Completed:** 2026-03-13T19:48:00Z
- **Tasks:** 3 (Task 1: HTML templates + write_pdf, Task 2: PackageBuilder TDD, Task 3: ReportHandler)
- **Files modified:** 11

## Accomplishments
- 7 Jinja2 HTML templates with A4 `@page` paged media, shared `base.html` layout, web-safe fonts (Arial/Helvetica/sans-serif), print-friendly CSS with alternating row colors and right-aligned numbers
- `write_pdf()` method added to `ReportEngine` using WeasyPrint 68.0
- `PackageBuilder` rewrites `generate.py` completely — discards legacy SQLite code — orchestrates all 10 report modules, runs gate check once, generates CSV + PDF per report, handles all three tax treatment modes (capital/business_inventory/hybrid)
- `ReportHandler` wired as `generate_reports` job type in `IndexerService` with priority=3; handles `ReportBlockedError` gracefully (returns error dict, does not raise)
- 92 tests pass across `test_reports.py` and `test_fifo.py`

## Task Commits

Each task was committed atomically:

1. **Task 1: Jinja2 HTML templates + write_pdf()** - `129782b` (feat)
2. **Task 2: PackageBuilder TDD** - `d9e9baa` (feat)
3. **Task 3: ReportHandler job wiring** - `3766f70` (feat)

## Files Created/Modified
- `reports/templates/base.html` - Shared A4 layout: @page media, header/footer, print-safe CSS, table styles
- `reports/templates/capital_gains.html` - Capital gains summary + disposal table, superficial loss row highlight
- `reports/templates/income.html` - Income summary by source, monthly breakdown, detail table
- `reports/templates/tax_summary.html` - Combined one-pager: CG summary, income, T1135 status, superficial losses
- `reports/templates/t1135.html` - T1135 status, per-token breakdown, self-custody CRA note
- `reports/templates/inventory.html` - Holdings table with ACB, FMV, unrealized gain/loss
- `reports/templates/business_income.html` - Revenue, COGS section, net business income
- `reports/engine.py` - Added `write_pdf(output_path, template_name, context)` method
- `reports/generate.py` - Full rewrite: `PackageBuilder` replaces all legacy functions
- `reports/__init__.py` - Added `PackageBuilder` to exports
- `reports/handlers/__init__.py` - Created (empty)
- `reports/handlers/report_handler.py` - `ReportHandler` class with `run(job_row, conn)` method
- `indexers/service.py` - Lazy import + registration of `ReportHandler` as `generate_reports`
- `tests/test_reports.py` - `TestPackageBuilder` (9 tests) + `TestReportHandler` (3 tests)

## Decisions Made
- Gate check runs once in PackageBuilder; sub-report instances have `specialist_override=True` temporarily set to skip redundant re-checks
- `ReportHandler` uses module-level imports (not lazy) for PackageBuilder and ReportBlockedError since no circular dep exists; `IndexerService` uses lazy import for ReportHandler matching existing pattern
- PDF rendering uses `base_url=templates_dir` so WeasyPrint can resolve any relative asset references
- Tax summary PDF assembled last (after all sub-report summaries collected)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test helper using invalid patch.multiple call**
- **Found during:** Task 2 (TestPackageBuilder TDD RED phase)
- **Issue:** Test `_build_with_mocks()` used `patch.multiple('', **{m: MagicMock() for m in []})` which raises `ValueError: Must supply at least one keyword argument`
- **Fix:** Rewrote helper to start/stop individual patchers manually, also patching `_check_gate` and `write_pdf` to avoid DB/WeasyPrint calls in tests
- **Files modified:** `tests/test_reports.py`
- **Committed in:** `d9e9baa` (Task 2 commit)

**2. [Rule 1 - Bug] Fixed test patch target for ReportHandler**
- **Found during:** Task 3 (TestReportHandler)
- **Issue:** Test patched `reports.handlers.report_handler.PackageBuilder` but PackageBuilder was lazily imported inside `run()` so it wasn't a module-level attribute — `AttributeError: module does not have the attribute 'PackageBuilder'`
- **Fix:** Moved PackageBuilder and ReportBlockedError to top-level imports in `report_handler.py` (no circular dep); kept lazy import only in `indexers/service.py` to match existing handler patterns
- **Files modified:** `reports/handlers/report_handler.py`, `indexers/service.py`
- **Committed in:** `3766f70` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep.

## Issues Encountered
None beyond the two auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 6 (Reporting) is now COMPLETE. All 5 plans delivered:
  - 06-01: ReportEngine + CapitalGainsReport + IncomeReport
  - 06-02: LedgerReport + T1135Checker + SuperficialLossReport
  - 06-03: KoinlyExport + AccountingExporter
  - 06-04: InventoryHoldingsReport + COGSReport + BusinessIncomeStatement + FIFOTracker
  - 06-05: PDF templates + PackageBuilder + ReportHandler
- Ready for Phase 7 (Web UI): reporting API endpoints can call `PackageBuilder.build()` or queue `generate_reports` jobs via IndexerService

## Self-Check: PASSED

All required files exist. All task commits confirmed in git log.

---
*Phase: 06-reporting*
*Completed: 2026-03-13*
