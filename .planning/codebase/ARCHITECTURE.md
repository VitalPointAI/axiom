# Architecture

**Analysis Date:** 2026-03-13

## Pattern Overview

**Overall:** Layered hexagonal architecture with separation between:
- **API Layer** - FastAPI REST endpoints serving Next.js frontend
- **Data Access Layer** - PostgreSQL with psycopg2 connection pooling
- **Engine Layer** - Tax calculation, classification, cost basis computation
- **Indexers Layer** - Blockchain fetchers, job queue processor, price services
- **Frontend Layer** - Next.js 16 with React 18, client-side auth context

**Key Characteristics:**
- Event-driven async indexing via job queue (PostgreSQL `indexing_jobs` table)
- Long-lived indexer service processes jobs in order with exponential backoff
- FastAPI dependency injection for database connections and auth
- Decimal-based monetary calculations (no float precision errors)
- Multi-chain support: NEAR, Ethereum, EVM-compatibles (Polygon, Optimism), XRP, Akash

## Layers

**Presentation Layer (Frontend):**
- Purpose: User interface for portfolio tracking, transaction classification, report generation
- Location: `web/app/`, `web/components/`, `web/contexts/`, `web/lib/`
- Contains: Next.js pages (App Router), React components, UI hooks, API client
- Depends on: FastAPI backend, session cookies, NEAR passkey auth
- Used by: End users (traders, accountants) in browser

**API Layer (Backend):**
- Purpose: HTTP REST endpoints for wallet management, portfolio queries, report generation, job status
- Location: `api/` (main.py, routers/, dependencies.py)
- Contains: FastAPI app factory, route handlers, dependency injection setup, session validation
- Depends on: PostgreSQL via psycopg2, indexer jobs, engine calculations
- Used by: Next.js frontend via fetch()

**Data Layer:**
- Purpose: PostgreSQL persistence for all domain data
- Location: `indexers/db.py` (connection pool management)
- Contains: Connection pooling, cursor management, transaction handling
- Depends on: DATABASE_URL environment variable
- Used by: All indexers, API routes, engine calculations

**Engine Layer (Tax Calculation):**
- Purpose: Core tax computation logic (cost basis, capital gains, income recognition, transaction classification)
- Location: `engine/` (classifier.py, acb.py, gains.py, fifo.py, prices.py, etc.)
- Contains: TransactionClassifier, ACBEngine, GainsCalculator, SpamDetector, WalletGraph
- Depends on: PostgreSQL pool, PriceService, classification rules
- Used by: Indexer service handlers, report generators

**Indexer Layer:**
- Purpose: Fetch blockchain data, detect transactions, parse exchange files, queue async jobs
- Location: `indexers/` (service.py is the job queue processor; specific fetchers: near_fetcher.py, evm_fetcher.py, price_service.py, etc.)
- Contains: Chain-specific fetchers, price service, file import handlers, job dispatch
- Depends on: PostgreSQL, external APIs (NearBlocks, Etherscan, CoinGecko)
- Used by: Job queue processor (indexers/service.py)

**Reports Layer:**
- Purpose: Generate tax documents (T1135, Schedule 3, capital gains ledger, Koinly CSV)
- Location: `reports/` (handlers/, templates/, + modules in `indexers/` for content generation)
- Contains: Report handler coordinator, template rendering, export formatters
- Depends on: Engine calculations (ACB, gains, income ledger)
- Used by: API reports endpoint, user download

## Data Flow

**Wallet Sync Flow:**
1. User adds wallet via `POST /api/wallets` (frontend)
2. API creates wallet row, queues jobs: full_sync (p=10), staking_sync (p=8), lockup_sync (p=7)
3. Indexer service polls `indexing_jobs` table, finds pending jobs
4. NearFetcher/EVMFetcher fetches transactions from NearBlocks/Etherscan APIs
5. Transactions stored in `transactions` table
6. classify_transactions job queues automatically (on full_sync completion)
7. TransactionClassifier loads ClassificationRules, applies deterministic rules, stores results
8. calculate_acb job queues automatically
9. ACBEngine replays all transactions for user, computes cost basis pools, stores in `acb_snapshots`
10. capital_gains_ledger and income_ledger rows written by GainsCalculator
11. Frontend polls `/api/wallets/{id}/status` to show progress bar (0-100% via stage mapping)

**Report Generation Flow:**
1. User clicks "Generate Report" on frontend, submits year
2. `POST /api/reports/generate` inserts generate_reports job with json_cursor tracking progress
3. Frontend polls `/api/jobs/{job_id}/status` to track completion
4. Indexer service executes job: calls report handlers to build T1135, Schedule 3, etc.
5. Report files written to `output/{user_id}/{tax_year}/`
6. Frontend calls `GET /api/reports/download/{year}` to list files
7. User downloads individual files via `GET /api/reports/download/{year}/{filename}`

**State Management:**
- **User Session**: Stored in PostgreSQL `sessions` table, validated via `neartax_session` cookie
- **Job State**: Tracked in `indexing_jobs` table with status (pending/running/completed/failed) and json_cursor for progress tracking
- **Auth Context**: Frontend React context (`useAuth()`) holds user profile, auto-refreshes from `/api/auth/current-user`
- **Accountant Viewing Mode**: Secondary cookie `neartax_viewing_as` enables accountants to access client data transparently

## Key Abstractions

**TransactionClassifier (engine/classifier.py):**
- Purpose: Maps raw blockchain transactions to tax categories (income, disposal, transfer, etc.)
- Examples: `engine/classifier.py` (1,200+ lines), used by classifier_handler.py
- Pattern: Rule-based classification with deterministic rules, spam detection, staking event linkage, AI fallback for low-confidence

**ACBEngine (engine/acb.py):**
- Purpose: Computes Adjusted Cost Base per token using Canadian average cost method
- Examples: `engine/acb.py` (1,000+ lines), used by acb_handler.py
- Pattern: Per-token pool state machine, full user transaction replay, Decimal precision for all math

**WalletGraph (engine/wallet_graph.py):**
- Purpose: Detects internal transfers between user-controlled wallets
- Examples: `engine/wallet_graph.py` (350 lines), used by classifier.py
- Pattern: Directed graph of wallet addresses, identifies known-user relationships

**PriceService (indexers/price_service.py):**
- Purpose: Fetches historical prices from CoinGecko, caches locally
- Examples: `indexers/price_service.py` (800+ lines), used by engine and reports
- Pattern: API wrapper with caching, fallback chains for price discovery

**JobQueue (indexers/service.py):**
- Purpose: Long-lived process that polls PostgreSQL for pending jobs, dispatches to handlers
- Examples: `indexers/service.py` (400+ lines), main entry point
- Pattern: Exponential backoff on failures, atomic transaction-based job leasing, chain auto-queueing

## Entry Points

**FastAPI Backend:**
- Location: `api/main.py` (create_app() function returns configured FastAPI app)
- Triggers: `uvicorn api.main:app --host 0.0.0.0 --port 8000`
- Responsibilities: CORS setup, router mounting, lifespan DB pool init/teardown

**Indexer Job Processor:**
- Location: `indexers/service.py` (main entry point)
- Triggers: `python -m indexers.service` or Docker container startup
- Responsibilities: Poll job queue, dispatch chain-specific handlers, implement retry backoff

**Next.js Frontend:**
- Location: `web/app/layout.tsx` (root layout)
- Triggers: `npm run dev` (dev) or `npm run build && npm start` (prod)
- Responsibilities: Auth redirect middleware, session validation, page rendering

## Error Handling

**Strategy:** Three-tier approach with logging, database audit trails, and user-facing error messages

**Patterns:**
- **API Errors**: HTTPException with status codes (401/403/400/500). Client receives JSON error detail.
- **Database Errors**: Caught in dependency injection; transaction rollback on exception, logged to server.
- **Job Failures**: Caught in service.py; incremented retry_count, backed off exponentially, failed jobs logged.
- **Classification Errors**: Low-confidence classifications set `needs_review=True` for specialist review.
- **Decimal Math Errors**: Decimal rounding mode set to ROUND_HALF_UP; no float conversions.

## Cross-Cutting Concerns

**Logging:** Python logging module (stdlib). Loggers created per module. Configured at runtime via config.py.

**Validation:**
- Authentication: FastAPI dependency get_current_user validates session cookie, queries users + sessions tables
- Authorization: get_effective_user checks accountant_access grants for viewing-as mode
- Data: Pydantic schemas in api/schemas/ validate request payloads; psycopg2 parameterized queries prevent SQL injection

**Authentication:**
- Session-based: session cookie + PostgreSQL session table
- Strategy: NextAuth-style approach with @vitalpoint/near-phantom-auth for passkey signup/login
- Accountant mode: Secondary cookie neartax_viewing_as allows account delegation

**Database Transactions:**
- Isolation: psycopg2 default (READ COMMITTED)
- Job leasing: Atomic SELECT FOR UPDATE + status flip prevents concurrent processing
- Connection pooling: Module-level SimpleConnectionPool in indexers/db.py, FastAPI lifecycle in api/main.py

---

*Architecture analysis: 2026-03-13*
