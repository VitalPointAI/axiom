# Roadmap

## Overview

| # | Phase | Goal | Requirements | Est. Time |
|---|-------|------|--------------|-----------|
| 1 | NEAR Indexer | Pull complete NEAR transaction history | DATA-01,02,03,06 | 2 days |
| 2 | Multi-Chain + Exchanges | Pull EVM data and parse exchange CSVs | DATA-04,05 | 2 days |
| 3 | Transaction Classification | Classify all transactions by tax type | CLASS-01,02,03,04,05 | 2 days |
| 4 | Cost Basis Engine | Calculate ACB and track gains/losses | ACB-01,02,03,04,05 | 2 days |
| 5 | Verification | Reconcile balances and detect issues | VER-01,02,03,04 | 1 day |
| 6 | Reporting | Generate tax reports for accountant | RPT-01,02,03,04,05,06 | 2 days |
| 7 | Web UI | User-friendly interface with NEAR wallet auth | UI-01,02,03,04,05,06,07,08 | 3 days |

**Total estimate:** 14 days

---

## Phase 1: NEAR Indexer

**Goal:** Pull complete transaction history for all 64 NEAR accounts including staking rewards and lockup vesting.

**Plans:** 4 plans in 3 waves

Plans:
- [x] 01-01-PLAN.md — Fresh PostgreSQL schema + Alembic migrations + config cleanup (Wave 1) [DATA-06] ✓ DONE
- [x] 01-02-PLAN.md — Standalone indexer service + NEAR transaction fetcher (Wave 2) [DATA-01, DATA-06] ✓ DONE
- [x] 01-03-PLAN.md — Multi-source price service + epoch staking rewards + lockup parser (Wave 2) [DATA-02, DATA-03] ✓ DONE
- [ ] 01-04-PLAN.md — Integration wiring: register all handlers + web API job queue (Wave 3) [DATA-01, DATA-02, DATA-03, DATA-06]

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

**Goal:** Pull EVM chain data and import exchange transaction history via CSV.

**Requirements:**
- DATA-04: Pull EVM transaction history
- DATA-05: Parse exchange CSV exports

**Success Criteria:**
1. [ ] ETH/Polygon/Optimism transactions for both addresses imported
2. [ ] Coinbase CSV parser works and imports transactions
3. [ ] At least 3 other exchange CSV parsers implemented
4. [ ] All imported transactions have consistent schema in database
5. [ ] Calculated EVM balances match on-chain balances

**Deliverables:**
- `indexers/evm_indexer.py` — Etherscan/Polygonscan scanner
- `indexers/exchange_parsers/coinbase.py`
- `indexers/exchange_parsers/crypto_com.py`
- `indexers/exchange_parsers/generic.py`

---

## Phase 3: Transaction Classification

**Goal:** Automatically classify all transactions by tax treatment.

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
- `engine/classifier.py` — Transaction classifier
- `engine/wallet_graph.py` — Owned wallet detection
- `engine/prices.py` — Historical price fetcher

---

## Phase 4: Cost Basis Engine

**Goal:** Calculate Adjusted Cost Base (ACB) and track capital gains/losses.

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
- `engine/acb.py` — ACB calculator
- `engine/gains.py` — Capital gains calculator
- `engine/superficial.py` — Superficial loss detector

---

## Phase 5: Verification

**Goal:** Ensure data accuracy by reconciling against on-chain state.

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
- `verify/reconcile.py` — Balance reconciler
- `verify/duplicates.py` — Duplicate detector
- `verify/gaps.py` — Missing transaction finder
- `DISCREPANCIES.md` — Manual review notes

---

## Phase 6: Reporting

**Goal:** Generate accountant-ready tax reports.

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
- `reports/capital_gains.py`
- `reports/income.py`
- `reports/ledger.py`
- `reports/t1135.py`
- `reports/export.py`
- `output/2025_tax_package/` — Final deliverable

---

---

## Phase 7: Web UI

**Goal:** Build a user-friendly web interface with NEAR wallet authentication for managing accounts, viewing transactions, and generating reports.

**Requirements:**
- UI-01: NEAR wallet authentication via near-phantom-auth
- UI-02: Portfolio dashboard with holdings summary
- UI-03: Wallet management (add/edit/remove, sync status)
- UI-04: Transaction ledger with filtering and search
- UI-05: Transaction detail editing
- UI-06: Report generation interface
- UI-07: Verification status dashboard
- UI-08: Multi-user data isolation

**Success Criteria:**
1. [ ] Users can sign in with NEAR wallet (mainnet)
2. [ ] Dashboard shows portfolio value, holdings by asset, staking positions
3. [ ] Users can add/manage wallets and trigger indexing
4. [ ] Transaction ledger supports filter by date, type, asset, amount
5. [ ] Users can edit transaction classifications and add notes
6. [ ] Reports can be generated and downloaded from UI
7. [ ] Verification issues are clearly displayed with resolution guidance
8. [ ] Each user's data is isolated by their NEAR account

**Deliverables:**
- `web/` — Next.js application
- `web/app/` — App router pages (dashboard, wallets, transactions, reports)
- `web/components/` — Reusable UI components
- `web/lib/near-auth.ts` — near-phantom-auth integration
- `api/` — FastAPI backend (or extend existing)

**Tech Stack:**
- Next.js 14+ with App Router
- near-phantom-auth for authentication
- Tailwind CSS + shadcn/ui components
- SQLite → PostgreSQL migration for multi-user

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

---
*Last updated: 2026-03-12 — 01-03 complete (PriceService + StakingFetcher + LockupFetcher + 17 tests)*
