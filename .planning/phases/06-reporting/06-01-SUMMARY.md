---
phase: 06-reporting
plan: 01
subsystem: reports
tags: [reporting, capital-gains, income, csv, decimal, gate-check]
dependency_graph:
  requires: [capital_gains_ledger, income_ledger, acb_snapshots]
  provides: [ReportEngine, CapitalGainsReport, IncomeReport]
  affects: [reports/__init__.py]
tech_stack:
  added: []
  patterns: [pool.getconn/putconn try/finally, stdlib csv.writer, Decimal precision throughout]
key_files:
  created:
    - reports/engine.py
    - reports/capital_gains.py
    - reports/income.py
    - tests/test_reports.py
  modified:
    - reports/__init__.py
    - .gitignore
decisions:
  - "reports/ removed from .gitignore — now a source package, not just an output dir"
  - "Gate check queries both capital_gains_ledger and acb_snapshots for needs_review"
  - "Opening ACB queried from acb_snapshots before fiscal year start epoch"
  - "taxable_amount = net_gain_loss * Decimal('0.50') for 50% inclusion rate"
  - "Monthly summary uses DB GROUP BY DATE_TRUNC — not in-Python aggregation"
metrics:
  duration_minutes: 4
  completed_date: "2026-03-13"
  tasks_completed: 3
  files_changed: 6
---

# Phase 6 Plan 01: ReportEngine + Capital Gains + Income Reports Summary

**One-liner:** ReportEngine base with needs_review gate check + CapitalGainsReport (chronological/grouped CSVs, 50% inclusion) + IncomeReport (detail/monthly CSVs) using Decimal precision throughout.

## What Was Built

### Task 1: ReportEngine base class (commit 22bb1fc)

`reports/engine.py` provides:
- `ReportBlockedError(Exception)` — raised when gate blocks report generation
- `ReportEngine.__init__(pool, specialist_override=False)` — stores pool + override flag
- `ReportEngine._check_gate(user_id, tax_year)` — queries capital_gains_ledger (by tax_year) and acb_snapshots (by block_timestamp converted to fiscal year range) for needs_review=TRUE rows. Raises ReportBlockedError unless specialist_override=True (which logs WARNING instead)
- `ReportEngine.write_csv(output_path, headers, rows)` — stdlib csv.writer with parent dir creation
- `fiscal_year_range(tax_year, year_end_month=12)` — returns (start_date, end_date); calendar year or configurable fiscal year-end
- `fmt_cad(value)` — Decimal to 2dp string; '' for None
- `fmt_units(value)` — Decimal to 8dp string; '' for None

`reports/__init__.py` exports all five names.

Also removed `reports/` from `.gitignore` (was listed as test output; now it's a source package).

### Task 2: CapitalGainsReport (commit 4ed46d2)

`reports/capital_gains.py` — `CapitalGainsReport(ReportEngine)`:
- `generate(user_id, tax_year, output_dir, year_end_month=12, excluded_wallet_ids=None)` — calls gate, queries capital_gains_ledger, writes two CSVs, returns summary dict
- `capital_gains_{year}.csv` — chronological by disposal_date; columns: Date, Token, Units Disposed, Proceeds (CAD), ACB Used (CAD), Fees (CAD), Gain/Loss (CAD), Superficial Loss, Denied Loss (CAD), Needs Review
- `capital_gains_{year}_by_token.csv` — aggregated by token_symbol; 9 columns including Superficial Loss Count and Total Denied (CAD)
- Summary dict: total_proceeds, total_acb_used, total_fees, total_gains, total_losses, net_gain_loss, taxable_amount (50% inclusion rate), superficial_losses_denied, opening_acb_cad, flagged_count
- Specialist override appends "NOTE: N items flagged for specialist review" footer row

### Task 3: IncomeReport (commit e34cfe5)

`reports/income.py` — `IncomeReport(ReportEngine)`:
- `generate(user_id, tax_year, output_dir, year_end_month=12, excluded_wallet_ids=None)` — calls gate, runs two queries, writes two CSVs, returns summary dict
- `income_summary_{year}.csv` — detail rows; columns: Date, Source Type, Token, Units Received, FMV USD, FMV CAD, ACB Added CAD
- `income_by_month_{year}.csv` — monthly summary via SQL GROUP BY DATE_TRUNC('month', income_date), source_type, token_symbol
- Summary dict: total_income_cad, by_source (dict source_type -> total), by_month (dict month -> total), event_count, flagged_count
- Specialist override appends "NOTE" footnote row

## Test Coverage

`tests/test_reports.py` — 475 lines, 25 tests:
- `TestReportGate` (5 tests): CGL needs_review blocks, ACB needs_review blocks, gate passes when clean, specialist override passes with flagged_count, specialist override logs WARNING
- `TestHelpers` (6 tests): fiscal_year_range calendar + fiscal, fmt_cad normal + None, fmt_units normal + None
- `TestCapitalGainsReport` (8 tests): headers include superficial loss columns, chronological order, grouped view, specialist footnote, summary dict keys + 50% calculation, Decimal precision, empty CSV, opening_acb_cad key
- `TestIncomeReport` (6 tests): CSV headers, monthly totals per source, annual total, required keys, empty result, specialist footnote

All 25 tests pass.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] reports/ directory was in .gitignore**
- **Found during:** Task 1 commit
- **Issue:** `.gitignore` had `reports/` listed under "Test output" section. This prevented staging any files in `reports/`.
- **Fix:** Removed `reports/` from `.gitignore` — the reports package is source code, not test output. The old `reports/generate.py` was a legacy stub that happened to live there.
- **Files modified:** `.gitignore`
- **Commit:** 22bb1fc

**2. [Rule 1 - Bug] TestCapitalGainsReport mock needed side_effect for fetchall**
- **Found during:** Task 2 test GREEN phase
- **Issue:** Test `_make_pool` set `cur.fetchall.return_value = rows` (single return). When `generate()` called `fetchall()` twice (once for disposals, once for opening ACB), both calls returned disposal rows. Unpacking opening ACB rows as `(token_symbol, total_cost_cad)` failed with ValueError on 10-column tuples.
- **Fix:** Changed test mock to use `cur.fetchall.side_effect = [rows or [], []]` — first call returns disposal rows, second returns empty list for opening ACB.
- **Files modified:** `tests/test_reports.py`
- **Commit:** 4ed46d2

## Self-Check: PASSED

All files confirmed present:
- reports/engine.py: FOUND
- reports/capital_gains.py: FOUND
- reports/income.py: FOUND
- tests/test_reports.py: FOUND

All commits confirmed:
- 22bb1fc (Task 1: ReportEngine): FOUND
- 4ed46d2 (Task 2: CapitalGainsReport): FOUND
- e34cfe5 (Task 3: IncomeReport): FOUND
