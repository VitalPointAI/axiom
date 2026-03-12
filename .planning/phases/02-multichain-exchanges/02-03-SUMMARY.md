---
phase: 02-multichain-exchanges
plan: 03
subsystem: exchange-parsers
tags: [parsers, postgresql, csv, tdd, exchange]
dependency_graph:
  requires: [02-01]
  provides: [exchange-csv-parsers-postgresql]
  affects: [file-import-job-handler]
tech_stack:
  added: []
  patterns: [psycopg2-pool, ON-CONFLICT-DO-NOTHING, JSONB-raw-data, TDD-red-green]
key_files:
  created:
    - tests/test_exchange_parsers.py
    - tests/fixtures/exchange_csv_samples.py
  modified:
    - indexers/exchange_parsers/base.py
    - indexers/exchange_parsers/coinbase.py
    - indexers/exchange_parsers/crypto_com.py
    - indexers/exchange_parsers/wealthsimple.py
    - indexers/exchange_parsers/generic.py
decisions:
  - "BaseExchangeParser.import_to_db uses pool.getconn()/putconn() in finally block — prevents connection leaks on errors"
  - "tx_id generated deterministically from tx_date+asset+quantity+tx_type when exchange does not provide one"
  - "raw_data stored as dict in parse_row(); serialized to JSON string only at INSERT time — keeps parse_row() output JSONB-ready"
  - "detect() default returns False in BaseExchangeParser — safe opt-in for subclasses"
metrics:
  duration_seconds: 304
  completed_date: "2026-03-12"
  tasks_completed: 2
  files_modified: 7
---

# Phase 2 Plan 03: Exchange Parser PostgreSQL Migration Summary

Migrated all 5 exchange CSV parsers from SQLite to PostgreSQL with full unit test coverage. All parsers now implement the ExchangeParser ABC, use `%s` placeholders, accept `user_id`/`pool` parameters, and insert into `exchange_transactions` with `ON CONFLICT DO NOTHING` deduplication.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for PostgreSQL migration | f1b53cf | tests/test_exchange_parsers.py, tests/fixtures/exchange_csv_samples.py |
| 1 (GREEN) | Migrate all exchange parsers to PostgreSQL | b84b156 | base.py, coinbase.py, crypto_com.py, wealthsimple.py, generic.py |
| 2 | Unit tests for all exchange parsers | f1b53cf | tests/test_exchange_parsers.py, tests/fixtures/exchange_csv_samples.py |

## What Was Built

**BaseExchangeParser (base.py):**
- Removed `from db.init import get_connection` (SQLite), now inherits `ExchangeParser` ABC
- `import_to_db(filepath, user_id, pool, batch_id)` uses `pool.getconn()`/`pool.putconn()` with `finally` block
- SQL uses `%s` throughout; `ON CONFLICT (user_id, exchange, tx_id) DO NOTHING`
- Returns `{imported, skipped, errors, batch_id}`
- `parse_file()` auto-populates `raw_data` as dict if subclass omits it
- `detect()` default returns False; subclasses override

**CoinbaseParser:** Added `detect()` (checks `Timestamp` + `Transaction Type` headers). Returns `raw_data` as dict.

**CryptoComParser:** Added `detect()` for App format (`Timestamp (UTC)` + `Transaction Kind`) and Exchange format (`Trade Date` + `Pair` + `Side`). Returns `raw_data` as dict in all format variants.

**WealthsimpleParser:** Added `detect()` (Date + Type + Asset + Quantity headers, no UTC/Exchange markers). Returns `raw_data` as dict.

**GenericParser / UpholdParser / CoinsquareParser:** Added `detect()` using signature columns — Uphold: `{destination currency, origin currency}`; Coinsquare: `{action, volume}`. Handles Uphold `Destination Currency`/`Destination Amount` columns. Returns `raw_data` as dict.

**Test suite (21 tests, all passing):**
- parse_row tests: CoinbaseParser buy row, raw_data is dict
- parse_file tests: Coinbase, Crypto.com App, Crypto.com Exchange, Wealthsimple, Uphold, Coinsquare
- detect tests: all 5 parsers (positive and negative cases)
- import_to_db mock tests: user_id in params, %s in SQL, ON CONFLICT in SQL, exchange_transactions table, putconn called on error
- compliance tests: no db.init imports, no ? SQL placeholders

## Verification Results

```
python -m pytest tests/test_exchange_parsers.py -x -v
21 passed in 0.06s
```

```
python -c "from indexers.exchange_parsers.base import BaseExchangeParser; ..."
All parsers import OK
```

No `db.init` imports found. No `?` SQL placeholders found.

## Deviations from Plan

### Auto-implemented additions

**1. [Rule 2 - Missing Functionality] tx_id generation when exchange provides none**
- **Found during:** Task 1 implementation
- **Issue:** Coinbase and Wealthsimple CSVs don't have an explicit tx_id column; the plan's INSERT requires a non-null tx_id for the UNIQUE constraint
- **Fix:** BaseExchangeParser generates a deterministic tx_id from `tx_date + asset + quantity + tx_type` when parse_row doesn't provide one
- **Files modified:** indexers/exchange_parsers/base.py
- **Commit:** b84b156

**2. [Rule 2 - Missing Functionality] Uphold Destination Amount extraction**
- **Found during:** Task 1 — UpholdParser test failing
- **Issue:** Generic _find_column didn't correctly prioritize Destination Amount for Uphold
- **Fix:** GenericParser.parse_row() explicitly checks `Destination Amount` before falling back to QUANTITY_COLUMNS
- **Files modified:** indexers/exchange_parsers/generic.py
- **Commit:** b84b156

## Self-Check: PASSED

- [x] tests/test_exchange_parsers.py exists and has 21 passing tests
- [x] tests/fixtures/exchange_csv_samples.py exists
- [x] indexers/exchange_parsers/base.py - no db.init import, uses ExchangeParser ABC
- [x] Commits f1b53cf and b84b156 verified in git log
