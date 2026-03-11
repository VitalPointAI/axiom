# Architecture

**Analysis Date:** 2026-03-11

## Pattern Overview

**Overall:** Dual-layer monolith with a Python backend engine and a Next.js web frontend, sharing a PostgreSQL database.

**Key Characteristics:**
- Python scripts handle blockchain indexing, tax calculation, and data pipeline (offline/batch processing)
- Next.js App Router serves the web UI and API routes (online/request processing)
- Both layers read/write the same PostgreSQL database but use different clients (Python: sqlite3/psycopg2 via `db/init.py`; TypeScript: `pg` via `web/lib/db.ts`)
- The Python layer retains a legacy SQLite path (`neartax.db`) used by CLI scripts; the web layer uses PostgreSQL exclusively
- Multi-user isolation enforced via `user_id` foreign key on `wallets` table, checked in every API route
- Canadian tax rules (ACB/average cost method, 50% inclusion rate, superficial loss rule) are the core domain logic

## Layers

**Web Frontend (Next.js):**
- Purpose: Dashboard UI for portfolio viewing, wallet management, tax reports, and settings
- Location: `web/app/`, `web/components/`, `web/contexts/`
- Contains: React pages, UI components, client-side state management
- Depends on: API routes, `@vitalpoint/near-phantom-auth` for authentication
- Used by: End users via browser

**API Layer (Next.js Route Handlers):**
- Purpose: RESTful API serving data to the frontend, orchestrating syncs
- Location: `web/app/api/`
- Contains: Route handlers using Next.js App Router convention (`route.ts` files)
- Depends on: `web/lib/db.ts` (PostgreSQL), `web/lib/auth.ts` (session validation), external APIs (NearBlocks, Pyth, CoinGecko, Ref Finance)
- Used by: Frontend components via `fetch()`

**Middleware:**
- Purpose: Rate limiting, authentication gating, security headers
- Location: `web/middleware.ts`
- Contains: In-memory rate limiter, session cookie validation, route protection
- Depends on: Request cookies (`neartax_session`)
- Used by: All incoming HTTP requests

**Indexers (Python):**
- Purpose: Fetch and normalize blockchain transaction data from external APIs
- Location: `indexers/`
- Contains: Chain-specific indexers (NEAR, EVM, exchanges), price fetchers, staking trackers
- Depends on: `db/init.py`, `config.py`, external APIs (NearBlocks, Etherscan V2, CoinGecko, exchange APIs)
- Used by: Cron jobs, manual CLI invocation, web API sync triggers

**Tax Engine (Python):**
- Purpose: Transaction classification, ACB calculation, capital gains computation
- Location: `engine/`, `tax/`
- Contains: Classifier, ACB tracker, price fetcher, wallet graph analysis
- Depends on: `db/init.py`
- Used by: Report generation, web API ACB endpoint

**Database Layer:**
- Purpose: Schema definitions and connection management
- Location: `db/` (Python), `web/lib/db.ts` (TypeScript)
- Contains: SQL schema files, connection helpers
- Depends on: PostgreSQL (production), SQLite (legacy CLI)
- Used by: All other layers

**Reports (Python):**
- Purpose: Generate tax reports (capital gains, income, T1135, Koinly export)
- Location: `reports/`, `tax/reports.py`
- Contains: CSV/report generators
- Depends on: `engine/acb.py`, `db/init.py`
- Used by: Web API report endpoints, CLI

**DeFi Parsers (Python):**
- Purpose: Parse DeFi protocol interactions (Burrow, Ref Finance, Meta Pool)
- Location: `defi/`
- Contains: Protocol-specific parsers
- Depends on: `db/init.py`
- Used by: Indexer pipeline

**Verification (Python):**
- Purpose: Reconcile indexed data against on-chain state
- Location: `verify/`
- Contains: Balance reconciliation logic
- Depends on: NEAR RPC, `db/init.py`
- Used by: CLI scripts, debugging

## Data Flow

**Wallet Sync Flow:**

1. User adds wallet via `POST /api/wallets` (web API)
2. API inserts wallet record into `wallets` table with `user_id`
3. API spawns Python indexer process via `child_process.spawn()` (`web/app/api/wallets/route.ts`)
4. Python indexer fetches transactions from NearBlocks/Etherscan API (`indexers/near_indexer.py`, `indexers/evm_indexer.py`)
5. Indexer writes transactions to `transactions`/`evm_transactions` tables with progress tracking in `indexing_progress`
6. Frontend polls `/api/sync/status` for progress updates

**Portfolio View Flow:**

1. Frontend calls `GET /api/portfolio`
2. API authenticates user via `getAuthenticatedUser()` (`web/lib/auth.ts`)
3. API queries DB for wallet balances, staking positions, token holdings, exchange holdings, DeFi positions
4. API fetches live prices from Pyth (primary), Ref Finance (NEAR ecosystem), CoinGecko (fallback)
5. API fetches live NEAR balances from NearBlocks API
6. API calculates portfolio totals in USD and CAD, returns JSON

**Tax Calculation Flow:**

1. Web API or CLI invokes ACB calculator (`tax/acb_calculator.py` or `engine/acb.py`)
2. Calculator loads all transactions chronologically from DB
3. For each transaction: classifies as acquisition or disposition (`engine/classifier.py`)
4. Maintains per-token ACB pools using average cost method
5. Calculates capital gains/losses on dispositions
6. Checks superficial loss rule (30-day rebuy window)
7. Summarizes by tax year with 50% inclusion rate

**Authentication Flow:**

1. User visits `/auth` page
2. Frontend uses `@vitalpoint/near-phantom-auth` for WebAuthn passkey, Google OAuth, or magic link auth
3. Auth API routes at `/api/phantom-auth/*` handle registration/login
4. On success, `createSession()` in `web/lib/auth.ts` generates session token, stores in DB `sessions` table, sets `neartax_session` cookie
5. Middleware validates cookie presence on protected routes
6. Route handlers validate session via `getAuthenticatedUser()`

**State Management:**
- Server state: PostgreSQL database is single source of truth
- Client state: React Context (`AuthProvider` in `web/components/auth-provider.tsx`, `CurrencyContext` in `web/contexts/currency-context.tsx`)
- No client-side state management library (Redux, Zustand, etc.) -- uses `useState`/`useEffect` with `fetch()`
- Price data: Fetched per-request with Next.js `revalidate` caching (60-300s depending on source)

## Key Abstractions

**ACBTracker / TaxLot:**
- Purpose: Track adjusted cost base per crypto asset using Canadian average cost method
- Examples: `engine/acb.py` (`ACBTracker`, `PortfolioACB`), `tax/acb_calculator.py` (`TaxLot`, `calculate_acb()`)
- Pattern: Two parallel implementations exist -- `engine/acb.py` is a clean class-based tracker, `tax/acb_calculator.py` is a DB-integrated calculator that reads directly from SQLite

**Transaction Classifier:**
- Purpose: Map blockchain transaction types to tax categories (income, disposition, transfer, fee)
- Examples: `engine/classifier.py` (`classify_near_transaction()`, `classify_exchange_transaction()`)
- Pattern: Rule-based classification using action type and method name lookup tables

**TaxCategory Enum:**
- Purpose: Standardized tax categories following Koinly taxonomy
- Examples: `tax/categories.py`
- Pattern: Enum with categories for income, trades, transfers, staking, DeFi, expenses

**Database Wrapper:**
- Purpose: Abstract database access with placeholder conversion (? to $1/$2)
- Examples: `web/lib/db.ts` (`db` object and `getDb()` legacy shim)
- Pattern: PostgreSQL pool with async methods (`all`, `get`, `run`, `transaction`), plus a `getDb()` compatibility layer that mimics better-sqlite3's `prepare().all()` interface

**NearBlocksClient:**
- Purpose: Rate-limited API client for NearBlocks blockchain data
- Examples: `indexers/nearblocks_client.py`
- Pattern: Request wrapper with configurable delay, exponential backoff on 429s, max retry limit

**AuthUser:**
- Purpose: Authenticated user context with accountant delegation support
- Examples: `web/lib/auth.ts` (`AuthUser` interface, `getAuthenticatedUser()`)
- Pattern: Cookie-based session lookup with optional client-switching for accountant view

## Entry Points

**Web Application:**
- Location: `web/app/layout.tsx` (root layout), `web/app/page.tsx` (landing)
- Triggers: HTTP requests to port 3003
- Responsibilities: Renders React app with `AuthProvider` context

**Dashboard:**
- Location: `web/app/dashboard/layout.tsx`, `web/app/dashboard/page.tsx`
- Triggers: Authenticated user navigation
- Responsibilities: Sidebar navigation, auth guard, portfolio display

**API Routes:**
- Location: `web/app/api/*/route.ts`
- Triggers: Frontend fetch calls
- Responsibilities: Data CRUD, sync orchestration, report generation

**Python Indexers:**
- Location: `indexers/near_indexer.py`, `indexers/evm_indexer.py`, `indexers/coinbase_indexer.py`, etc.
- Triggers: CLI invocation, cron (via `indexers/crontab`), web API spawn
- Responsibilities: Fetch and store blockchain/exchange transaction data

**Python CLI Scripts:**
- Location: `scripts/` (batch operations), root-level `*.py` files (analysis/debugging)
- Triggers: Manual CLI invocation
- Responsibilities: Batch price backfill, wallet indexing, balance checks, data analysis

**Docker Compose:**
- Location: `docker-compose.yml`
- Triggers: `docker compose up`
- Responsibilities: Orchestrates web, indexer, and postgres containers

## Error Handling

**Strategy:** Catch-and-log with graceful degradation

**Patterns:**
- API routes wrap entire handler in try/catch, return `{ error: string, details?: string }` with appropriate HTTP status
- Indexers use retry with exponential backoff on rate limits (429), log errors and continue to next wallet
- Price fetches cascade through providers: Pyth -> Ref Finance -> CoinGecko -> hardcoded fallback (e.g., CAD rate defaults to 1.38)
- Portfolio endpoint returns 503 with partial data if price service is unavailable
- Database errors propagate as 500 responses

## Cross-Cutting Concerns

**Logging:** `console.log`/`console.error` in TypeScript; `print()` in Python. No structured logging framework.

**Validation:** Minimal -- API routes validate auth and basic parameter parsing. No schema validation library (no Zod, Joi, etc.). SQL parameterization prevents injection.

**Authentication:** WebAuthn passkeys + Google OAuth + magic link via `@vitalpoint/near-phantom-auth`. Session tokens stored in `sessions` table, validated per-request. Middleware blocks unauthenticated access to protected routes. Accountant delegation via `accountant_access` table.

**Rate Limiting:** In-memory Map in `web/middleware.ts` with per-minute windows (500 auth, 100 API, 200 default). Resets on server restart. Python indexers use per-request delays (1-3s) with exponential backoff.

**Multi-tenancy:** All data queries filter by `user_id` from authenticated session. Wallets, transactions, and derived data are user-scoped.

---

*Architecture analysis: 2026-03-11*
