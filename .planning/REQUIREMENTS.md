# Requirements

## v1 Requirements

### Data Ingestion

- [ ] **DATA-01**: System can pull complete transaction history for any NEAR account via RPC/indexer
- [ ] **DATA-02**: System can pull staking rewards history from validator pool contracts
- [ ] **DATA-03**: System can pull lockup contract vesting events
- [ ] **DATA-04**: System can pull EVM transaction history via Etherscan/Polygonscan APIs
- [ ] **DATA-05**: System can parse exchange CSV exports (Coinbase, Crypto.com, Bitbuy, Coinsquare, Wealthsimple, Uphold)
- [ ] **DATA-06**: System stores all transactions in PostgreSQL with consistent schema

### Classification

- [ ] **CLASS-01**: System classifies transactions as: income, capital_gain, capital_loss, transfer, fee
- [ ] **CLASS-02**: System detects internal transfers (between owned wallets) and marks as non-taxable
- [ ] **CLASS-03**: System identifies staking reward distributions and marks as income
- [ ] **CLASS-04**: System identifies lockup vesting events and marks as income
- [ ] **CLASS-05**: System identifies token swaps/trades and calculates gain/loss

### Cost Basis

- [ ] **ACB-01**: System calculates Adjusted Cost Base (ACB) using Canadian average cost method
- [ ] **ACB-02**: System tracks ACB per token across all wallets (pooled, not per-wallet)
- [ ] **ACB-03**: System fetches historical FMV prices for income events (staking, vesting)
- [ ] **ACB-04**: System adjusts cost basis for fees paid
- [ ] **ACB-05**: System handles superficial loss rules (30-day rule) — flag for manual review

### Verification

- [ ] **VER-01**: System reconciles calculated balance vs current on-chain balance for each wallet
- [ ] **VER-02**: System flags discrepancies for manual review
- [ ] **VER-03**: System detects and flags duplicate transactions
- [ ] **VER-04**: System detects missing transactions (balance gaps)

### Reporting

- [ ] **RPT-01**: System generates capital gains/losses summary for tax year (2025)
- [ ] **RPT-02**: System generates income summary (staking rewards, airdrops) by month
- [ ] **RPT-03**: System generates full transaction ledger with classifications
- [ ] **RPT-04**: System checks T1135 threshold (foreign property > $100K CAD)
- [ ] **RPT-05**: System exports accountant-ready CSV package
- [ ] **RPT-06**: System generates PDF summary report

## v2 Requirements (Deferred)

- [ ] Plaid integration for automated bank data
- [ ] Real-time portfolio value tracking
- [ ] Multi-entity support (multiple corporations)
- [ ] Web UI for transaction review/editing
- [ ] Automatic exchange API sync (vs CSV import)

## Out of Scope

- **Tax filing automation** — Accountant handles actual filing
- **Tax advice/optimization** — We report facts, accountant advises
- **Other jurisdictions** — Canada only for now
- **NFT valuation** — Track transfers but don't value (complex)
- **DeFi yield farming** — Flag for manual review if detected

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| DATA-01 | Phase 1 | Not Started |
| DATA-02 | Phase 1 | Not Started |
| DATA-03 | Phase 1 | Not Started |
| DATA-04 | Phase 1 | Not Started |
| DATA-05 | Phase 2 | Not Started |
| DATA-06 | Phase 1 | Not Started |
| CLASS-01 | Phase 3 | Not Started |
| CLASS-02 | Phase 3 | Not Started |
| CLASS-03 | Phase 3 | Not Started |
| CLASS-04 | Phase 3 | Not Started |
| CLASS-05 | Phase 3 | Not Started |
| ACB-01 | Phase 4 | Not Started |
| ACB-02 | Phase 4 | Not Started |
| ACB-03 | Phase 4 | Not Started |
| ACB-04 | Phase 4 | Not Started |
| ACB-05 | Phase 4 | Not Started |
| VER-01 | Phase 5 | Not Started |
| VER-02 | Phase 5 | Not Started |
| VER-03 | Phase 5 | Not Started |
| VER-04 | Phase 5 | Not Started |
| RPT-01 | Phase 6 | Not Started |
| RPT-02 | Phase 6 | Not Started |
| RPT-03 | Phase 6 | Not Started |
| RPT-04 | Phase 6 | Not Started |
| RPT-05 | Phase 6 | Not Started |
| RPT-06 | Phase 6 | Not Started |

---
*Last updated: 2026-02-23 after initialization*
