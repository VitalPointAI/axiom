# Codebase Structure

**Analysis Date:** 2026-03-11

## Directory Layout

```
Axiom/
├── config.py                    # Global Python config (DB path, API keys, rate limits)
├── docker-compose.yml           # Container orchestration (PostgreSQL, web, indexers)
├── 01_create_table.sql          # Root-level schema creation script
├── wallets.json                 # Wallet address configuration
├── neartax.db                   # Legacy SQLite database file (10MB)
├── *.py (30+ files)             # Ad-hoc analysis/debug/fix scripts (root clutter)
├── *.sql (2 files)              # Ad-hoc SQL scripts
│
├── db/                          # Database schema and initialization
│   ├── __init__.py
│   ├── init.py                  # DB initialization logic
│   ├── schema.sql               # Core NEAR transaction schema (PostgreSQL)
│   ├── schema_evm.sql           # EVM chain schema
│   ├── schema_exchanges.sql     # Exchange import schema
│   ├── schema_users.sql         # User/auth schema
│   └── seed_wallets.py          # Wallet seeding script
│
├── engine/                      # Core business logic (Python)
│   ├── __init__.py
│   ├── acb.py                   # Adjusted Cost Base calculator
│   ├── classifier.py            # Transaction classification engine
│   ├── prices.py                # Price resolution logic
│   └── wallet_graph.py          # Wallet relationship graph
│
├── indexers/                    # Blockchain & exchange data ingestion (Python)
│   ├── __init__.py
│   ├── Dockerfile               # Indexer container build
│   ├── requirements.txt         # Python dependencies for indexers
│   ├── crontab                  # Scheduled indexer jobs
│   ├── near_indexer.py          # NEAR Protocol indexer (RPC-based)
│   ├── near_indexer_nearblocks.py  # NEAR via NearBlocks API
│   ├── neardata_indexer.py      # NEAR via neardata service (largest: 34KB)
│   ├── neardata_fast.py         # Fast NEAR indexing variant
│   ├── evm_indexer.py           # EVM chain indexer (Etherscan)
│   ├── evm_indexer_alchemy.py   # EVM via Alchemy API
│   ├── ft_indexer.py            # Fungible token indexer (SQLite)
│   ├── ft_indexer_pg.py         # Fungible token indexer (PostgreSQL)
│   ├── xrp_indexer.py           # XRP Ledger indexer
│   ├── akash_indexer.py         # Akash Network indexer
│   ├── cryptoorg_indexer.py     # Crypto.org chain indexer
│   ├── coinbase_indexer.py      # Coinbase exchange indexer
│   ├── coinbase_pro_indexer.py  # Coinbase Pro indexer
│   ├── cryptocom_indexer.py     # Crypto.com exchange indexer
│   ├── staking_indexer.py       # Staking data indexer
│   ├── epoch_rewards_indexer.py # NEAR epoch rewards (largest indexer: 27KB)
│   ├── hybrid_indexer.py        # Combined indexing strategy
│   ├── price_service.py         # Price fetching service
│   ├── price_fetcher.py         # Price API client
│   ├── nearblocks_client.py     # NearBlocks API wrapper
│   ├── burrow_tracker.py        # Burrow DeFi tracking
│   ├── burrow_history_parser.py # Burrow transaction parsing
│   ├── lockup_parser.py         # NEAR lockup contract parser
│   ├── mpdao_tracker.py         # Meta Pool DAO tracker
│   ├── sweat_jars_tracker.py    # Sweat Economy tracker
│   ├── balance_snapshot.py      # Balance snapshot utility
│   ├── rewards_calculator.py    # Staking rewards calculation
│   ├── staking_rewards.py       # Staking rewards data
│   ├── staking_rewards_history.py # Historical staking rewards
│   ├── backfill_*.py (8 files)  # Various historical data backfill scripts
│   ├── sync-staking-pg.py       # PostgreSQL staking sync
│   ├── exchange_connectors/     # Exchange API connectors
│   │   ├── __init__.py
│   │   ├── coinbase.py          # Coinbase API connector
│   │   ├── cryptocom.py         # Crypto.com API connector
│   │   └── kraken.py            # Kraken API connector
│   └── exchange_parsers/        # CSV/file import parsers
│       ├── __init__.py
│       ├── base.py              # Base parser class
│       ├── coinbase.py          # Coinbase CSV parser
│       ├── crypto_com.py        # Crypto.com CSV parser
│       ├── generic.py           # Generic CSV parser
│       └── wealthsimple.py      # Wealthsimple CSV parser
│
├── tax/                         # Tax calculation and reporting (Python)
│   ├── __init__.py
│   ├── acb_calculator.py        # ACB tax lot tracking
│   ├── categories.py            # Transaction tax categories
│   ├── cost_basis.py            # Cost basis computation
│   ├── currency.py              # Currency conversion (CAD focus)
│   ├── price_warnings.py        # Missing/suspicious price alerts
│   └── reports.py               # Tax report generation
│
├── defi/                        # DeFi protocol parsers (Python)
│   ├── __init__.py
│   ├── burrow_parser.py         # Burrow lending protocol
│   ├── meta_pool_parser.py      # Meta Pool liquid staking
│   └── ref_finance_parser.py    # Ref Finance DEX
│
├── verify/                      # Balance reconciliation (Python)
│   ├── __init__.py
│   └── reconcile.py             # Balance verification logic
│
├── reports/                     # Report generation (Python)
│   ├── __init__.py
│   └── generate.py              # Report output generator
│
├── scripts/                     # Operational scripts (Python + JS)
│   ├── package.json             # JS dependencies for scripts
│   ├── verify-all.cjs           # JS verification script
│   ├── backfill_*.py (5 files)  # Price/data backfill scripts
│   ├── index_*.py (3 files)     # Indexing orchestration
│   ├── import_*.py (2 files)    # Data import utilities
│   ├── fetch_prices.py          # Price fetching
│   ├── coingecko_prices.py      # CoinGecko price source
│   ├── categorize_transactions.py # Transaction categorization
│   ├── detect_uncategorized.py  # Find uncategorized txs
│   ├── check_balances.py        # Balance checking
│   ├── parse_all_defi.py        # DeFi parsing orchestrator
│   ├── scan_near_accounts.py    # NEAR account scanner
│   └── slow_sync_all.py         # Throttled full sync
│
├── docs/                        # Documentation
│   ├── INDEXER_RULES.md         # Indexer classification rules
│   ├── INDEXER_RULES.pdf        # PDF version of rules
│   └── EXCHANGE_IMPORT_DESIGN.md # Exchange import design doc
│
├── output/                      # Generated output files (gitignored)
│
├── web/                         # Next.js web application (TypeScript)
│   ├── package.json             # Web app dependencies
│   ├── package-lock.json        # Locked dependencies
│   ├── tsconfig.json            # TypeScript configuration
│   ├── next.config.mjs          # Next.js config (active)
│   ├── next.config.ts           # Next.js config (alternate)
│   ├── tailwind.config.ts       # Tailwind CSS configuration
│   ├── postcss.config.mjs       # PostCSS configuration
│   ├── eslint.config.mjs        # ESLint configuration
│   ├── middleware.ts            # Next.js middleware (auth, routing)
│   ├── Dockerfile               # Web app container build
│   ├── *.cjs / *.js (40+ files) # Ad-hoc debug/analysis scripts (web root clutter)
│   │
│   ├── app/                     # Next.js App Router pages
│   │   ├── layout.tsx           # Root layout
│   │   ├── page.tsx             # Landing page
│   │   ├── globals.css          # Global styles
│   │   ├── favicon.ico
│   │   │
│   │   ├── auth/
│   │   │   └── page.tsx         # Login/registration page
│   │   │
│   │   ├── accountant/
│   │   │   └── accept/
│   │   │       └── page.tsx     # Accountant invitation acceptance
│   │   │
│   │   ├── dashboard/           # Protected dashboard pages
│   │   │   ├── layout.tsx       # Dashboard layout (sidebar)
│   │   │   ├── page.tsx         # Dashboard home (portfolio overview)
│   │   │   ├── admin/page.tsx   # Admin panel
│   │   │   ├── assets/page.tsx  # Asset holdings view
│   │   │   ├── defi/page.tsx    # DeFi positions
│   │   │   ├── exchanges/page.tsx # Exchange connections
│   │   │   ├── import/page.tsx  # CSV/PDF import
│   │   │   ├── prices/page.tsx  # Price management
│   │   │   ├── reports/page.tsx # Tax reports
│   │   │   ├── settings/page.tsx # User settings
│   │   │   ├── staking/page.tsx # Staking overview
│   │   │   ├── swap/page.tsx    # Token swap
│   │   │   ├── transactions/page.tsx # Transaction list
│   │   │   └── wallets/page.tsx # Wallet management
│   │   │
│   │   └── api/                 # API routes (Next.js Route Handlers)
│   │       ├── health/route.ts
│   │       ├── acb/route.ts            # Adjusted cost base calc
│   │       ├── accountant/             # Accountant multi-client features
│   │       │   ├── accept/route.ts
│   │       │   ├── access/route.ts
│   │       │   ├── invite/route.ts
│   │       │   └── switch/route.ts
│   │       ├── admin/                  # Admin endpoints
│   │       │   ├── stats/route.ts
│   │       │   └── sync/route.ts
│   │       ├── assets/                 # Asset management
│   │       │   ├── route.ts
│   │       │   └── spam/route.ts
│   │       ├── auth/                   # NextAuth session endpoints
│   │       │   ├── session/route.ts
│   │       │   ├── signin/route.ts
│   │       │   └── signout/route.ts
│   │       ├── defi/                   # DeFi data
│   │       │   ├── route.ts
│   │       │   ├── positions/route.ts
│   │       │   ├── summary/route.ts
│   │       │   └── sync/route.ts
│   │       ├── exchange-rates/route.ts # Fiat exchange rates
│   │       ├── exchanges/              # Exchange connections
│   │       │   ├── route.ts
│   │       │   └── [exchange]/sync/route.ts
│   │       ├── import/pdf/route.ts     # PDF import
│   │       ├── indexers/status/route.ts # Indexer health
│   │       ├── phantom-auth/          # Passkey (WebAuthn) authentication
│   │       │   ├── login/start/route.ts
│   │       │   ├── login/finish/route.ts
│   │       │   ├── logout/route.ts
│   │       │   ├── register/start/route.ts
│   │       │   ├── register/finish/route.ts
│   │       │   ├── session/route.ts
│   │       │   ├── username/check/route.ts
│   │       │   └── oauth/              # OAuth providers
│   │       │       ├── callback/route.ts
│   │       │       ├── providers/route.ts
│   │       │       └── start/route.ts
│   │       ├── portfolio/              # Portfolio data
│   │       │   ├── route.ts
│   │       │   ├── history/route.ts
│   │       │   ├── live/route.ts
│   │       │   └── summary/route.ts
│   │       ├── price/route.ts          # Single price lookup
│   │       ├── price-warnings/route.ts # Price anomalies
│   │       ├── prices/manual/route.ts  # Manual price entry
│   │       ├── reports/                # Tax report generation
│   │       │   ├── export/route.ts
│   │       │   ├── income/route.ts
│   │       │   ├── inventory/route.ts
│   │       │   ├── schedule3/route.ts
│   │       │   ├── summary/route.ts
│   │       │   └── t1135/route.ts
│   │       ├── spam/route.ts           # Spam token management
│   │       ├── staking/                # Staking data
│   │       │   ├── route.ts
│   │       │   ├── multichain/route.ts
│   │       │   ├── rewards/route.ts
│   │       │   └── transactions/route.ts
│   │       ├── sync/                   # Sync orchestration
│   │       │   ├── control/route.ts
│   │       │   ├── run/route.ts
│   │       │   └── status/route.ts
│   │       ├── tally/route.ts          # Balance tally
│   │       ├── transactions/route.ts   # Transaction CRUD
│   │       ├── user/preferences/route.ts # User prefs
│   │       ├── validators/route.ts     # Validator data
│   │       └── wallets/                # Wallet management
│   │           ├── route.ts
│   │           ├── verify/route.ts
│   │           └── [id]/
│   │               ├── route.ts
│   │               ├── backfill/route.ts
│   │               └── sync/route.ts
│   │
│   ├── components/              # React components
│   │   ├── SwapWidget.tsx       # Token swap widget
│   │   ├── accountant-settings.tsx # Accountant management UI
│   │   ├── auth-provider.tsx    # Auth context provider
│   │   ├── client-switcher.tsx  # Accountant client switching
│   │   ├── holdings-chart.tsx   # Asset holdings visualization
│   │   ├── indexer-status.tsx   # Indexer status display
│   │   ├── login-buttons.tsx    # Auth login buttons
│   │   ├── multichain-staking.tsx # Multi-chain staking view
│   │   ├── portfolio-chart.tsx  # Portfolio value chart
│   │   ├── portfolio-summary.tsx # Portfolio overview (largest: 19KB)
│   │   ├── sidebar.tsx          # Navigation sidebar
│   │   ├── sign-in-button.tsx   # Sign-in CTA
│   │   ├── staking-positions.tsx # Staking position cards
│   │   ├── staking-rewards-table.tsx # Rewards data table
│   │   ├── sync-status.tsx      # Sync progress indicator
│   │   ├── tally.tsx            # Balance tally display
│   │   ├── validator-tracking.tsx # Validator monitoring (24KB)
│   │   ├── wallet-verification.tsx # Wallet verification flow
│   │   └── ui/                  # Reusable UI primitives (shadcn/ui)
│   │       ├── badge.tsx
│   │       ├── button.tsx
│   │       ├── card.tsx
│   │       ├── input.tsx
│   │       └── label.tsx
│   │
│   ├── contexts/                # React context providers
│   │   └── currency-context.tsx # Currency selection context
│   │
│   ├── lib/                     # Shared utilities (TypeScript)
│   │   ├── db.ts                # PostgreSQL connection pool (pg)
│   │   ├── auth.ts              # Auth helpers (passkey + session)
│   │   ├── auth-db.ts           # Auth database operations
│   │   ├── passkey-challenges.ts # WebAuthn challenge storage
│   │   ├── email.ts             # Email sending (Resend)
│   │   ├── near-rpc.ts          # NEAR RPC client
│   │   ├── prices.ts            # Price utility functions
│   │   ├── token-prices.ts      # Token price resolution
│   │   ├── balance-utils.ts     # Balance calculation helpers
│   │   ├── utils.ts             # General utilities (cn helper)
│   │   └── db-sqlite.bak        # Legacy SQLite DB module (backup)
│   │
│   ├── public/                  # Static assets
│   │   └── *.svg                # Icons (file, globe, next, vercel, window)
│   │
│   └── scripts/                 # Web-specific scripts
│       └── epoch-indexer.js     # Epoch indexing from web context
│
└── .planning/                   # GSD planning documents
    ├── codebase/                # Codebase analysis docs
    └── phases/                  # Implementation phase plans
        ├── 01-near-indexer/
        ├── 02-multichain-exchanges/
        └── 07-web-ui/
```

## Directory Purposes

**`db/`:**
- Purpose: Database schema definitions and initialization
- Contains: SQL schema files split by domain, Python init script
- Key files: `db/schema.sql` (core NEAR schema), `db/schema_evm.sql` (EVM schema), `db/schema_users.sql` (auth schema), `db/init.py` (DB setup)

**`engine/`:**
- Purpose: Core business logic for transaction processing and tax calculation
- Contains: Transaction classifier, ACB calculator, price resolver, wallet graph
- Key files: `engine/classifier.py` (tx type classification), `engine/acb.py` (adjusted cost base), `engine/prices.py` (price resolution)

**`indexers/`:**
- Purpose: All blockchain and exchange data ingestion code
- Contains: Chain-specific indexers, exchange connectors/parsers, price services, backfill utilities
- Key files: `indexers/neardata_indexer.py` (primary NEAR indexer), `indexers/evm_indexer_alchemy.py` (EVM indexer), `indexers/hybrid_indexer.py` (combined strategy)
- Subdirectories: `exchange_connectors/` (API clients), `exchange_parsers/` (CSV import parsers)

**`tax/`:**
- Purpose: Canadian tax calculation logic (ACB method, Schedule 3, T1135)
- Contains: Cost basis tracking, tax categorization, report generation, currency conversion
- Key files: `tax/acb_calculator.py`, `tax/categories.py`, `tax/reports.py`, `tax/currency.py`

**`defi/`:**
- Purpose: DeFi protocol-specific transaction parsers
- Contains: Parsers for Burrow, Meta Pool, Ref Finance
- Key files: `defi/ref_finance_parser.py`, `defi/burrow_parser.py`, `defi/meta_pool_parser.py`

**`verify/`:**
- Purpose: Balance reconciliation and verification
- Contains: Single reconciliation module
- Key files: `verify/reconcile.py`

**`reports/`:**
- Purpose: Report output generation
- Contains: Report formatting and file generation
- Key files: `reports/generate.py`

**`scripts/`:**
- Purpose: Operational and maintenance scripts (batch operations)
- Contains: Price backfill, indexing orchestration, data import utilities
- Key files: `scripts/index_all.py`, `scripts/backfill_prices.py`, `scripts/verify-all.cjs`

**`docs/`:**
- Purpose: Project documentation
- Contains: Indexer classification rules, exchange import design
- Key files: `docs/INDEXER_RULES.md` (comprehensive tx classification rules)

**`web/`:**
- Purpose: Next.js web application (dashboard, API, auth)
- Contains: App Router pages, API routes, React components, shared lib
- Key files: `web/middleware.ts` (auth middleware), `web/app/layout.tsx` (root layout)

**`web/app/api/`:**
- Purpose: REST API endpoints via Next.js Route Handlers
- Contains: All backend API logic organized by domain
- Pattern: Each endpoint is a `route.ts` file exporting HTTP method handlers (GET, POST, PUT, DELETE)

**`web/components/`:**
- Purpose: React UI components (feature-level and primitives)
- Contains: Feature components (flat structure) + `ui/` subdirectory for shadcn primitives
- Key files: `web/components/portfolio-summary.tsx`, `web/components/sidebar.tsx`

**`web/lib/`:**
- Purpose: Shared server-side utilities for the web app
- Contains: Database connection, auth helpers, price utilities, RPC clients
- Key files: `web/lib/db.ts` (PostgreSQL pool), `web/lib/auth.ts` (session/passkey auth)

**`web/contexts/`:**
- Purpose: React context providers for client-side state
- Contains: Currency selection context
- Key files: `web/contexts/currency-context.tsx`

## Key File Locations

**Entry Points:**
- `web/app/layout.tsx`: Root layout for web application
- `web/app/page.tsx`: Landing page
- `web/middleware.ts`: Request middleware (auth checks, route protection)
- `config.py`: Python backend configuration (DB path, API keys, rate limits)

**Configuration:**
- `web/package.json`: Web app dependencies
- `web/tsconfig.json`: TypeScript config
- `web/tailwind.config.ts`: Tailwind CSS theme
- `web/next.config.mjs`: Next.js settings
- `web/eslint.config.mjs`: Linting rules
- `docker-compose.yml`: Container orchestration
- `indexers/requirements.txt`: Python indexer dependencies
- `indexers/crontab`: Scheduled job definitions
- `.env.example`: Environment variable template (never read .env)

**Database:**
- `db/schema.sql`: Core NEAR transaction tables
- `db/schema_evm.sql`: EVM chain tables
- `db/schema_exchanges.sql`: Exchange data tables
- `db/schema_users.sql`: User authentication tables
- `db/init.py`: Database initialization
- `01_create_table.sql`: Root-level schema script (may be legacy)
- `web/lib/db.ts`: PostgreSQL connection pool for web app

**Core Business Logic (Python):**
- `engine/classifier.py`: Transaction type classification
- `engine/acb.py`: Adjusted cost base calculation
- `engine/prices.py`: Price resolution
- `tax/acb_calculator.py`: Tax lot tracking
- `tax/categories.py`: Tax category definitions
- `tax/reports.py`: Tax report generation

**Authentication:**
- `web/lib/auth.ts`: Auth utilities (passkey + OAuth session management)
- `web/lib/auth-db.ts`: Auth database operations (user lookup, credential storage)
- `web/lib/passkey-challenges.ts`: WebAuthn challenge management
- `web/app/api/phantom-auth/`: Full passkey auth flow (register, login, OAuth)
- `web/app/api/auth/`: Session management endpoints
- `web/components/auth-provider.tsx`: Client-side auth context

**Testing:**
- No formal test suite detected. Ad-hoc test/verification scripts exist at root level (`test_trace.py`, `test_trace_tx.py`) and in `web/` (`test-verify.js`, `test-portfolio-api.js`).

## Naming Conventions

**Files (Python backend):**
- snake_case for modules: `near_indexer.py`, `acb_calculator.py`, `wallet_graph.py`
- Hyphenated for scripts: `check-cdao-balance.py`, `find-missing-txs.py`
- Mixed conventions in root (both snake_case and hyphenated coexist)

**Files (TypeScript/web):**
- kebab-case for components: `portfolio-summary.tsx`, `sync-status.tsx`
- kebab-case for lib modules: `auth-db.ts`, `balance-utils.ts`, `token-prices.ts`
- PascalCase exception: `SwapWidget.tsx` (inconsistent with other components)
- API routes always: `route.ts`

**Directories:**
- snake_case for Python packages: `exchange_connectors/`, `exchange_parsers/`
- kebab-case for API routes: `phantom-auth/`, `exchange-rates/`
- lowercase for web dirs: `components/`, `lib/`, `contexts/`
- Dynamic routes use brackets: `[exchange]/`, `[id]/`

**UI Primitives:**
- Lowercase kebab-case in `web/components/ui/`: `button.tsx`, `card.tsx`, `badge.tsx`

## Where to Add New Code

**New Blockchain Indexer:**
- Implementation: `indexers/{chain_name}_indexer.py`
- Follow pattern of `indexers/evm_indexer.py` or `indexers/xrp_indexer.py`
- Add schema if needed: `db/schema_{chain}.sql`

**New Exchange Connector (API-based):**
- API client: `indexers/exchange_connectors/{exchange}.py`
- Follow pattern of `indexers/exchange_connectors/coinbase.py`

**New Exchange Parser (CSV import):**
- Parser: `indexers/exchange_parsers/{exchange}.py`
- Extend base class from `indexers/exchange_parsers/base.py`
- Register in `indexers/exchange_parsers/__init__.py`

**New DeFi Protocol Parser:**
- Parser: `defi/{protocol}_parser.py`
- Follow pattern of `defi/ref_finance_parser.py`
- Register in `defi/__init__.py`

**New API Endpoint:**
- Route file: `web/app/api/{domain}/{action}/route.ts`
- Export named functions: `GET`, `POST`, `PUT`, `DELETE`
- Use `web/lib/auth.ts` for session validation
- Use `web/lib/db.ts` for database queries

**New Dashboard Page:**
- Page: `web/app/dashboard/{feature}/page.tsx`
- Automatically gets dashboard layout with sidebar
- Add navigation link in `web/components/sidebar.tsx`

**New React Component:**
- Feature component: `web/components/{feature-name}.tsx` (kebab-case)
- UI primitive: `web/components/ui/{element}.tsx` (shadcn/ui pattern)

**New React Context:**
- Provider: `web/contexts/{name}-context.tsx`

**New Shared Web Utility:**
- Server-side: `web/lib/{name}.ts`
- Keep client utilities in components or contexts

**New Tax Report Type:**
- Logic: `tax/reports.py` (add method)
- API endpoint: `web/app/api/reports/{report-type}/route.ts`
- UI: `web/app/dashboard/reports/page.tsx` (add section)

**New Database Table:**
- Schema: `db/schema_{domain}.sql` or add to existing schema file
- Run via `db/init.py` initialization

## Special Directories

**`output/`:**
- Purpose: Generated CSV/report output files
- Generated: Yes
- Committed: No (gitignored)

**`reports/` (root):**
- Purpose: Generated tax report files
- Generated: Yes
- Committed: No (gitignored)

**`__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: Yes
- Committed: No (gitignored)

**`web/.next/`:**
- Purpose: Next.js build output
- Generated: Yes
- Committed: No (gitignored)

**`.planning/`:**
- Purpose: GSD planning documents and phase plans
- Generated: By tooling
- Committed: Yes

**Root-level ad-hoc scripts (30+ .py files):**
- Purpose: One-off analysis, debugging, and fix scripts
- These are NOT part of the application architecture
- They are investigation/maintenance tools that accumulated over time
- Should ideally be moved to a `scripts/adhoc/` directory

**Web root ad-hoc scripts (40+ .cjs/.js files):**
- Purpose: One-off debugging and analysis scripts for web/DB
- Same situation as root scripts -- accumulated investigation tools
- Should ideally be moved to `web/scripts/` or cleaned up

---

*Structure analysis: 2026-03-11*
