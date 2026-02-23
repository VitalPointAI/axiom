---
name: neartax
description: Crypto tax preparation for Canadian corporate taxes. Indexes NEAR/ETH wallets, tracks staking rewards via NEAR Lake, syncs to Koinly, categorizes expenses. Use for tax reporting, cost basis calculation, staking reward tracking, or preparing accountant packages.
---

# NearTax

Crypto tax preparation tool for Canadian corporate taxes.

## Capabilities

1. **Wallet Indexing** - Track NEAR and Ethereum wallets
2. **Staking Rewards** - Index validator rewards via NEAR Lake (100% accurate)
3. **Koinly Sync** - Automated import to minimize transaction count
4. **Expense Categorization** - Bank/credit card CSV processing
5. **Tax Reports** - Canadian T1135, Schedule 3, T5008 ready output

## Configuration

### Fiscal Year
- User-configurable fiscal year (stored in account settings)
- **Default:** January 1 - December 31 (calendar year)
- Canadian corps can have non-calendar fiscal years

### Output Formats
1. **Koinly-compatible CSV** - Same format Koinly exports (for re-import/verification)
2. **Universal CSV** - Standard format for other tax software import
3. **No OTC support currently** - Standard exchange/on-chain only

## Quick Reference

### Wallets File
Store wallet list in `projects/neartax/wallets.json`:
```json
{
  "near": ["account.near", "account2.near"],
  "ethereum": ["0x123..."],
  "validator": "vitalpoint.pool.near"
}
```

### Commands

**Index staking rewards:**
```bash
python3 scripts/index_staking_rewards.py vitalpoint.pool.near
```

**Export for Koinly (consolidated):**
```bash
python3 scripts/export_koinly.py --consolidate daily
```

### Koinly Credentials
Stored in `~/.openclaw/credentials/koinly.json`

## Architecture

### NEAR Lake Indexer
Uses NEAR Lake Framework to index all staking-related transactions:
- Delegation deposits/withdrawals
- Staking reward distributions
- Validator commission

### Consolidation Strategy
To minimize Koinly costs:
- Aggregate daily staking rewards into single entries
- Batch small transactions
- Use internal transfers where possible

## References
- [NEAR Lake setup](references/near-lake.md)
- [Koinly API](references/koinly-api.md)
- [Canadian tax rules](references/canadian-crypto-tax.md)
