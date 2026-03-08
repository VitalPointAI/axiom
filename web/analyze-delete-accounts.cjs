const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// For each mismatched wallet, check DELETE_ACCOUNT pattern
const wallets = [
  "challenge-coin-nft.credz.near",
  "challenge-coin-game.credz.near", 
  "funding-registry.credz.near"
];

const allWalletIds = db.prepare("SELECT id FROM wallets WHERE chain = 'NEAR'").all().map(w => w.id);

for (const account of wallets) {
  const wallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get(account);
  if (!wallet) continue;

  console.log(`\n=== ${account} ===`);
  
  // Get DELETE_ACCOUNT transactions
  const deletes = db.prepare(`
    SELECT tx_hash, direction, counterparty, CAST(amount AS REAL)/1e24 as amt
    FROM transactions 
    WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT'
    LIMIT 5
  `).all(wallet.id);
  
  console.log(`DELETE_ACCOUNT txs: ${deletes.length}`);
  deletes.forEach(d => console.log(`  ${d.direction} amt:${d.amt} counterparty:${d.counterparty}`));
  
  // Find system transfers with matching tx_hash
  if (deletes.length > 0) {
    const txHashes = deletes.map(d => d.tx_hash);
    const placeholders = txHashes.map(() => '?').join(',');
    
    const systemTransfers = db.prepare(`
      SELECT t.tx_hash, t.wallet_id, t.direction, CAST(t.amount AS REAL)/1e24 as amt,
             w.account_id as wallet_account
      FROM transactions t
      JOIN wallets w ON w.id = t.wallet_id
      WHERE t.tx_hash IN (${placeholders})
        AND t.counterparty = 'system'
    `).all(...txHashes);
    
    console.log(`\nMatching system transfers:`);
    systemTransfers.forEach(s => {
      console.log(`  ${s.wallet_account}: ${s.direction} ${s.amt.toFixed(4)} NEAR`);
    });
    
    // Calculate total that should be outflow from this wallet
    const outflows = systemTransfers.filter(s => s.wallet_id !== wallet.id);
    const totalOutflow = outflows.reduce((sum, s) => sum + s.amt, 0);
    console.log(`\nTotal DELETE_ACCOUNT outflow: ${totalOutflow.toFixed(4)} NEAR`);
  }
}

db.close();
