# NearTax Indexer Rules & Tax Treatment Guide

> **Version**: 1.1.0  
> **Last Updated**: 2026-02-26  
> **Status**: Draft - Pending Accountant Review

This document defines how the NearTax indexer categorizes NEAR blockchain transactions and their recommended tax treatment. All rules should be verified with a qualified tax professional before use.

---

## Table of Contents

1. [Transaction Parsing Rules](#transaction-parsing-rules)
2. [Action Types](#action-types)
3. [Method Name Rules](#method-name-rules)
4. [Counterparty Rules](#counterparty-rules)
5. [Tax Categories](#tax-categories)
6. [Special Cases](#special-cases)
7. [Monitoring & Alerts](#monitoring--alerts)
8. [Changelog](#changelog)

---

## Transaction Parsing Rules

### Amount Extraction

| Scenario | Source Field | Notes |
|----------|--------------|-------|
| TRANSFER action | `action.deposit` | Direct transfer amount |
| Multi-action tx (CREATE_ACCOUNT + TRANSFER) | `actions_agg.deposit` | Sum of all deposits |
| FUNCTION_CALL with deposit | `actions_agg.deposit` or `action.deposit` | Use aggregate if available |
| Callback/receipt TRANSFER | `action.deposit` | `actions_agg.deposit` is often 0 for callbacks |

### Direction Determination

```
if predecessor_account_id == wallet_being_indexed:
    direction = "out"
    counterparty = receiver_account_id
else:
    direction = "in"
    counterparty = predecessor_account_id
```

### Failed Transaction Handling

**Rule**: Skip all failed transactions (`outcomes.status = false`)

**Rationale**: Failed transactions are fully reverted on NEAR. No funds change hands, so they have no tax implications. They are noise in the transaction list.

---

## Action Types

| Action Type | Tax Category | Notes |
|-------------|--------------|-------|
| `TRANSFER` | Varies by context | See counterparty rules |
| `STAKE` | `staking_deposit` | Native staking action |
| `CREATE_ACCOUNT` | `internal` if to owned account | Account creation with funding |
| `ADD_KEY` | `non_taxable` | Key management |
| `DELETE_KEY` | `non_taxable` | Key management |
| `DEPLOY_CONTRACT` | `non_taxable` | No value transfer |
| `DELETE_ACCOUNT` | Special handling | See DELETE_ACCOUNT section |
| `FUNCTION_CALL` | Varies by method | See method rules below |

---

## Method Name Rules

### Staking Methods (High Volume)

| Method | Direction | Category | Count | Notes |
|--------|-----------|----------|-------|-------|
| `on_stake_action` | out | `staking_deposit` | 65,292 | Validator callback |
| `deposit_and_stake` | in | `staking_deposit` | 40,310 | Pool deposit received |
| `deposit_and_stake` | out | `staking_deposit` | 77 | Direct pool deposit |
| `withdraw_all` | in | `non_taxable` | 16,715 | Unstake trigger (0 value) |
| `withdraw_all` | out | `unstake_return` | 6 | Direct withdrawal |
| `unstake_all` | in | `non_taxable` | 10,777 | Unstake trigger (0 value) |
| `unstake` | in | `non_taxable` | 9,630 | Unstake trigger |
| `unstake` | out | `unstake_return` | 3 | Direct unstake |
| `withdraw` | in | `non_taxable` | 2,049 | Withdrawal trigger |
| `withdraw` | out | `unstake_return` | 17 | Direct withdrawal |
| `ping` | in | `non_taxable` | 13,988 | Validator ping (no value) |
| `stake` | in | `non_taxable` | 19 | Stake trigger |

### View/Query Methods (Non-Taxable)

| Method | Category | Notes |
|--------|----------|-------|
| `get_account_total_balance` | `non_taxable` | View function |
| `get_account_unstaked_balance` | `non_taxable` | View function |
| `get_account_staked_balance` | `non_taxable` | View function |
| `get_account` | `non_taxable` | View function |
| `get_accounts` | `non_taxable` | View function |
| `get_owner_id` | `non_taxable` | View function |
| `get_number_of_accounts` | `non_taxable` | View function |
| `is_account_unstaked_balance_available` | `non_taxable` | View function |

### DeFi Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `near_deposit` | out | `defi_deposit` | Wrap NEAR to wNEAR |
| `near_withdraw` | out | `defi_withdrawal` | Unwrap wNEAR to NEAR |
| `ft_transfer_call` | out | `swap` or `defi_deposit` | Token transfer with call |
| `ft_transfer` | out | `transfer` | Direct token transfer |
| `swap` | out | `swap` | Direct swap |
| `add_liquidity` | out | `liquidity_add` | LP deposit |
| `remove_liquidity` | out | `liquidity_remove` | LP withdrawal |
| `add_stable_liquidity` | out | `liquidity_add` | Stable LP deposit |
| `mft_transfer_call` | out | `swap` | Multi-token transfer |
| `execute` | out | `swap` | Generic DeFi execution |
| `execute_with_pyth` | out | `swap` | Pyth oracle swap |

### Farming/Rewards Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `claim_reward_by_seed` | out | `income` | Farming reward claim |
| `claim_reward_by_farm` | out | `income` | Farming reward claim |
| `account_farm_claim_all` | out | `income` | Batch farming claim |
| `withdraw_reward` | out | `income` | Reward withdrawal |
| `claim` | out | `income` | Generic claim |
| `claim_stnear` | out | `income` | stNEAR claim |
| `claim_and_lock` | out | `income` | Claim with lock |
| `claim_unlocked_mpdao` | out | `income` | mpDAO claim |
| `harvest` | out | `income` | Yield harvest |
| `harvest_meta` | out | `income` | Meta Pool harvest |
| `withdraw_seed` | out | `defi_withdrawal` | Seed withdrawal |
| `unlock_and_withdraw_seed` | out | `defi_withdrawal` | Unlocked seed withdrawal |

### Account/Storage Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `storage_deposit` | out | `non_taxable` | Storage reservation |
| `create_account` | out | `internal` | Sub-account creation |
| `init` | out/in | `internal` | Contract initialization |
| `new` | out/in | `non_taxable` | Contract constructor |
| `new_default_meta` | out/in | `non_taxable` | NFT contract init |
| `migrate` | out/in | `non_taxable` | Contract migration |
| `clear_all_state` | out/in | `non_taxable` | State clear |

### DAO Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `leave` | out | `dao_withdrawal` | Leave DAO (triggers refund) |
| `vote` | out | `non_taxable` | DAO vote |
| `vote_proposal` | out | `non_taxable` | DAO vote |
| `add_proposal` | out | `non_taxable` | Create proposal |
| `donate` | out | `gift_given` | Donation |
| `donate` | in | `gift_received` | Donation received |

### NFT Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `nft_mint` | out | `nft_purchase` | NFT minting |
| `nft_mint_batch` | out | `nft_purchase` | Batch minting |
| `nft_mint_batch_with_restrictions` | out | `nft_purchase` | Restricted minting |
| `nft_transfer` | out | `nft_transfer` | NFT transfer |
| `nft_transfer` | in | `nft_received` | NFT received |
| `mint_sbt` | out | `nft_purchase` | Soul-bound token |
| `sbt_mint` | out | `nft_purchase` | Soul-bound token |

### Social/Identity Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `set` | out | `non_taxable` | Social DB set |
| `storeAlias` | out | `non_taxable` | Store alias |
| `putDID` | out | `non_taxable` | DID registration |
| `set_username` | out | `non_taxable` | Username set |
| `set_metadata` | out | `non_taxable` | Metadata update |

### Inscription Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `inscribe` | out | `nft_purchase` | Inscription creation |

### Liquid Staking Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `liquid_unstake` | out | `defi_withdrawal` | Meta Pool unstake |
| `nslp_add_liquidity` | out | `liquidity_add` | NSLP deposit |
| `nslp_remove_liquidity` | out | `liquidity_remove` | NSLP withdrawal |
| `select_farming_preference` | out | `non_taxable` | Preference change |
| `account_stake_booster` | out | `staking_deposit` | Booster stake |
| `account_unstake_booster` | out | `unstake_return` | Booster unstake |

### Trading/Bot Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `create_bot` | out | `non_taxable` | Bot creation (deposit) |
| `close_bot` | out | `non_taxable` | Bot closure (withdrawal) |
| `oracle_call` | out | `non_taxable` | Oracle interaction |

### Key Management Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `owner_get_encrypted_key` | out/in | `non_taxable` | Key retrieval |
| `owner_store_encrypted_key` | out/in | `non_taxable` | Key storage |
| `owner_register_key` | out/in | `non_taxable` | Key registration |
| `owner_delete_backup` | out/in | `non_taxable` | Backup deletion |
| `add_public_key` | out | `non_taxable` | Key addition |
| `user_announce_key` | out | `non_taxable` | Key announcement |
| `user_request_set_trading_key` | out | `non_taxable` | Trading key |

### Credit/Payment Methods

| Method | Direction | Category | Notes |
|--------|-----------|----------|-------|
| `deduct_credits` | out/in | `non_taxable` | Credit deduction |
| `add_credits_from_usdc` | out/in | `non_taxable` | USDC credit add |
| `add_bonus_credits` | out/in | `non_taxable` | Bonus credits |
| `purchase` | out | `purchase` | Direct purchase |
| `send` | out | `transfer` | Direct send |
| `transfer_near` | out | `transfer` | NEAR transfer |

---

## Counterparty Rules

| Pattern | Category (out) | Category (in) | Notes |
|---------|----------------|---------------|-------|
| `*.poolv1.near` | `staking_deposit` | `unstake_return` | Validator pools |
| `*.pool.near` | `staking_deposit` | `unstake_return` | Validator pools |
| `meta-pool.near` | `staking_deposit` | `unstake_return` | Liquid staking |
| `linear-protocol.near` | `staking_deposit` | `unstake_return` | LiNEAR |
| `v2-nearx.stader-labs.near` | `staking_deposit` | `unstake_return` | Stader |
| `wrap.near` | `defi_deposit` | `defi_withdrawal` | wNEAR |
| `v2.ref-finance.near` | `swap` | `swap` | Ref Finance |
| `token.v2.ref-finance.near` | `swap` | `swap` | Ref tokens |
| `v2.ref-farming.near` | `defi_deposit` | `income` | Ref farming |
| `boostfarm.ref-labs.near` | `defi_deposit` | `income` | Boost farming |
| `contract.main.burrow.near` | `defi_deposit` | `defi_withdrawal` | Burrow lending |
| `*.cdao.near` | `dao_deposit` | `dao_withdrawal` | CDAOs |
| `*.sputnikdao.near` | `dao_deposit` | `dao_withdrawal` | Sputnik DAOs |
| `*.lockup.near` | `internal` | `internal` | Lockup contracts |
| `[implicit_account]` (64 hex chars) | `internal` | `internal` | NEAR Intents |
| `system` | - | `fee_refund` or `delete_account_received` | Protocol |
| Own wallets | `internal` | `internal` | Between owned accounts |
| `social.near` | `non_taxable` | - | Social DB |
| `inscription.near` | `nft_purchase` | - | Inscriptions |
| `priceoracle.near` | `non_taxable` | - | Oracle calls |

---

## Tax Categories

### Income Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `staking_income` | Validator/pool rewards | **Income** at FMV when received |
| `income` | Generic income (farming, etc.) | **Income** at FMV when received |
| `airdrop` | Free token distributions | **Income** at FMV when received |
| `gift_received` | Gift from third party | **Non-taxable** receipt, cost basis = FMV |

### Transfer Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `internal` | Between own wallets | **Non-taxable** (no disposition) |
| `transfer` | To/from third party | **Potential disposition** - review context |
| `gift_given` | Gift to third party | **Disposition** at FMV |
| `delete_account_received` | From deleted account | Depends on source ownership |

### Staking Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `staking_deposit` | Staking NEAR to validator/pool | **Non-taxable** (not a disposition) |
| `unstake_return` | Unstaking from validator/pool | **Non-taxable** (principal return) |

### DeFi Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `swap` | Token exchange | **Disposition** - capital gain/loss |
| `liquidity_add` | Adding to LP | **Potential disposition** - complex |
| `liquidity_remove` | Removing from LP | **Potential disposition** - complex |
| `defi_deposit` | Lending/wrapping | **Non-taxable** if same token returned |
| `defi_withdrawal` | Withdrawing from DeFi | **Non-taxable** if same token returned |

### DAO Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `dao_deposit` | DAO membership deposit | **Non-taxable** (deposit) |
| `dao_withdrawal` | DAO leave refund | **Non-taxable** (return of deposit) |

### NFT Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `nft_purchase` | NFT minting/buying | **Acquisition** at cost |
| `nft_transfer` | NFT sent | **Disposition** at FMV |
| `nft_received` | NFT received | **Acquisition** at FMV |

### Other Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `fee_refund` | Gas refund from system | **Non-taxable** |
| `non_taxable` | No tax implications | Key changes, views, etc. |
| `purchase` | Buying goods/services | **Disposition** at FMV |
| `NEEDS_REVIEW` | Manual review required | Complex/ambiguous |

---

## Special Cases

### 1. DELETE_ACCOUNT Beneficiary Transfers

**How NEAR handles this**:
1. Source account executes `DELETE_ACCOUNT` action (deposit: 0)
2. Beneficiary receives `TRANSFER` from `system` (not the deleted account!)
3. Both receipts share the same `transaction_hash`

**Example** (`APynxgFzGoH1V2ToWRdVrE8H259YCFYGf58v2gtLfTU2`):
```
Source: challenge-coin-game.credz.near
  → DELETE_ACCOUNT action, deposit: 0

Beneficiary: credz.near  
  → TRANSFER from "system", deposit: 2.999 NEAR
```

**Classification**:
- If DELETE_ACCOUNT tx_hash exists in owned wallets → `internal`
- Otherwise → `delete_account_received` (potential income)

### 2. Account Creation (`init` method)

**Pattern**: `FUNCTION_CALL` with `method_name = "init"` and attached deposit

**Rule**: 
- If `predecessor` is owned wallet → `internal`
- If `predecessor` is third party → `gift_received` or `income`

### 3. DAO Leave (`leave` method)

**Pattern**: `FUNCTION_CALL` with `method_name = "leave"` followed by `TRANSFER` callback

**Rule**:
- The `leave` call itself has 0 deposit
- The refund comes as a separate `TRANSFER` receipt from the DAO contract
- Category: `dao_withdrawal` (return of membership deposit)

### 4. Staking Rewards

**Note**: Staking rewards are NOT direct transactions. They accumulate in the pool balance and are realized when unstaking returns more than deposited.

**Tracking method**:
- Track deposits via `deposit_and_stake`, `stake` methods
- Track withdrawals via `withdraw`, `withdraw_all` methods  
- Difference = rewards (if positive)

### 5. System Transfers

**Pattern**: `TRANSFER` with `counterparty = "system"`

**Rules**:
- If same tx_hash as DELETE_ACCOUNT → `delete_account_received`
- Otherwise → `fee_refund` (gas refunds)

---

## Monitoring & Alerts

### Uncategorized Pattern Detection

Run `scripts/detect_uncategorized.py` after each categorization to find new patterns.

**Triggers alert when**:
- Pattern has ≥3 occurrences, OR
- Pattern has ≥0.1 NEAR total value

**Alert output**: `/home/deploy/neartax/uncategorized_alerts.json`

### Adding New Rules

1. Review alert output for uncategorized patterns
2. Determine appropriate tax category
3. Add rule to `careful_categorize.py`
4. Document in this file under appropriate section
5. Run categorization again
6. Verify alert is resolved

---

## Changelog

### v1.1.0 (2026-02-26)
- Added comprehensive method name rules (100+ methods documented)
- Added counterparty pattern rules
- Added DELETE_ACCOUNT beneficiary transfer handling
- Added `init` and `leave` method rules
- Added DAO, NFT, farming, liquid staking categories
- Added uncategorized pattern detection script
- Reorganized document structure

### v1.0.0 (2026-02-26)
- Initial documentation
- Basic action types and tax categories
- Amount extraction logic
- Failed transaction filtering

---

## Disclaimer

This document is for informational purposes only and does not constitute tax advice. Tax treatment may vary by jurisdiction and individual circumstances. Always consult with a qualified tax professional before making tax decisions based on this information.

**Accountant Review Status**: ⏳ Pending

---

## Questions for Accountant

1. **Liquid staking tokens (stNEAR, LiNEAR)**: Is the appreciation taxable annually or only on disposal?
2. **LP tokens**: What is the correct treatment for adding/removing liquidity?
3. **DAO membership deposits**: Are these treated as investments or deposits?
4. **Failed transactions**: Confirm they should be excluded entirely?
5. **Internal transfers**: Confirm no disposition occurs between owned wallets?
6. **Staking rewards**: Should we estimate and record annually, or only on withdrawal?
7. **NFT minting**: Is this an acquisition at cost, or a creation event?
