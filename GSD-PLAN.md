# NearTax - GSD Project Plan

## Goal
Build a comprehensive crypto tax solution for VitalPoint AI's 2025 Canadian corporate taxes that:
- Pulls complete transaction history for all wallets (64 NEAR + multi-chain)
- Calculates Adjusted Cost Base (ACB) per Canadian tax rules
- Tracks staking rewards as income at FMV
- Handles internal transfers (non-taxable)
- Generates accountant-ready reports

## Success Criteria
1. **Accuracy**: Final calculated balances match current on-chain balances for all wallets
2. **Completeness**: Every transaction from account creation captured
3. **Compliance**: Proper Canadian tax treatment applied
4. **Deliverable**: Reports ready for accountant to file corporate taxes

## Scope

### In Scope
- 64 NEAR Protocol accounts (including lockup, validator, DAOs)
- 2 Ethereum addresses (shared across ETH/Polygon/Optimism)
- 1 Cronos, 1 Akash, 1 XRP, 1 Sweat address
- 7 exchanges (via CSV import)
- Staking rewards for vitalpoint.pool.near
- Lockup vesting from NEAR Foundation grant
- 2025 tax year (full history needed for cost basis)

### Out of Scope (for now)
- Automated bank/Plaid integration
- Real-time portfolio tracking
- Multi-user support
- SaaS productization

## Deliverables

### D1: Data Infrastructure
- [ ] PostgreSQL schema for transactions, wallets, cost basis
- [ ] NEAR transaction indexer (full history via NEAR Lake or indexer API)
- [ ] EVM transaction scanner (Etherscan/Polygonscan APIs)
- [ ] Exchange CSV parser (Coinbase, Crypto.com, Bitbuy, etc.)

### D2: Tax Engine
- [ ] ACB calculator (Canadian adjusted cost base method)
- [ ] Transaction classifier:
  - Income (staking rewards, airdrops)
  - Capital gains/losses (sales, swaps)
  - Internal transfers (wallet-to-wallet, not taxable)
  - Fees (cost basis adjustment)
- [ ] FMV price fetcher (historical NEAR/ETH/etc prices)
- [ ] Staking rewards extractor

### D3: Reports
- [ ] Capital gains/losses summary (2025)
- [ ] Income summary (staking rewards, by month)
- [ ] Transaction ledger (full audit trail)
- [ ] T1135 foreign property check (>$100K CAD threshold)
- [ ] Accountant export (CSV format)

### D4: Verification
- [ ] Balance reconciliation (calculated vs on-chain)
- [ ] Missing transaction detector
- [ ] Duplicate transaction detector
- [ ] Manual adjustment support

## Dependencies

### External APIs
- **NEAR**: FastNear RPC, NearBlocks API (rate limited), or NEAR Lake
- **Ethereum**: Etherscan API (free tier: 5 calls/sec)
- **Polygon**: Polygonscan API
- **Optimism**: Optimistic Etherscan API
- **Prices**: CoinGecko API (free tier available)

### Data from Aaron
- Exchange CSV exports (Coinbase, Crypto.com, Bitbuy, Coinsquare, Wealthsimple, Uphold)
- Confirmation on lockup vesting schedule
- Any manual OTC trades or off-chain transactions

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| API rate limits | Slow data ingestion | Use NEAR Lake, batch requests, caching |
| Missing historical prices | Incorrect FMV for income | Multiple price sources, interpolation |
| Complex DeFi transactions | Misclassification | Manual review flag, conservative treatment |
| Lockup contract complexity | Wrong vesting income | Research NEAR lockup contract specifics |
| Exchange data gaps | Incomplete picture | Cross-reference with on-chain where possible |

## Timeline

### Week 1: Data Foundation
- Day 1-2: Database schema, NEAR indexer
- Day 3-4: EVM scanners, price fetcher
- Day 5: Exchange CSV parsers

### Week 2: Tax Engine
- Day 1-2: ACB calculator, transaction classifier
- Day 3-4: Staking rewards extraction
- Day 5: Internal transfer detection

### Week 3: Reports & Verification
- Day 1-2: Generate reports
- Day 3-4: Balance reconciliation, fix discrepancies
- Day 5: Final review with Aaron

## Tech Stack

```
neartax/
├── db/
│   ├── schema.sql          # PostgreSQL schema
│   └── migrations/
├── indexers/
│   ├── near_indexer.py     # NEAR transaction scanner
│   ├── evm_indexer.py      # ETH/Polygon/Optimism scanner
│   └── exchange_parser.py  # CSV importers
├── engine/
│   ├── acb.py              # Cost basis calculator
│   ├── classifier.py       # Transaction classifier
│   ├── prices.py           # Historical price fetcher
│   └── staking.py          # Staking rewards extractor
├── reports/
│   ├── capital_gains.py
│   ├── income.py
│   └── export.py
├── verify/
│   ├── reconcile.py        # Balance verification
│   └── audit.py            # Transaction audit
├── wallets.json            # Wallet list (done)
├── config.py
└── main.py                 # CLI interface
```

## Questions for Aaron

1. **Lockup vesting**: What was the original grant amount and vesting schedule for `db59d...lockup.near`?
2. **Exchange priority**: Which exchanges have the most activity? (to prioritize CSV parsing)
3. **Fiscal year**: Is VitalPoint AI calendar year (Jan-Dec) or different fiscal year end?
4. **OTC trades**: Any trades done outside exchanges that need manual entry?
5. **Accountant format**: Any specific format your accountant prefers?

## Next Steps (Pending Approval)

1. Create database schema
2. Build NEAR transaction indexer for vitalpointai.near (largest account)
3. Verify against current balance
4. Expand to remaining 63 NEAR accounts
5. Add EVM chain support
6. Build tax engine
7. Generate reports

---
*Plan created: 2026-02-23*
*Status: PENDING REVIEW*
