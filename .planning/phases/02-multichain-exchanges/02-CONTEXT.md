# Phase 2: Multi-Chain + Exchanges - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Pull complete transaction history from all blockchain networks (EVM chains, Cronos, Akash, XRP, Sweat) and import exchange transaction data via API connections and AI-powered file ingestion. Build a chain plugin system and exchange plugin system for extensibility. All data flows into PostgreSQL with multi-user isolation, job queue integration, and cross-source deduplication.

</domain>

<decisions>
## Implementation Decisions

### Chain Coverage
- Support ALL chains from current wallet inventory: ETH, Polygon, Optimism, Cronos, Akash (Cosmos SDK), XRP (Ripple), Sweat (NEAR-based)
- Full transaction history for every chain — not just basic transfers. Every taxable event must be captured
- Design for Koinly-level chain support over time — BTC (UTXO-based), Solana, and any chain users connect
- Plugin architecture: chain registry with standard interface (fetch_transactions, get_balance, etc.) — each chain is a plugin
- Plugin interface must accommodate different chain models: account-based (ETH, NEAR), UTXO-based (BTC), and unique models (Solana)

### Exchange Integration
- Two ingestion modes per exchange: (1) API connection when available, (2) AI-powered file ingestion as universal fallback
- Build API connectors for ALL exchanges that support APIs (Coinbase, Crypto.com, Wealthsimple, Uphold, Coinsquare, Bitbuy — research which have viable APIs)
- Unified plugin pattern for exchanges — same interface concept as chain plugins: connect(), fetch_transactions(), get_balances()
- Auto-sync on schedule once connected (same job queue pattern as NEAR indexer)
- Exchange API credentials encrypted at rest in PostgreSQL
- Tag all transactions with their source (exchange name, chain, import batch) for reports and dashboards

### AI-Powered File Ingestion
- AI agent extraction team for processing exchange export files
- Supports ANY file format: CSV, PDF, XLSX, DOC, etc.
- User experience: drop all export files into one dialog (Phase 7 UI) or POST to API endpoint (Phase 2)
- AI agent parses each file, removes irrelevant data, extracts transaction data accurately
- Auto-commit with confidence score — never lose data, never block on user input
- Low-confidence transactions get 'needs_review' flag with AI recommendation for acceptance or modification
- Smart routing: traditional parsers handle known simple formats, AI agent handles unknown/complex formats

### Transaction Processing
- Parallel file processing — each file gets its own job in the queue
- End result must be a unified, chronologically correct set of transactions across ALL ingestion sources
- Cross-source deduplication — detect when same transaction appears from multiple sources (e.g., Coinbase CSV + ETH on-chain receive). Link together, don't double-count
- Idempotent re-import — skip duplicates, add only new transactions when same file is imported again

### EVM Contract Decoding
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

</decisions>

<specifics>
## Specific Ideas

- "Ultimately need to support any chain that a user decides to connect a wallet from" — Koinly-level ambition
- "Create an AI agent extraction and processing team for exchange files" — not just parsers, an agentic system
- "From user perspective, they simply export from an exchange or multiple exchanges and drop all those files into one dialog in Axiom which will then handle processing and ingestion — super simple for the user and complexity abstracted"
- "These transactions are typically time sequenced, so parallel is desirable but only if the end result is going to be a unified chronologically correct set of transactions across all ingestion sources"
- "Find contract source and figure out how the transactions are built and executed to properly record transaction steps for classification"
- "AI recommendation for acceptance or modification along with confidence score" for flagged transactions

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `indexers/evm_indexer.py`: Working Etherscan V2 client with ETH/Polygon/Cronos/Optimism support, rate limiting, incremental sync — needs PostgreSQL migration and job queue integration
- `indexers/exchange_parsers/base.py`: CSV parser framework with BaseExchangeParser ABC (parse_row, parse_file, import_to_db) — needs PostgreSQL migration, will be supplemented by AI agent
- `indexers/exchange_parsers/coinbase.py`: Complete Coinbase CSV parser with type mapping — working but SQLite
- `indexers/exchange_parsers/crypto_com.py`, `wealthsimple.py`, `generic.py`: Exist (may be partial implementations)
- `indexers/service.py`: Standalone indexer service with job queue polling from Phase 1 — chain plugins register here
- `indexers/price_service.py`: Multi-source price service (CoinGecko + CryptoCompare) — reusable for all chains/exchanges
- `indexers/near_fetcher.py`: Reference implementation for chain plugin pattern

### Established Patterns
- Job queue: PostgreSQL-backed indexing_jobs table with cursor-based resume (Phase 1)
- Plugin dispatch: job_type-based handler dispatch in service.py (Phase 1 decision)
- Rate limiting: Adaptive delay based on API key presence (config.py)
- Multi-user: user_id FK on all data tables (Phase 1 schema)
- Price caching: Shared price_cache table, token-agnostic (Phase 1)

### Integration Points
- `indexers/service.py`: Register new chain fetchers and exchange sync handlers
- `db/models.py`: Add EVM, exchange, and multi-chain tables (migrate from SQLite schemas)
- `db/migrations/`: Alembic framework for schema changes
- `web/app/api/`: REST endpoints for file upload and exchange connection management
- `docker-compose.prod.yml`: Indexer service container handles all chain/exchange sync

</code_context>

<deferred>
## Deferred Ideas

- Per-minute price tables for all tokens (pre-build as background job)
- Email/notification alerts for sync failures
- Exchange-specific advanced features (Coinbase Pro margin trades, etc.)
- NFT valuation beyond transfer tracking

</deferred>

---

*Phase: 02-multichain-exchanges*
*Context gathered: 2026-03-12*
