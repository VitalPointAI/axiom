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
    
    // Initialize tables if they don't exist (compatible with Python indexer schema)
    db.exec(`
      -- Users table (web app specific)
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        near_account_id TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP
      );
      
      CREATE INDEX IF NOT EXISTS idx_users_near_account_id ON users(near_account_id);

      -- Wallets table (compatible with Python indexer)
      CREATE TABLE IF NOT EXISTS wallets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT UNIQUE NOT NULL,
        label TEXT,
        chain TEXT DEFAULT 'NEAR',
        user_id INTEGER REFERENCES users(id),
        is_owned BOOLEAN DEFAULT 1,
        sync_status TEXT DEFAULT 'pending',
        last_synced_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );

      CREATE INDEX IF NOT EXISTS idx_wallets_user ON wallets(user_id);

      -- Transaction history (from Python indexer)
      CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tx_hash TEXT UNIQUE NOT NULL,
        receipt_id TEXT,
        wallet_id INTEGER REFERENCES wallets(id),
        direction TEXT CHECK(direction IN ('in', 'out')),
        counterparty TEXT,
        action_type TEXT,
        method_name TEXT,
        amount TEXT,
        fee TEXT,
        block_height INTEGER,
        block_timestamp INTEGER,
        success BOOLEAN,
        raw_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );

      CREATE INDEX IF NOT EXISTS idx_tx_wallet ON transactions(wallet_id);
      CREATE INDEX IF NOT EXISTS idx_tx_timestamp ON transactions(block_timestamp);

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

      CREATE INDEX IF NOT EXISTS idx_staking_wallet ON staking_events(wallet_id);
    `);

    // Add missing columns if they don't exist (for web app compatibility)
    try {
      db.exec(`ALTER TABLE wallets ADD COLUMN chain TEXT DEFAULT 'NEAR'`);
    } catch (e) { /* column already exists */ }
    
    try {
      db.exec(`ALTER TABLE wallets ADD COLUMN user_id INTEGER REFERENCES users(id)`);
    } catch (e) { /* column already exists */ }

    try {
      db.exec(`ALTER TABLE wallets ADD COLUMN sync_status TEXT DEFAULT 'pending'`);
    } catch (e) { /* column already exists */ }

    try {
      db.exec(`ALTER TABLE wallets ADD COLUMN last_synced_at TIMESTAMP`);
    } catch (e) { /* column already exists */ }
  }
  
  return db;
}

export function closeDb() {
  if (db) {
    db.close();
    db = null;
  }
}
