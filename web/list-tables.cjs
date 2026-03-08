const Database = require("better-sqlite3");
const db = new Database("../neartax.db");
const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all();
console.log("Tables:", tables.map(t => t.name));

// Check wallets table schema
const cols = db.prepare("PRAGMA table_info(wallets)").all();
console.log("Wallet columns:", cols.map(c => c.name));

// Check if there's a balance column or related table
for (const t of tables) {
  if (t.name.includes('balance') || t.name.includes('rpc')) {
    console.log(`\n${t.name} columns:`);
    const tcols = db.prepare(`PRAGMA table_info(${t.name})`).all();
    console.log(tcols.map(c => c.name));
  }
}

db.close();
