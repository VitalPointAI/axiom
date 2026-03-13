# Requirements

## v1 Requirements

### Data Ingestion

- [ ] **DATA-01**: System can pull complete transaction history for any NEAR account via RPC/indexer
- [ ] **DATA-02**: System can pull staking rewards history from validator pool contracts
- [ ] **DATA-03**: System can pull lockup contract vesting events
- [x] **DATA-04**: System can pull EVM transaction history via Etherscan/Polygonscan APIs
- [x] **DATA-05**: System can parse exchange CSV exports (Coinbase, Crypto.com, Bitbuy, Coinsquare, Wealthsimple, Uphold)
- [ ] **DATA-06**: System stores all transactions in PostgreSQL with consistent schema

### Classification

- [x] **CLASS-01**: System classifies transactions as: income, capital_gain, capital_loss, transfer, fee
- [x] **CLASS-02**: System detects internal transfers (between owned wallets) and marks as non-taxable
- [x] **CLASS-03**: System identifies staking reward distributions and marks as income
- [x] **CLASS-04**: System identifies lockup vesting events and marks as income
- [x] **CLASS-05**: System identifies token swaps/trades and calculates gain/loss

### Cost Basis

- [x] **ACB-01**: System calculates Adjusted Cost Base (ACB) using Canadian average cost method
- [x] **ACB-02**: System tracks ACB per token across all wallets (pooled, not per-wallet)
- [x] **ACB-03**: System fetches historical FMV prices for income events (staking, vesting)
- [x] **ACB-04**: System adjusts cost basis for fees paid
- [ ] **ACB-05**: System handles superficial loss rules (30-day rule) — flag for manual review

### Verification

- [x] **VER-01**: System reconciles calculated balance vs current on-chain balance for each wallet
- [x] **VER-02**: System flags discrepancies for manual review
- [x] **VER-03**: System detects and flags duplicate transactions
- [x] **VER-04**: System detects missing transactions (balance gaps)

### Reporting

- [x] **RPT-01**: System generates capital gains/losses summary for tax year (2025)
- [x] **RPT-02**: System generates income summary (staking rewards, airdrops) by month
- [x] **RPT-03**: System generates full transaction ledger with classifications
- [x] **RPT-04**: System checks T1135 threshold (foreign property > $100K CAD)
- [ ] **RPT-05**: System exports accountant-ready CSV package
- [ ] **RPT-06**: System generates PDF summary report

### User Interface

- [ ] **UI-01**: Web UI with user authentication via near-phantom-auth (NEAR wallet login)
- [ ] **UI-02**: Dashboard showing portfolio summary (total holdings, value by asset, staking positions)
- [ ] **UI-03**: Wallet management view (add/edit/remove wallets, view balances, sync status)
- [ ] **UI-04**: Transaction ledger with filtering, search, and pagination
- [ ] **UI-05**: Transaction detail view with classification editing and notes
- [ ] **UI-06**: Report generation UI (select tax year, generate/download reports)
- [ ] **UI-07**: Verification dashboard showing reconciliation status and flagged issues
- [ ] **UI-08**: Multi-user support with isolated data per NEAR account

### CI/CD Deployment

- [ ] **CICD-01**: GitHub Actions workflow for automated deployment on push to main
- [x] **CICD-02**: Docker Compose orchestration for all services (PostgreSQL, FastAPI backend, Next.js frontend, indexer)
- [x] **CICD-03**: Server deployment via SSH with zero-downtime strategy

## v2 Requirements (Deferred)

- [ ] Plaid integration for automated bank data
- [ ] Real-time portfolio value tracking
- [ ] Multi-entity support (multiple corporations)
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
| CLASS-02 | Phase 3 | Complete |
| CLASS-03 | Phase 3 | Not Started |
| CLASS-04 | Phase 3 | Not Started |
| CLASS-05 | Phase 3 | Not Started |
| ACB-01 | Phase 4 | Complete (04-02) |
| ACB-02 | Phase 4 | Complete (04-02) |
| ACB-03 | Phase 4 | Complete (04-01) |
| ACB-04 | Phase 4 | Complete (04-02) |
| ACB-05 | Phase 4 | Not Started |
| VER-01 | Phase 5 | Complete (05-01) |
| VER-02 | Phase 5 | Complete (05-01) |
| VER-03 | Phase 5 | Complete |
| VER-04 | Phase 5 | Complete (05-04) |
| RPT-01 | Phase 6 | Complete (06-01) |
| RPT-02 | Phase 6 | Complete (06-01) |
| RPT-03 | Phase 6 | Complete |
| RPT-04 | Phase 6 | Complete |
| RPT-05 | Phase 6 | Not Started |
| RPT-06 | Phase 6 | Not Started |
| UI-01 | Phase 7 | Not Started |
| UI-02 | Phase 7 | Not Started |
| UI-03 | Phase 7 | Not Started |
| UI-04 | Phase 7 | Not Started |
| UI-05 | Phase 7 | Not Started |
| UI-06 | Phase 7 | Not Started |
| UI-07 | Phase 7 | Not Started |
| UI-08 | Phase 7 | Not Started |
| CICD-01 | Phase 8 | Not Started |
| CICD-02 | Phase 8 | Complete |
| CICD-03 | Phase 8 | Complete |

---
*Last updated: 2026-03-13 after completing 05-01 verification schema + handler wiring*
