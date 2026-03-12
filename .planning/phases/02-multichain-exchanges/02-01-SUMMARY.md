---
phase: 02-multichain-exchanges
plan: 01
subsystem: database
tags: [alembic, postgresql, migration, exchange, abc, plugin, psycopg2]

# Dependency graph
requires:
  - phase: 01-near-indexer
    provides: "Initial Alembic migration 001 with users, wallets, transactions, indexing_jobs tables"
provides:
  - "Alembic migration 002 with exchange_transactions, exchange_connections, supported_exchanges, file_imports tables"
  - "supported_exchanges seeded with 6 exchanges (Coinbase, Crypto.com, Wealthsimple, Uphold, Coinsquare, Bitbuy)"
  - "ChainFetcher ABC defining the contract for all chain fetcher plugins"
  - "ExchangeParser ABC defining the contract for CSV/file-based exchange parsers"
  - "ExchangeConnector ABC defining the contract for exchange API connectors"
affects: [02-02-evm-indexer, 02-03-exchange-parsers, 02-04-ai-ingestion, 02-05-exchange-connectors, 03-transaction-classification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Plugin ABC pattern: chain fetchers subclass ChainFetcher, exchange parsers subclass ExchangeParser"
    - "Alembic op.bulk_insert() for seed data in migrations"
    - "NUMERIC(30,10) for exchange quantities, NUMERIC(4,3) for AI confidence scores"
    - "source column with 'csv'/'api'/'ai_agent' enum for provenance tracking"

key-files:
  created:
    - db/migrations/versions/002_multichain_exchanges.py
    - indexers/chain_plugin.py
    - indexers/exchange_plugin.py
  modified: []

key-decisions:
  - "confidence_score NUMERIC(4,3) NULL for traditional parsers, 0-1 range for AI agent imports"
  - "needs_review BOOLEAN flag enables AI imports to surface low-confidence records for human review"
  - "file_imports.file_hash SHA-256 dedup prevents re-importing the same file by content"
  - "supported_exchanges uses VARCHAR(50) id PK (slug style) not SERIAL — readable foreign keys"
  - "ExchangeParser and ExchangeConnector are separate ABCs (file vs API are distinct operations)"
  - "ChainFetcher.supported_job_types class variable enables self-registration pattern"

patterns-established:
  - "Chain plugin pattern: set chain_name and supported_job_types class vars, implement sync_wallet() and get_balance()"
  - "Exchange parser pattern: implement detect() for auto-routing, parse_file() for extraction, import_to_db() for insertion"
  - "Exchange connector pattern: implement connect() for credential validation, fetch_transactions() for incremental sync"

requirements-completed: [DATA-04, DATA-05]

# Metrics
duration: 4min
completed: 2026-03-12
---

# Phase 2 Plan 01: Multi-Chain + Exchange Schema and Plugin ABCs Summary

**Alembic migration 002 creating 4 exchange/import tables with 6-exchange seed data, plus ChainFetcher, ExchangeParser, and ExchangeConnector abstract base classes defining the plugin contracts for all Phase 2 implementations**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-12T18:34:27Z
- **Completed:** 2026-03-12T18:37:57Z
- **Tasks:** 2/2
- **Files modified:** 3

## Accomplishments
- Created migration 002 extending the Alembic revision chain from 001 with 4 new tables designed for multi-exchange transaction storage, API credentials, exchange catalog, and file import tracking
- Seeded supported_exchanges with 6 Canadian-relevant exchanges (Coinbase, Crypto.com, Wealthsimple, Uphold, Coinsquare, Bitbuy) using op.bulk_insert()
- Defined three plugin ABCs that all Phase 2 concrete implementations must satisfy: ChainFetcher (EVM, Akash, XRP fetchers), ExchangeParser (CSV/file parsers), ExchangeConnector (API connectors)

## Task Commits

Each task was committed atomically:

1. **Task 1: Alembic migration 002** - `572f4f0` (feat)
2. **Task 2: ChainFetcher and Exchange plugin ABCs** - `ad31e10` (feat)

## Files Created/Modified
- `db/migrations/versions/002_multichain_exchanges.py` - Migration 002: exchange_transactions, exchange_connections, supported_exchanges (seeded), file_imports tables
- `indexers/chain_plugin.py` - ChainFetcher ABC with sync_wallet() and get_balance() abstract methods
- `indexers/exchange_plugin.py` - ExchangeParser ABC (detect, parse_file, import_to_db) and ExchangeConnector ABC (connect, fetch_transactions, get_balances)

## Decisions Made
- confidence_score NUMERIC(4,3) is NULL for traditional CSV parsers; non-NULL (0.000-1.000) for AI agent imports so low-confidence records can be surfaced via needs_review flag
- file_imports.UNIQUE(user_id, file_hash) uses SHA-256 content hash for idempotent re-upload protection — same file uploaded twice is a no-op
- supported_exchanges primary key is a VARCHAR slug ('coinbase', 'crypto_com') not a SERIAL integer — makes foreign key references human-readable in exchange_transactions and exchange_connections
- ExchangeParser and ExchangeConnector are separate ABCs because file parsing and API connectivity are orthogonal concerns; some exchanges (Wealthsimple) are CSV-only

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Migration 002 tables are ready for Alembic upgrade when database is available
- ChainFetcher ABC is ready for EVM fetcher implementation (02-02)
- ExchangeParser ABC is ready for CSV parser implementations (02-03)
- ExchangeConnector ABC is ready for Coinbase/Crypto.com API connector implementations (02-05)
- supported_exchanges seed data is in place for UI exchange selection

---
*Phase: 02-multichain-exchanges*
*Completed: 2026-03-12*
