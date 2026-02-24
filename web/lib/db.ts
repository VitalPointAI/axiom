import Database from 'better-sqlite3';
import path from 'path';

let db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (!db) {
    // Use the main neartax database
    const dbPath = path.join(process.cwd(), '..', 'neartax.db');
    db = new Database(dbPath);
    
    // Enable WAL mode for better concurrency
    db.pragma('journal_mode = WAL');
    
    // Initialize tables if they don't exist
    db.exec(`
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        near_account_id TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP
      );
      
      CREATE INDEX IF NOT EXISTS idx_users_near_account_id ON users(near_account_id);

      CREATE TABLE IF NOT EXISTS wallets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        address TEXT NOT NULL,
        chain TEXT NOT NULL,
        label TEXT,
        sync_status TEXT DEFAULT 'pending',
        last_synced_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, address, chain)
      );
      
      CREATE INDEX IF NOT EXISTS idx_wallets_user_id ON wallets(user_id);
      CREATE INDEX IF NOT EXISTS idx_wallets_address ON wallets(address);

      CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wallet_id INTEGER NOT NULL REFERENCES wallets(id),
        tx_hash TEXT NOT NULL,
        timestamp TIMESTAMP NOT NULL,
        tx_type TEXT,
        from_address TEXT,
        to_address TEXT,
        asset TEXT,
        amount REAL,
        fee REAL,
        fee_asset TEXT,
        classification TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(wallet_id, tx_hash)
      );

      CREATE INDEX IF NOT EXISTS idx_transactions_wallet_id ON transactions(wallet_id);
      CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp);

      CREATE TABLE IF NOT EXISTS staking_rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wallet_id INTEGER NOT NULL REFERENCES wallets(id),
        validator_id TEXT NOT NULL,
        epoch INTEGER,
        staked_amount REAL,
        reward_amount REAL,
        timestamp TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );

      CREATE INDEX IF NOT EXISTS idx_staking_wallet_id ON staking_rewards(wallet_id);
    `);
  }
  
  return db;
}

export function closeDb() {
  if (db) {
    db.close();
    db = null;
  }
}
