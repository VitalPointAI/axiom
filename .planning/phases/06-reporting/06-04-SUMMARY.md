---
phase: 06-reporting
plan: 04
subsystem: reporting
tags: [fifo, inventory, cogs, business-income, decimal, tax-reporting]

requires:
  - phase: 06-01
    provides: ReportEngine base class, _check_gate, write_csv, fiscal_year_range, fmt_cad, fmt_units
  - phase: 04-02
    provides: ACBPool, acb_snapshots table schema (event_type, units_delta, cost_cad_delta, block_timestamp)

provides:
  - FIFOTracker: lot-level FIFO inventory valuation engine (engine/fifo.py)
  - InventoryHoldingsReport: current holdings with ACB per unit + optional unrealized gain/loss (reports/inventory.py)
  - COGSReport: opening + acquisitions - closing = COGS, ACB and FIFO methods (reports/inventory.py)
  - BusinessIncomeStatement: aggregates crypto income + capital gains + COGS + fiat flow (reports/business.py)
  - Hybrid tax treatment: generates both capital (50%) and business inventory (100%) views

affects: [06-05, 07-ui]

tech-stack:
  added: []
  patterns:
    - FIFOTracker uses collections.deque per token for O(1) FIFO queue operations
    - replay_from_snapshots() feeds acb_snapshot rows to FIFOTracker for lot reconstruction
    - COGSReport formula: opening_inventory + acquisitions - closing_inventory
    - BusinessIncomeStatement delegates COGS calculation to COGSReport internally
    - Hybrid treatment generates two summary sub-dicts (capital_view, business_view)

key-files:
  created:
    - engine/fifo.py - FIFOTracker with acquire/dispose/get_holdings/get_cogs/replay_from_snapshots
    - reports/inventory.py - InventoryHoldingsReport + COGSReport
    - reports/business.py - BusinessIncomeStatement
    - tests/test_fifo.py - 9 tests for FIFOTracker
  modified:
    - tests/test_reports.py - Added TestInventoryHoldings, TestCOGS, TestBusinessIncome (13 new tests)

key-decisions:
  - "FIFOTracker uses deque per token: O(1) popleft() for FIFO disposal vs O(n) list.pop(0)"
  - "FIFO COGS derived via get_cogs(year) from disposal history, not from ACB formula"
  - "COGSReport fetches all acb_snapshots for FIFO replay (full history, not just fiscal year)"
  - "BusinessIncomeStatement delegates to COGSReport internally for hybrid/business_inventory treatment"
  - "Oversell in FIFOTracker flags needs_review=True on all disposals, returns partial with $0 residual"
  - "FIFO produces different gain: Test 7 demonstrates ACB=$100 vs FIFO=$150 for same 20-unit transaction set"

patterns-established:
  - "All FIFOTracker arithmetic uses Decimal (no float); _to_decimal() helper for safe conversion"
  - "replay_from_snapshots() supports both dict and object attribute access for flexibility"
  - "TDD RED-GREEN pattern: tests written first confirming ModuleNotFoundError, then implementation"

requirements-completed: [RPT-01, RPT-02]

duration: 5min
completed: 2026-03-13
---

# Phase 6 Plan 4: Inventory Holdings + COGS + Business Income Statement Summary

**FIFOTracker lot-level engine + InventoryHoldingsReport + COGSReport + BusinessIncomeStatement supporting ACB and FIFO methods with hybrid tax treatment generating both capital (50%) and business inventory (100%) views**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-13T19:26:48Z
- **Completed:** 2026-03-13T19:32:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- FIFOTracker with per-token lot queues (deque): acquire, FIFO dispose, holdings queries, COGS by year, replay from acb_snapshots
- InventoryHoldingsReport queries latest ACB snapshot per token, optionally adds unrealized gain/loss when current prices provided
- COGSReport computes opening + acquisitions - closing via 3 SQL queries; FIFO variant replays snapshots via FIFOTracker
- BusinessIncomeStatement aggregates income_ledger, capital_gains_ledger, and exchange_transactions fiat flow
- Hybrid tax treatment in BusinessIncomeStatement produces capital_view (50% inclusion) and business_view (100% + COGS) sub-dicts
- 22 new tests across TestFIFOTracker, TestInventoryHoldings, TestCOGS, TestBusinessIncome; all 71 test_reports tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: FIFOTracker — lot-level tracking for inventory valuation** - `2c20e48` (feat, TDD)
2. **Task 2: InventoryHoldingsReport + COGSReport + BusinessIncomeStatement** - `0d5da98` (feat, TDD)

**Plan metadata:** (final commit hash below)

_Note: TDD tasks have two commits (RED test commit + GREEN implementation commit merged into single feat commit)_

## Files Created/Modified

- `/home/vitalpointai/projects/Axiom/engine/fifo.py` - FIFOTracker with lot-level FIFO inventory valuation; all Decimal arithmetic
- `/home/vitalpointai/projects/Axiom/reports/inventory.py` - InventoryHoldingsReport (ACB per unit + FMV) and COGSReport (ACB/FIFO methods)
- `/home/vitalpointai/projects/Axiom/reports/business.py` - BusinessIncomeStatement with hybrid view support
- `/home/vitalpointai/projects/Axiom/tests/test_fifo.py` - 9 tests for FIFOTracker
- `/home/vitalpointai/projects/Axiom/tests/test_reports.py` - Added TestInventoryHoldings, TestCOGS, TestBusinessIncome

## Decisions Made

- FIFOTracker uses `collections.deque` per token for O(1) FIFO disposal. list.pop(0) is O(n), which would be slow for wallets with many acquisition lots.
- COGS is computed via `get_cogs(year)` on FIFOTracker's disposal history rather than re-deriving from the ACB formula. This keeps the methods independent.
- BusinessIncomeStatement creates a COGSReport instance internally for hybrid/business_inventory treatment rather than duplicating the COGS SQL.
- Oversell handling: FIFOTracker flags `needs_review=True` on all disposals in the batch and appends a $0 residual record, matching ACBPool's oversell pattern from Plan 04-02.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All three business/inventory reports are available for PackageBuilder integration in Plan 06-05
- FIFOTracker is ready for use by any future plan requiring lot-level cost tracking
- Hybrid tax treatment output format is stable: `summary['capital_view']` and `summary['business_view']` keys

---
*Phase: 06-reporting*
*Completed: 2026-03-13*
