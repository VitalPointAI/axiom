# Codebase Structure

**Analysis Date:** 2026-03-13

## Directory Layout

```
axiom/
├── api/                          # FastAPI backend
│   ├── __init__.py
│   ├── main.py                   # App factory, router mounting, lifespan
│   ├── dependencies.py           # Database pool, auth, dependency injection
│   ├── auth/                     # Auth endpoints (login, logout, passkey)
│   ├── routers/                  # API endpoint handlers
│   │   ├── __init__.py
│   │   ├── wallets.py            # Wallet CRUD + sync status
│   │   ├── transactions.py       # Transaction search, classification override
│   │   ├── portfolio.py          # Balance, holdings, allocation
│   │   ├── reports.py            # Report generation, preview, download
│   │   ├── jobs.py               # Job queue status polling
│   │   ├── verification.py       # Balance reconciliation
│   │   └── exchanges.py          # Exchange import endpoints
│   └── schemas/                  # Pydantic request/response models
├── engine/                       # Tax calculation logic
│   ├── __init__.py
│   ├── classifier.py             # Transaction classification engine (1200+ lines)
│   ├── acb.py                    # ACB cost basis calculation (1000+ lines)
│   ├── gains.py                  # Capital gains ledger records
│   ├── fifo.py                   # FIFO method (alternative to ACB)
│   ├── superficial.py            # Superficial loss rule detection
│   ├── spam_detector.py          # Spam transaction filtering
│   ├── wallet_graph.py           # Internal transfer detection
│   ├── evm_decoder.py            # EVM contract call decoding
│   ├── rule_seeder.py            # Classification rule initialization
│   └── prices.py                 # Price fetching (legacy, see price_service)
├── indexers/                     # Blockchain data fetching + job queue
│   ├── __init__.py
│   ├── db.py                     # PostgreSQL connection pool, cursor context
│   ├── service.py                # Main job queue processor (400+ lines)
│   ├── near_fetcher.py           # NEAR transaction fetcher via NearBlocks
│   ├── evm_fetcher.py            # EVM transaction fetcher via Etherscan/Alchemy
│   ├── staking_fetcher.py        # NEAR staking rewards fetcher
│   ├── lockup_fetcher.py         # NEAR lockup events fetcher
│   ├── price_service.py          # Price data aggregation (800+ lines)
│   ├── price_fetcher.py          # Individual price fetch utility
│   ├── xrp_fetcher.py            # XRP transaction fetcher
│   ├── akash_fetcher.py          # Akash network fetcher
│   ├── nearblocks_client.py      # NearBlocks API rate-limited client
│   ├── classifier_handler.py     # Job handler: run TransactionClassifier
│   ├── acb_handler.py            # Job handler: run ACBEngine
│   ├── dedup_handler.py          # Job handler: remove duplicate transactions
│   ├── file_handler.py           # Job handler: parse exchange CSV imports
│   ├── verify_handler.py         # Job handler: reconcile wallet balances
│   ├── exchange_connectors/      # Per-exchange integrations (Coinbase, Crypto.com, etc.)
│   ├── exchange_parsers/         # Parser implementations
│   ├── ai_file_agent.py          # AI-assisted file classification
│   └── [legacy backfill scripts]
├── reports/                      # Tax report generation
│   ├── __init__.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   └── report_handler.py     # Main report coordinator
│   ├── templates/                # Report template rendering
│   └── [report type modules in indexers/]
├── tax/                          # Tax category definitions
│   ├── __init__.py
│   ├── categories.py             # TaxCategory enum, classification results
│   └── [currency, cost basis, acb_calculator, reports modules]
├── db/                           # Database initialization
│   ├── __init__.py
│   ├── migrations/               # Schema migration SQL files
│   └── 01_create_table.sql       # Initial schema (referenced in docs)
├── web/                          # Next.js frontend
│   ├── app/                      # Next.js App Router
│   │   ├── layout.tsx            # Root layout with auth check
│   │   ├── page.tsx              # Landing page
│   │   ├── auth/                 # Auth flow
│   │   │   └── page.tsx
│   │   ├── dashboard/            # Protected dashboard
│   │   │   ├── layout.tsx        # Sidebar, sync status, navigation
│   │   │   ├── page.tsx          # Dashboard home
│   │   │   ├── transactions/
│   │   │   ├── assets/
│   │   │   ├── portfolio/
│   │   │   ├── staking/
│   │   │   ├── reports/
│   │   │   ├── exchanges/
│   │   │   ├── settings/
│   │   │   ├── admin/
│   │   │   └── defi/
│   │   └── accountant/           # Accountant features
│   │       └── accept/page.tsx   # Accept access grants
│   ├── components/               # React components (auth-provider, sidebar, etc.)
│   ├── contexts/                 # React context providers (auth state)
│   ├── lib/                      # Utility functions
│   │   ├── api.ts                # Centralized API client
│   │   ├── utils.ts              # Common utilities
│   │   ├── balance-utils.ts
│   │   ├── token-prices.ts
│   │   └── [other utilities]
│   ├── public/                   # Static assets
│   ├── middleware.ts             # Next.js middleware (auth redirect, security headers)
│   ├── next.config.mjs           # Next.js config
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── package.json
│   └── Dockerfile                # Frontend container config
├── scripts/                      # Development/admin scripts
├── verify/                       # Data verification utilities
├── output/                       # Generated report outputs (user/{id}/{year}/)
├── defi/                         # DeFi protocol integrations (burrow, ref, etc.)
├── docs/                         # Documentation
├── tests/                        # Python pytest test suite
│   ├── test_*.py                 # Test files
│   └── fixtures/                 # Test data
├── config.py                     # Global configuration (ENV vars, API keys, tolerances)
├── .env.example                  # Environment variables template
├── .planning/                    # GSD planning artifacts
│   └── codebase/                 # Architecture docs (this output)
└── [standalone analysis scripts] # Full analysis, balance checks, etc.
```

## Directory Purposes

**`api/`**
- Purpose: FastAPI REST backend serving the Next.js frontend
- Contains: Main app factory, route handlers for all endpoints, dependency injection
- Key files: `api/main.py` (app factory), `api/dependencies.py` (auth, DB), `api/routers/` (endpoints)

**`engine/`**
- Purpose: Core tax calculation logic
- Contains: TransactionClassifier, ACBEngine, GainsCalculator, supporting utilities
- Key files: `engine/classifier.py` (1200+ lines), `engine/acb.py` (1000+ lines), `engine/gains.py`

**`indexers/`**
- Purpose: Blockchain data fetching, job queue processing, external API integration
- Contains: Chain-specific fetchers (near_fetcher, evm_fetcher, etc.), price service, file import handlers
- Key files: `indexers/service.py` (job processor), chain fetchers, `indexers/db.py` (pool management)

**`reports/`**
- Purpose: Tax report generation and export
- Contains: Report handler coordinator, template rendering, Koinly/CRA format exporters
- Key files: `reports/handlers/report_handler.py`, template modules in `indexers/`

**`tax/`**
- Purpose: Tax category definitions and currency handling
- Contains: TaxCategory enum, classification result models, currency converters
- Key files: `tax/categories.py`

**`web/`**
- Purpose: Next.js frontend user interface
- Contains: App Router pages, React components, API client, auth context
- Key files: `web/middleware.ts` (auth redirect), `web/app/layout.tsx` (root), `web/lib/api.ts` (API client)

**`db/`**
- Purpose: Database schema and migrations
- Contains: SQL schema definition, migration scripts
- Key files: `db/migrations/`, referenced schema docs

**`tests/`**
- Purpose: Python pytest test suite
- Contains: Unit tests for indexers, engine, API routes
- Key files: `tests/test_*.py`, `tests/fixtures/`

**`scripts/`**
- Purpose: Admin and development utilities
- Contains: Data import scripts, debugging tools, analysis utilities
- Generated or manual maintenance scripts

**`output/`**
- Purpose: Generated tax report files
- Structure: `output/{user_id}/{tax_year}/` containing T1135, Schedule 3, Koinly CSV, etc.
- Generated: Yes (created at runtime)
- Committed: No (.gitignore'd)

## Key File Locations

**Entry Points:**
- `api/main.py`: FastAPI app factory; run with `uvicorn api.main:app`
- `indexers/service.py`: Job queue processor; run with `python -m indexers.service`
- `web/app/layout.tsx`: Next.js root layout; run with `npm run dev`
- `web/middleware.ts`: Session validation and auth redirect

**Configuration:**
- `config.py`: Global ENV var loading, database URL, API keys, rate limits, tolerances
- `.env`: Environment variables (not committed)
- `.env.example`: Template for required ENV vars

**Core Logic:**
- `engine/classifier.py`: Transaction classification (1200 lines)
- `engine/acb.py`: Cost basis calculation (1000 lines)
- `indexers/service.py`: Job queue processor (400 lines)
- `api/main.py`: API app factory (100 lines)
- `api/dependencies.py`: Auth, DB injection (200 lines)

**Testing:**
- `tests/test_classifier.py`: Classifier tests
- `tests/test_acb.py`: ACB tests
- `tests/test_api_*.py`: Route tests
- `tests/fixtures/`: Test data and factories

## Naming Conventions

**Files:**
- `snake_case.py` for Python modules
- `camelCase.ts(x)` for TypeScript/React files
- `UPPERCASE.md` for documentation
- `test_*.py` for Python tests
- `*.spec.ts` or `*.test.ts` for TypeScript tests

**Directories:**
- `snake_case/` for Python packages (indexers/, engine/, etc.)
- `camelCase/` for React component groups (components/, contexts/, etc.)
- `[feature]/` for grouped functionality (auth/, dashboard/, routers/)

**Classes:**
- `PascalCase` for Python classes (TransactionClassifier, ACBEngine, WalletGraph)
- `PascalCase` for React components (Sidebar, SyncStatus, ClientSwitcher)

**Functions/Variables:**
- `snake_case()` for Python functions (get_pool, classify_transactions)
- `camelCase()` for JavaScript/TypeScript functions (useAuth, fetchWallets)

**Constants:**
- `UPPER_SNAKE_CASE` for Python constants (REVIEW_THRESHOLD, NEAR_DIVISOR)
- `UPPER_SNAKE_CASE` for TypeScript constants (API_URL, RATE_LIMIT_DELAY)

## Where to Add New Code

**New Feature (e.g., new tax report format):**
- Primary code: `indexers/` (if data fetch) or `reports/handlers/` (if generation)
- Tests: `tests/test_new_feature.py`
- Configuration: Add to `config.py` if new ENV vars needed
- Database: Add migration SQL to `db/migrations/` if schema changes needed

**New Chain Integration (e.g., Solana support):**
- Fetcher: `indexers/solana_fetcher.py` (follows pattern from near_fetcher.py)
- Handler: `indexers/solana_handler.py` in service.py dispatch
- Decoder: `engine/solana_decoder.py` if needed for contract calls
- Database: Add chain enum value and columns if needed

**New Component (e.g., Solana holdings display):**
- Component: `web/components/solana-holdings.tsx`
- Page: `web/app/dashboard/solana/page.tsx`
- API: New endpoint in `api/routers/[feature].py`
- Tests: `tests/test_api_solana.py`

**API Endpoint:**
- Router: `api/routers/[feature].py` (create or add to existing)
- Import: Register in `api/routers/__init__.py`
- Mount: Add to `api/main.py` in `include_router()` calls
- Schemas: Define request/response models in `api/schemas/` Pydantic classes
- Tests: `tests/test_api_[feature].py`

**New Job Type:**
- Handler: `indexers/[name]_handler.py` with async handler function
- Import: Add to `indexers/service.py` imports and job dispatch match/case
- Database: Add job_type enum value if needed
- Tests: `tests/test_indexers.py` or feature test file

**Utilities:**
- Python: `engine/` (core logic) or `indexers/` (data utilities)
- TypeScript: `web/lib/` (shared) or `web/components/` (component-specific)

**Shared Utilities:**
- Python: Create module in `engine/` or appropriate package
- TypeScript: Create module in `web/lib/` with clear naming

## Special Directories

**`output/`:**
- Purpose: Generated tax report files per user/year
- Generated: Yes (created by report_handler at runtime)
- Committed: No (.gitignored)
- Structure: `output/{user_id}/{tax_year}/{filename}`
- Cleanup: Manual or via admin endpoint

**`.planning/`:**
- Purpose: GSD orchestrator planning artifacts
- Generated: Yes (by /gsd:map-codebase and /gsd:plan-phase)
- Committed: Yes (tracked in version control)
- Structure: Contains STACK.md, ARCHITECTURE.md, phase plans, etc.

**`db/migrations/`:**
- Purpose: PostgreSQL schema evolution
- Generated: Manual (developer creates migrations)
- Committed: Yes
- Structure: Numbered SQL files (01_create_table.sql, 02_add_column.sql)

**`tests/fixtures/`:**
- Purpose: Test data, mock responses, factory utilities
- Generated: Manual (created by test authors)
- Committed: Yes
- Structure: Fixture modules with reusable test objects

**`web/node_modules/`:**
- Purpose: npm dependencies
- Generated: Yes (by npm install)
- Committed: No (.gitignored)
- Lockfile: `web/package-lock.json` (committed)

**`__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: Yes (by Python runtime)
- Committed: No (.gitignored)
- Cleanup: Automatic on new runs

---

*Structure analysis: 2026-03-13*
