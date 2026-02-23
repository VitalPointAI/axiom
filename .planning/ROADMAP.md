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

**Total estimate:** 11 days

---

## Phase 1: NEAR Indexer

**Goal:** Pull complete transaction history for all 64 NEAR accounts including staking rewards and lockup vesting.

**Requirements:**
- DATA-01: Pull complete transaction history for any NEAR account
- DATA-02: Pull staking rewards history from validator pool
- DATA-03: Pull lockup contract vesting events
- DATA-06: Store transactions in PostgreSQL

**Success Criteria:**
1. [ ] All 64 NEAR accounts have complete transaction history in database
2. [ ] Staking rewards for vitalpointai.near are captured with timestamps and amounts
3. [ ] Lockup vesting events are captured with unlock dates and amounts
4. [ ] Calculated NEAR balance matches on-chain balance for vitalpointai.near (±0.01 NEAR)
5. [ ] Database schema supports all NEAR transaction types (transfer, stake, unstake, function_call)

**Deliverables:**
- `db/schema.sql` — PostgreSQL schema
- `indexers/near_indexer.py` — NEAR transaction scanner
- `indexers/staking_rewards.py` — Validator reward extractor
- `indexers/lockup_parser.py` — Lockup contract parser

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

## Dependencies

```
Phase 1 ──┬──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6
Phase 2 ──┘
```

- Phases 1 & 2 can run in parallel (data ingestion)
- Phase 3 requires Phase 1 & 2 complete (needs all transactions)
- Phase 4 requires Phase 3 (needs classifications)
- Phase 5 requires Phase 4 (needs calculated balances)
- Phase 6 requires Phase 5 (needs verified data)

---
*Last updated: 2026-02-23 after initialization*
