const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_DECIMALS = 1e24;

// Get credz wallets 
const wallets = db.prepare("SELECT * FROM wallets WHERE account_id LIKE ?").all("%credz%");

console.log("CREDZ WALLET TRANSACTION ANALYSIS:\n");
for (const w of wallets) {
  // Get sample transactions
  const txs = db.prepare(`
    SELECT direction, action_type, amount, fee, counterparty
    FROM transactions WHERE wallet_id = ?
    ORDER BY block_timestamp DESC
    LIMIT 5
  `).all(w.id);
  
  // Calculate totals
  const stats = db.prepare(`
    SELECT 
      SUM(CASE WHEN LOWER(direction)='in' THEN CAST(amount AS REAL) ELSE 0 END) / ${NEAR_DECIMALS} as total_in,
      SUM(CASE WHEN LOWER(direction)='out' THEN CAST(amount AS REAL) ELSE 0 END) / ${NEAR_DECIMALS} as total_out,
      SUM(CASE WHEN LOWER(direction)='out' THEN CAST(fee AS REAL) ELSE 0 END) / ${NEAR_DECIMALS} as total_fees,
      COUNT(*) as tx_count
    FROM transactions WHERE wallet_id = ?
  `).get(w.id);
  
  if (stats && stats.tx_count > 0) {
    const computed = (stats.total_in || 0) - (stats.total_out || 0) - (stats.total_fees || 0);
    console.log(`${w.account_id}:`);
    console.log(`  IN: ${(stats.total_in || 0).toFixed(4)} NEAR`);
    console.log(`  OUT: ${(stats.total_out || 0).toFixed(4)} NEAR`);
    console.log(`  FEES: ${(stats.total_fees || 0).toFixed(4)} NEAR`);
    console.log(`  Computed Balance: ${computed.toFixed(4)} NEAR`);
    console.log(`  TX Count: ${stats.tx_count}`);
    
    // Show sample txs
    if (txs.length > 0 && (stats.total_in > 0 || stats.total_out > 0)) {
      console.log(`  Sample TXs:`);
      txs.slice(0, 3).forEach(tx => {
        const amt = Number(tx.amount) / NEAR_DECIMALS;
        console.log(`    ${tx.direction} ${tx.action_type}: ${amt.toFixed(4)} NEAR to/from ${tx.counterparty || 'N/A'}`);
      });
    }
    console.log();
  }
}

// Get total portfolio value from all wallets
console.log("\n=== TOTAL PORTFOLIO ANALYSIS ===\n");
const allStats = db.prepare(`
  SELECT 
    SUM(CASE WHEN LOWER(direction)='in' THEN CAST(amount AS REAL) ELSE 0 END) / ${NEAR_DECIMALS} as total_in,
    SUM(CASE WHEN LOWER(direction)='out' THEN CAST(amount AS REAL) ELSE 0 END) / ${NEAR_DECIMALS} as total_out,
    SUM(CASE WHEN LOWER(direction)='out' THEN CAST(fee AS REAL) ELSE 0 END) / ${NEAR_DECIMALS} as total_fees,
    COUNT(*) as tx_count
  FROM transactions
`).get();

console.log("All wallets combined:");
console.log(`  Total IN: ${allStats.total_in.toFixed(2)} NEAR`);
console.log(`  Total OUT: ${allStats.total_out.toFixed(2)} NEAR`);
console.log(`  Total FEES: ${allStats.total_fees.toFixed(4)} NEAR`);
console.log(`  Computed: ${(allStats.total_in - allStats.total_out - allStats.total_fees).toFixed(2)} NEAR`);
