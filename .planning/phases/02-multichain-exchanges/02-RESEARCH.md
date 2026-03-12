# Phase 2: Multi-Chain + Exchanges - Research

**Researched:** 2026-03-12
**Domain:** EVM chain indexing (Etherscan V2 API), exchange CSV parsing, PostgreSQL migration, job queue integration
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Chain Coverage:**
- Support ALL chains from current wallet inventory: ETH, Polygon, Optimism, Cronos, Akash (Cosmos SDK), XRP (Ripple), Sweat (NEAR-based)
- Full transaction history for every chain — not just basic transfers. Every taxable event must be captured
- Design for Koinly-level chain support over time — BTC (UTXO-based), Solana, and any chain users connect
- Plugin architecture: chain registry with standard interface (fetch_transactions, get_balance, etc.) — each chain is a plugin
- Plugin interface must accommodate different chain models: account-based (ETH, NEAR), UTXO-based (BTC), and unique models (Solana)

**Exchange Integration:**
- Two ingestion modes per exchange: (1) API connection when available, (2) AI-powered file ingestion as universal fallback
- Build API connectors for ALL exchanges that support APIs (Coinbase, Crypto.com, Wealthsimple, Uphold, Coinsquare, Bitbuy — research which have viable APIs)
- Unified plugin pattern for exchanges — same interface concept as chain plugins: connect(), fetch_transactions(), get_balances()
- Auto-sync on schedule once connected (same job queue pattern as NEAR indexer)
- Exchange API credentials encrypted at rest in PostgreSQL
- Tag all transactions with their source (exchange name, chain, import batch) for reports and dashboards

**AI-Powered File Ingestion:**
- AI agent extraction team for processing exchange export files
- Supports ANY file format: CSV, PDF, XLSX, DOC, etc.
- User experience: drop all export files into one dialog (Phase 7 UI) or POST to API endpoint (Phase 2)
- AI agent parses each file, removes irrelevant data, extracts transaction data accurately
- Auto-commit with confidence score — never lose data, never block on user input
- Low-confidence transactions get 'needs_review' flag with AI recommendation for acceptance or modification
- Smart routing: traditional parsers handle known simple formats, AI agent handles unknown/complex formats

**Transaction Processing:**
- Parallel file processing — each file gets its own job in the queue
- End result must be a unified, chronologically correct set of transactions across ALL ingestion sources
- Cross-source deduplication — detect when same transaction appears from multiple sources (e.g., Coinbase CSV + ETH on-chain receive). Link together, don't double-count
- Idempotent re-import — skip duplicates, add only new transactions when same file is imported again

**EVM Contract Decoding:**
- AI-powered decoding for contract interactions — find contract source, understand how transactions are built and executed
- Record individual transaction steps for proper classification (e.g., DeFi swap = sell token A + buy token B + pay fee)
- Smart cost routing: use traditional decoders (ABI, method signatures) for simple transfers/swaps, route genuinely complex transactions to AI agent
- Unknown contract interactions imported with review flag, not skipped

### Claude's Discretion
- Specific chain plugin interface design (method signatures, error handling patterns)
- AI agent orchestration framework (single agent vs multi-agent, tool selection)
- Confidence score thresholds for auto-commit vs review flag
- Exchange API library choices
- Rate limiting strategy per exchange API
- How to handle chains with limited API availability (Akash, Sweat)
- Contract ABI caching strategy
- File format detection approach

### Deferred Ideas (OUT OF SCOPE)
- Per-minute price tables for all tokens (pre-build as background job)
- Email/notification alerts for sync failures
- Exchange-specific advanced features (Coinbase Pro margin trades, etc.)
- NFT valuation beyond transfer tracking
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DATA-04 | System can pull EVM transaction history via Etherscan/Polygonscan APIs | EVMIndexer class exists, needs PostgreSQL migration + job queue registration |
| DATA-05 | System can parse exchange CSV exports (Coinbase, Crypto.com, Bitbuy, Coinsquare, Wealthsimple, Uphold) | BaseExchangeParser + Coinbase complete, remaining parsers need PostgreSQL migration and validation against real CSVs |
</phase_requirements>

---

## Summary

Phase 2 inherits a substantial amount of working code from prior development, but all of it targets SQLite or mixed patterns. The primary work is migrating four categories of code to the Phase 1 PostgreSQL/job-queue architecture: (1) `EVMIndexer` — an Etherscan V2 client that fetches normal transactions, internal transactions, ERC20 transfers, and NFT transfers, (2) `BaseExchangeParser` and its subclasses (Coinbase complete, Crypto.com/Wealthsimple/Uphold/Coinsquare exist but need validation), (3) exchange API connectors (Coinbase connector exists with SQLite pattern), and (4) new Alembic migrations for EVM and exchange tables.

The chain plugin architecture decision requires designing a uniform `ChainFetcher` abstract base class that can express both account-based chains (EVM, NEAR, Cosmos SDK, XRP) and wraps each as a registered handler in `service.py`. The job queue pattern from Phase 1 (`full_sync`/`incremental_sync` job types, cursor resume, `FOR UPDATE SKIP LOCKED`) must be extended to cover EVM chains (block-number cursor), exchange CSV imports (batch-ID cursor), and eventually XRP/Akash (ledger/pagination cursor).

The exchange table schema in `db/schema_evm.sql` and `db/schema_exchanges.sql` is SQLite DDL and must be translated into a new Alembic migration (`002`). The key design decisions for the migration are: (a) `exchange_transactions` should carry `user_id` FK (consistent with all Phase 1 tables), (b) `evm_transactions` should join `wallets` (not maintain a separate `evm_wallets` table), and (c) `exchange_connections` replaces `exchange_credentials` and must be joined to `supported_exchanges` (the web API already references these table names).

**Primary recommendation:** Migrate EVMIndexer and exchange parsers to use `indexers/db.py` + `wallets` table + job queue, add one Alembic migration (002) for all new tables, then register EVM and exchange sync handlers in `service.py`. Defer AI agent ingestion to a self-contained sub-plan.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg2-binary | >=2.9.9 | PostgreSQL driver (already in requirements.txt) | Project standard from Phase 1 |
| SQLAlchemy | >=2.0.0 | ORM / model declarations (already in requirements.txt) | Project standard from Phase 1 |
| alembic | >=1.13.0 | Schema migrations (already in requirements.txt) | Project standard — 001 migration already exists |
| requests | >=2.31.0 | HTTP client for Etherscan V2, XRPL, Cosmos LCD (already in requirements.txt) | Project standard |
| anthropic | latest | Claude API for AI agent file ingestion | Required for AI-powered parsing path |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| openpyxl | >=3.1.0 | XLSX parsing for exchange exports | When exchange exports XLSX (Wealthsimple, Coinsquare may) |
| pdfplumber or pypdf | latest | PDF parsing for exchange exports | When AI agent needs PDF text extraction before Claude API call |
| python-multipart | >=0.0.9 | File upload handling in FastAPI | For POST /api/upload-file endpoint |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| requests (sync) | aiohttp (async) | aiohttp is in requirements.txt but all existing indexers use requests; keeping sync avoids refactor |
| Separate evm_wallets table | Reuse wallets table with chain column | wallets already has chain column + user_id FK — reuse avoids schema complexity |
| Separate exchange_credentials table | exchange_connections table | Web API already references exchange_connections and supported_exchanges; use those names |

**Installation:**
```bash
pip install anthropic openpyxl pdfplumber python-multipart
```

---

## Architecture Patterns

### Recommended Project Structure

The existing structure is correct. New files slot into established locations:

```
indexers/
├── evm_fetcher.py          # Migrated EVMIndexer — uses wallets table + job queue (replaces evm_indexer.py pattern)
├── exchange_sync.py        # ExchangeSyncHandler — API connector scheduler (registered in service.py)
├── file_ingestion.py       # AI-powered file ingestion agent
├── exchange_parsers/
│   ├── base.py             # Already exists — needs PostgreSQL migration
│   ├── coinbase.py         # Already complete — needs PostgreSQL migration
│   ├── crypto_com.py       # Already exists — needs PostgreSQL migration + validation
│   ├── wealthsimple.py     # Already exists — needs PostgreSQL migration + validation
│   ├── generic.py          # Already exists (includes Uphold + Coinsquare as aliases)
│   └── bitbuy.py           # New — no existing implementation
├── exchange_connectors/
│   ├── coinbase.py         # Already exists — needs PostgreSQL migration
│   ├── cryptocom.py        # Already exists — needs PostgreSQL migration
│   └── kraken.py           # Already exists
db/
├── migrations/
│   └── versions/
│       ├── 001_initial_schema.py   # EXISTS — Phase 1 tables
│       └── 002_multichain_exchanges.py  # NEW — EVM + exchange tables
├── models.py               # Add EvmTransaction, ExchangeTransaction, ExchangeConnection, SupportedExchange
```

### Pattern 1: Chain Fetcher Plugin Interface

All chain fetchers implement a uniform interface so `service.py` can dispatch generically.

The Phase 1 `NearFetcher` provides the reference pattern. EVM fetcher must mirror it:

```python
# Source: indexers/near_fetcher.py (existing pattern)
class EVMFetcher:
    """Registered in service.py handlers dict for EVM job types."""

    def __init__(self, pool: SimpleConnectionPool):
        self.pool = pool

    def sync_wallet(self, job: dict) -> None:
        """
        Process a full_sync or incremental_sync job for an EVM wallet.

        job dict keys (from _claim_next_job):
          - wallet_id: int
          - user_id: int
          - chain: str  ('ethereum', 'polygon', 'optimism', 'cronos')
          - cursor: str | None  — last indexed block number (resume point)
          - job_type: 'full_sync' | 'incremental_sync'
        """
        # 1. Resolve chain config from job['chain']
        # 2. Determine start_block from job['cursor'] or 0
        # 3. Call Etherscan V2 for normal/internal/ERC20/NFT txs
        # 4. Upsert into transactions table (ON CONFLICT DO NOTHING)
        # 5. Update job cursor to max_block_seen
        # 6. Update job progress_fetched
```

**service.py registration** (new entries in `__init__`):
```python
from indexers.evm_fetcher import EVMFetcher

self.handlers = {
    # Existing NEAR handlers
    "full_sync":        NearFetcher(self.pool),
    "incremental_sync": NearFetcher(self.pool),
    "staking_sync":     StakingFetcher(self.pool, self.price_service),
    "lockup_sync":      LockupFetcher(self.pool, self.price_service),
    # Phase 2: EVM handlers
    "evm_full_sync":    EVMFetcher(self.pool),
    "evm_incremental":  EVMFetcher(self.pool),
    # Phase 2: Exchange sync handler
    "exchange_sync":    ExchangeSyncHandler(self.pool),
    # Phase 2: File ingestion handler
    "file_import":      FileIngestionHandler(self.pool),
}
```

**Dispatch** in `service.py run()` needs a new branch:
```python
elif job_type in ("evm_full_sync", "evm_incremental"):
    handler.sync_wallet(job)
elif job_type == "exchange_sync":
    handler.sync_exchange(job)
elif job_type == "file_import":
    handler.process_file(job)
```

### Pattern 2: EVM Transactions in the Unified `transactions` Table

The existing `transactions` table (from Phase 1 migration 001) already has `chain`, `tx_hash`, `receipt_id`, `wallet_id`, `user_id`, `direction`, `counterparty`, `action_type`, `method_name`, `amount`, `fee`, `block_height`, `block_timestamp`, `raw_data` (JSONB).

EVM transactions map cleanly to this schema:
- `chain` = 'ethereum' | 'polygon' | 'optimism' | 'cronos'
- `tx_hash` = Etherscan `hash`
- `receipt_id` = NULL (no receipt concept in EVM)
- `direction` = 'in' if `to_address == wallet_address` else 'out'
- `counterparty` = `to_address` or `from_address` (opposite of direction)
- `action_type` = 'transfer' | 'erc20' | 'internal' | 'nft'
- `method_name` = contract method if decoded, else NULL
- `amount` = value in wei (NUMERIC(40,0)) — already correct type
- `fee` = gas_used * gas_price in wei
- `block_height` = blockNumber
- `block_timestamp` = BigInteger (unix timestamp)
- `raw_data` = JSONB of raw Etherscan response

This means **no new `evm_transactions` table is needed** — the Phase 1 `transactions` table is the target. The unique constraint `(chain, tx_hash, receipt_id, wallet_id)` handles deduplication.

**ERC20 and NFT transfers** need a separate row per transfer event since multiple token transfers can occur within one parent tx_hash. Use a composite unique key: `tx_hash + '-' + log_index` as the effective hash stored in `tx_hash` column (matches existing evm_indexer.py pattern).

### Pattern 3: Exchange Transactions Table

The web API (`/api/exchanges/`) already references `exchange_connections` and `supported_exchanges` tables. A new Alembic migration must create these tables plus `exchange_transactions`:

```python
# Migration 002 tables needed:

# exchange_transactions — stores all exchange CSV + API-imported transactions
CREATE TABLE exchange_transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    exchange VARCHAR(50) NOT NULL,          -- 'coinbase', 'crypto_com', etc.
    tx_id VARCHAR(256),                     -- exchange's internal ID (dedup key)
    tx_date TIMESTAMPTZ NOT NULL,
    tx_type VARCHAR(50),                    -- 'buy', 'sell', 'send', 'receive', etc.
    asset VARCHAR(50) NOT NULL,
    quantity NUMERIC(30, 10) NOT NULL,
    price_per_unit NUMERIC(24, 10),
    total_value NUMERIC(24, 10),
    fee NUMERIC(24, 10),
    fee_asset VARCHAR(20),
    currency VARCHAR(10) DEFAULT 'CAD',
    notes TEXT,
    raw_data JSONB,
    import_batch VARCHAR(128),
    source VARCHAR(20) DEFAULT 'csv',       -- 'csv', 'api', 'ai_agent'
    confidence_score NUMERIC(4,3),          -- 0.000-1.000, NULL = traditional parser
    needs_review BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, exchange, tx_id)        -- dedup by exchange + tx ID
)

# exchange_connections — replaces exchange_credentials (web API uses this name)
CREATE TABLE exchange_connections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    exchange VARCHAR(50) NOT NULL,
    display_name VARCHAR(128),
    api_key TEXT NOT NULL,                  -- will be encrypted
    api_secret TEXT,                        -- will be encrypted
    additional_config JSONB,
    status VARCHAR(20) DEFAULT 'active',
    last_sync_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, exchange)
)

# supported_exchanges — catalog of available exchange integrations
CREATE TABLE supported_exchanges (
    id VARCHAR(50) PRIMARY KEY,             -- 'coinbase', 'crypto_com', etc.
    name VARCHAR(128) NOT NULL,
    logo_url VARCHAR(512),
    requires_api_key BOOLEAN DEFAULT TRUE,
    requires_api_secret BOOLEAN DEFAULT FALSE,
    additional_fields JSONB,
    help_url VARCHAR(512),
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0
)
```

### Pattern 4: BaseExchangeParser PostgreSQL Migration

The existing `base.py` uses `db.init.get_connection()` which now points to PostgreSQL via `indexers/db.py`. But the INSERT query uses `?` placeholders (SQLite) instead of `%s` (psycopg2). This is the critical migration fix:

```python
# Source: indexers/exchange_parsers/base.py (current — WRONG for PostgreSQL)
conn.execute("INSERT INTO exchange_transactions (...) VALUES (?, ?, ...)")

# Correct PostgreSQL pattern (matches indexers/db.py):
with db_cursor() as cur:
    cur.execute("""
        INSERT INTO exchange_transactions
            (user_id, exchange, tx_id, tx_date, tx_type, asset, quantity,
             price_per_unit, total_value, fee, fee_asset, currency,
             notes, raw_data, import_batch, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, exchange, tx_id) DO NOTHING
    """, (...))
```

The `import_to_db` method in `BaseExchangeParser` also needs `user_id` as a parameter since all Phase 1 data tables require `user_id`.

### Pattern 5: Job Queue for File Imports

Each file upload becomes a `file_import` job in `indexing_jobs`. This gives resumability, retry, and visibility in the sync status UI.

```python
# Enqueueing a file import (in web API POST /api/upload-file)
# 1. Save file to a temporary location (or object storage path)
# 2. Insert job with cursor = file_path, chain = 'exchange', job_type = 'file_import'
INSERT INTO indexing_jobs (user_id, wallet_id, job_type, chain, status, cursor, priority)
VALUES (%s, %s, 'file_import', 'exchange', 'queued', %s, 5)
-- cursor stores the file path or storage key
-- wallet_id can reference a special "exchange" wallet row
```

### Anti-Patterns to Avoid

- **SQLite placeholders (`?`) in psycopg2 queries:** All existing exchange connector files (`indexers/exchange_connectors/coinbase.py`) use `?` — these WILL silently fail or error in PostgreSQL. Use `%s` throughout.
- **Separate chain-specific wallet tables:** The `evm_wallets` table in `schema_evm.sql` should not be recreated. Use the unified `wallets` table with `chain` column.
- **Using `db.init.get_connection()` instead of `indexers.db`:** `db/init.py` is the old SQLite path. All new code uses `indexers/db.py` (PostgreSQL pool).
- **Storing raw_data as TEXT:** Phase 1 decision: always use JSONB, not TEXT, for `raw_data`.
- **Blocking the job queue on file I/O:** Parse files synchronously within the job handler — don't spawn subprocesses. psycopg2 is not thread-safe without connection pools.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSV delimiter detection | Custom sniffer | `csv.Sniffer` (already in base.py) | Already handles comma/semicolon/tab |
| PostgreSQL deduplication | Custom check-then-insert | `ON CONFLICT DO NOTHING` / `ON CONFLICT DO UPDATE` | Atomic, no race condition |
| File format detection | Magic byte sniffing | Check file extension + try-parse approach | Exchanges use consistent formats |
| Exchange API auth (HMAC) | Custom signing | Use existing `CoinbaseConnector._sign_request()` pattern | Already implemented |
| Backoff/retry | Manual sleep loops | Job queue `_mark_failed_or_retry()` | Already implemented with exponential backoff |
| AI response parsing | Custom JSON extractors | Structured output via Claude API `response_format` | More reliable than regex on free-form text |

**Key insight:** The job queue infrastructure handles all retry, backoff, and visibility concerns. File imports should be thin handlers that parse + bulk-insert, then let the job queue handle failure recovery.

---

## Common Pitfalls

### Pitfall 1: SQLite vs PostgreSQL Placeholder Mismatch
**What goes wrong:** `evm_indexer.py`, `exchange_connectors/coinbase.py`, and parts of `exchange_parsers/base.py` all use `?` as SQL parameter placeholder. psycopg2 requires `%s`. Running these files against PostgreSQL raises `ProgrammingError: syntax error at or near "?"`.
**Why it happens:** All these files predate Phase 1's PostgreSQL migration. They reference `db.init.get_connection()` (SQLite path) or contain SQLite DDL.
**How to avoid:** Grep all files being migrated for `?` in SQL strings and replace with `%s`. Use `indexers/db.py`'s `db_cursor()` context manager, never `db.init.get_connection()`.
**Warning signs:** Any file importing from `db.init` (not `indexers.db`) is using the wrong path.

### Pitfall 2: Etherscan V2 Pagination — 10,000 Row Limit
**What goes wrong:** Etherscan API returns maximum 10,000 transactions per page for `txlist`, `tokentx`, `txlistinternal`. Wallets with >10,000 transactions silently truncate.
**Why it happens:** The existing `EVMIndexer.get_normal_transactions()` does not paginate — it makes one request and returns up to 10,000 rows.
**How to avoid:** Use `offset` and `page` params to loop until result count < page size. Cursor = last `blockNumber` seen. Free tier rate limit is 5 req/sec; with 0.25s delay (existing) this is safe.
**Warning signs:** A wallet with many transactions reports fewer than expected after indexing.

### Pitfall 3: Optimism/Arbitrum/Base Require Paid Etherscan Plan
**What goes wrong:** Requesting chain ID 10 (Optimism), 42161 (Arbitrum), or 8453 (Base) via Etherscan V2 free tier returns `"This endpoint is not supported on the free tier"`.
**Why it happens:** Etherscan V2 free tier only supports ETH (1) and Polygon (137) natively. Optimism and others require an upgraded plan or their own explorer APIs.
**How to avoid:** The existing `CHAIN_CONFIG['free_tier']` flag is correct. In `service.py`, check `free_tier` before queueing EVM jobs, or let the job fail gracefully and log the reason.
**Warning signs:** Jobs for Optimism/Arbitrum fail immediately with paid plan error.

### Pitfall 4: Cronos Uses Separate API Endpoint
**What goes wrong:** Using Etherscan V2 `chainid=25` for Cronos returns an error — Cronos is not on the Etherscan network.
**Why it happens:** Cronos has its own block explorer at `https://cronos.org/explorer/api`. The existing `CHAIN_CONFIG['Cronos']['custom_api']` already handles this correctly, but any refactor must preserve the `custom_api` override.
**How to avoid:** Keep the `custom_api` / `api_key_env` pattern in CHAIN_CONFIG when migrating EVMIndexer.

### Pitfall 5: Exchange CSV Column Name Instability
**What goes wrong:** Coinbase, Crypto.com, and Wealthsimple periodically change their CSV export column names (capitalization, spacing, added/removed columns). A parser that relies on exact column names breaks silently.
**Why it happens:** Exchanges update their export formats without notice.
**How to avoid:** The existing parsers already use `.get('Timestamp') or .get('timestamp') or .get('Date')` multi-key fallback pattern — preserve and extend this. Log a warning (not error) when a row yields `None` from `parse_row()`. Count and report skipped rows.

### Pitfall 6: Duplicate Transactions from Multiple Sources
**What goes wrong:** A user's ETH receive transaction appears in both the on-chain Etherscan data AND in the Coinbase CSV export. Naively importing both creates a double-count.
**Why it happens:** Exchanges record their sends/receives which also appear on-chain.
**How to avoid:** Add a `cross_source_dedup` step after import that joins `transactions` (on-chain) with `exchange_transactions` by (asset, amount, timestamp ± 10 minutes, direction). Link matched pairs with a `dedup_link_id` column (or a separate `tx_links` table), mark one as `is_duplicate = true`.
**Warning signs:** Running an ACB calculation later produces unexpectedly high balances.

### Pitfall 7: exchange_connections Table Not Seeded
**What goes wrong:** The web API GET `/api/exchanges` queries `supported_exchanges` for the catalog. If this table is empty, the UI shows no supported exchanges.
**Why it happens:** The table is new; there's no seed data.
**How to avoid:** Include an Alembic data migration (or seed script) that inserts the supported exchange catalog: coinbase, crypto_com, wealthsimple, uphold, coinsquare, bitbuy.

---

## Code Examples

Verified patterns from the existing codebase:

### Correct PostgreSQL upsert pattern (from near_fetcher.py)
```python
# Source: indexers/near_fetcher.py (Phase 1 reference)
from psycopg2.extras import execute_values

execute_values(
    cur,
    """
    INSERT INTO transactions
        (user_id, wallet_id, tx_hash, receipt_id, chain, direction,
         counterparty, action_type, method_name, amount, fee, token_id,
         block_height, block_timestamp, success, raw_data)
    VALUES %s
    ON CONFLICT (chain, tx_hash, receipt_id, wallet_id) DO NOTHING
    """,
    rows,
    template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
```

### Job cursor update pattern (from near_fetcher.py / service.py)
```python
# Source: indexers/service.py — job cursor update pattern
cur.execute(
    """
    UPDATE indexing_jobs
    SET cursor = %s,
        progress_fetched = progress_fetched + %s,
        updated_at = NOW()
    WHERE id = %s
    """,
    (str(max_block_seen), rows_inserted, job["id"]),
)
```

### Etherscan V2 chain request pattern (from evm_indexer.py — correct, keep)
```python
# Source: indexers/evm_indexer.py (existing correct logic)
ETHERSCAN_V2_URL = 'https://api.etherscan.io/v2/api'

params = {
    'module': 'account',
    'action': 'txlist',
    'address': address,
    'startblock': str(start_block),
    'endblock': '99999999',
    'sort': 'asc',
    'chainid': str(self.config['chainid']),  # V2 uses chainid param
}
if self.api_key:
    params['apikey'] = self.api_key
```

### EVM transaction direction determination
```python
# Determine direction for unified transactions table
wallet_lower = wallet_address.lower()
from_lower = tx.get('from', '').lower()
to_lower = (tx.get('to') or '').lower()

if to_lower == wallet_lower:
    direction = 'in'
    counterparty = from_lower
elif from_lower == wallet_lower:
    direction = 'out'
    counterparty = to_lower
else:
    direction = 'in'   # internal tx, treat as received
    counterparty = from_lower
```

### Fee calculation (gas_used * gas_price in wei — NUMERIC(40,0))
```python
# Both gas_used and gas_price are string integers from Etherscan
gas_used = int(tx.get('gasUsed', '0'))
gas_price = int(tx.get('gasPrice', '0'))
fee_wei = gas_used * gas_price  # store as NUMERIC(40,0)
```

### Exchange CSV parser PostgreSQL migration pattern
```python
# Corrected base.py import_to_db method
from indexers.db import db_cursor   # NOT db.init.get_connection

def import_to_db(self, filepath: str, user_id: int, batch_id: str = None) -> dict:
    batch_id = batch_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    transactions = self.parse_file(filepath)
    imported = 0

    with db_cursor() as cur:
        for tx in transactions:
            cur.execute("""
                INSERT INTO exchange_transactions
                    (user_id, exchange, tx_id, tx_date, tx_type, asset, quantity,
                     price_per_unit, total_value, fee, fee_asset, currency,
                     notes, import_batch, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'csv')
                ON CONFLICT (user_id, exchange, tx_id) DO NOTHING
            """, (user_id, self.exchange_name, tx.get('tx_id'), ...))
            imported += 1

    return {'imported': imported, 'errors': len(self.errors), 'batch_id': batch_id}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Etherscan V1 (api.etherscan.io/api) | Etherscan V2 (api.etherscan.io/v2/api with chainid param) | Aug 2025 | V1 deprecated; evm_indexer.py already uses V2 correctly |
| SQLite via `db.init.get_connection()` | PostgreSQL via `indexers.db.db_cursor()` | Phase 1 | All new code must use indexers.db, not db.init |
| Standalone indexer scripts (`if __name__ == '__main__'`) | IndexerService job queue polling | Phase 1 | Chain fetchers become handlers registered in service.py |
| `?` SQL placeholders | `%s` SQL placeholders | Phase 1 | psycopg2 requires %s; all migrated files need this change |
| Separate evm_wallets table | wallets table with chain column | Phase 1 design | Eliminates table proliferation |

**Deprecated/outdated:**
- `db/init.py` `get_connection()`: returns SQLite connection; do not use in any Phase 2 code
- `schema_evm.sql` / `schema_exchanges.sql`: SQLite DDL; replaced by Alembic migration 002
- `exchange_credentials` table: web API uses `exchange_connections`; use that name
- `evm_indexing_progress` table: phase 1 job queue cursor in `indexing_jobs` replaces this

---

## Exchange API Availability Assessment

Based on code inspection and known exchange capabilities (confidence: MEDIUM — needs validation against actual APIs):

| Exchange | API Available | Notes |
|----------|---------------|-------|
| Coinbase | YES | Advanced Trade API at api.coinbase.com/v2; connector exists in `indexers/exchange_connectors/coinbase.py` |
| Crypto.com | YES | Exchange API exists; connector skeleton in `indexers/exchange_connectors/cryptocom.py` |
| Kraken | YES | REST API well-documented; `indexers/exchange_connectors/kraken.py` exists |
| Wealthsimple | NO (likely) | Wealthsimple does not publish a public crypto API; CSV is the primary path |
| Uphold | PARTIAL | Uphold has an API but crypto transaction history access requires OAuth, non-trivial |
| Coinsquare | NO | No public API; CSV only |
| Bitbuy | UNKNOWN | Canadian exchange; no connector found — research needed |

**Recommendation:** For Phase 2, implement CSV path for all exchanges (it's the guaranteed path). API connectors for Coinbase and Crypto.com are bonus deliverables if API keys are available.

---

## Open Questions

1. **Sweat Economy (NEAR-based) chain support**
   - What we know: Sweat is NEAR-based, so `near_fetcher.py` may already handle it via account_id
   - What's unclear: Sweat uses NEAR protocol but has its own token/staking contracts — does the NEAR indexer already capture Sweat transactions?
   - Recommendation: Treat Sweat wallet as a NEAR wallet; verify Sweat token transfers appear via NearBlocks FUNCTION_CALL actions

2. **Bitbuy CSV format**
   - What we know: No existing parser. No CSV sample available.
   - What's unclear: Column names and transaction type values
   - Recommendation: Implement via `GenericParser` as `BitbuyParser(GenericParser)` alias; refine once CSV sample is available

3. **Akash (Cosmos SDK) — Phase 2 scope vs Phase 3**
   - What we know: `akash_indexer.py` exists with Cosmos LCD client; references missing `xrp_wallets` table (wrong table)
   - What's unclear: Whether Akash needs to be in Phase 2 deliverables or can follow EVM
   - Recommendation: Include Akash in the chain plugin registration for Phase 2 (it's in the wallet inventory) but treat its `sync_wallet` as low-priority — it has no rate limits and complete API access

4. **AI Agent: which Claude model and tool configuration**
   - What we know: The Anthropic Python SDK is available; claude-sonnet-4-6 (current model) is appropriate
   - What's unclear: Whether to use tool-calling, structured output, or a multi-turn agent pattern
   - Recommendation: Use single-turn structured output with `response_format={"type": "json_object"}` for file parsing; multi-agent is overkill for CSV/PDF extraction

5. **cross-source deduplication timing**
   - What we know: Same transaction may appear in both on-chain data and exchange CSV
   - What's unclear: Whether deduplication should run at import time or as a separate post-processing step
   - Recommendation: Run deduplication as a separate post-import job (own `job_type = 'dedup_scan'`) — cleaner separation of concerns

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (inferred from tests/ directory structure and test_near_fetcher.py / test_price_service.py) |
| Config file | none detected — pytest runs with defaults |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-04 | EVMFetcher.sync_wallet processes full_sync job and inserts into transactions table | unit | `pytest tests/test_evm_fetcher.py -x` | No — Wave 0 |
| DATA-04 | EVMFetcher handles Etherscan pagination (>10k txs) without truncation | unit | `pytest tests/test_evm_fetcher.py::test_pagination -x` | No — Wave 0 |
| DATA-04 | Calculated EVM balance matches on-chain balance after import | integration/smoke | `pytest tests/test_evm_fetcher.py::test_balance_reconciliation -x` | No — Wave 0 |
| DATA-05 | CoinbaseParser.parse_file() correctly maps all known Coinbase transaction types | unit | `pytest tests/test_exchange_parsers.py::test_coinbase -x` | No — Wave 0 |
| DATA-05 | CryptoCom App format and Exchange format both parsed correctly | unit | `pytest tests/test_exchange_parsers.py::test_crypto_com -x` | No — Wave 0 |
| DATA-05 | Wealthsimple parser handles CAD-only transactions | unit | `pytest tests/test_exchange_parsers.py::test_wealthsimple -x` | No — Wave 0 |
| DATA-05 | GenericParser auto-detects Uphold and Coinsquare formats | unit | `pytest tests/test_exchange_parsers.py::test_generic -x` | No — Wave 0 |
| DATA-05 | import_to_db uses %s placeholders, inserts with user_id, deduplicates on re-import | unit | `pytest tests/test_exchange_parsers.py::test_import_dedup -x` | No — Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_evm_fetcher.py tests/test_exchange_parsers.py -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_evm_fetcher.py` — covers DATA-04 (mock Etherscan API responses, verify inserts)
- [ ] `tests/test_exchange_parsers.py` — covers DATA-05 (fixture CSV rows for each exchange parser)
- [ ] `tests/fixtures/` — sample CSV fixture rows for coinbase, crypto_com, wealthsimple, generic parsers
- [ ] `pytest.ini` or `pyproject.toml [tool.pytest]` — add testpaths configuration

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `indexers/evm_indexer.py` — Etherscan V2 API client, CHAIN_CONFIG, pagination gaps identified
- Direct code inspection: `indexers/exchange_parsers/base.py`, `coinbase.py`, `crypto_com.py`, `wealthsimple.py`, `generic.py` — complete parser implementations, SQLite migration issues identified
- Direct code inspection: `indexers/service.py` — job queue dispatch pattern, handler registration pattern
- Direct code inspection: `indexers/near_fetcher.py` — reference implementation for chain plugin interface
- Direct code inspection: `db/models.py`, `db/migrations/versions/001_initial_schema.py` — Phase 1 schema, confirmed `transactions` table accommodates EVM data
- Direct code inspection: `indexers/exchange_connectors/coinbase.py` — SQLite placeholder issue confirmed
- Direct code inspection: `web/app/api/exchanges/route.ts` — confirmed `exchange_connections` and `supported_exchanges` table names expected
- Direct code inspection: `db/schema_evm.sql`, `db/schema_exchanges.sql` — confirmed SQLite DDL, needs Alembic migration

### Secondary (MEDIUM confidence)
- Code inspection `indexers/evm_indexer.py` docstring: "Updated Feb 2026: Etherscan deprecated V1 API (Aug 2025). Now uses unified V2 endpoint with chainid parameter."
- Code inspection `indexers/xrp_indexer.py` + `indexers/akash_indexer.py` — confirmed public API patterns for XRP and Cosmos chains
- `web/app/api/wallets/route.ts` — confirmed Phase 2 comment noting EVM tables expected from Phase 2

### Tertiary (LOW confidence — needs validation)
- Exchange API availability table above: Wealthsimple, Uphold, Coinsquare, Bitbuy assessments based on general knowledge, not current documentation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in requirements.txt; only additions are anthropic, openpyxl, pdfplumber
- Architecture: HIGH — patterns read directly from existing codebase
- Pitfalls: HIGH — SQLite vs PostgreSQL issues identified from actual code; Etherscan limits from API docs in code comments
- Exchange API availability: LOW — no live API testing performed

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (30 days; Etherscan API and exchange formats are stable)
