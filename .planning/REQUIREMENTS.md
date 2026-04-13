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
- [x] **RPT-05**: System exports accountant-ready CSV package
- [x] **RPT-06**: System generates PDF summary report

### User Interface

- [x] **UI-01**: Web UI with user authentication via near-phantom-auth (NEAR wallet login)
- [x] **UI-02**: Dashboard showing portfolio summary (total holdings, value by asset, staking positions)
- [x] **UI-03**: Wallet management view (add/edit/remove wallets, view balances, sync status)
- [x] **UI-04**: Transaction ledger with filtering, search, and pagination
- [x] **UI-05**: Transaction detail view with classification editing and notes
- [x] **UI-06**: Report generation UI (select tax year, generate/download reports)
- [x] **UI-07**: Verification dashboard showing reconciliation status and flagged issues
- [x] **UI-08**: Multi-user support with isolated data per NEAR account

### CI/CD Deployment

- [ ] **CICD-01**: GitHub Actions workflow for automated deployment on push to main
- [x] **CICD-02**: Docker Compose orchestration for all services (PostgreSQL, FastAPI backend, Next.js frontend, indexer)
- [x] **CICD-03**: Server deployment via SSH with zero-downtime strategy


### Post-Quantum Encryption (Phase 16)

- [x] **PQE-01**: Each user has an ML-KEM-768 keypair provisioned at registration; public encapsulation key (`mlkem_ek`, 1184 bytes) stored server-side; private decapsulation key (`mlkem_sealed_dk`) sealed via PRF-derived (or IPFS+password fallback) sealing key, never stored unsealed.
- [x] **PQE-02**: Per-user 256-bit DEK generated at registration, wrapped with user's ML-KEM-768 encapsulation key (envelope encryption), stored as `users.wrapped_dek`. DEK only present in process memory during an authenticated session or an opt-in worker.
- [x] **PQE-03**: All sensitive columns on `transactions`, `wallets`, `staking_events`, `lockup_events`, `epoch_snapshots`, `transaction_classifications`, `acb_snapshots`, `capital_gains_ledger`, `income_ledger`, `verification_results`, `account_verification_status`, `audit_log` (data entries), user-scoped `classification_rules`, user-scoped `spam_rules` are stored as AES-256-GCM ciphertext via SQLAlchemy `EncryptedBytes` TypeDecorator. A `pg_dump | strings` scan finds zero plaintext amounts, counterparties, or tx hashes.
- [x] **PQE-04**: `users.email` replaced by `email_hmac` (HMAC-SHA256 with server key) for login lookup. `users.username` and `users.near_account_id` encrypted with user DEK; `near_account_id_hmac` added as cleartext login-lookup surrogate.
- [x] **PQE-05**: Per-user materialization pipeline (classifier, ACB, verifier, reports, wallet sync) only runs when a session DEK is resolvable. The Rust account indexer (Phase 15 public data plane) is untouched and continues running. Requests without a resolvable DEK that touch encrypted data raise an explicit error, never silently return `None`.
- [x] **PQE-06**: Opt-in "Background processing" worker key: users can enable a sealed worker copy of their DEK (`users.worker_sealed_dek`) via Settings; revocation wipes the worker key atomically; UI surfaces privacy tradeoff, status, last-run, and revoke control; every toggle writes an audit log entry.
- [x] **PQE-07**: Migration performs a clean-slate wipe of all user-data tables (D-20), preserves auth tables (D-22), provides a documented rollback via `pg_dump` backup (D-23), and the onboarding wizard has a "returning from pre-encryption release" path that guides users to re-enter wallets (D-21).
- [x] **PQE-08**: DEKs and ML-KEM private keys are explicitly zeroed with `ctypes.memset` on session end, logout, process exit (`atexit` handler), and after every request; a memory-scan test confirms DEK bytes are not present in process memory after `zero_dek()`.

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
| RPT-05 | Phase 6 | Complete |
| RPT-06 | Phase 6 | Complete |
| UI-01 | Phase 7 | Complete |
| UI-02 | Phase 7 | Complete |
| UI-03 | Phase 7 | Complete |
| UI-04 | Phase 7 | Complete |
| UI-05 | Phase 7 | Complete |
| UI-06 | Phase 7 | Complete |
| UI-07 | Phase 7 | Complete |
| UI-08 | Phase 7 | Complete (07-01) |
| CICD-01 | Phase 8 | Not Started |
| CICD-02 | Phase 8 | Complete |
| CICD-03 | Phase 8 | Complete |
| PQE-01 | Phase 16 | Not Started |
| PQE-02 | Phase 16 | Not Started |
| PQE-03 | Phase 16 | Not Started |
| PQE-04 | Phase 16 | Not Started |
| PQE-05 | Phase 16 | Not Started |
| PQE-06 | Phase 16 | Not Started |
| PQE-07 | Phase 16 | Not Started |
| PQE-08 | Phase 16 | Not Started |

---
*Last updated: 2026-03-13 after completing 05-01 verification schema + handler wiring*
