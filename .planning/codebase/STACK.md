# Technology Stack

**Analysis Date:** 2026-03-11

## Languages

**Primary:**
- TypeScript 5.9.3 - Web application (`web/`), Next.js API routes, React components
- Python 3.11 - Blockchain indexers (`indexers/`), tax engine (`engine/`), DeFi parsers (`defi/`), DB scripts (`db/`)

**Secondary:**
- SQL (PostgreSQL dialect) - Schema definitions (`db/schema.sql`, `db/schema_evm.sql`, `db/schema_users.sql`, `db/schema_exchanges.sql`, `01_create_table.sql`)
- JavaScript (Node.js) - Utility scripts (`scripts/`)

## Runtime

**Environment:**
- Node.js 20 (Alpine) - Web app runtime (per `web/Dockerfile`)
- Python 3.11 (slim) - Indexer runtime (per `indexers/Dockerfile`)

**Package Manager:**
- npm - Web app (`web/package.json`)
- pip - Python indexers (`indexers/requirements.txt`)
- Lockfile: `web/package-lock.json` expected (npm ci used in Dockerfile)

## Frameworks

**Core:**
- Next.js 16.1.6 - Full-stack web framework (`web/package.json`), App Router pattern
- React 18.3.1 - UI library (`web/package.json`)

**Testing:**
- No test framework detected in either `web/package.json` or `indexers/requirements.txt`

**Build/Dev:**
- Tailwind CSS 4.2.1 - Styling (`web/tailwind.config.ts`, `web/postcss.config.mjs`)
- PostCSS 8.5.6 - CSS processing (`web/postcss.config.mjs`)
- ESLint 8.57.0 + eslint-config-next 14.2.5 - Linting (`web/eslint.config.mjs`)
- Docker Compose 3.8 - Multi-service orchestration (`docker-compose.yml`)

## Key Dependencies

**Critical (Web):**
- `pg` 8.19.0 - PostgreSQL client for web app (`web/lib/db.ts`)
- `@simplewebauthn/server` 13.2.3 + `@simplewebauthn/browser` 13.2.2 - Passkey/WebAuthn authentication
- `@vitalpoint/near-phantom-auth` 0.5.2 - NEAR wallet authentication
- `@walletconnect/sign-client` 2.23.6 - WalletConnect integration
- `recharts` 2.15.0 - Charting library for dashboard
- `pdf-parse` 1.1.0 + `pdf2json` 3.1.4 + `pdfjs-dist` 3.11.174 - PDF import for exchange statements

**Critical (Web - UI):**
- `lucide-react` 0.469.0 - Icon library
- `class-variance-authority` 0.7.1 - Component variant styling (shadcn/ui pattern)
- `clsx` 2.1.1 + `tailwind-merge` 2.6.0 - Conditional class merging (`web/lib/utils.ts`)

**Critical (Web - Infrastructure):**
- `@aws-sdk/client-ses` 3.1000.0 - Email sending via AWS SES (`web/lib/email.ts`)
- `@aurora-is-near/intents-swap-widget` 6.3.1 - Aurora swap widget integration

**Critical (Python Indexers):**
- `aiohttp` >= 3.9.0 - Async HTTP for high-throughput indexing (`indexers/neardata_indexer.py`)
- `requests` >= 2.31.0 - Sync HTTP for API calls
- `psycopg2-binary` >= 2.9.9 - PostgreSQL client for indexers
- `python-dotenv` >= 1.0.0 - Environment variable loading

**Critical (Python - Optional):**
- `PyJWT` + `cryptography` - Required for Coinbase API connector (`indexers/coinbase_indexer.py`), optional import

**Legacy:**
- `better-sqlite3` 11.0.0 - Listed in `web/package.json` but web app uses PostgreSQL; legacy from SQLite era
- `better-sqlite3` 12.6.2 - Used in `scripts/package.json` for utility scripts

## Configuration

**Environment:**
- `.env` file at project root - Loaded manually in `config.py` (no dotenv dependency for Python root)
- `.env` for web app - Standard Next.js env var loading
- Required env vars documented in `docker-compose.yml`:
  - `DATABASE_URL` - PostgreSQL connection string
  - `POSTGRES_PASSWORD` - Database password
  - `NEARBLOCKS_API_KEY` - NearBlocks API access
  - `ALCHEMY_API_KEY` - Alchemy (EVM chains) access
  - `ETHERSCAN_API_KEY` - Etherscan V2 API access
  - `COINGECKO_API_KEY` - CoinGecko price data
  - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SES_REGION` - AWS SES email
  - `AWS_SES_FROM_EMAIL` - Sender email address
  - `FASTNEAR_API_KEY` - FastNEAR RPC (optional, improves rate limits)
  - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` - Google OAuth
  - `NEXT_PUBLIC_APP_URL` - Application base URL
  - `COINBASE_CREDS` - Path to Coinbase credentials JSON file
  - `CRONOS_API_KEY` - Cronos chain API (optional)

**Build:**
- `web/tsconfig.json` - TypeScript config, strict mode, ES2017 target, `@/*` path alias
- `web/next.config.ts` - Next.js config (minimal/default)
- `web/tailwind.config.ts` - Tailwind with shadcn/ui-style CSS variables, dark mode via media query
- `web/postcss.config.mjs` - PostCSS with Tailwind plugin

**Python Config:**
- `config.py` - Root-level Python config, loads `.env` manually, defines `DATABASE_PATH`, `NEARBLOCKS_BASE_URL`, rate limit constants

## Platform Requirements

**Development:**
- Node.js 20+
- Python 3.11+
- PostgreSQL 16 (or Docker)
- npm for web dependencies
- pip for Python dependencies

**Production:**
- Docker + Docker Compose
- PostgreSQL 16 Alpine (`postgres:16-alpine`)
- Node.js 20 Alpine (`node:20-alpine`)
- Python 3.11 slim (`python:3.11-slim`)
- Web app exposed on port 3003 (mapped to container 3000)
- PostgreSQL on port 5432 (localhost only)
- Cron daemon in indexer container for scheduled tasks

**Deployment:**
- Standalone Next.js output (used in Docker production stage)
- Health check endpoint: `/api/health`
- Indexer runs cron internally for scheduled blockchain/price syncing

---

*Stack analysis: 2026-03-11*
