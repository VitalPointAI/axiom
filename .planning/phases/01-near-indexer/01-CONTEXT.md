# Phase 1: NEAR Indexer - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Pull complete NEAR transaction history for all user-added wallets including staking rewards (epoch-level) and lockup vesting events into PostgreSQL. Build the indexer as a standalone multi-chain-ready service with a database-backed job queue. Includes a multi-source price service for all tokens from day one.

</domain>

<decisions>
## Implementation Decisions

### Data Source Strategy
- Use NearBlocks API as primary data source for NEAR transaction history
- Adaptive rate limiting: faster with paid API key, throttled on free tier (config.py pattern already exists)
- Dynamic wallet list — indexer tracks whatever wallets users add, not a fixed set
- When user adds a wallet, create a queued background job (not immediate on-demand)
- Periodic incremental sync after initial full history pull (cron-based, e.g. every 15-30 min)
- All SQLite usage must be eliminated — every indexer and script must use PostgreSQL

### Indexer Architecture
- Standalone Python service running in the indexer Docker container
- Polls a PostgreSQL-backed job queue for pending work
- Decoupled from Next.js web app — no subprocess spawning from API routes
- Multi-chain ready from day one: architecture supports plugging in EVM/other chain handlers in Phase 2
- NEAR is the only chain implemented in Phase 1, but the job queue and service structure are chain-agnostic

### Staking Reward Tracking
- Epoch-level granularity (~7.5 hour epochs) for staking rewards
- Calculation method: retrieve total stake from validators epoch-to-epoch, determine reward received, calculate user's staked share of that reward minus validator fees
- Full history backfill for each wallet from first stake event (not just current tax year)
- Multi-user: each user tracks staking income per validator they delegate to
- Use FastNear archival RPC for historical validator epoch data
- Capture FMV at time of reward receipt (stored in shared price_cache table)

### Price Service
- Multi-source price aggregation with outlier filtering for accuracy
- Primary: CoinGecko. Fallback: CryptoCompare. Consult multiple sources and average results (excluding outliers) for more accurate price history
- On-demand with caching: look up price when needed, cache in a dedicated price_cache table
- Price cache is token-agnostic — supports all chains/tokens from day one, not just NEAR
- Shared across all transaction types (staking rewards, transfers, swaps, etc.)
- Per-minute price tables for all tokens as a future enhancement (deferred to pre-build step)

### Resume & Reliability
- Cursor-based resume: track last successful cursor/page per wallet in job queue table
- Self-healing indexer: auto-retry failed jobs indefinitely with exponential backoff until fully synced
- No manual intervention expected from users — indexer must auto-recover
- Dual verification after syncing each wallet:
  1. Transaction count check against NearBlocks reported count
  2. Balance reconciliation: calculated balance vs on-chain balance via RPC
- Sync status surfaced in UI (existing sync-status.tsx and indexer-status.tsx components)

### Schema & Migration
- Fresh PostgreSQL schema from scratch — no adaptation of SQLite-flavored db/schema.sql
- Proper PostgreSQL types: SERIAL, NUMERIC, JSONB, TIMESTAMPTZ
- Multi-user isolation from day one: user_id foreign key on all data tables
- Migration framework (Alembic or node-pg-migrate) for versioned schema changes and rollbacks
- Address CONCERNS.md items: remove hardcoded API key fallbacks, remove hardcoded database credentials, eliminate all SQLite references

### Claude's Discretion
- Whether to migrate existing SQLite data or re-index from scratch (priority: 100% data accuracy)
- Specific migration framework choice (Alembic vs node-pg-migrate vs other)
- Job queue polling interval and concurrency settings
- Exact periodic sync frequency (15 vs 30 min)
- Price outlier detection algorithm
- How to handle wallets with zero on-chain activity

</decisions>

<specifics>
## Specific Ideas

- "The indexer must accurately ingest all transactions for all wallets that need to be tracked and do so in the most efficient manner possible staying within current API rate limits"
- "Can't expect the user to do something to help it — it needs to self heal"
- "The ultimate goal is 100% data accuracy"
- Originally a single-user system for 64 NEAR accounts, now expanding to multi-user service — all design decisions reflect this shift
- Existing epoch_rewards_indexer.py has a working pattern for epoch reward calculation with price caching that can inform the new implementation

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `indexers/nearblocks_client.py`: Rate-limited NearBlocks API client with exponential backoff — core of data fetching, needs PostgreSQL migration
- `indexers/epoch_rewards_indexer.py`: Epoch reward calculation pattern with CryptoCompare price lookup and price_cache table — already uses PostgreSQL (psycopg2)
- `indexers/staking_rewards.py`: FastNear RPC calls for validator pool balance queries — reusable for epoch backfill
- `indexers/lockup_parser.py`: Lockup contract state queries and method calls via RPC — reusable
- `config.py`: Centralized API key and rate limit configuration with adaptive paid/free tier handling
- `web/components/sync-status.tsx`, `web/components/indexer-status.tsx`: Existing UI components for sync status display

### Established Patterns
- Rate limiting: Adaptive delay based on API key presence (config.py RATE_LIMIT_DELAY)
- Error handling: Exponential backoff with max retries (nearblocks_client.py)
- Database access: psycopg2 for Python indexers, pg Pool for web app (web/lib/db.ts)
- Docker: Separate indexer container with cron (docker-compose.yml, indexers/Dockerfile)

### Integration Points
- `wallets.json`: Current wallet list (will be replaced by database-driven wallet management)
- `docker-compose.yml`: Indexer service container — needs updated entrypoint for standalone service
- `web/app/api/wallets/route.ts`: Wallet management API — will need to create job queue entries when wallets are added
- `web/app/api/sync/status/route.ts`: Sync status API — will read from job queue table
- `db/schema_users.sql`: Existing user auth tables for multi-user foreign keys

</code_context>

<deferred>
## Deferred Ideas

- Pre-built per-minute price tables for all tokens (build as background job, not blocking indexing)
- Email notifications for sync failures on long-running jobs (Phase 7 or later)
- Full multi-chain indexing implementation (Phase 2 — architecture ready in Phase 1)

</deferred>

---

*Phase: 01-near-indexer*
*Context gathered: 2026-03-11*
