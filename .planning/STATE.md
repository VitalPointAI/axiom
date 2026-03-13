---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-03-13T19:03:00.000Z"
progress:
  total_phases: 8
  completed_phases: 6
  total_plans: 28
  completed_plans: 28
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-02-23)

**Core value:** Accurate tax reporting — every transaction correctly classified, every balance reconciled.
**Current focus:** Phase 1 - NEAR Indexer

## Current Phase

**Phase 6: Reporting** IN PROGRESS
- Plan 06-01: ReportEngine base class + CapitalGainsReport + IncomeReport ✅ DONE (2026-03-13)
- Plan 06-02: LedgerReport + T1135Checker + SuperficialLossReport (Wave 2) - PENDING
- Plan 06-03: KoinlyExport + accounting software exports - PENDING
- Plan 06-04: Inventory Holdings + COGS + Business Income Statement + FIFO engine - PENDING
- Plan 06-05: PDF templates + PackageBuilder + ReportHandler job wiring - PENDING

**Phase 5: Verification** COMPLETE ✅
- Plan 05-01: Migration 005 + SQLAlchemy models + VerifyHandler skeleton + service/ACB wiring + config tolerances ✅ DONE (2026-03-13)
- Plan 05-02: BalanceReconciler: NEAR decomposed + EVM + dual cross-check + auto-diagnosis ✅ DONE (2026-03-13)
- Plan 05-03: DuplicateDetector: hash dedup + bridge heuristic + exchange re-scan + balance-aware merge ✅ DONE (2026-03-13)
- Plan 05-04: GapDetector + DiscrepancyReporter + VerifyHandler final wiring ✅ DONE (2026-03-13)
- Full pipeline: classify -> ACB -> verify_balances (reconcile -> duplicates -> gaps -> report)

**Phase 2: Multi-Chain + Exchanges** COMPLETE ✅
- Plan 02-01: Alembic migration 002 + ChainFetcher/ExchangeParser/ExchangeConnector ABCs ✅ DONE (2026-03-12)
- Plan 02-02: EVMFetcher (Etherscan V2 pagination + PostgreSQL upsert, 4 chains) ✅ DONE (2026-03-12)
- Plan 02-03: Exchange CSV parsers migrated to PostgreSQL (all 5 parsers + 21 unit tests) ✅ DONE (2026-03-12)
- Plan 02-04: Service wiring + file upload API (EVMFetcher + FileImportHandler wired, POST /api/upload-file) ✅ DONE (2026-03-12)
- Plan 02-05: AIFileAgent + Claude API + confidence scoring (CONFIDENCE_THRESHOLD=0.8, 17 tests) ✅ DONE (2026-03-12)
- Plan 02-06: DedupHandler + XRP/Akash stubs + AI fallback + all 8 job types in service.py ✅ DONE (2026-03-12)
- Plan 02-07: Gap closure — migration 002b (updated_at), DedupHandler epoch integers, upload-file ON CONFLICT fix ✅ DONE (2026-03-12)
- EVM schema created (`db/schema_evm.sql`)
- Exchange parser framework built (`indexers/exchange_parsers/`)
- All 5 exchange parsers (Coinbase, Crypto.com, Wealthsimple, Uphold, Coinsquare) COMPLETE ✅

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
| 2. Multi-Chain + Exchanges | **Complete** | 100% (6/6 plans) |
| 3. Transaction Classification | **Complete** | 100% (5/5 plans) |
| 4. Cost Basis Engine | **Complete** | 100% (3/3 plans) |
| 5. Verification | **Complete** | 100% (4/4 plans) |
| 6. Reporting | In Progress | 20% (1/5 plans) |
| 7. Web UI | **PLANNED** | 0% |

## Accumulated Context

### Roadmap Evolution
- Phase 8 added: GitHub Actions CI/CD deployment - deploy dockerized components on push to existing server

## Blockers

None currently.

## Recent Activity

- 2026-03-13: **06-01 complete** - ReportEngine (needs_review gate check + specialist override), CapitalGainsReport (chronological + grouped-by-token CSVs, 50% inclusion), IncomeReport (detail + monthly CSVs), 25 tests; reports/ removed from .gitignore
- 2026-03-13: **05-04 complete** - GapDetector (monthly balance checkpoints vs archival NEAR RPC relative deltas, targeted re-index queuing), DiscrepancyReporter (DISCREPANCIES.md generation), VerifyHandler fully wired with all 4 modules. Phase 5 COMPLETE.
- 2026-03-13: **05-03 complete** - DuplicateDetector with 3-scan pipeline (hash dedup score=1.0, bridge heuristic score=0.60, exchange re-scan multi-signal 0.85/0.80/0.60), balance-aware auto-merge, verification_results audit trail; 885 lines
- 2026-03-13: **05-02 complete** - BalanceReconciler rewrite (1002 lines): NEAR decomposed balance (liquid+locked+staked via RPC), EVM Etherscan V2 native balance, dual cross-check (ACBPool vs raw replay), 4-category auto-diagnosis (missing_staking_rewards, uncounted_fees, unindexed_period, classification_error), exchange manual balance path, verification_results upsert
- 2026-03-13: **05-01 complete** - Migration 005 (verification_results, account_verification_status), VerifyHandler skeleton, service.py + acb_handler.py wiring, RECONCILIATION_TOLERANCES config; pipeline: classify -> ACB -> verify_balances
- 2026-03-12: **04-03 complete** - SuperficialLossDetector (61-day window, cross-source, pro-rated denial, needs_review), ACBHandler job type, calculate_acb registered in IndexerService, ClassifierHandler auto-queues ACB job after classification; 182 tests pass. Phase 4 COMPLETE.
- 2026-03-12: **04-02 complete** - Rewrote engine/acb.py (ACBPool Decimal-precise, ACBEngine replay + acb_snapshots upsert, resolve_token_symbol, normalize_timestamp), created engine/gains.py (GainsCalculator: record_disposal + record_income), 13 unit tests; 179 tests pass.
- 2026-03-12: **04-01 complete** - Migration 004 (acb_snapshots, capital_gains_ledger, income_ledger, price_cache_minute), 4 SQLAlchemy models, PriceService extended with get_price_at_timestamp() (CoinGecko market_chart/range, minute cache), get_boc_cad_rate() (BoC Valet API, 5-day weekend fallback), get_price_cad_at_timestamp(); test scaffolds for ACBPool, ACBEngine, SuperficialLoss; 176 tests pass.
- 2026-03-12: **03-05 complete** - ClassifierHandler job type + AI fallback via Claude API (confidence < 0.70 threshold), rule auto-seeding, full pipeline wired into IndexerService; 151 tests pass. Phase 3 COMPLETE.
- 2026-03-12: **03-04 complete** - TransactionClassifier rewrite (rule priority matching, WalletGraph/SpamDetector integration, staking/lockup linkage, EVM swap decomposition, audit logging), 15 tests; 151 tests pass
- 2026-03-12: **03-03 complete** - EVMDecoder (21 DeFi selectors, multi-token grouping), rule seeder (56 rules: 23 NEAR + 23 EVM + 10 exchange), 16 new tests; 136 tests pass
- 2026-03-12: **03-02 complete** - WalletGraph PostgreSQL rewrite (internal transfer detection, 5%/30-min cross-chain matching, wallet discovery), SpamDetector (multi-signal 0.46/signal, 0.99 for known contracts, global propagation), 13 unit tests; 136 tests pass
- 2026-03-12: **03-01 complete** - Classification schema: migration 003 (4 tables: transaction_classifications, classification_rules, spam_rules, classification_audit_log), 4 SQLAlchemy models, 30 test scaffolds; 107 pre-existing tests pass
- 2026-03-12: **02-07 complete** - Gap closure: migration 002b (updated_at TIMESTAMPTZ), DedupHandler epoch int conversion, upload-file ON CONFLICT(user_id, account_id, chain); 54 tests pass
- 2026-03-12: **02-06 complete** - DedupHandler (1% tolerance + 10-min window + direction alignment), XRPFetcher + AkashFetcher stubs, AI fallback in FileImportHandler, all 8 Phase 2 job types in service.py; 10 unit tests
- 2026-03-12: **02-05 complete** - AIFileAgent: Claude claude-sonnet-4-20250514 extracts transactions from any CSV/XLSX/PDF; CONFIDENCE_THRESHOLD=0.8; needs_review flag; 17 unit tests (all mocked, zero real API calls)
- 2026-03-12: **02-04 complete** - Service wiring: EVMFetcher + FileImportHandler registered in IndexerService; FileImportHandler auto-detects exchange format; POST /api/upload-file with SHA-256 dedup, 50MB limit, job queuing
- 2026-03-12: **02-03 complete** - All 5 exchange CSV parsers (Coinbase, Crypto.com, Wealthsimple, Uphold, Coinsquare) migrated to PostgreSQL; import_to_db uses pool/user_id/ON CONFLICT; 21 unit tests passing
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
| 2026-03-12 | import_to_db pool.putconn() in finally block | Prevents connection leaks when DB insert raises exception |
| 2026-03-12 | tx_id generated from tx_date+asset+qty+type when absent | Coinbase/Wealthsimple CSVs have no exchange tx_id; deterministic ID enables ON CONFLICT dedup |
| 2026-03-12 | raw_data as dict in parse_row, JSON string only at INSERT | Keeps parse_row output JSONB-ready; serialization happens once at persistence boundary |
| 2026-03-12 | Per-user exchange wallet: exchange_imports_{userId} | wallets.account_id is globally UNIQUE; user-scoped name prevents constraint violation for multi-user |
| 2026-03-12 | file_imports.id as indexing_jobs.cursor | Cursor (TEXT) stores file_imports.id so FileImportHandler can look up file without extra join |
| 2026-03-12 | needs_ai vs failed for unknown exchange formats | Unknown formats → needs_ai for AI agent (plan 05); 'failed' would block re-processing |
| 2026-03-12 | Lazy Anthropic client init via @property | Avoids startup failure if anthropic SDK not installed; client only instantiated when process_file() called |
| 2026-03-12 | CONFIDENCE_THRESHOLD=0.8 as importable module constant | Smart routing layer can import same threshold; easy to tune without changing agent class |
| 2026-03-12 | Regex fallback for JSON extraction in AI response | Claude sometimes wraps JSON in markdown code blocks; regex handles without crashing |
| 2026-03-12 | ai_{file_import_id}_{index} for missing tx_id | Deterministic ID enables ON CONFLICT dedup on re-import without requiring consistent Claude output |
| 2026-03-12 | DedupHandler uses needs_review+notes for flagging | Avoids ALTER TABLE; leverages existing columns from migration 002 |
| 2026-03-12 | 1% amount tolerance for cross-source dedup | Covers exchange rounding vs exact on-chain wei/drops values |
| 2026-03-12 | 10-minute timestamp window for cross-source dedup | Covers network propagation latency + exchange recording delay |
| 2026-03-12 | Sweat wallets handled by NearFetcher | Sweat is NEAR-based; no separate fetcher needed |
| 2026-03-12 | Release conn before AIFileAgent call in FileImportHandler | AIFileAgent manages its own connections; releasing first prevents pool exhaustion |
| 2026-03-12 | Migration 002b as additive gap-fix | nullable=True updated_at columns; no backfill required; preserves 002 for teams already migrated |
| 2026-03-12 | Epoch integers for BIGINT BETWEEN | int(window.timestamp()) before BETWEEN on BIGINT block_timestamp; datetime objects cause type mismatch |
| 2026-03-12 | ON CONFLICT (user_id, account_id, chain) in upload-file | Must match exact UNIQUE constraint column set from migration 001 wallets table |
| 2026-03-12 | Partial unique indexes via op.execute() in migration 003 | op.create_unique_constraint() has no WHERE clause support; raw SQL in op.execute() is Alembic-documented approach |
| 2026-03-12 | classification_rules created before transaction_classifications | FK dependency order: transaction_classifications.rule_id references classification_rules.id |
| 2026-03-12 | uq_cr_name UNIQUE on classification_rules.name | Enables idempotent ON CONFLICT (name) DO UPDATE upsert pattern for rule seeder |
| 2026-03-12 | Self-referential parent/child_legs on TransactionClassification | Multi-leg decomposition: parent row + sell_leg/buy_leg/fee_leg child rows share parent_classification_id |
| 2026-03-12 | EVMDecoder is purely data-driven (no DB) | Tested with synthetic tx dicts, no fixtures required; clean separation from DB layer |
| 2026-03-12 | get_evm_rules() iterates EVMDecoder signature dicts | Single source of truth — adding a selector to EVMDecoder automatically adds its DB rule |
| 2026-03-12 | REVIEW_THRESHOLD=0.90 for TransactionClassifier | Plan spec: confidence < 0.90 -> needs_review; stricter than 0.70 in legacy categories.py |
| 2026-03-12 | fee_leg only emitted when tx.fee is truthy | Prevents spurious fee rows; test explicitly passes fee field to get 4-row decomposition |
| 2026-03-12 | _decompose_swap is pure (no DB calls) | parent_classification_id linking deferred to upsert (DB assigns IDs at write time) |
| 2026-03-12 | Rules must be pre-sorted by priority DESC before _match_rules | First match wins; loader sorts on SELECT; tests must sort explicitly when combining rule sets |
| 2026-03-12 | AI_CONFIDENCE_THRESHOLD=0.70 as module constant | Below this triggers AI fallback even for rule matches; importable by routing layer |
| 2026-03-12 | AI fallback takes higher-confidence result (rule vs AI) | Deterministic rules with confidence >= 0.70 not overridden by uncertain AI responses |
| 2026-03-12 | classification_source='ai' for AI-classified rows | Distinguishes AI vs rule-matched in audit trail; same pattern as confidence_score NULL for CSV parsers |
| 2026-03-12 | ClassifierHandler._rules_seeded flag | Prevents repeated COUNT(*) queries across multiple classify_transactions jobs on same handler instance |
| 2026-03-12 | price_cache_minute as separate table from daily price_cache | Different granularity (unix_ts BigInteger vs Date), different retention, different cardinality |
| 2026-03-12 | INSERT ON CONFLICT DO NOTHING for minute cache | Simpler than DO UPDATE; concurrent requests silently skip without overwrite |
| 2026-03-12 | is_estimated=True when CoinGecko gap >15 min (900s) | Tax-safe: flags prices needing review without being overly aggressive on low-tick markets |
| 2026-03-12 | BoC Valet API for CAD rates in get_boc_cad_rate() | Authoritative Canadian source for tax purposes; replaces CryptoCompare approximation |
| 2026-03-12 | 5-day lookback for BoC weekend/holiday gaps | Covers long weekends without excessive API calls |
| 2026-03-12 | STABLECOIN_MAP shortcut for tether/usd-coin/dai | Always 1:1 USD; avoids unnecessary API calls |
| 2026-03-12 | acb_added_cad = fmv_cad in IncomeLedger | Income FMV at receipt becomes cost basis for newly acquired units (Canadian ACB rule) |
| 2026-03-12 | Legacy ACBTracker/PortfolioACB removed entirely | Float arithmetic incompatible with Canadian tax precision; Decimal-based ACBPool is clean replacement |
| 2026-03-12 | GainsCalculator takes conn not pool | ACBEngine owns transaction boundary; calculator is stateless persistence helper |
| 2026-03-12 | Lazy import of GainsCalculator in ACBEngine | Avoids circular import (gains.py imports normalize_timestamp from acb.py); enables patch('engine.acb.GainsCalculator') in tests |
| 2026-03-12 | is_superficial_loss excluded from GainsCalculator INSERT params | Column defaults False; SuperficialLossDetector (Plan 04-03) updates rows after initial population |
| 2026-03-12 | Oversell clamp not exception in ACBPool.dispose() | Produces valid snapshot with needs_review=True; partial data reviewable without blocking full replay |
| 2026-03-12 | SuperficialLossDetector takes conn not pool | ACBEngine owns transaction boundary; detector is stateless helper — same pattern as GainsCalculator |
| 2026-03-13 | UniqueConstraint(wallet_id, token_symbol) on verification_results | Enables upsert-per-run pattern; one active result per wallet+token |
| 2026-03-13 | verify_balances priority=4 (lower than ACB at 5) | Verification runs last in pipeline: classify -> ACB -> verify |
| 2026-03-13 | RECONCILIATION_TOLERANCES as string values | Clean Decimal conversion without float precision issues |
| 2026-03-13 | VerifyHandler takes pool only (no price_service) | Verification reads existing computed data, no FMV lookups needed |
| 2026-03-13 | Bridge window 30min vs 10min same-chain | Cross-chain confirmation times are slower; 30-min window reduces false negatives |
| 2026-03-13 | Bridge duplicates never auto-merged | Score 0.60 always flagged; specialist must verify bridge direction |
| 2026-03-13 | Balance-aware merge requires on-chain ground truth | Returns False without verification_results actual_balance; prevents incorrect merges |
| 2026-03-13 | Duplicate detection as INSERT not upsert | Each detection is a separate verification_results row for complete audit trail |
| 2026-03-13 | Per-wallet raw replay vs user-level ACBPool cross-check | ACBPool is user-scoped (all wallets pooled); raw replay gives per-wallet expected for on-chain comparison |
| 2026-03-13 | Archival RPC relative delta comparison (not absolute) | Archival balance is liquid only; comparing deltas between checkpoints catches gaps without requiring absolute balance accuracy |
| 2026-03-13 | Gap diagnosis confidence 0.60 | Archival liquid balance is an approximation; lower confidence triggers specialist review |
| 2026-03-13 | Lazy imports in VerifyHandler.run_verify() | Matches ACBHandler pattern; avoids circular imports; handler skeleton works before all modules exist |
| 2026-03-13 | DISCREPANCIES.md grouped by diagnosis_category | Clear specialist review: reconciliation issues, duplicate merges, gap detections in separate sections |
| 2026-03-13 | reports/ removed from .gitignore | Reports package is source code (engine.py, capital_gains.py, income.py), not test output |
| 2026-03-13 | Gate check queries both CGL and ACB for needs_review | Both tables can have unresolved items that block report accuracy |
| 2026-03-13 | taxable_amount = net_gain_loss * Decimal('0.50') | Canadian 50% capital gains inclusion rate for 2024 tax year |
| 2026-03-13 | Monthly income summary uses DB GROUP BY DATE_TRUNC | Aggregation at DB level is more efficient than Python-side; query pattern from RESEARCH.md |
| 2026-03-13 | NearBlocks kitwallet as optional staking fallback | Catches pre-indexing validators not in staking_events table; try/except so API key not required |
| 2026-03-13 | Auto-diagnosis priority order with confidence > 0.5 threshold | First matching heuristic wins; prevents multiple conflicting diagnoses per discrepancy |
| 2026-03-12 | scan_for_user() and apply_superficial_losses() as separate methods | Allows dry-run inspection before persistence; specialist can review scan output before applying |
| 2026-03-12 | needs_review=True on all superficial losses | CRA ITA s.54 cases require specialist confirmation before finalizing tax submission |
| 2026-03-12 | denied_loss quantized to 2 decimal places | Monetary precision for tax reporting (CAD cents) |
| 2026-03-12 | Dedup check before calculate_acb INSERT | Prevents duplicate ACB recalculations when classify_transactions jobs run for multiple user wallets simultaneously |
| 2026-03-12 | stats['superficial_losses'] added to ACBEngine return | ACBHandler log includes count for observability; consistent with other stats keys |

---
*Last updated: 2026-03-13 — Stopped at: Completed 06-reporting 06-01-PLAN.md.*
