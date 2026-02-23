-- NearTax Database Schema
-- SQLite-compatible (PostgreSQL migration path available)

-- Wallets we're tracking
CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT UNIQUE NOT NULL,
    label TEXT,
    is_owned BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Transaction history
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_hash TEXT UNIQUE NOT NULL,
    receipt_id TEXT,
    wallet_id INTEGER REFERENCES wallets(id),
    direction TEXT CHECK(direction IN ('in', 'out')),
    counterparty TEXT,
    action_type TEXT,
    method_name TEXT,
    amount TEXT,  -- Store as string to avoid precision loss (yoctoNEAR)
    fee TEXT,
    block_height INTEGER,
    block_timestamp INTEGER,
    success BOOLEAN,
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexing progress for resumability
CREATE TABLE IF NOT EXISTS indexing_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER UNIQUE REFERENCES wallets(id),
    last_cursor TEXT,
    total_fetched INTEGER DEFAULT 0,
    total_expected INTEGER,
    status TEXT CHECK(status IN ('pending', 'in_progress', 'complete', 'error')),
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Staking events
CREATE TABLE IF NOT EXISTS staking_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER REFERENCES wallets(id),
    validator_id TEXT NOT NULL,
    event_type TEXT CHECK(event_type IN ('deposit', 'withdraw', 'reward')),
    amount TEXT,
    block_timestamp INTEGER,
    tx_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tx_wallet ON transactions(wallet_id);
CREATE INDEX IF NOT EXISTS idx_tx_timestamp ON transactions(block_timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions(tx_hash);
CREATE INDEX IF NOT EXISTS idx_progress_wallet ON indexing_progress(wallet_id);
CREATE INDEX IF NOT EXISTS idx_progress_status ON indexing_progress(status);
CREATE INDEX IF NOT EXISTS idx_staking_wallet ON staking_events(wallet_id);
