const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Check what wallets were affected by the deletion
// We can't check deleted rows, but we can look at transaction counts per wallet

console.log("=== Investigating Transaction Counts ===\n");

// Get wallets with the biggest discrepancies
const bigIssues = [
  "challenge-coin-nft.credz.near",
  "challenge-coin-game.credz.near", 
  "funding-registry.credz.near",
  "credz-operations.near",
  "relayer.vitalpointai.near"
];

for (const acct of bigIssues) {
  const wallet = db.prepare("SELECT id, account_id FROM wallets WHERE account_id = ?").get(acct);
  if (!wallet) continue;
  
  console.log(`\n${acct}:`);
  
  // Get counts by direction
  const byDirection = db.prepare(`
    SELECT direction, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
    FROM transactions WHERE wallet_id = ?
    GROUP BY direction
  `).all(wallet.id);
  
  byDirection.forEach(d => {
    console.log(`  ${d.direction}: ${d.cnt} txs, ${d.total?.toFixed(4)} NEAR`);
  });
  
  // Check for DELETE_ACCOUNT related outflows
  const deleteAccounts = db.prepare(`
    SELECT COUNT(*) as cnt FROM transactions 
    WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT'
  `).get(wallet.id);
  
  console.log(`  DELETE_ACCOUNT txs: ${deleteAccounts.cnt}`);
  
  // Check raw_json patterns - look for any remaining suspicious patterns
  const suspiciousPatterns = db.prepare(`
    SELECT COUNT(*) as cnt FROM transactions 
    WHERE wallet_id = ? AND raw_json IS NOT NULL
  `).get(wallet.id);
  
  console.log(`  Has raw_json: ${suspiciousPatterns.cnt}`);
}

// Also check total transaction count now vs what we expect
const totalTxs = db.prepare("SELECT COUNT(*) as cnt FROM transactions").get();
console.log(`\n\nTotal transactions in DB: ${totalTxs.cnt}`);

// Check if there are any wallets with 0 transactions
const emptyWallets = db.prepare(`
  SELECT w.account_id, 
    (SELECT COUNT(*) FROM transactions t WHERE t.wallet_id = w.id) as tx_count
  FROM wallets w 
  WHERE w.chain = 'NEAR'
  ORDER BY tx_count ASC
  LIMIT 10
`).all();

console.log("\nWallets with fewest transactions:");
emptyWallets.forEach(w => console.log(`  ${w.account_id}: ${w.tx_count} txs`));

db.close();
