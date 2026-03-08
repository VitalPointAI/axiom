const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// For challenge-coin-nft.credz.near, check the DELETE_ACCOUNT pattern
const wallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("challenge-coin-nft.credz.near");

console.log("=== challenge-coin-nft.credz.near DELETE_ACCOUNT Analysis ===\n");

// Get all DELETE_ACCOUNT transactions
const deleteAccts = db.prepare(`
  SELECT tx_hash, direction, counterparty, CAST(amount AS REAL)/1e24 as amt, raw_json
  FROM transactions 
  WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT'
  ORDER BY id
`).all(wallet.id);

console.log(`Found ${deleteAccts.length} DELETE_ACCOUNT transactions:\n`);

// For each DELETE_ACCOUNT, we need to find the system transfer that shows the beneficiary
for (const da of deleteAccts) {
  console.log(`TX: ${da.tx_hash.substring(0, 15)}...`);
  console.log(`  Direction: ${da.direction}, Counterparty: ${da.counterparty}, Amount: ${da.amt}`);
  
  // Check if there's a matching system transfer
  const systemTransfer = db.prepare(`
    SELECT wallet_id, direction, CAST(amount AS REAL)/1e24 as amt,
      (SELECT account_id FROM wallets WHERE id = transactions.wallet_id) as wallet_account
    FROM transactions 
    WHERE tx_hash = ? AND counterparty = 'system'
  `).all(da.tx_hash);
  
  if (systemTransfer.length > 0) {
    console.log(`  System transfers with same tx_hash:`);
    systemTransfer.forEach(st => {
      console.log(`    ${st.wallet_account}: ${st.direction} ${st.amt.toFixed(4)} NEAR`);
    });
  } else {
    console.log(`  No system transfers found with same tx_hash`);
  }
  console.log();
}

// Also check CREATE_ACCOUNT pattern - how much was sent out?
console.log("\n=== CREATE_ACCOUNT Outflows ===\n");
const createAccts = db.prepare(`
  SELECT direction, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT'
  GROUP BY direction
`).all(wallet.id);

createAccts.forEach(ca => {
  console.log(`  ${ca.direction}: ${ca.cnt} txs, ${ca.total.toFixed(4)} NEAR`);
});

// Let's also see what the IN transactions are
console.log("\n=== Large IN Transactions (top 10) ===\n");
const largeIn = db.prepare(`
  SELECT tx_hash, action_type, method_name, counterparty, CAST(amount AS REAL)/1e24 as amt
  FROM transactions 
  WHERE wallet_id = ? AND direction = 'in'
  ORDER BY CAST(amount AS REAL) DESC
  LIMIT 10
`).all(wallet.id);

largeIn.forEach(t => {
  console.log(`  ${t.amt.toFixed(4)} NEAR - ${t.action_type} ${t.method_name || ''} from ${t.counterparty}`);
});

db.close();
