# Phase 1 Discovery: NEAR Indexer Options

## Research Date
2026-02-23

## Question
What's the best approach to get complete NEAR transaction history for 64 accounts?

## Options Evaluated

### Option 1: NearBlocks API (RECOMMENDED)
**Endpoint:** `https://api.nearblocks.io/v1/`

**Pros:**
- Free tier available
- Full transaction history with pagination (cursor-based)
- Includes staking deposit data via `/kitwallet/staking-deposits/{account}`
- Good data structure (tx hash, receipt_id, timestamps, actions, fees)
- No infrastructure to run

**Cons:**
- Rate limits (need to test - appears reasonable)
- No direct staking rewards endpoint (shows net deposits, not individual reward events)

**Test Results:**
- `GET /v1/account/vitalpointai.near/txns?page=1&per_page=5` ✅ Returns transactions
- `GET /v1/kitwallet/staking-deposits/vitalpointai.near` ✅ Returns staking data

### Option 2: NEAR Lake Framework
**Description:** S3-based indexed blockchain data

**Pros:**
- Complete block-level data
- No rate limits (you run your own)
- Can capture staking reward distributions at epoch level

**Cons:**
- Requires running indexer infrastructure
- More complex setup
- Overkill for 64 accounts

### Option 3: Direct RPC (FastNear)
**Pros:**
- Already using for balance checks
- Fast

**Cons:**
- Limited to recent transactions
- No historical data access
- Not suitable for full history

### Option 4: Pikespeak API
**Description:** Another NEAR indexer

**Pros:**
- Alternative to NearBlocks

**Cons:**
- Less documentation
- Unclear pricing/limits
- NearBlocks is more established

## Decision
**Use NearBlocks API with aggressive rate limiting** for transaction history.

### Rate Limit Testing (2026-02-23)
- Free tier hits rate limit after ~6 rapid requests
- vitalpointai.near alone has **23,679 transactions**
- At 25/page = 948 API calls for one account
- **Strategy:** 1-2 second delay between requests, exponential backoff on 429

### Alternative: FastNear
- `archival-rpc.mainnet.fastnear.com` - Full blockchain history
- BUT: No "list transactions" endpoint (RPC is per-tx lookup only)
- Good for: balance checks, individual tx verification
- Not good for: bulk transaction history

### Fallback Options
1. NearBlocks paid API (pricing TBD)
2. NEAR Lake (S3 bucket, requires running own indexer)
3. Pikespeak API (alternative indexer)
4. Hybrid: Koinly NEAR integration first, fill gaps manually

For staking rewards specifically:
- Use NearBlocks for staking deposits/withdrawals
- Calculate rewards as: current_staked - sum(deposits) + sum(withdrawals)
- Or: query validator pool contract for epoch rewards via RPC

## Staking Rewards Strategy
NEAR staking rewards compound automatically via pool shares. To track:
1. Pull all `deposit_and_stake` and `unstake` actions from NearBlocks
2. Query pool contract for current shares and exchange rate
3. Calculate total rewards = (current_value - sum_deposits + sum_withdrawals)

For tax purposes, we may need to estimate reward timing. Options:
- Use epoch boundaries (every 12 hours)
- Attribute rewards proportionally based on deposit periods

## Lockup Contract
Aaron confirmed: vesting COMPLETE as of ~2021.
- Query lockup contract for historical unlock events
- Or pull all transactions from lockup account via NearBlocks
- Focus on capturing the final unlock/transfer, not ongoing tracking

## Rate Limit Strategy
- Add 100ms delay between requests
- Retry with exponential backoff on 429
- Process accounts sequentially initially
- Can parallelize later if needed

## Schema Considerations
```sql
CREATE TABLE transactions (
  id SERIAL PRIMARY KEY,
  tx_hash VARCHAR(64) UNIQUE NOT NULL,
  receipt_id VARCHAR(64),
  account_id VARCHAR(128) NOT NULL,  -- the account we're tracking
  predecessor_id VARCHAR(128),
  receiver_id VARCHAR(128),
  action_type VARCHAR(32),  -- TRANSFER, FUNCTION_CALL, STAKE, etc
  method_name VARCHAR(128), -- for function calls
  amount NUMERIC(40, 0),    -- in yoctoNEAR
  fee NUMERIC(40, 0),
  block_height BIGINT,
  block_timestamp BIGINT,
  success BOOLEAN,
  raw_data JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tx_account ON transactions(account_id);
CREATE INDEX idx_tx_timestamp ON transactions(block_timestamp);
```

## Next Steps
1. Create PostgreSQL schema
2. Build NearBlocks API client with rate limiting
3. Start with vitalpointai.near (largest account)
4. Verify balance reconciliation before expanding to all 64 accounts
