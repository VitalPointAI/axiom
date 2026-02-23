# NearTax

## What This Is

A crypto tax calculation tool for VitalPoint AI's 2025 Canadian corporate taxes. Pulls complete transaction history from 64 NEAR accounts and multi-chain wallets, calculates Adjusted Cost Base (ACB) per Canadian tax rules, and generates accountant-ready reports.

## Core Value

**Accurate tax reporting** — Every transaction correctly classified, every balance reconciled, every taxable event properly calculated. The accountant receives a complete, defensible package.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Pull complete transaction history for all NEAR accounts
- [ ] Pull complete transaction history for EVM chains (ETH/Polygon/Optimism)
- [ ] Import exchange data via CSV (Coinbase, Crypto.com, Bitbuy, etc.)
- [ ] Calculate Adjusted Cost Base (ACB) per Canadian tax rules
- [ ] Track staking rewards as income at FMV when received
- [ ] Detect internal transfers (own wallet → own wallet = not taxable)
- [ ] Handle lockup vesting events as income
- [ ] Reconcile calculated balances vs on-chain balances
- [ ] Generate capital gains/losses report for 2025
- [ ] Generate income summary (staking rewards by month)
- [ ] Export accountant-ready package (CSV/PDF)

### Out of Scope

- **Real-time portfolio tracking** — This is tax prep, not portfolio management
- **Multi-user support** — Single company use case
- **Automated bank/Plaid integration** — CSV import sufficient for now
- **SaaS productization** — Build for VitalPoint first, productize later if valuable
- **Tax filing** — Generates reports for accountant, doesn't file directly

## Context

**Wallet inventory:**
- 64 NEAR Protocol accounts (including lockup, validator pool, DAOs)
- 2 EVM addresses used across Ethereum/Polygon/Optimism
- 1 Cronos, 1 Akash, 1 XRP, 1 Sweat address
- 7 exchanges requiring CSV import

**Key accounts:**
- `vitalpointai.near` — 19,763 NEAR (47 liquid + 19,716 staked)
- `vitalpoint.pool.near` — Validator pool, source of staking rewards
- `db59d3239f2939bb7d8a4a578aceaa8c85ee8e3f.lockup.near` — NEAR Foundation lockup

**Tax jurisdiction:** Canada (federal + provincial)
**Tax year:** 2025 (Jan 1 - Dec 31, 2025)
**Entity:** VitalPoint AI (corporation)

**Prior attempt:** Tried Koinly but it lacks API access and misses many transactions. Building custom solution for accuracy and control.

## Constraints

- **Timeline**: Accountant waiting — need this completed ASAP
- **Accuracy**: Must reconcile to on-chain balances (calculated = actual)
- **Tax method**: Canadian ACB (Adjusted Cost Base) — average cost, not FIFO/LIFO
- **API limits**: NEAR RPC and indexer APIs have rate limits — need caching/batching
- **Historical prices**: Need reliable FMV data for income events (staking rewards, vesting)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Build custom vs use Koinly | Koinly lacks API, misses transactions, charges per-transaction | — Pending |
| Use FastNear RPC | Default NEAR RPC rate-limited us heavily | — Pending |
| Python + PostgreSQL stack | Familiar, good for data processing, battle-tested | — Pending |
| Full history for cost basis | Need acquisition dates to calculate gains on 2025 disposals | — Pending |

---
*Last updated: 2026-02-23 after initialization*
