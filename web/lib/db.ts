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
    
    // Initialize users table if it doesn't exist
    db.exec(`
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        near_account_id TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP
      );
      
      CREATE INDEX IF NOT EXISTS idx_users_near_account_id ON users(near_account_id);
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
