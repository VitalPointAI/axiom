# NearTax Indexer Rules & Tax Treatment Guide

> **Version**: 1.0.0  
> **Last Updated**: 2026-02-26  
> **Status**: Draft - Pending Accountant Review

This document defines how the NearTax indexer categorizes NEAR blockchain transactions and their recommended tax treatment. All rules should be verified with a qualified tax professional before use.

---

## Table of Contents

1. [Transaction Parsing Rules](#transaction-parsing-rules)
2. [Action Types](#action-types)
3. [Tax Categories](#tax-categories)
4. [Special Cases](#special-cases)
5. [Changelog](#changelog)

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

### TRANSFER
- **Description**: Direct NEAR transfer between accounts
- **Tax Category**: Depends on context (see Tax Categories)
- **Amount Source**: `action.deposit`

### CREATE_ACCOUNT
- **Description**: Account creation, often bundled with TRANSFER + ADD_KEY
- **Tax Category**: `transfer-internal` if to own account, `gift-given` if to third party
- **Amount Source**: `actions_agg.deposit` (sum across all actions)

### FUNCTION_CALL
- **Description**: Smart contract interaction
- **Tax Category**: Based on `method_name` and `counterparty` (see Special Cases)
- **Amount Source**: `actions_agg.deposit`

### STAKE
- **Description**: Staking NEAR to a validator
- **Tax Category**: `staking-deposit` (out) or `staking-withdrawal` (in)
- **Amount Source**: `action.deposit`

### ADD_KEY / DELETE_KEY
- **Description**: Key management operations
- **Tax Category**: `non-taxable` (no value transfer)
- **Amount Source**: 0

### DEPLOY_CONTRACT
- **Description**: Smart contract deployment
- **Tax Category**: `non-taxable` (no value transfer)
- **Amount Source**: 0

### DELETE_ACCOUNT
- **Description**: Account deletion with beneficiary transfer
- **Tax Category**: `transfer-internal` if to own account
- **Special Handling**: See DELETE_ACCOUNT section below

---

## Tax Categories

### Income Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `staking-reward` | Validator/pool rewards | **Income** at FMV when received |
| `airdrop` | Free token distributions | **Income** at FMV when received |
| `mining-reward` | Block rewards (validators) | **Income** at FMV when received |
| `interest` | DeFi lending interest | **Income** at FMV when received |

### Transfer Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `transfer-internal` | Between own wallets | **Non-taxable** (no disposition) |
| `transfer-external` | To/from third party | **Potential disposition** - review context |
| `gift-received` | Gift from third party | **Non-taxable** receipt, cost basis = FMV |
| `gift-given` | Gift to third party | **Disposition** at FMV |

### DeFi Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `swap` | Token exchange (Ref Finance, etc.) | **Disposition** - capital gain/loss |
| `liquidity-add` | Adding to LP | **Potential disposition** - complex |
| `liquidity-remove` | Removing from LP | **Potential disposition** - complex |
| `defi-deposit` | Lending/staking in DeFi | **Non-taxable** if same token returned |
| `defi-withdrawal` | Withdrawing from DeFi | **Non-taxable** if same token returned |

### Staking Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `staking-deposit` | Staking NEAR to validator | **Non-taxable** (not a disposition) |
| `staking-withdrawal` | Unstaking from validator | **Non-taxable** (principal return) |
| `staking-reward` | Staking rewards received | **Income** at FMV when received |

### Other Categories

| Category | Description | Tax Treatment (Canada) |
|----------|-------------|------------------------|
| `fee` | Transaction/gas fees | **Deductible** against capital gains |
| `purchase` | Buying goods/services | **Disposition** at FMV |
| `sale` | Selling goods/services | **Income** (business) or **Capital** |
| `non-taxable` | No tax implications | Key changes, contract deploys, etc. |
| `needs-review` | Requires manual review | Complex or ambiguous transactions |

---

## Special Cases

### 1. Account Creation (`init` method)

**Pattern**: `FUNCTION_CALL` with `method_name = "init"` and attached deposit

**Rule**: 
- If `predecessor` is owned wallet → `transfer-internal`
- If `predecessor` is third party → `gift-received` or `income`

**Example**:
```
vitalpointai.near calls init on funding.vitalpointai.near with 5 NEAR attached
→ funding.vitalpointai.near receives 5 NEAR (direction: in)
→ Category: transfer-internal (same owner)
```

### 2. DAO Leave (`leave` method)

**Pattern**: `FUNCTION_CALL` with `method_name = "leave"` followed by `TRANSFER` callback

**Rule**:
- The `leave` call itself has 0 deposit
- The refund comes as a separate `TRANSFER` receipt from the DAO contract
- Category: `defi-withdrawal` (return of staked funds)

**Example**:
```
aaron.near calls leave on vitalpointai.cdao.near
→ vitalpointai.cdao.near sends 2.5 NEAR to aaron.near (TRANSFER)
→ Category: defi-withdrawal
```

### 3. DELETE_ACCOUNT

**Pattern**: `DELETE_ACCOUNT` action with beneficiary

**Rule**:
- Remaining account balance transfers to `beneficiary_id`
- Create synthetic `DELETE_ACCOUNT_TRANSFER` record
- Category: `transfer-internal` if beneficiary is owned

**Note**: Failed DELETE_ACCOUNT transactions are skipped (no funds transferred)

### 4. Staking Operations

**Deposit Pattern**: `FUNCTION_CALL` to `*.poolv1.near` or `*.pool.near` with `method_name` in [`deposit`, `deposit_and_stake`]

**Withdrawal Pattern**: `TRANSFER` from pool contract to user after `withdraw` call

**Rewards**: Calculated separately via epoch data (not direct transactions)

### 5. Ref Finance Swaps

**Pattern**: `FUNCTION_CALL` to `v2.ref-finance.near` with methods like `swap`, `ft_transfer_call`

**Rule**: 
- Input token: disposition at FMV
- Output token: acquisition at FMV
- Category: `swap`

### 6. Burrow Lending

**Pattern**: `FUNCTION_CALL` to `contract.main.burrow.near`

**Methods**:
- `supply` / `deposit` → `defi-deposit`
- `withdraw` → `defi-withdrawal`
- `borrow` → `defi-loan` (not taxable)
- `repay` → `defi-loan-repayment`

### 7. Meta Pool (stNEAR)

**Pattern**: `FUNCTION_CALL` to `meta-pool.near`

**Methods**:
- `deposit_and_stake` → `defi-deposit` (receive stNEAR)
- `unstake` / `withdraw` → `defi-withdrawal`

**Note**: stNEAR appreciates over time. Tax treatment of appreciation is complex - consult accountant.

### 8. System Transfers

**Pattern**: `TRANSFER` with `predecessor_account_id = "system"`

**Rule**: 
- Usually gas refunds or protocol-level transfers
- Category: `fee-refund` or `staking-reward` depending on context

---

## Counterparty-Based Rules

| Counterparty Pattern | Likely Category |
|---------------------|-----------------|
| `*.poolv1.near`, `*.pool.near` | Staking operation |
| `v2.ref-finance.near` | Swap |
| `contract.main.burrow.near` | DeFi lending |
| `meta-pool.near` | Liquid staking |
| `wrap.near` | wNEAR wrap/unwrap |
| `*.cdao.near` | DAO operation |
| `system` | Protocol transfer |
| Own wallets | Internal transfer |

---

## Changelog

### v1.0.0 (2026-02-26)
- Initial documentation
- Added rules for: TRANSFER, CREATE_ACCOUNT, FUNCTION_CALL, STAKE, DELETE_ACCOUNT
- Added special cases: init, leave, staking, Ref Finance, Burrow, Meta Pool
- Added tax category definitions with Canadian treatment
- Documented amount extraction logic (action.deposit vs actions_agg.deposit)
- Added failed transaction filtering rule

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
