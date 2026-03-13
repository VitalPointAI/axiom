---
phase: 07-web-ui
plan: 04
subsystem: api
tags: [fastapi, postgresql, psycopg2, pydantic, union-all, pagination, tdd]

# Dependency graph
requires:
  - phase: 07-01
    provides: "FastAPI app factory, get_effective_user, get_pool_dep dependencies"
  - phase: 03-classification
    provides: "transaction_classifications table with tx_hash, chain, tax_category, needs_review"
  - phase: 01-near-indexer
    provides: "transactions table, wallets table"
  - phase: 02-multi-chain
    provides: "exchange_transactions table"

provides:
  - "GET /api/transactions: paginated UNION ALL ledger (on-chain + exchange) with 6 filter types"
  - "GET /api/transactions/review: needs_review queue sorted by confidence ASC with counts_by_category"
  - "PATCH /api/transactions/{tx_hash}/classification: dynamic UPDATE with reviewed_at tracking"
  - "POST /api/transactions/apply-changes: calculate_acb job with JSON cursor (targeted token recalc)"
  - "api/schemas/transactions.py: TransactionResponse, TransactionListResponse, ClassificationUpdate, ReviewQueueResponse, ApplyChangesRequest/Response"

affects:
  - 07-05-portfolio-router
  - 07-06-reports-verification-routers

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "UNION ALL across transactions + exchange_transactions with COUNT(*) OVER() for single-pass pagination"
    - "GET /review registered before /{tx_hash}/... to prevent 'review' being parsed as path param"
    - "Dynamic UPDATE using list-built set_clauses to only update provided fields"
    - "JSON cursor in indexing_jobs for targeted token ACB recalculation"
    - "run_in_threadpool() wraps all psycopg2 synchronous calls in async route handlers"

key-files:
  created:
    - api/schemas/transactions.py
    - api/routers/transactions.py
    - tests/test_api_transactions.py
  modified:
    - api/routers/__init__.py (replaced transactions stub with real router import)

key-decisions:
  - "GET /review registered before /{tx_hash}/classification — FastAPI matches routes in registration order; 'review' as literal must precede the path param pattern"
  - "UNION ALL single-pass with COUNT(*) OVER() — returns total count alongside rows without a separate COUNT query"
  - "Dynamic UPDATE via list-built set_clauses — avoids building SET None = NULL for omitted fields"
  - "JSON cursor in calculate_acb indexing_jobs — enables ACBHandler to recalc only affected token symbols"
  - "exchange_transactions join via tc.tx_hash = et.tx_id — existing pattern from reports/ledger.py; classification stores tx_id in tx_hash column for exchange rows"

# Metrics
duration: 5min
completed: 2026-03-13
---

# Phase 7 Plan 04: Transaction Ledger API Summary

**Transaction ledger UNION ALL (on-chain + exchange) with 6 filter types, review queue sorted by confidence, classification PATCH with reviewed_at tracking, and apply-changes triggering targeted ACB recalculation via JSON cursor**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-13T21:56:26Z
- **Completed:** 2026-03-13T22:01:20Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 4

## Accomplishments

- `api/schemas/transactions.py`: 6 Pydantic schemas (TransactionResponse, TransactionListResponse, ClassificationUpdate, ReviewQueueResponse, ApplyChangesRequest, ApplyChangesResponse)
- `api/routers/transactions.py`: 4 endpoints built with UNION ALL pattern from reports/ledger.py
  - GET /api/transactions: wallet_id-scoped on-chain + user_id-scoped exchange UNION ALL with 6 filter clauses, COUNT(*) OVER() for total, LIMIT/OFFSET pagination
  - GET /api/transactions/review: needs_review=true filtered UNION ALL sorted by confidence_score ASC, counts_by_category built in Python
  - PATCH /api/transactions/{tx_hash}/classification: ownership verified via wallet→wallets or direct user_id, dynamic SET clauses, reviewed_at=NOW() on needs_review=False
  - POST /api/transactions/apply-changes: auto-discovers recently-edited tokens if none provided, inserts calculate_acb job with JSON cursor for targeted recalc
- 20 tests pass (all test classes: TestTransactionList 11, TestClassificationEdit 3, TestReviewQueue 3, TestApplyChanges 3)
- Full test suite: 351 passed, 1 skipped

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for transaction ledger** - `bdfca79` (test)
2. **Task 1+2 GREEN: Transaction ledger + classification + review + apply-changes** - `24bba33` (feat)

## Files Created/Modified

- `api/schemas/transactions.py` - 6 Pydantic schemas for transaction endpoints
- `api/routers/transactions.py` - 4 endpoints: list, review, PATCH classification, apply-changes
- `tests/test_api_transactions.py` - 20 tests covering all endpoint behaviors
- `api/routers/__init__.py` - replaced transactions stub with `from api.routers.transactions import router as transactions_router`

## Decisions Made

- **GET /review before /{tx_hash}/classification:** FastAPI route matching is order-dependent; the literal `/review` path must be registered before the `/{tx_hash}` path parameter to prevent "review" being parsed as a tx_hash value.
- **UNION ALL with COUNT(*) OVER():** Single-pass pagination — total count returned alongside paginated rows without a second COUNT query. Same pattern confirmed in reports/ledger.py.
- **Dynamic UPDATE set_clauses:** Build list of clauses only for non-None fields; avoids setting columns to NULL when they're not in the request body.
- **JSON cursor for calculate_acb:** Stores `{"token_symbols": [...]}` in the indexing_jobs.cursor TEXT column so ACBHandler can extract the targeted token list without an extra join.
- **exchange_transactions via tc.tx_hash = et.tx_id:** Matches the existing pattern in reports/ledger.py — transaction_classifications stores the exchange tx_id in the tx_hash column for exchange-sourced rows.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Note on Route Registration Order

The plan specified two separate tasks but the /review route was implemented in Task 1 alongside the list endpoint (because it uses the same UNION ALL infrastructure). Task 2 added PATCH classification and POST apply-changes as specified. All 20 tests were written upfront in the RED phase covering both tasks.

## Self-Check: PASSED

All files verified present:
- api/schemas/transactions.py: FOUND
- api/routers/transactions.py: FOUND
- tests/test_api_transactions.py: FOUND

All commits verified:
- bdfca79 (test RED): FOUND
- 24bba33 (feat GREEN): FOUND
