# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-02-23)

**Core value:** Accurate tax reporting — every transaction correctly classified, every balance reconciled.
**Current focus:** Phase 1 - NEAR Indexer

## Current Phase

**Phase 2: Multi-Chain + Exchanges** 🔨 IN PROGRESS
- EVM schema created (`db/schema_evm.sql`)
- Exchange parser framework built (`indexers/exchange_parsers/`)
- Coinbase parser COMPLETE ✅
- Remaining parsers: Crypto.com, Wealthsimple, Uphold, Coinsquare

**Phase 1: NEAR Indexer** 🔨 IN PROGRESS
- Plan 01-01: PostgreSQL schema + Alembic + config cleanup ✅ DONE (2026-03-12)
- Plan 01-02: Standalone indexer service + NEAR transaction fetcher ✅ DONE (2026-03-12)
- Plan 01-03: Multi-source price service + epoch staking rewards + lockup parser (next)
- Plan 01-04: Integration wiring + web API job queue

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
| 1. NEAR Indexer | **In Progress** | 50% (2/4 plans) |
| 2. Multi-Chain + Exchanges | In Progress | 40% |
| 3. Transaction Classification | Not Started | 0% |
| 4. Cost Basis Engine | Not Started | 0% |
| 5. Verification | Not Started | 0% |
| 6. Reporting | Not Started | 0% |
| 7. Web UI | **PLANNED** | 0% |

## Blockers

None currently.

## Recent Activity

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

---
*Last updated: 2026-03-12 — Stopped at: Completed 01-near-indexer 01-02-PLAN.md*
