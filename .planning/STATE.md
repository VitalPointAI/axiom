---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-03-12T18:46:21.806Z"
progress:
  total_phases: 8
  completed_phases: 2
  total_plans: 19
  completed_plans: 10
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-02-23)

**Core value:** Accurate tax reporting — every transaction correctly classified, every balance reconciled.
**Current focus:** Phase 1 - NEAR Indexer

## Current Phase

**Phase 2: Multi-Chain + Exchanges** 🔨 IN PROGRESS
- Plan 02-01: Alembic migration 002 + ChainFetcher/ExchangeParser/ExchangeConnector ABCs ✅ DONE (2026-03-12)
- Plan 02-02: EVMFetcher (Etherscan V2 pagination + PostgreSQL upsert, 4 chains) ✅ DONE (2026-03-12)
- EVM schema created (`db/schema_evm.sql`)
- Exchange parser framework built (`indexers/exchange_parsers/`)
- Coinbase parser COMPLETE ✅
- Remaining parsers: Crypto.com, Wealthsimple, Uphold, Coinsquare

**Phase 1: NEAR Indexer** COMPLETE
- Plan 01-01: PostgreSQL schema + Alembic + config cleanup ✅ DONE (2026-03-12)
- Plan 01-02: Standalone indexer service + NEAR transaction fetcher ✅ DONE (2026-03-12)
- Plan 01-03: Multi-source price service + epoch staking rewards + lockup parser ✅ DONE (2026-03-12)
- Plan 01-04: Integration wiring + web API job queue ✅ DONE (2026-03-12)
- Plan 01-05: Gap closure: account_id dispatch + staking backfill timestamp ✅ DONE (2026-03-12)
- Plan 01-06: Gap closure: wallet API handler schema fix ✅ DONE (2026-03-12)

**Phase 8: CI/CD Deployment** COMPLETE
- Plan 08-01: Production Docker Compose + deployment scripts ✅ DONE (2026-03-12)
- Plan 08-02: GitHub Actions deploy workflow + .gitignore hardening ✅ DONE (2026-03-12)

**Phase 7: Web UI** 📋 PLANNED
- Requirements added (UI-01 through UI-08)
- Will use near-phantom-auth for NEAR wallet login
- Next.js + Tailwind + shadcn/ui stack

**Needs from Aaron:**
1. Exchange CSV files (Crypto.com, Wealthsimple, Uphold, Coinsquare, Coinbase)
2. Etherscan API key for EVM chains
3. CoinGecko API key for historical prices

## Progress

| Phase | Status | Completion |
|-------|--------|------------|
| 1. NEAR Indexer | **Complete** | 100% (6/6 plans) |
| 2. Multi-Chain + Exchanges | In Progress | 33% (2/6 plans) |
| 3. Transaction Classification | Not Started | 0% |
| 4. Cost Basis Engine | Not Started | 0% |
| 5. Verification | Not Started | 0% |
| 6. Reporting | Not Started | 0% |
| 7. Web UI | **PLANNED** | 0% |

## Accumulated Context

### Roadmap Evolution
- Phase 8 added: GitHub Actions CI/CD deployment - deploy dockerized components on push to existing server

## Blockers

None currently.

## Recent Activity

- 2026-03-12: **02-02 complete** - EVMFetcher: Etherscan V2 pagination (10k/page), 4 chains (ETH/Polygon/Cronos/Optimism), PostgreSQL execute_values upsert, 23 unit tests
- 2026-03-12: **02-01 complete** - Migration 002 (exchange_transactions, exchange_connections, supported_exchanges seeded, file_imports) + ChainFetcher/ExchangeParser/ExchangeConnector ABCs
- 2026-03-12: **08-02 complete** - GitHub Actions deploy workflow (auto-deploy on push to main, manual rollback, .gitignore hardened)
- 2026-03-12: **08-01 complete** - Production Docker Compose (postgres, migrate, web, indexer) + SSH deploy script with rolling restart + health check script
- 2026-03-12: **01-06 complete** - Wallet API schema fix: GET derives sync_status from indexing_jobs subqueries, POST inserts without sync_status column, removed indexing_progress references
- 2026-03-12: **01-05 complete** - Gap closure: _claim_next_job() JOINs wallets for account_id, _get_first_stake_timestamp() falls back to transactions table, all print() replaced with logger
- 2026-03-12: **01-04 complete** - Integration wiring: StakingFetcher+LockupFetcher registered in IndexerService, wallet API uses job queue (3 jobs per wallet), sync status API reads from indexing_jobs
- 2026-03-12: **01-03 complete** - PriceService (CoinGecko+CryptoCompare+outlier filtering, 17 tests), StakingFetcher (epoch reward calc), LockupFetcher (lockup event parser)
- 2026-03-12: **01-02 complete** - Standalone IndexerService + NearFetcher (cursor resume, 20 unit tests, Dockerfile updated to service mode)
- 2026-03-12: **01-01 complete** - PostgreSQL schema (8 tables), Alembic framework, indexers/db.py, config.py cleaned (no SQLite)
- 2026-03-11: **Phase 1 context gathered** - Major scope expansion: multi-user, multi-chain-ready architecture, standalone indexer service, PostgreSQL-only, epoch-level staking, multi-source price service
- 2026-02-24: **Phase 7 (Web UI) added** - NEAR wallet auth + portfolio UI
- 2026-02-23: Phase 2 started - EVM schema + exchange parser framework
- 2026-02-23: Coinbase parser complete
- 2026-02-23: Phase 1 COMPLETE - NEAR indexer working
- 2026-02-23: Project initialized with GSD framework
- 2026-02-23: Wallet inventory confirmed (64 NEAR + multi-chain)
- 2026-02-23: Initial balance scan completed (20,076.35 NEAR total)
- 2026-02-23: Discovery UPDATED - NearBlocks rate limits found (~6 req before 429)

## Questions Pending

1. ~~Lockup vesting schedule for `db59d...lockup.near`?~~ **ANSWERED:** Vesting COMPLETE ~2021 (1 year after opening)
2. Which exchanges have most activity? (needed for Phase 2)
3. ~~VitalPoint AI fiscal year end (calendar year or different)?~~ **ANSWERED:** User-configurable, default Jan-Dec
4. ~~Any OTC trades outside exchanges?~~ **ANSWERED:** No OTC currently
5. Accountant's preferred report format? **ANSWERED:** Koinly-compatible CSV + Universal CSV

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-23 | Build custom vs Koinly | Koinly lacks API, misses transactions |
| 2026-02-23 | FastNear RPC | Default NEAR RPC rate-limited |
| 2026-02-23 | NearBlocks with 1.5s delay | Free tier rate limits after ~6 rapid requests |
| 2026-02-23 | Resumable indexer | 23,679 txs for main account = 15-30 min, needs interruption handling |
| 2026-03-12 | JSONB for raw_data | Enables indexed queries on tx data vs TEXT |
| 2026-03-12 | NUMERIC(40,0) for yoctoNEAR | Prevents floating point precision loss |
| 2026-03-12 | No DATABASE_URL fallback | Explicit failure prevents silent misconfiguration |
| 2026-03-12 | Alembic for schema | Versioned migrations via op.create_table(), not raw SQL files |
| 2026-03-12 | parse_transaction() module-level | Allows direct import in tests without instantiating DB pool |
| 2026-03-12 | Action priority for multi-action txs | TRANSFER > FUNCTION_CALL > STAKE > CREATE > DELETE > DEPLOY > KEY ops |
| 2026-03-12 | Dockerfile build context = project root | Required to COPY config.py and db/ alongside indexers/ |
| 2026-03-12 | check_incremental_syncs() on empty poll | Simpler than a timer thread; latency = JOB_POLL_INTERVAL when queue empties |
| 2026-03-12 | 50% outlier threshold for multi-source price | Balances detecting bad data vs. normal spread between CoinGecko + CryptoCompare |
| 2026-03-12 | CAD rate in price_cache table | Reuses existing table vs separate exchange_rates table — simpler schema |
| 2026-03-12 | Lockup event de-dup by tx_hash+event_type | No unique constraint on tx_hash alone in lockup_events schema |
| 2026-03-12 | Dispatch by job_type not chain | Handlers map to operation not blockchain; correct abstraction |
| 2026-03-12 | Staking sync at 4x tx interval | Staking rewards are epoch-level (~12h), hourly polling is sufficient |
| 2026-03-12 | EVM spawn removed, job queue deferred | EVM job queue is Phase 2 scope; NEAR pipeline complete without it |
| 2026-03-12 | Derive wallet sync_status from indexing_jobs via CASE subqueries | wallets table has no sync_status column; status derived live from job states |
| 2026-03-12 | FOR UPDATE OF ij SKIP LOCKED for JOINed job claims | PostgreSQL requires specifying locked table when SELECT JOINs multiple tables |
| 2026-03-12 | transactions table as fallback for first-stake timestamp | staking_events is unpopulated for fresh wallets; transactions always has STAKE/FUNCTION_CALL records |
| 2026-03-12 | No Docker registry for deployment | Single-server: build on server is simpler than push/pull through registry |
| 2026-03-12 | Rolling restart order: web then indexer | User-facing service first, background indexer second; postgres never restarts |
| 2026-03-12 | Rollback via git checkout SHA | Simpler than image tagging for single-server setup |
| 2026-03-12 | SSH key temp file with always() cleanup | Prevents key leakage in GitHub Actions runners |
| 2026-03-12 | .env via SSH heredoc from GitHub Secrets | Secrets never written to repo or runner filesystem |
| 2026-03-12 | Concurrency group with cancel-in-progress: false | Queues deployments rather than canceling in-flight ones |
| 2026-03-12 | confidence_score NUMERIC(4,3) NULL for CSV parsers | AI agent imports use 0-1 score; NULL means traditional parser (always correct) |
| 2026-03-12 | file_imports SHA-256 content hash dedup | Prevents re-importing same file; UNIQUE(user_id, file_hash) enforced at DB level |
| 2026-03-12 | supported_exchanges VARCHAR slug PK | Human-readable FK in exchange_transactions ('coinbase' vs 42); easier to debug |
| 2026-03-12 | ExchangeParser and ExchangeConnector as separate ABCs | File parsing and API connectivity are orthogonal; CSV-only exchanges (Wealthsimple) need no Connector |
| 2026-03-12 | CHAIN_NAME_MAP for bidirectional resolution | Bidirectional mapping between CHAIN_CONFIG keys (ETH/Polygon) and DB values (ethereum/polygon) |
| 2026-03-12 | ERC20/NFT tx_hash = hash-logIndex | Multiple token transfers share parent tx_hash; logIndex suffix prevents unique constraint violations |
| 2026-03-12 | fee=None for internal/ERC20/NFT | Gas already counted in the parent normal tx; avoids double-counting fees |

---
*Last updated: 2026-03-12 — Stopped at: Completed 02-multichain-exchanges 02-02-PLAN.md*
