const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Look for any accounts that might be sub-accounts of the NFT contract
const subAccounts = db.prepare("SELECT account_id FROM wallets WHERE account_id LIKE '%challenge-coin%'").all();
console.log("Accounts containing 'challenge-coin':");
subAccounts.forEach(s => console.log("  " + s.account_id));

// Also check the DELETE_ACCOUNT transactions more closely
const nftWallet = db.prepare("SELECT id FROM wallets WHERE account_id = 'challenge-coin-nft.credz.near'").get();
const deletes = db.prepare(`
  SELECT tx_hash, counterparty, raw_json 
  FROM transactions 
  WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT'
  LIMIT 3
`).all(nftWallet.id);

console.log("\nSample DELETE_ACCOUNT raw_json:");
deletes.forEach(d => {
  console.log(`\nTX: ${d.tx_hash.substring(0, 20)}...`);
  console.log(`Counterparty: ${d.counterparty}`);
  if (d.raw_json) {
    // Show first 500 chars of raw_json
    console.log(`Raw (first 500 chars): ${d.raw_json.substring(0, 500)}`);
  }
});

// Check if there are transactions in other wallets that might show the sub-account creation
const gameWallet = db.prepare("SELECT id FROM wallets WHERE account_id = 'challenge-coin-game.credz.near'").get();
if (gameWallet) {
  console.log("\n\nchallenge-coin-game.credz.near transactions:");
  const gameTxs = db.prepare(`
    SELECT action_type, direction, counterparty, CAST(amount AS REAL)/1e24 as amt
    FROM transactions WHERE wallet_id = ?
    ORDER BY id LIMIT 10
  `).all(gameWallet.id);
  gameTxs.forEach(t => console.log(`  ${t.direction} ${t.amt.toFixed(4)} ${t.action_type} ${t.counterparty || ''}`));
}

db.close();
