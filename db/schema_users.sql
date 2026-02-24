-- User accounts for multi-user support
-- Links NEAR wallet to user data

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    near_account_id TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_near_account_id ON users(near_account_id);

-- Add user_id to wallets table for multi-user isolation
-- Run as migration:
-- ALTER TABLE wallets ADD COLUMN user_id INTEGER REFERENCES users(id);
-- CREATE INDEX idx_wallets_user_id ON wallets(user_id);
