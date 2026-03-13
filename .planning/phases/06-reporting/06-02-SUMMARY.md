---
phase: 06-reporting
plan: 02
subsystem: reports
tags: [reporting, ledger, t1135, superficial-loss, csv, decimal, union-all, acb]
dependency_graph:
  requires:
    - phase: 06-01
      provides: "ReportEngine base class (gate check, write_csv, fmt_cad, fmt_units, fiscal_year_range)"
    - phase: 04-01
      provides: "acb_snapshots table with total_cost_cad per token"
    - phase: 04-03
      provides: "capital_gains_ledger with is_superficial_loss and denied_loss_cad columns"
    - phase: 03-01
      provides: "transaction_classifications with leg_type, category, fmv_cad, classification_source"
  provides:
    - LedgerReport — unified transaction ledger CSV joining NEAR/EVM + exchange transactions with classifications
    - T1135Checker — peak ACB cost T1135 foreign property threshold check with per-token CSV
    - SuperficialLossReport — denied loss listing from capital_gains_ledger
  affects: [06-03, 06-05]
tech_stack:
  added: []
  patterns:
    - "UNION ALL joining on-chain (transactions) and exchange side (exchange_transactions via transaction_classifications)"
    - "T1135 uses MAX(total_cost_cad) from acb_snapshots — peak cost, never current FMV"
    - "Self-custodied wallet tokens flagged as ambiguous with CRA position unclear note"
    - "Decimal precision throughout — no float arithmetic in CAD amounts"
key_files:
  created:
    - reports/ledger.py
    - reports/t1135.py
    - reports/superficial.py
  modified:
    - reports/__init__.py
    - tests/test_reports.py
key_decisions:
  - "LedgerReport uses UNION ALL (not JOIN) to combine on-chain + exchange tx sources"
  - "NEAR block_timestamp in nanoseconds — converted via block_timestamp * 1e9 for BETWEEN comparisons"
  - "T1135 threshold determination uses MAX(total_cost_cad) per token — Canadian tax law uses peak cost, not FMV at year-end"
  - "CANADIAN_EXCHANGES = {wealthsimple}; FOREIGN_EXCHANGES = {coinbase, crypto_com, uphold, coinsquare}"
  - "Coinsquare listed as foreign despite being Canadian-incorporated — has US parent, flagged for specialist review"
  - "Self-custodied NEAR/EVM wallets are ambiguous for T1135 — not counted in foreign total, listed in self_custody_tokens with specialist review note"
  - "SuperficialLossReport queries by tax_year column (integer) not date range — aligns with how CGL is populated"
requirements-completed: [RPT-03, RPT-04]
duration: 4min
completed: "2026-03-13"
---

# Phase 6 Plan 02: LedgerReport + T1135Checker + SuperficialLossReport Summary

**LedgerReport UNION ALL joining NEAR/EVM + exchange transactions with classifications; T1135 peak ACB cost threshold with foreign/domestic/ambiguous categorisation; SuperficialLossReport listing all CRA ITA s.54 denied losses.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-13T19:06:58Z
- **Completed:** 2026-03-13T19:11:13Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- LedgerReport joins on-chain transactions and exchange transactions into 17-column unified CSV ordered chronologically, with wallet exclusion support
- T1135Checker computes MAX(total_cost_cad) per token from acb_snapshots within fiscal year, categorises tokens as foreign/domestic/ambiguous, and compares to $100,000 CAD threshold
- SuperficialLossReport queries capital_gains_ledger for all rows where is_superficial_loss=TRUE, outputs denied amounts for accountant review

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests for LedgerReport, T1135Checker, SuperficialLossReport** - `2a76249` (test)
2. **Task 1 (GREEN): LedgerReport implementation** - `634f9af` (feat)
3. **Task 2 (GREEN): T1135Checker + SuperficialLossReport** - `af42b7a` (feat)

## Files Created/Modified

- `reports/ledger.py` — LedgerReport with UNION ALL on-chain + exchange query, 17 consistent columns, chronological ordering by epoch nanoseconds
- `reports/t1135.py` — T1135Checker with CANADIAN_EXCHANGES/FOREIGN_EXCHANGES constants, peak ACB cost threshold, self-custody ambiguity flag, TOTAL footer row in CSV
- `reports/superficial.py` — SuperficialLossReport listing is_superficial_loss=TRUE rows from capital_gains_ledger
- `reports/__init__.py` — Exports updated to include LedgerReport, T1135Checker, SuperficialLossReport
- `tests/test_reports.py` — Added 18 new tests across 3 test classes (7 + 7 + 4)

## Decisions Made

- **LedgerReport UNION ALL**: On-chain side queries `transactions` LEFT JOIN `transaction_classifications` (leg_type='parent') LEFT JOIN `wallets`. Exchange side queries `transaction_classifications` WHERE `exchange_transaction_id IS NOT NULL` JOIN `exchange_transactions`. UNION ALL preserves all rows and maintains consistent column ordering.
- **NEAR timestamp conversion**: block_timestamp is nanoseconds (BigInteger); multiply epoch seconds by 1_000_000_000 for BETWEEN comparison. Exchange tx_date is a timezone-aware datetime.
- **T1135 peak cost**: Canadian tax law requires reporting peak foreign property cost during the year — MAX(total_cost_cad) per token correctly captures this vs. end-of-year FMV which could understate.
- **Self-custody ambiguity**: CRA has not issued definitive guidance on whether self-custodied crypto (NEAR/EVM wallets) constitutes "foreign property" under ITA s.233.3. Listed separately with specialist review note — not counted toward threshold.
- **SuperficialLossReport uses tax_year column**: The capital_gains_ledger.tax_year integer column (not date range) ensures correct scoping for superficial losses even if disposal_date spans the fiscal year boundary.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TestLedgerReport test_ledger_includes_near_transactions re-opened csv file after tmpdir closed**
- **Found during:** Task 1 GREEN phase (first test run)
- **Issue:** Test opened `csv_path` inside `with tempfile.TemporaryDirectory() as tmpdir:` block for row data, then tried to re-open the same path outside the block to read headers — but the temp directory had already been deleted.
- **Fix:** Combined both reads into a single `with open(csv_path)` call inside the tmpdir context block.
- **Files modified:** `tests/test_reports.py`
- **Verification:** TestLedgerReport::test_ledger_includes_near_transactions passes
- **Committed in:** `634f9af` (Task 1 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in test)
**Impact on plan:** Minimal — test authoring bug, no implementation changes needed.

## Issues Encountered

None beyond the test bug above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All three report modules (LedgerReport, T1135Checker, SuperficialLossReport) ready for 06-05 PackageBuilder integration
- reports/__init__.py exports all report classes; 06-03 (KoinlyExport) can follow the same ReportEngine inheritance pattern
- 43 tests pass (25 from 06-01 + 18 from 06-02)

---
*Phase: 06-reporting*
*Completed: 2026-03-13*
