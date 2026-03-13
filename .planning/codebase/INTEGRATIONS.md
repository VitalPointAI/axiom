# External Integrations

**Analysis Date:** 2026-03-13

## APIs & External Services

**Blockchain Data:**
- NearBlocks (`https://api.nearblocks.io/v1`) - NEAR transaction indexing and account data
  - SDK/Client: requests library (custom client in `indexers/near_indexer_nearblocks.py`)
  - Auth: `NEARBLOCKS_API_KEY` environment variable
  - Rate limit: 1 req/sec when key present, 3 req/sec without key (paid tier ~190 calls/min)
  - Implementation: `indexers/near_indexer_nearblocks.py`, `indexers/near_fetcher.py`

- Alchemy (`https://eth-mainnet.g.alchemy.com/v2/`, `https://polygon-mainnet.g.alchemy.com/v2/`) - EVM transaction indexing for Ethereum and Polygon
  - SDK/Client: requests library (custom RPC client in `indexers/evm_indexer_alchemy.py`)
  - Auth: `ALCHEMY_API_KEY` environment variable
  - Implementation: `indexers/evm_indexer_alchemy.py`, `indexers/evm_fetcher.py`
  - Methods: alchemy_getAssetTransfers (all transfers including zero-value contract calls)

- FastNEAR RPC (`https://free.rpc.fastnear.com`, `https://archival-rpc.mainnet.fastnear.com`) - NEAR balance checks and archival queries
  - SDK/Client: fetch API (browser) or requests (backend)
  - Auth: Optional `FASTNEAR_API_KEY` environment variable
  - Implementation: `web/lib/near-rpc.ts`, `config.py` (FASTNEAR_RPC, FASTNEAR_ARCHIVAL_RPC)
  - No rate limit if using free endpoint; API key improves tier

- Etherscan API - EVM block explorer data (fallback, optional)
  - Auth: `ETHERSCAN_API_KEY` environment variable
  - Implementation: referenced in docker-compose env but usage location unclear

**Price Data:**
- CoinGecko API (primary) - Historical and current crypto prices
  - Base URL: `https://api.coingecko.com/api/v3` (free) or `https://pro-api.coingecko.com/api/v3` (pro)
  - Auth: `COINGECKO_API_KEY` environment variable (optional, enables pro tier)
  - Rate limit: Free tier 30 calls/min, enforced with 2.1sec delay between calls
  - Implementation: `indexers/price_service.py`, `engine/prices.py`, `verify/reconcile.py`
  - Features: CAD conversion (uses Bank of Canada Valet API), outlier detection (>50% variance triggers alert)

- CryptoCompare API (fallback) - Historical prices when CoinGecko unavailable
  - Base URL: `https://min-api.cryptocompare.com/data`
  - Auth: `CRYPTOCOMPARE_API_KEY` environment variable (optional)
  - Implementation: `indexers/price_service.py`
  - Fallback strategy: Uses CoinGecko as primary, CryptoCompare for validation

- Bank of Canada Valet API (`https://www.bankofcanada.ca/valet`) - CAD/USD historical exchange rates
  - No auth required
  - Implementation: Referenced in `indexers/price_service.py` for CAD conversion
  - Caching: Results stored in PostgreSQL price_cache table

**Blockchain SDKs:**
- NEAR SDK (@vitalpoint/near-phantom-auth 0.5.2) - Custom NEAR wallet authentication
  - Implementation: `web/components/` (assumed WalletConnect integration)

- WalletConnect Sign Client (2.23.6) - Multi-chain wallet connection
  - Implementation: Referenced in web package.json, assumed used in auth flow

- Algorand SDK (algosdk) - Algorand blockchain support (installed but minimal usage)
  - Implementation: If used, likely in indexers for Algorand transaction parsing

## Data Storage

**Databases:**
- PostgreSQL 16 (primary and only database)
  - Connection: `DATABASE_URL` environment variable (format: `postgresql://user:pass@host:5432/dbname`)
  - Client: psycopg2-binary (Python) via connection pool
  - Migrations: Alembic 1.13.0 (`db/migrations/alembic.ini`)
  - Schema files: `db/models.py`, `db/init.sql`, migration versions in `db/migrations/versions/`
  - Pool management: `indexers/db.py` (SimpleConnectionPool for async handlers)

- SQLite (legacy, minimal use)
  - Client: better-sqlite3
  - Purpose: Possible legacy scripts or sync operations (not primary)

**File Storage:**
- S3 compatible storage (implied by boto3 import in web dependencies)
  - Implementation: AWS SES is actively used; S3 integration possible but not explicitly configured
  - Configuration: None explicitly set in docker-compose or config.py
  - If used: Would require `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` in environment

**Caching:**
- PostgreSQL price_cache table - In-database caching for price data
  - Schema: `(coin_id, date, currency, price, cached_at)` with UniqueConstraint
  - INSERT ... ON CONFLICT pattern for idempotent writes
  - Implementation: `indexers/price_service.py`
- No Redis or external cache layer detected

## Authentication & Identity

**Auth Provider:**
- Custom implementation (hybrid multi-method)
  - Methods supported:
    1. WebAuthn/Passkeys - Server-side verification via `webauthn 2.0.0` library
    2. Google OAuth 2.0 - PKCE flow, token exchange, email-based user upsert
    3. Magic Link (email) - Signed tokens via itsdangerous, SES delivery
    4. NEAR Wallet - Via @vitalpoint/near-phantom-auth and WalletConnect

**Implementation:**
- Location: `api/auth/` module
  - `passkey.py` - WebAuthn registration and authentication (RP_ID, RP_NAME, ORIGIN configured)
  - `oauth.py` - Google OAuth 2.0 (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OAUTH_REDIRECT_URI)
  - `magic_link.py` - Email magic links with SES (SECRET_KEY for signing, SES_FROM_EMAIL, SES_REGION)
  - `session.py` - Session management (httponly, samesite=lax cookies, 7-day TTL)

**Challenge Storage:**
- PostgreSQL `challenges` table - Stores WebAuthn and OAuth state challenges
  - Columns: `id, challenge, challenge_type, expires_at, metadata`
  - TTL: WebAuthn 60s, OAuth 600s (10 minutes)
  - Implementation: `api/auth/passkey.py`, `api/auth/oauth.py`

**User Table:**
- PostgreSQL `users` table - Core identity
  - Columns: `id, near_account_id, email, username, codename, is_admin, created_at`
  - Upsert on OAuth/magic link: INSERT ... ON CONFLICT (email)

## Monitoring & Observability

**Error Tracking:**
- Not detected in codebase
- No Sentry, DataDog, or Rollbar integration found

**Logs:**
- Docker logging driver: json-file (production docker-compose.prod.yml)
  - Max size: 10m per file, max 3 files per container
  - stdout/stderr capture (standard Docker approach)
- Python logging: `logging` module (standard library, not explicitly configured)
- Implementation: Standard print statements or logging.getLogger in Python code

**Monitoring Metrics:**
- Health check endpoints (docker-compose only)
  - API: `GET /health` (8000/8000)
  - Web: `GET http://127.0.0.1:3000` (HTTP 200 check)
  - Postgres: pg_isready check

## CI/CD & Deployment

**Hosting:**
- Docker containers (self-hosted or cloud-agnostic)
- Infrastructure agnostic (works on any Docker-compatible platform)

**CI Pipeline:**
- Not detected in repository
- No GitHub Actions, GitLab CI, or Jenkins configuration found
- Deployment: Manual via docker-compose up or orchestration tool (Kubernetes assumed for prod)

**Deployment Configuration:**
- docker-compose.yml - Development environment
- docker-compose.prod.yml - Production environment with resource limits, logging, health checks
- Dockerfiles: `web/Dockerfile`, `api/Dockerfile`, `indexers/Dockerfile`
- Database migrations: Alembic runs on startup (migrate service in prod compose)

## Environment Configuration

**Required env vars (production):**
- `DATABASE_URL` - PostgreSQL connection string (REQUIRED, no default)
- `POSTGRES_PASSWORD` - Database password
- `NEARBLOCKS_API_KEY` - NearBlocks API access (rate limiting depends on presence)
- `ALCHEMY_API_KEY` - Ethereum/Polygon indexing
- `ETHERSCAN_API_KEY` - Block explorer fallback (optional)
- `COINGECKO_API_KEY` - CoinGecko pricing (optional, enables pro tier)
- `CRYPTOCOMPARE_API_KEY` - Price fallback (optional)
- `FASTNEAR_API_KEY` - FastNEAR RPC key (optional)

**Auth & Security:**
- `SECRET_KEY` - Token signing secret (REQUIRED in production)
- `GOOGLE_CLIENT_ID` - OAuth 2.0 client ID
- `GOOGLE_CLIENT_SECRET` - OAuth 2.0 client secret
- `RP_ID` - WebAuthn relying party domain (default: localhost)
- `RP_NAME` - WebAuthn relying party name (default: Axiom)
- `ORIGIN` - WebAuthn expected origin (default: http://localhost:3003)
- `OAUTH_REDIRECT_URI` - Google callback (default: http://localhost:3003/auth/oauth/callback)

**AWS Configuration:**
- `AWS_ACCESS_KEY_ID` - AWS credentials for SES
- `AWS_SECRET_ACCESS_KEY` - AWS credentials for SES
- `AWS_SES_REGION` - AWS region (default: ca-central-1)
- `AWS_SES_FROM_EMAIL` - SES sender email (default: axiom@vitalpoint.ai)
- `SES_FROM_EMAIL` - Alias for AWS_SES_FROM_EMAIL
- `SES_REGION` - Alias for AWS_SES_REGION

**Frontend Configuration:**
- `NEXT_PUBLIC_API_URL` - Backend API endpoint (default: http://localhost:8000)
- `NODE_ENV` - Environment (default: production)
- `ALLOWED_ORIGINS` - CORS origins for FastAPI (default: http://localhost:3000)

**Indexer Configuration:**
- `JOB_POLL_INTERVAL` - Job check interval in seconds (default: 5)
- `SYNC_INTERVAL_MINUTES` - Indexing sync interval (default: 15)

**Secrets location:**
- .env file (not committed, listed in .gitignore)
- Production: Environment variables injected at container runtime
- Development: `.env` in project root (with secrets, not committed)

## Webhooks & Callbacks

**Incoming:**
- OAuth 2.0 callback: `POST /auth/oauth/callback` (Google redirect)
  - Consumes: authorization code, state
  - Verifies: CSRF token via challenges table
  - Returns: Session cookie (neartax_session)

**Outgoing:**
- Magic link emails - SES outbound (not webhooks, direct email)
- No webhook subscriptions to external services detected
- No event streaming (Kafka, NATS, etc.) configured

## Integration Patterns

**Price Data Pipeline:**
1. Indexer requests price from CoinGecko API (or CryptoCompare fallback)
2. Result cached in PostgreSQL price_cache table (INSERT ... ON CONFLICT)
3. CAD conversion via Bank of Canada Valet API (if CAD requested)
4. Outlier detection: if >50% variance between sources, prefer CoinGecko
5. API endpoint returns cached price to frontend

**Blockchain Transaction Indexing:**
1. NearBlocks API queries NEAR transactions → stored in PostgreSQL
2. Alchemy API queries Ethereum/Polygon transfers → stored in PostgreSQL
3. Rate limiting enforced per-chain (NEAR: 1-3 req/sec, Alchemy: per-chain limits)
4. Indexer runs on schedule (JOB_POLL_INTERVAL, SYNC_INTERVAL_MINUTES)
5. Frontend queries PostgreSQL via FastAPI `/transactions` endpoint

**Authentication Flow:**
1. WebAuthn: Client (browser) starts ceremony → API verifies → session created
2. OAuth: Client redirects to Google → Google redirects back to callback → API upserts user
3. Magic Link: Client enters email → API sends signed link via SES → Client clicks → API verifies token
4. NEAR: Client connects wallet → API resolves account_id → session created

---

*Integration audit: 2026-03-13*
