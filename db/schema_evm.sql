-- EVM Chain Transactions Schema
-- Extends base schema for Ethereum, Polygon, Optimism

-- EVM wallets
CREATE TABLE IF NOT EXISTS evm_wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL,  -- 0x... format
    chain TEXT NOT NULL,  -- ethereum, polygon, optimism
    label TEXT,
    is_owned BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(address, chain)
);

-- EVM transactions
CREATE TABLE IF NOT EXISTS evm_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_hash TEXT NOT NULL,
    wallet_id INTEGER REFERENCES evm_wallets(id),
    chain TEXT NOT NULL,
    block_number INTEGER,
    block_timestamp INTEGER,
    from_address TEXT,
    to_address TEXT,
    value TEXT,  -- in wei
    gas_used TEXT,
    gas_price TEXT,
    tx_type TEXT,  -- normal, internal, erc20, erc721
    token_symbol TEXT,  -- for token transfers
    token_decimal INTEGER,
    token_value TEXT,
    success BOOLEAN,
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tx_hash, chain, tx_type)
);

-- Exchange transactions (from CSV imports)
CREATE TABLE IF NOT EXISTS exchange_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL,  -- coinbase, crypto_com, wealthsimple, etc
    tx_id TEXT,  -- exchange's internal ID
    tx_date TIMESTAMP NOT NULL,
    tx_type TEXT,  -- buy, sell, send, receive, staking_reward, etc
    asset TEXT NOT NULL,  -- BTC, ETH, NEAR, etc
    quantity TEXT NOT NULL,
    price_per_unit TEXT,
    total_value TEXT,
    fee TEXT,
    fee_asset TEXT,
    currency TEXT,  -- CAD, USD
    notes TEXT,
    raw_data TEXT,
    import_batch TEXT,  -- to track which import
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexing progress for EVM
CREATE TABLE IF NOT EXISTS evm_indexing_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER UNIQUE REFERENCES evm_wallets(id),
    chain TEXT NOT NULL,
    last_block INTEGER,
    total_fetched INTEGER DEFAULT 0,
    status TEXT CHECK(status IN ('pending', 'in_progress', 'complete', 'error')),
    error_message TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evm_tx_wallet ON evm_transactions(wallet_id);
CREATE INDEX IF NOT EXISTS idx_evm_tx_chain ON evm_transactions(chain);
CREATE INDEX IF NOT EXISTS idx_evm_tx_timestamp ON evm_transactions(block_timestamp);
CREATE INDEX IF NOT EXISTS idx_exchange_tx_date ON exchange_transactions(tx_date);
CREATE INDEX IF NOT EXISTS idx_exchange_tx_asset ON exchange_transactions(asset);
