-- Exchange API Credentials Table
-- Stores encrypted API keys for exchange connections

CREATE TABLE IF NOT EXISTS exchange_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    exchange TEXT NOT NULL,  -- 'coinbase', 'cryptocom', 'kraken'
    api_key TEXT NOT NULL,
    api_secret TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_sync_at TIMESTAMP,
    sync_status TEXT DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, exchange)
);

-- Index for quick lookup
CREATE INDEX IF NOT EXISTS idx_exchange_credentials_user 
ON exchange_credentials(user_id);
