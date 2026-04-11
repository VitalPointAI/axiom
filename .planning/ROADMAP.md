# Roadmap

## Overview

| # | Phase | Goal | Requirements | Est. Time |
|---|-------|------|--------------|-----------|
| 1 | NEAR Indexer | Pull complete NEAR transaction history | DATA-01,02,03,06 | 2 days | 7/7 | Complete   | 2026-03-12 | Pull EVM data and parse exchange CSVs | DATA-04,05 | 2 days |
| 3 | 5/5 | Complete   | 2026-03-12 | 2 days |
| 4 | Cost Basis Engine | Calculate ACB and track gains/losses | ACB-01,02,03,04,05 | 2 days |
| 5 | Verification | Reconcile balances and detect issues | VER-01,02,03,04 | 1 day |
| 6 | Reporting | Generate tax reports for accountant | RPT-01,02,03,04,05,06 | 2 days |
| 7 | Web UI | User-friendly interface with NEAR wallet auth | UI-01,02,03,04,05,06,07,08 | 3 days |
| 8 | CI/CD Deployment | GitHub Actions CI/CD to deploy dockerized components on push | CICD-01,02,03 | 1 day |
| 9 | Code Quality & Hardening | Refactor, test coverage, rate limiting, CI gates | QH-01 through QH-12 | 2 days |
| 10 | Remaining Concerns | Large module refactors, performance, robustness | RC-01 through RC-14 | 2 days |
| 11 | Robustness & Missing Features | Audit log, invariants, export validation, offline mode | ROB-01 through ROB-10 | 2 days |
| 12 | 3/3 | Complete    | 2026-03-16 | 2 days |



**Total estimate:** 15 days

---

## Phase 1: NEAR Indexer

**Goal:** Pull complete transaction history for all 64 NEAR accounts including staking rewards and lockup vesting.

**Plans:** 6 plans in 4 waves (6/6 COMPLETE)

Plans:
- [x] 01-01-PLAN.md — Fresh PostgreSQL schema + Alembic migrations + config cleanup (Wave 1) [DATA-06] ✓ DONE
- [x] 01-02-PLAN.md — Standalone indexer service + NEAR transaction fetcher (Wave 2) [DATA-01, DATA-06] ✓ DONE
- [x] 01-03-PLAN.md — Multi-source price service + epoch staking rewards + lockup parser (Wave 2) [DATA-02, DATA-03] ✓ DONE
- [x] 01-04-PLAN.md — Integration wiring: register all handlers + web API job queue (Wave 3) [DATA-01, DATA-02, DATA-03, DATA-06] ✓ DONE
- [x] 01-05-PLAN.md — Gap closure: fix account_id dispatch + staking backfill timestamp fallback (Wave 4) [DATA-01, DATA-02, DATA-03] ✓ DONE
- [x] 01-06-PLAN.md — Gap closure: fix wallet API handler to use indexing_jobs schema (Wave 4) [DATA-01, DATA-06] ✓ DONE

**Requirements:**
- DATA-01: Pull complete transaction history for any NEAR account
- DATA-02: Pull staking rewards history from validator pool (epoch-level)
- DATA-03: Pull lockup contract vesting events
- DATA-06: Store transactions in PostgreSQL (fresh schema, multi-user, multi-chain ready)

**Success Criteria:**
1. [ ] All user-added NEAR wallets have complete transaction history in database
2. [ ] Staking rewards captured at epoch-level granularity with FMV (USD + CAD)
3. [ ] Lockup vesting events captured with unlock dates, amounts, and FMV
4. [ ] Balance verification runs after each wallet sync (count check + balance reconciliation)
5. [ ] Database schema uses proper PostgreSQL types with multi-user isolation
6. [ ] Indexer service runs standalone, polls job queue, self-heals on failures
7. [ ] No SQLite references in any indexer or config code

**Deliverables:**
- `db/models.py` — SQLAlchemy models
- `db/migrations/` — Alembic migration framework
- `indexers/service.py` — Standalone indexer service
- `indexers/near_fetcher.py` — NEAR transaction fetcher
- `indexers/staking_fetcher.py` — Epoch staking reward calculator
- `indexers/lockup_fetcher.py` — Lockup contract parser
- `indexers/price_service.py` — Multi-source price service
- `indexers/db.py` — Shared PostgreSQL connection module

---

## Phase 2: Multi-Chain + Exchanges

**Goal:** Pull EVM chain data, import exchange transaction history via CSV and AI-powered file ingestion, and register chain plugins for all wallet inventory chains (ETH, Polygon, Optimism, Cronos, XRP, Akash).

**Plans:** 7/7 plans complete

Plans:
- [x] 02-01-PLAN.md — Alembic migration 002 + chain/exchange plugin ABCs (Wave 1) [DATA-04, DATA-05] ✓ DONE
- [x] 02-02-PLAN.md — EVMFetcher with Etherscan V2 pagination + PostgreSQL upsert (Wave 2) [DATA-04] ✓ DONE
- [x] 02-03-PLAN.md — Exchange parser PostgreSQL migration + unit tests (Wave 2) [DATA-05] ✓ DONE
- [x] 02-04-PLAN.md — Service wiring: EVM + file import handlers + upload API (Wave 3) [DATA-04, DATA-05] ✓ DONE
- [x] 02-05-PLAN.md — AI-powered file ingestion agent via Claude API (Wave 3) [DATA-05] ✓ DONE
- [x] 02-06-PLAN.md — Cross-source dedup + XRP/Akash stubs + final integration (Wave 4) [DATA-04, DATA-05] ✓ DONE
- [ ] 02-07-PLAN.md — Gap closure: migration 002b updated_at + dedup epoch fix + upload ON CONFLICT fix (Wave 5) [DATA-04, DATA-05]

**Requirements:**
- DATA-04: Pull EVM transaction history
- DATA-05: Parse exchange CSV exports

**Success Criteria:**
1. [ ] ETH/Polygon/Optimism/Cronos transactions imported via Etherscan V2
2. [ ] Coinbase CSV parser works and imports transactions
3. [ ] At least 3 other exchange CSV parsers implemented (Crypto.com, Wealthsimple, Uphold/Coinsquare via generic)
4. [ ] All imported transactions have consistent schema in database
5. [ ] AI agent handles unknown file formats with confidence scoring
6. [ ] Cross-source deduplication flags matching on-chain + exchange records
7. [ ] XRP and Akash chain fetcher stubs registered in service.py

**Deliverables:**
- `db/migrations/versions/002_multichain_exchanges.py` — Phase 2 schema migration
- `db/migrations/versions/002b_add_updated_at.py` — Gap closure: add updated_at columns
- `indexers/chain_plugin.py` — ChainFetcher ABC
- `indexers/exchange_plugin.py` — ExchangeParser + ExchangeConnector ABCs
- `indexers/evm_fetcher.py` — Etherscan V2 fetcher with pagination
- `indexers/file_handler.py` — File import job handler with parser auto-detection
- `indexers/ai_file_agent.py` — Claude API-powered file ingestion
- `indexers/dedup_handler.py` — Cross-source deduplication
- `indexers/xrp_fetcher.py` — XRP Ledger chain fetcher
- `indexers/akash_fetcher.py` — Akash (Cosmos SDK) chain fetcher
- `web/app/api/upload-file/route.ts` — File upload API endpoint

---

## Phase 3: Transaction Classification

**Goal:** Build a rule-based + AI-assisted classification engine that classifies all transactions (NEAR, EVM, exchange) by tax treatment, with multi-leg decomposition, internal transfer detection, spam filtering, staking/lockup linkage, and full audit trail.

**Plans:** 5/5 plans complete

Plans:
- [ ] 03-01-PLAN.md — Migration 003 (4 new tables) + SQLAlchemy models + test scaffolds (Wave 1) [CLASS-01, CLASS-02, CLASS-03, CLASS-04, CLASS-05]
- [ ] 03-02-PLAN.md — WalletGraph PostgreSQL rewrite + SpamDetector (Wave 2) [CLASS-02]
- [ ] 03-03-PLAN.md — EVMDecoder + classification rule seeder (Wave 2) [CLASS-01, CLASS-05]
- [ ] 03-04-PLAN.md — TransactionClassifier core engine (Wave 3) [CLASS-01, CLASS-03, CLASS-04, CLASS-05]
- [ ] 03-05-PLAN.md — ClassifierHandler + service wiring + AI fallback (Wave 4) [CLASS-01, CLASS-02, CLASS-03, CLASS-04, CLASS-05]

**Requirements:**
- CLASS-01: Classify as income/gain/loss/transfer/fee
- CLASS-02: Detect internal transfers
- CLASS-03: Identify staking rewards
- CLASS-04: Identify lockup vesting
- CLASS-05: Identify swaps/trades

**Success Criteria:**
1. [ ] All transactions have a classification assigned
2. [ ] Internal transfers (between owned wallets) correctly identified and marked non-taxable
3. [ ] Staking rewards classified as income with correct FMV
4. [ ] Token swaps classified with both legs (sell + buy)
5. [ ] <5% of transactions flagged for manual review

**Deliverables:**
- `db/migrations/versions/003_classification_schema.py` — Classification schema (4 tables)
- `db/models.py` — Extended with 4 new SQLAlchemy models
- `engine/classifier.py` — TransactionClassifier (rewritten from SQLite)
- `engine/wallet_graph.py` — WalletGraph (rewritten for PostgreSQL)
- `engine/evm_decoder.py` — EVM swap/DeFi decoder
- `engine/spam_detector.py` — Multi-signal spam detector
- `engine/rule_seeder.py` — Classification rule seeder
- `indexers/classifier_handler.py` — Job handler for classify_transactions

---

## Phase 4: Cost Basis Engine

**Goal:** Calculate Adjusted Cost Base (ACB) per Canadian average cost method with Decimal precision, track capital gains/losses on disposals, capture FMV for income events, and detect superficial losses with pro-rated partial rebuy handling.

**Plans:** 3 plans in 3 waves (3/3 COMPLETE)

Plans:
- [x] 04-01-PLAN.md — Migration 004 + SQLAlchemy models + PriceService extension (BoC + minute-level) + test scaffolds (Wave 1) [ACB-03] ✓ DONE
- [x] 04-02-PLAN.md — ACBEngine (Decimal pools, chronological replay, snapshot persistence) + GainsCalculator (capital gains + income ledgers) (Wave 2) [ACB-01, ACB-02, ACB-04] ✓ DONE
- [x] 04-03-PLAN.md — SuperficialLossDetector (61-day window, pro-rated denial) + ACBHandler job wiring + ClassifierHandler trigger (Wave 3) [ACB-05, ACB-01, ACB-02, ACB-03, ACB-04] ✓ DONE

**Requirements:**
- ACB-01: Calculate ACB using Canadian average cost
- ACB-02: Track pooled ACB per token
- ACB-03: Fetch historical FMV for income events
- ACB-04: Adjust cost basis for fees
- ACB-05: Flag superficial losses

**Success Criteria:**
1. [ ] ACB calculated for NEAR token across all wallets
2. [ ] ACB calculated for ETH and other tokens
3. [ ] Disposal events have gain/loss calculated
4. [ ] Income events have FMV captured at time of receipt
5. [ ] Superficial loss candidates flagged for review

**Deliverables:**
- `db/migrations/versions/004_cost_basis_schema.py` — Cost basis schema (4 tables)
- `db/models.py` — Extended with ACBSnapshot, CapitalGainsLedger, IncomeLedger, PriceCacheMinute
- `engine/acb.py` — ACBEngine (Decimal-precise, PostgreSQL-backed)
- `engine/gains.py` — GainsCalculator (capital gains + income ledger)
- `engine/superficial.py` — SuperficialLossDetector (61-day window scan)
- `indexers/acb_handler.py` — Job handler for calculate_acb
- `indexers/price_service.py` — Extended with minute-level prices + Bank of Canada CAD rates

---

## Phase 5: Verification

**Goal:** Ensure data accuracy by reconciling calculated balances against on-chain state, detecting duplicate transactions, and finding missing transactions via balance-based inference.

**Plans:** 4 plans in 3 waves (4/4 COMPLETE)

Plans:
- [x] 05-01-PLAN.md — Migration 005 + SQLAlchemy models + VerifyHandler skeleton + service/ACB wiring + config tolerances (Wave 1) [VER-01, VER-02] ✓ DONE
- [x] 05-02-PLAN.md — BalanceReconciler: NEAR decomposed + EVM + dual cross-check + auto-diagnosis (Wave 2) [VER-01, VER-02] ✓ DONE
- [x] 05-03-PLAN.md — DuplicateDetector: hash dedup + bridge heuristic + exchange re-scan + balance-aware merge (Wave 2) [VER-03] ✓ DONE
- [x] 05-04-PLAN.md — GapDetector + DiscrepancyReporter + VerifyHandler final wiring (Wave 3) [VER-04, VER-01, VER-02, VER-03] ✓ DONE

**Requirements:**
- VER-01: Reconcile calculated vs on-chain balances
- VER-02: Flag discrepancies
- VER-03: Detect duplicates
- VER-04: Detect missing transactions

**Success Criteria:**
1. [ ] All 64 NEAR accounts reconciled within tolerance (±0.01 NEAR)
2. [ ] EVM accounts reconciled
3. [ ] No duplicate transactions in database
4. [ ] Missing transaction report generated (if any gaps)
5. [ ] All discrepancies documented with investigation notes

**Deliverables:**
- `db/migrations/versions/005_verification_schema.py` — Verification schema (2 tables)
- `db/models.py` — Extended with VerificationResult, AccountVerificationStatus
- `verify/reconcile.py` — Balance reconciler (full PostgreSQL rewrite)
- `verify/duplicates.py` — Duplicate detector (multi-signal scoring)
- `verify/gaps.py` — Missing transaction finder (archival RPC)
- `verify/report.py` — Discrepancy report generator
- `indexers/verify_handler.py` — Job handler for verify_balances
- `DISCREPANCIES.md` — Manual review notes (generated)

---

## Phase 6: Reporting

**Goal:** Generate accountant-ready tax reports with full Koinly parity, corporate/business reports, accounting software exports, and PDF output. Multi-user with configurable fiscal year and tax treatment (capital/business/hybrid).

**Plans:** 5/5 plans COMPLETE

Plans:
- [x] 06-01-PLAN.md — ReportEngine base class + CapitalGainsReport + IncomeReport (Wave 1) [RPT-01, RPT-02] ✓ DONE
- [x] 06-02-PLAN.md — LedgerReport + T1135Checker + SuperficialLossReport (Wave 2) [RPT-03, RPT-04] ✓ DONE
- [x] 06-03-PLAN.md — KoinlyExport + accounting software exports (QuickBooks/Xero/Sage/double-entry) (Wave 2) [RPT-05] ✓ DONE
- [x] 06-04-PLAN.md — Inventory Holdings + COGS + Business Income Statement + FIFO engine (Wave 2) [RPT-01, RPT-02] ✓ DONE
- [x] 06-05-PLAN.md — PDF templates (WeasyPrint) + PackageBuilder + ReportHandler job wiring (Wave 3) [RPT-05, RPT-06] ✓ DONE

**Requirements:**
- RPT-01: Capital gains/losses summary
- RPT-02: Income summary by month
- RPT-03: Full transaction ledger
- RPT-04: T1135 threshold check
- RPT-05: CSV export
- RPT-06: PDF summary

**Success Criteria:**
1. [ ] Capital gains report shows all 2025 disposals with gain/loss
2. [ ] Income report shows staking rewards by month with FMV
3. [ ] Transaction ledger is complete and auditable
4. [ ] T1135 status determined (above/below $100K CAD threshold)
5. [ ] Accountant confirms package is complete and usable

**Deliverables:**
- `reports/engine.py` — ReportEngine base class with gate check
- `reports/capital_gains.py` — Capital gains report (chronological + grouped)
- `reports/income.py` — Income summary by month + source type
- `reports/ledger.py` — Full transaction ledger
- `reports/t1135.py` — T1135 foreign property check
- `reports/superficial.py` — Superficial loss report
- `reports/export.py` — Koinly + accounting software exports
- `reports/inventory.py` — Inventory holdings + COGS
- `reports/business.py` — Business income statement
- `reports/generate.py` — PackageBuilder (rewritten)
- `reports/templates/` — Jinja2 HTML templates for PDF
- `reports/handlers/report_handler.py` — IndexerService job handler
- `engine/fifo.py` — FIFO lot tracking engine
- `output/{year}_tax_package/` — Final deliverable

---

## Phase 7: Web UI

**Goal:** Wire the existing Next.js frontend to a new FastAPI backend replacing all Next.js API routes. Migrate auth (passkey + email magic link + Google OAuth) to Python, implement full pipeline auto-chaining in UI, verification dashboard with actionable resolution, report generation with inline previews, and transaction classification editing.

**Plans:** 7 plans in 5 waves

Plans:
- [x] 07-01-PLAN.md — Migration 006 (auth schema) + FastAPI app skeleton + dependencies + test infrastructure (Wave 1) [UI-08] ✅ DONE (2026-03-13)
- [x] 07-02-PLAN.md — Auth: WebAuthn passkey + Google OAuth + email magic link + session management (Wave 2) [UI-01, UI-08] ✓ DONE
- [x] 07-03-PLAN.md — Wallet CRUD + portfolio summary + job status + pipeline progress (Wave 2) [UI-02, UI-03] ✅ DONE (2026-03-13)
- [x] 07-04-PLAN.md — Transaction ledger + classification editing + review queue + batch recalc (Wave 3) [UI-04, UI-05] ✅ DONE (2026-03-13)
- [x] 07-05-PLAN.md — Report generation/preview/download + verification dashboard (Wave 3) [UI-06, UI-07] ✅ DONE (2026-03-13)
- [x] 07-06-PLAN.md — Frontend rewiring: API client + auth-provider + dashboard pages + progress bar (Wave 4) [UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07] ✓ DONE
- [x] 07-07-PLAN.md — Docker integration + deploy workflow update + old API route cleanup + e2e verify (Wave 5) [UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, UI-08] ✅ DONE (2026-03-13)

**Requirements:**
- UI-01: Web UI with user authentication via near-phantom-auth (passkey + email + Google OAuth)
- UI-02: Portfolio dashboard with holdings summary
- UI-03: Wallet management (add/edit/remove, sync status, pipeline progress bar)
- UI-04: Transaction ledger with filtering and search
- UI-05: Transaction detail editing with classification changes and batch recalc
- UI-06: Report generation interface with inline previews and downloads
- UI-07: Verification status dashboard with issue grouping and resolution actions
- UI-08: Multi-user data isolation via user_id filtering on all queries

**Success Criteria:**
1. [ ] Users can sign in with passkey, Google OAuth, or email magic link
2. [ ] Dashboard shows portfolio value, holdings by asset, staking positions
3. [ ] Users can add/manage wallets and see pipeline progress (Indexing -> Classifying -> Cost Basis -> Verifying -> Done)
4. [ ] Transaction ledger supports filter by date, type, asset, amount, chain, needs_review
5. [ ] Users can edit transaction classifications and trigger ACB recalculation
6. [ ] Reports can be generated via job queue, previewed inline, and downloaded
7. [ ] Verification issues grouped by diagnosis category with resolution actions
8. [ ] Each user's data is isolated by user_id across all endpoints

**Deliverables:**
- `api/` — FastAPI backend (main.py, dependencies.py, auth/, routers/, schemas/)
- `api/Dockerfile` — FastAPI Docker image
- `db/migrations/versions/006_auth_schema.py` — Auth table migration
- `web/lib/api.ts` — Centralized API client for FastAPI
- Updated `docker-compose.prod.yml` — 4 services (postgres, web, api, indexer)
- Updated `.github/workflows/deploy.yml` — Deploys api container

**Tech Stack:**
- Frontend: Next.js 16+ with App Router, React 19, Tailwind CSS 4, shadcn/ui, Recharts
- Backend: FastAPI + py_webauthn + itsdangerous + boto3 + slowapi
- Database: PostgreSQL (multi-user, all tables have user_id FK)
- Auth: py_webauthn (passkey), Google OAuth PKCE, itsdangerous (magic link)
- Deployment: Separate Docker containers: web (Next.js), api (FastAPI), indexer (Python), postgres

---

## Phase 8: CI/CD Deployment

**Goal:** Set up GitHub Actions CI/CD pipeline to automatically deploy all dockerized components (database, frontend, backend, indexer) on push to main branch to existing server.

**Depends on:** Phase 7 (full stack ready for deployment)

**Plans:** 2 plans in 2 waves (2/2 COMPLETE)

Plans:
- [x] 08-01-PLAN.md — Production Docker Compose + deployment scripts (Wave 1) [CICD-02, CICD-03] ✓ DONE
- [x] 08-02-PLAN.md — GitHub Actions deploy workflow + .gitignore hardening (Wave 2) [CICD-01, CICD-02, CICD-03] ✓ DONE

**Requirements:**
- CICD-01: GitHub Actions workflow for automated deployment on push to main
- CICD-02: Docker Compose orchestration for all services (PostgreSQL, FastAPI backend, Next.js frontend, indexer)
- CICD-03: Server deployment via SSH with zero-downtime strategy

**Success Criteria:**
1. [ ] Push to main triggers automated build and deploy
2. [ ] All Docker containers build successfully in CI
3. [ ] Deployment to existing server completes without manual intervention
4. [ ] Health checks verify all services are running post-deploy
5. [ ] Rollback mechanism available if deployment fails
6. [ ] Environment secrets managed securely via GitHub Secrets

**Deliverables:**
- `.github/workflows/deploy.yml` — GitHub Actions deployment workflow
- `docker-compose.prod.yml` — Production Docker Compose configuration
- `scripts/deploy.sh` — SSH deployment with rolling restart
- `scripts/healthcheck.sh` — Post-deploy health verification

---

### Phase 13: Reliable Indexing

**Goal:** Replace rate-limited NearBlocks/Etherscan polling with near real-time streaming indexing via neardata.xyz (NEAR) and Alchemy WebSocket (EVM). Add cost tracking, chain plugin registry via DB config, gap detection with re-index loop protection, SSE for frontend real-time updates, and admin cost dashboard.

**Requirements:** IDX-01 through IDX-10
- IDX-01: Migration 011 — api_cost_log + chain_sync_config tables
- IDX-02: NEAR streaming fetcher via neardata.xyz (replaces NearBlocks for real-time)
- IDX-03: EVM real-time streaming via WebSocket eth_subscribe (Alchemy)
- IDX-04: Cost tracking middleware (CostTracker) + admin cost dashboard API
- IDX-05: Chain plugin registry via database config (chain_sync_config)
- IDX-06: Streaming worker (asyncio long-running process for near real-time updates)
- IDX-07: Gap detection with re-index loop protection (3 retries/day/wallet max)
- IDX-08: PostgreSQL LISTEN/NOTIFY + SSE for frontend real-time updates
- IDX-09: XRP + Akash fetcher hardening (cost tracking, stub label removal)
- IDX-10: Service.py integration — register fetchers from chain_sync_config, --streaming flag

**Depends on:** Phase 12
**Plans:** 5/5 plans complete

Plans:
- [ ] 13-01-PLAN.md — Migration 011 + CostTracker middleware + chain registry loader (Wave 1) [IDX-01, IDX-04, IDX-05]
- [ ] 13-02-PLAN.md — NEAR stream fetcher via neardata.xyz (Wave 1) [IDX-02]
- [ ] 13-03-PLAN.md — EVM stream fetcher via Alchemy WebSocket (Wave 1) [IDX-03]
- [ ] 13-04-PLAN.md — Streaming worker + service.py wiring + gap detection (Wave 2) [IDX-06, IDX-07, IDX-10]
- [ ] 13-05-PLAN.md — SSE endpoint + admin cost dashboard API + XRP/Akash hardening (Wave 2) [IDX-08, IDX-09]

**Success Criteria:**
1. [ ] neardata.xyz block streaming fetches NEAR transactions in < 5 min from on-chain confirmation
2. [ ] EVM WebSocket receives new block notifications with auto-reconnect on disconnect
3. [ ] api_cost_log tracks all external API calls with chain, provider, cost estimate
4. [ ] chain_sync_config stores per-chain fetcher configuration; service.py loads from DB
5. [ ] StreamingWorker runs NEAR + EVM streaming in parallel asyncio tasks
6. [ ] Balance mismatch triggers re-index with 3/day/wallet cap; excess flagged manual_review
7. [ ] SSE endpoint pushes real-time transaction updates to frontend via pg_notify
8. [ ] Admin cost dashboard shows monthly cost per chain/provider with budget alerts
9. [ ] XRP and Akash fetchers track API costs; stub labels removed
10. [ ] All new tests pass (streaming, cost tracking, gap detection, admin API, SSE)

**Deliverables:**
- `db/migrations/versions/011_cost_tracking_chain_config.py` — Migration 011
- `indexers/cost_tracker.py` — CostTracker middleware
- `indexers/near_stream_fetcher.py` — neardata.xyz NEAR streaming fetcher
- `indexers/evm_stream_fetcher.py` — WebSocket EVM streaming fetcher
- `indexers/streaming_worker.py` — Asyncio streaming worker
- `indexers/gap_reindex.py` — Gap detection with loop protection
- `indexers/service.py` — Extended with --streaming flag + chain_sync_config loading
- `api/routers/admin.py` — Cost dashboard + indexing status endpoints
- `api/routers/streaming.py` — SSE endpoint for real-time wallet updates
- `config.py` — Extended with ALCHEMY_API_KEY, INFURA_API_KEY
- `tests/test_near_stream_fetcher.py` — NEAR stream fetcher tests
- `tests/test_evm_stream_fetcher.py` — EVM stream fetcher tests
- `tests/test_cost_tracker.py` — Cost tracker tests
- `tests/test_chain_registry.py` — Chain registry tests
- `tests/test_streaming_worker.py` — Streaming worker tests
- `tests/test_gap_reindex.py` — Gap re-index tests
- `tests/test_admin_api.py` — Admin API tests
- `tests/test_streaming_api.py` — SSE streaming API tests

### Phase 15: Account Block Index Integer Encoding

**Goal:** Reduce NEAR account_block_index disk footprint from ~1.3 TB to under 250 GB via dictionary-encoded integer IDs + segment-based indexing (1K-block granules), while maintaining sub-2-minute wallet lookup performance.
**Requirements:** INT-01 through INT-08
**Depends on:** Phase 13
**Plans:** 3 plans in 3 waves

Plans:
- [ ] 15-01-PLAN.md — Alembic migration 020: account_dictionary + account_block_index_v2 schema (Wave 1) [INT-01]
- [ ] 15-02-PLAN.md — Rust indexer dictionary cache + segment output + Python COPY pipeline v2 (Wave 2) [INT-02, INT-03, INT-04]
- [ ] 15-03-PLAN.md — Python lookup via dictionary+segments + admin status + data migration script (Wave 3) [INT-05, INT-06, INT-07, INT-08]

**Requirements:**
- INT-01: Migration 020 creates account_dictionary and account_block_index_v2 tables
- INT-02: Rust indexer resolves account strings to integer IDs via PostgreSQL dictionary
- INT-03: Rust indexer emits (account_int, segment_start) integer pairs to stdout
- INT-04: Python COPY pipeline uses v2 staging table with INTEGER columns
- INT-05: near_fetcher.py queries v2 table via dictionary join + segment expansion
- INT-06: admin.py reports v2 table stats (entry count, dictionary size)
- INT-07: Data migration script converts existing old-format rows to v2 in batches
- INT-08: Wallet lookup completes under 2 minutes end-to-end

**Success Criteria:**
1. [ ] account_dictionary table maps ~15M account strings to compact integer IDs
2. [ ] account_block_index_v2 uses INTEGER account_int + INTEGER segment_start (8 bytes/row data)
3. [ ] Rust indexer pre-warms dictionary HashMap and resolves strings to ints in writer thread
4. [ ] Bulk indexing throughput >= 2,700 blocks/sec (same as current)
5. [ ] Wallet lookup via dictionary join + segment scan completes in < 2 minutes
6. [ ] Data migration script converts existing data in 1M-block batches without locking
7. [ ] Old table retained for manual verification before drop
8. [ ] Full index fits under 250 GB on 500 GB disk

**Deliverables:**
- db/migrations/versions/020_integer_encoded_index.py — Migration 020
- indexers/account-indexer-rs/src/main.rs — Rust indexer with dictionary cache + segment output
- indexers/account-indexer-rs/Cargo.toml — Added postgres dependency
- indexers/account_indexer.py — Updated COPY pipeline for v2
- indexers/near_fetcher.py — Updated lookup via dictionary + segments
- scripts/run_account_indexer.sh — Updated shell pipeline for v2
- scripts/migrate_to_v2.py — Data migration script (old -> v2)
- api/routers/admin.py — Updated status endpoint for v2
- scripts/check_account_indexer.sh — Updated health check for v2

---

## Dependencies

```
Phase 1 ──┬──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6 ──► Phase 7
Phase 2 ──┘                                              │
                                                         └──► Phase 7 (can start UI scaffolding earlier)
```

- Phases 1 & 2 can run in parallel (data ingestion)
- Phase 3 requires Phase 1 & 2 complete (needs all transactions)
- Phase 4 requires Phase 3 (needs classifications)
- Phase 5 requires Phase 4 (needs calculated balances)
- Phase 6 requires Phase 5 (needs verified data)
- Phase 7 requires Phase 6 (needs complete data pipeline), but UI scaffolding can start in parallel

### Phase 9: Code Quality & Hardening

**Goal:** Refactor monolithic modules (classifier, reconcile), complete SQLite->PostgreSQL migration, fix N+1 query patterns, add test coverage, API rate limiting, CI/CD quality gates

**Requirements:** QH-01 through QH-12 (derived from CONCERNS.md unfixed items)
**Depends on:** Phase 8
**Plans:** 5 plans in 2 waves

Plans:
- [x] 09-01-PLAN.md — CI quality gates (ci.yml + ruff) + legacy SQLite cleanup + stub documentation (Wave 1) [QH-01, QH-08, QH-12] ✅ DONE (2026-03-14)
- [x] 09-02-PLAN.md — API rate limiting (slowapi) + env validation + SQL whitelist + rollback consistency (Wave 1) [QH-04, QH-05, QH-06, QH-07] ✅ DONE (2026-03-14)
- [x] 09-03-PLAN.md — Classifier N+1 fix (batch event loading) + NearBlocks retry hardening (Wave 1) [QH-02, QH-03] ✅ DONE (2026-03-14)
- [x] 09-04-PLAN.md — Test coverage: authorization isolation + indexer edge cases + parser robustness (Wave 2) [QH-09, QH-10, QH-11] ✅ DONE (2026-03-14)
- [x] 09-05-PLAN.md — Reconcile module refactor: extract diagnosis helpers (Wave 2) [QH-02] ✅ DONE (2026-03-14)

**Requirements:**
- QH-01: SQLite->PostgreSQL: migrate/remove remaining SQLite modules
- QH-02: Refactor monolithic modules (classifier, reconcile)
- QH-03: Fix N+1 query patterns in classifier
- QH-04: Fix SQL injection risk in dynamic UPDATE
- QH-05: Add API rate limiting
- QH-06: Startup environment variable validation
- QH-07: Complete transaction rollback pattern
- QH-08: Add CI/CD quality gates
- QH-09: Test coverage: authorization isolation
- QH-10: Test coverage: indexer edge cases
- QH-11: Test coverage: exchange parser robustness
- QH-12: Document stub implementations

**Success Criteria:**
1. [ ] CI pipeline runs pytest + ruff before deploy can proceed
2. [ ] Zero SQLite imports in production code path
3. [ ] API rate limits active on auth, job trigger, and data endpoints
4. [ ] Application fails fast on missing DATABASE_URL
5. [ ] Classifier loads staking/lockup events in batch, not per-transaction
6. [ ] NearBlocks API calls retry with exponential backoff on 429
7. [ ] Cross-user data access returns 403/404 on all protected endpoints
8. [ ] Indexer handles rate limits and malformed responses without crashing
9. [ ] Exchange parsers handle missing columns and malformed CSV gracefully
10. [ ] verify/reconcile.py diagnosis logic extracted into verify/diagnosis.py

### Phase 10: Remaining Concerns Remediation

**Goal:** Address all remaining unfixed concerns from CONCERNS.md — refactor large modules, improve performance, harden robustness, fill test gaps, clean up dependencies.

**Requirements:**
- RC-01: Refactor large modules — split classifier.py, acb.py, db/models.py into focused sub-modules
- RC-02: Add price_cache composite index (symbol, timestamp)
- RC-03: Streaming report export (chunked CSV generation)
- RC-04: Backfill generator pattern (increase batch size, streaming processing)
- RC-05: API response caching for repeated NearBlocks calls
- RC-06: Configure connection pool sizing with monitoring
- RC-07: Add logging policy — sanitize sensitive fields before logging
- RC-08: Remove or document stub implementations (xrp_fetcher, portfolio, akash_fetcher)
- RC-09: Add python_requires constraint to pyproject.toml
- RC-10: Classification rule interaction tests (priority resolution, conflicts)
- RC-11: ACB gap data tests (missing transactions, missing prices)
- RC-12: Concurrent classification tests (lost writes, duplicate processing)
- RC-13: Deprecate Coinbase Pro indexer with migration warning
- RC-14: Update scaling limits documentation (remove SQLite references)

**Out of scope:** Audit log, multi-currency support, offline mode, export validation (feature work for future milestones)

**Depends on:** Phase 9
**Plans:** 5 plans in 2 waves

Plans:
- [x] 10-01-PLAN.md — Module split: classifier.py, acb.py, models.py into sub-packages (Wave 1) [RC-01] ✅ DONE (2026-03-14)
- [x] 10-02-PLAN.md — DB index migration 007 + configurable pool sizing + pyproject.toml (Wave 1) [RC-02, RC-06, RC-09] ✅ DONE (2026-03-14)
- [x] 10-03-PLAN.md — Streaming CSV export + backfill batching + NearBlocks API caching (Wave 1) [RC-03, RC-04, RC-05] ✅ DONE (2026-03-14)
- [x] 10-04-PLAN.md — Logging policy + stub documentation + deprecation warnings + docs cleanup (Wave 1) [RC-07, RC-08, RC-13, RC-14] ✅ DONE (2026-03-14)
- [x] 10-05-PLAN.md — Test gaps: classifier rule interactions + ACB edge cases + concurrent classification (Wave 2) [RC-10, RC-11, RC-12] ✅ DONE (2026-03-14)

**Success Criteria:**
1. [x] classifier.py, acb.py, models.py split into sub-packages with backward-compatible imports
2. [x] price_cache has composite index; migration 007 applied
3. [x] Report CSVs stream via named cursors (no fetchall on large tables)
4. [x] Staking backfill commits in batches of 100
5. [x] NearBlocks API caches repeated calls with 5-min TTL
6. [x] Pool sizing configurable via DB_POOL_MIN/DB_POOL_MAX env vars
7. [x] sanitize_for_log() redacts sensitive fields
8. [x] Stubs documented, Coinbase Pro deprecated, docs free of SQLite refs
9. [x] pyproject.toml has requires-python >= 3.11
10. [x] Rule priority, ACB gap, and concurrent classification tests pass

### Phase 11: Robustness & Missing Features — audit log consistency, fragile area hardening, data export validation

**Goal:** Harden fragile areas across the pipeline, establish a unified audit log for all data mutations, add data export validation with manifest checksums, implement multi-currency swap decomposition for arbitrary multi-hop routes, and add a read-only offline/cached mode for working without live APIs.

**Requirements:**
- ROB-01: Unified audit log table replacing classification_audit_log (migration 008 + write_audit helper)
- ROB-02: Audit log wired to all mutation points + queryable via API
- ROB-03: MANIFEST.json with SHA-256 checksums in tax package
- ROB-04: Stale report detection via data fingerprint comparison
- ROB-05: ACB runtime invariant checks (pool consistency, negative detection)
- ROB-06: Classifier runtime invariant checks (parent classification, leg balance)
- ROB-07: Reconciler runtime invariant checks (wallet coverage, diagnosis completeness)
- ROB-08: Exchange parser runtime invariant checks (schema validation, zero-amount detection)
- ROB-09: Multi-hop swap decomposition (V3 exactInput path decoding)
- ROB-10: Offline/cached mode (IndexerService gate + API status)

**Depends on:** Phase 10
**Plans:** 5/5 plans complete

Plans:
- [ ] 11-01-PLAN.md — Migration 008 (unified audit_log) + AuditLog model + write_audit() helper (Wave 1) [ROB-01]
- [ ] 11-02-PLAN.md — MANIFEST.json generation in PackageBuilder + stale report detection (Wave 1) [ROB-03, ROB-04]
- [ ] 11-03-PLAN.md — Multi-hop swap path decoding + classifier leg decomposition (Wave 1) [ROB-09]
- [ ] 11-04-PLAN.md — Runtime invariant checks: ACB + classifier + reconciler + exchange parsers (Wave 2) [ROB-05, ROB-06, ROB-07, ROB-08]
- [ ] 11-05-PLAN.md — Audit wiring to all mutation points + audit API + offline mode (Wave 2) [ROB-02, ROB-10]

**Success Criteria:**
1. [ ] audit_log table exists with unified schema; classification_audit_log migrated and dropped
2. [ ] write_audit() called at all mutation points (classifier, ACB, duplicates, manual edits, verification, reports)
3. [ ] GET /api/audit/history returns filtered audit rows per entity
4. [ ] MANIFEST.json generated with SHA-256 per file + data fingerprint
5. [ ] Stale report detection warns when data changed since last generation
6. [ ] ACB, classifier, reconciler, exchange parsers have runtime invariant checks
7. [ ] Invariant violations logged to audit_log + needs_review set + pipeline continues
8. [ ] Multi-hop swaps decoded and decomposed into correct leg structure
9. [ ] Offline mode gates network-dependent jobs without crashing
10. [ ] All tests pass (existing + new invariant/manifest/offline tests)

**Deliverables:**
- `db/migrations/versions/008_unified_audit_log.py` — Unified audit table migration
- `db/audit.py` — write_audit() helper module
- `db/models/_all_models.py` — AuditLog model (replaces ClassificationAuditLog)
- `api/routers/audit.py` — Audit history API endpoint
- `reports/generate.py` — Extended with MANIFEST.json generation
- `api/routers/reports.py` — Extended with stale report detection
- `engine/evm_decoder.py` — Extended with multi-hop path decoding
- `engine/classifier/core.py` — Extended with multi-hop leg decomposition
- `engine/acb/pool.py` — ACB invariant checks
- `engine/classifier/writer.py` — Classifier invariant checks + audit wiring
- `verify/reconcile.py` — Reconciler invariant checks
- `indexers/exchange_parsers/base.py` — Exchange parser invariant checks
- `tests/test_invariants.py` — Integration tests for invariant checks
- `tests/test_api_audit.py` — Audit API tests
- `tests/test_offline_mode.py` — Offline mode tests
