-- Create staking_epoch_rewards table for per-epoch reward tracking
-- This tracks calculated rewards for each wallet/validator/epoch combination

CREATE TABLE IF NOT EXISTS staking_epoch_rewards (
    id SERIAL PRIMARY KEY,
    wallet_id INTEGER NOT NULL REFERENCES wallets(id),
    validator_id VARCHAR(100) NOT NULL,
    epoch_id INTEGER NOT NULL,
    epoch_timestamp BIGINT,           -- nanoseconds since epoch
    epoch_date DATE,                  -- derived date for easy querying
    
    -- Balance tracking
    balance_before NUMERIC(38, 0),    -- yoctoNEAR at previous epoch end
    balance_after NUMERIC(38, 0),     -- yoctoNEAR at this epoch end
    
    -- Movement tracking (from staking_events)
    deposits NUMERIC(38, 0) DEFAULT 0,      -- stake/deposit_and_stake in this epoch
    withdrawals NUMERIC(38, 0) DEFAULT 0,   -- unstake/withdraw in this epoch
    
    -- Calculated reward
    reward_yocto NUMERIC(38, 0),            -- reward in yoctoNEAR
    reward_near NUMERIC(30, 10),            -- reward in NEAR
    
    -- Price data
    near_price_usd NUMERIC(20, 8),
    near_price_cad NUMERIC(20, 8),
    
    -- Value in fiat
    reward_usd NUMERIC(20, 8),
    reward_cad NUMERIC(20, 8),
    
    -- Metadata
    calculation_method VARCHAR(20) DEFAULT 'snapshot', -- 'snapshot' or 'estimated'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(wallet_id, validator_id, epoch_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_epoch_rewards_wallet ON staking_epoch_rewards(wallet_id);
CREATE INDEX IF NOT EXISTS idx_epoch_rewards_validator ON staking_epoch_rewards(validator_id);
CREATE INDEX IF NOT EXISTS idx_epoch_rewards_epoch ON staking_epoch_rewards(epoch_id);
CREATE INDEX IF NOT EXISTS idx_epoch_rewards_date ON staking_epoch_rewards(epoch_date);
CREATE INDEX IF NOT EXISTS idx_epoch_rewards_wallet_date ON staking_epoch_rewards(wallet_id, epoch_date);

-- Comment on purpose
COMMENT ON TABLE staking_epoch_rewards IS 'Per-epoch staking rewards calculated from balance snapshots';
COMMENT ON COLUMN staking_epoch_rewards.calculation_method IS 'snapshot = calculated from actual snapshots, estimated = calculated from proportional validator rewards';
