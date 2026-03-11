# External Integrations

**Analysis Date:** 2026-03-11

## APIs & External Services

### Blockchain Data APIs

**NearBlocks API:**
- Purpose: NEAR Protocol transaction history, staking deposits, account data
- Client: `indexers/nearblocks_client.py` (`NearBlocksClient` class)
- Base URL: `https://api.nearblocks.io/v1`
- Auth: `NEARBLOCKS_API_KEY` env var (paid tier: 190 calls/min; free tier: ~6 rapid requests before 429)
- Rate limiting: 1.0s delay (paid) or 3.0s (free), exponential backoff on 429, max 5 retries
- Used by: `indexers/near_indexer_nearblocks.py`, `indexers/ft_indexer.py`

**FastNEAR RPC:**
- Purpose: NEAR blockchain RPC calls (account balances, contract state)
- Client (TypeScript): `web/lib/near-rpc.ts` (`nearRpcCall()`, `viewAccount()`)
- Client (Python): Direct in `config.py`
- Base URLs:
  - `https://rpc.mainnet.fastnear.com/{API_KEY}` (with key)
  - `https://rpc.fastnear.com` (free, no rate limit for basic calls)
  - `https://archival-rpc.mainnet.fastnear.com` (archival data)
- Auth: `FASTNEAR_API_KEY` env var (optional)

**NEARDATA API:**
- Purpose: High-throughput block-level indexing for tax-grade reliability
- Client: `indexers/neardata_indexer.py` (async with aiohttp)
- Features: Block-level state tracking, gap detection, verification passes, graceful shutdown

**Etherscan V2 API:**
- Purpose: EVM chain transaction history (Ethereum, Polygon, Cronos, Optimism)
- Client: `indexers/evm_indexer.py`
- Base URL: `https://api.etherscan.io/v2/api` (unified V2 endpoint with chainid param)
- Auth: `ETHERSCAN_API_KEY` env var
- Supported chains: ETH (chainid 1), Polygon (137), Cronos (25, uses separate API), Optimism (10, paid tier)
- Note: V1 API deprecated Aug 2025

**Alchemy API:**
- Purpose: EVM asset transfers with full gas fee tracking (Ethereum, Polygon)
- Client: `indexers/evm_indexer_alchemy.py`
- Base URLs: `https://eth-mainnet.g.alchemy.com/v2/{KEY}`, `https://polygon-mainnet.g.alchemy.com/v2/{KEY}`
- Auth: `ALCHEMY_API_KEY` env var
- Method: `getAssetTransfers` (includes zero-value contract calls)

**Cronos Explorer API:**
- Purpose: Cronos chain transaction data
- Client: `indexers/evm_indexer.py` (custom_api path)
- Base URL: `https://cronos.org/explorer/api`
- Auth: `CRONOS_API_KEY` env var

**XRP Ledger API:**
- Purpose: XRP transaction history
- Client: `indexers/xrp_indexer.py` (`XRPIndexer` class)
- Endpoints: `https://xrplcluster.com`, `https://s1.ripple.com:51234`, `https://s2.ripple.com:51234`
- Auth: None required (public JSON-RPC)
- Rate limit: 0.5s delay (2 req/sec)

**Akash Network LCD API:**
- Purpose: Akash (Cosmos SDK) transaction history
- Client: `indexers/akash_indexer.py` (`AkashIndexer` class)
- Endpoints: `https://api.akash.forbole.com`, `https://akash-api.polkachu.com`, `https://akash-rest.publicnode.com`
- Auth: None required (public REST)
- Rate limit: 0.5s delay

### Price Data APIs

**Pyth Network (Hermes):**
- Purpose: Real-time price feeds for major tokens (NEAR, ETH, BTC, AURORA, USDC, USDT)
- Client: `web/lib/token-prices.ts` (`fetchPythPrice()`)
- Base URL: `https://hermes.pyth.network`
- Auth: None required
- Priority: Primary price source in web app
- Cache: 5-minute in-memory TTL

**Ref Finance API:**
- Purpose: NEAR ecosystem token prices (wNEAR, stNEAR, LiNEAR, REF, OCT, AURORA)
- Client: `web/lib/token-prices.ts` (`fetchRefPrices()`)
- Base URL: `https://api.ref.finance`
- Auth: None required
- Priority: Secondary price source (after Pyth)

**CoinGecko API:**
- Purpose: Historical price data, current price fallback
- Client (TypeScript): `web/lib/prices.ts` (`getNearPriceForDate()`, `getCurrentNearPrice()`)
- Base URL: `https://api.coingecko.com/api/v3`
- Auth: `COINGECKO_API_KEY` env var (optional, for indexer)
- Cache: 24h for historical, 60s for current (Next.js revalidate)

**CoinCap API:**
- Purpose: Fallback current price source
- Client: `web/lib/prices.ts` (`getCurrentNearPrice()` fallback)
- Base URL: `https://api.coincap.io/v2`
- Auth: None required

**CryptoCompare API:**
- Purpose: Historical hourly/daily price data for cost basis calculations
- Client: `indexers/price_service.py` (`get_hourly_price()`)
- Base URL: `https://min-api.cryptocompare.com/data/v2`
- Auth: None (free tier)
- Used for: Backfilling cost basis on indexed transactions

**Exchange Rate API:**
- Purpose: Fiat currency exchange rates (USD to CAD, EUR, GBP, etc.)
- Client: `web/app/api/exchange-rates/route.ts`
- Base URL: `https://api.exchangerate.host/latest`
- Auth: None required
- Cache: 1 hour in-memory
- Fallback: Hardcoded rates for 12 currencies

### Exchange Connectors (CEX APIs)

**Coinbase Advanced Trade API:**
- Purpose: Trade history, deposits, withdrawals from Coinbase
- Client: `indexers/coinbase_indexer.py`, `indexers/exchange_connectors/coinbase.py`
- Base URL: `https://api.coinbase.com`
- Auth: JWT with EC private key (`COINBASE_CREDS` env var pointing to JSON file)
- Dependencies: `PyJWT`, `cryptography` (optional import)

**Kraken API:**
- Purpose: Account balances, trade history, deposit/withdrawal history
- Client: `indexers/exchange_connectors/kraken.py` (`KrakenConnector` class)
- Base URL: `https://api.kraken.com`
- Auth: HMAC-SHA512 signature with base64-encoded API keys

**Crypto.com Exchange API:**
- Purpose: Account balances, trade history, deposits/withdrawals
- Client: `indexers/exchange_connectors/cryptocom.py` (`CryptoComConnector` class)
- Base URL: `https://api.crypto.com/exchange/v1`
- Auth: HMAC-SHA256 signature

### Exchange Statement Parsers (CSV/PDF Import)

**Supported formats (parsed from uploaded files, no API):**
- Coinbase: `indexers/exchange_parsers/coinbase.py`
- Crypto.com: `indexers/exchange_parsers/crypto_com.py`
- Wealthsimple: `indexers/exchange_parsers/wealthsimple.py`
- Generic CSV: `indexers/exchange_parsers/generic.py`
- PDF statements: `web/app/api/import/pdf/route.ts` (uses `pdf-parse`, `pdf2json`, `pdfjs-dist`)

## Data Storage

**Databases:**
- PostgreSQL 16 (Production)
  - Connection: `DATABASE_URL` env var (format: `postgres://neartax:{password}@{host}:5432/neartax`)
  - Web client: `pg` (Node.js) via connection pool in `web/lib/db.ts` (max 20 connections, 30s idle timeout)
  - Indexer client: `psycopg2-binary` (Python)
  - Schemas: `db/schema.sql`, `db/schema_evm.sql`, `db/schema_users.sql`, `db/schema_exchanges.sql`, `01_create_table.sql`
  - Note: Web DB layer converts `?` placeholders to `$1, $2...` for Postgres compatibility (`web/lib/db.ts` `convertPlaceholders()`)

- SQLite (Legacy/Scripts)
  - Path: `neartax.db` (configured via `NEARTAX_DB` env var or `config.py` `DATABASE_PATH`)
  - Client (Python): `sqlite3` stdlib via `db/init.py` `get_connection()`
  - Client (Node.js): `better-sqlite3` in `scripts/`
  - Status: Python indexers still reference SQLite via `db/init.py`; web app fully migrated to PostgreSQL

**File Storage:**
- Local filesystem only (no cloud storage)
- Output directory: `output/` (gitignored)
- Reports directory: `reports/` (gitignored)

**Caching:**
- In-memory Map caches in web app:
  - Token prices: 5-min TTL (`web/lib/token-prices.ts`)
  - Historical prices: unbounded Map (`web/lib/prices.ts`)
  - Exchange rates: 1-hour TTL (`web/app/api/exchange-rates/route.ts`)
  - Passkey challenges: global Map with 60s cleanup interval (`web/lib/passkey-challenges.ts`)
- Next.js `revalidate` for fetch caching (24h historical prices, 60s current prices)

## Authentication & Identity

**Passkey/WebAuthn (Primary):**
- Implementation: `@simplewebauthn/server` + `@simplewebauthn/browser`
- Registration flow: `web/app/api/phantom-auth/register/start/route.ts` -> `finish/route.ts`
- Login flow: `web/app/api/phantom-auth/login/start/route.ts` -> `finish/route.ts`
- Challenge storage: In-memory global Map (`web/lib/passkey-challenges.ts`)
- DB tables: `users`, `passkeys`, `sessions` (PostgreSQL)
- Session: Cookie-based (`neartax_session`), 7-day expiry, httpOnly + secure + sameSite:lax

**Google OAuth (Secondary):**
- Implementation: Custom OAuth 2.0 flow
- Client: `web/app/api/phantom-auth/oauth/callback/route.ts`
- Auth: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` env vars
- Redirect: `{NEXT_PUBLIC_APP_URL}/api/phantom-auth/oauth/callback`
- Providers endpoint: `web/app/api/phantom-auth/oauth/providers/route.ts`

**NEAR Wallet Auth:**
- Package: `@vitalpoint/near-phantom-auth` 0.5.2
- WalletConnect: `@walletconnect/sign-client` 2.23.6

**Session Management:**
- Implementation: `web/lib/auth.ts` (`getAuthenticatedUser()`, `createSession()`, `invalidateCurrentSession()`)
- DB-backed sessions with expiry checks
- Accountant delegation: Cookie `neartax_viewing_as` for viewing client accounts
- Permission levels: `read`, `readwrite` for accountant access
- Admin check: `is_admin` flag on users table

**Auth DB Helper:**
- `web/lib/auth-db.ts` - Separate pool for auth queries (`getUser()`, `getPasskey()`, `getSession()`)

## Email Service

**AWS SES:**
- Purpose: Transactional emails (accountant invitations)
- Client: `@aws-sdk/client-ses` in `web/lib/email.ts`
- Region: `AWS_SES_REGION` env var (default: `ca-central-1`)
- From: `AWS_SES_FROM_EMAIL` env var (default: `neartax@vitalpoint.ai`)
- Auth: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` env vars
- Functions: `sendEmail()`, `sendAccountantInviteEmail()`

## DeFi Protocol Integrations

**Burrow Finance (Lending/Borrowing):**
- Parser: `defi/burrow_parser.py`
- Tracker: `indexers/burrow_tracker.py`
- Contracts: `contract.main.burrow.near`, `burrow.near`
- Tax events: Interest earned (income), BRRR rewards (income), liquidations (capital loss)

**Ref Finance (DEX):**
- Parser: `defi/ref_finance_parser.py`
- Price API: `https://api.ref.finance/list-token-price`

**Meta Pool (Liquid Staking):**
- Parser: `defi/meta_pool_parser.py`

**SWEAT Jars:**
- Tracker: `indexers/sweat_jars_tracker.py`
- Cron: Daily at 5am UTC

**Aurora (Intents/Swap):**
- Widget: `@aurora-is-near/intents-swap-widget` 6.3.1

## Monitoring & Observability

**Error Tracking:**
- None (console.error only)

**Logs:**
- Console logging throughout (`console.log`, `console.error`)
- Python: `print()` statements, some `logging` module usage in `neardata_indexer.py`
- Cron logs: `/var/log/cron.log` in indexer container

**Health Check:**
- Endpoint: `web/app/api/health/` (used in Docker healthcheck)
- Docker: 30s interval, 10s timeout, 3 retries

## CI/CD & Deployment

**Hosting:**
- Docker Compose on self-hosted infrastructure
- Domain: `neartax.vitalpoint.ai` (inferred from `NEXT_PUBLIC_APP_URL`)

**CI Pipeline:**
- None detected (GitHub Actions workflow was removed per commit history: "Remove workflow (token scope issue)")

## Scheduled Tasks

**Cron Jobs (in indexer container):**
- `indexers/crontab` defines the schedule:
  - Every 5 min: Price indexer (`price_indexer.py`)
  - Every 6 hours: NEAR indexer (`near_indexer_nearblocks.py`)
  - Every 6 hours (offset +1h): FT token indexer (`ft_indexer.py`)
  - Every 6 hours (offset +2h): EVM indexer (`evm_indexer.py`)
  - Every 6 hours (offset +3h): DeFi/Burrow tracker (`burrow_tracker.py`)
  - Daily 4am UTC: Staking tracker
  - Daily 5am UTC: SWEAT Jars tracker

## Environment Configuration

**Required env vars (critical for operation):**
- `DATABASE_URL` - PostgreSQL connection string
- `POSTGRES_PASSWORD` - Database password
- `NEARBLOCKS_API_KEY` - NEAR transaction indexing

**Required env vars (for full functionality):**
- `ETHERSCAN_API_KEY` - EVM chain indexing
- `ALCHEMY_API_KEY` - EVM detailed transfers
- `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` - Email sending
- `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` - Google OAuth login
- `NEXT_PUBLIC_APP_URL` - Base URL for OAuth redirects and links

**Optional env vars:**
- `FASTNEAR_API_KEY` - Better RPC rate limits
- `COINGECKO_API_KEY` - Better price data rate limits
- `COINBASE_CREDS` - Path to Coinbase API credentials JSON
- `CRONOS_API_KEY` - Cronos chain indexing
- `AWS_SES_REGION` - SES region (default: ca-central-1)
- `AWS_SES_FROM_EMAIL` - Email sender (default: neartax@vitalpoint.ai)

**Secrets location:**
- `.env` file at project root (gitignored)
- `.credentials/` directory (gitignored)
- Coinbase credentials in JSON file at path specified by `COINBASE_CREDS`

## Webhooks & Callbacks

**Incoming:**
- Google OAuth callback: `GET /api/phantom-auth/oauth/callback`

**Outgoing:**
- None detected

---

*Integration audit: 2026-03-11*
