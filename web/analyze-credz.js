const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Check all tables
const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all();
console.log("TABLES:", tables.map(t => t.name).join(", "));

// Get credz wallets 
const wallets = db.prepare("SELECT * FROM wallets WHERE account_id LIKE ?").all("%credz%");
console.log("\nCREDZ WALLETS:");
wallets.forEach(w => console.log(`  ${w.id}: ${w.account_id}`));

// Check balance tables
const balanceSchema = db.prepare("PRAGMA table_info(wallet_balances)").all();
if (balanceSchema.length > 0) {
  console.log("\nWALLET_BALANCES SCHEMA:");
  balanceSchema.forEach(col => console.log(`  ${col.name}: ${col.type}`));
}

// Check if there's a cached balance
const cacheTables = tables.filter(t => t.name.includes('balance') || t.name.includes('cache'));
console.log("\nBALANCE-RELATED TABLES:", cacheTables.map(t => t.name).join(", "));

// Get transaction totals for credz wallets
console.log("\nCREDZ WALLET TRANSACTION ANALYSIS:");
for (const w of wallets) {
  const txStats = db.prepare(`
    SELECT 
      SUM(CASE WHEN direction='IN' THEN amount ELSE 0 END) as total_in,
      SUM(CASE WHEN direction='OUT' THEN amount ELSE 0 END) as total_out,
      SUM(CASE WHEN direction='OUT' THEN fee ELSE 0 END) as total_fees,
      COUNT(*) as tx_count
    FROM transactions WHERE wallet_id = ?
  `).get(w.id);
  
  if (txStats && txStats.tx_count > 0) {
    const computed = (txStats.total_in || 0) - (txStats.total_out || 0) - (txStats.total_fees || 0);
    console.log(`  ${w.account_id}:`);
    console.log(`    IN: ${(txStats.total_in || 0).toFixed(2)}, OUT: ${(txStats.total_out || 0).toFixed(2)}, FEES: ${(txStats.total_fees || 0).toFixed(4)}`);
    console.log(`    Computed: ${computed.toFixed(2)}, TXs: ${txStats.tx_count}`);
  }
}
