const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const wallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("challenge-coin-nft.credz.near");

console.log("=== challenge-coin-nft.credz.near Full Transaction Flow ===\n");

// Get ALL transactions by action type and direction
const summary = db.prepare(`
  SELECT action_type, direction, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE wallet_id = ?
  GROUP BY action_type, direction
  ORDER BY total DESC
`).all(wallet.id);

console.log("By action_type and direction:");
summary.forEach(s => {
  console.log(`  ${s.direction} ${s.action_type}: ${s.cnt} txs, ${s.total.toFixed(4)} NEAR`);
});

// Check what the OUT transactions actually are
console.log("\n=== All OUT transactions ===\n");
const outTxs = db.prepare(`
  SELECT action_type, method_name, counterparty, CAST(amount AS REAL)/1e24 as amt, tx_hash
  FROM transactions 
  WHERE wallet_id = ? AND direction = 'out'
  ORDER BY CAST(amount AS REAL) DESC
`).all(wallet.id);

outTxs.forEach(t => {
  console.log(`  ${t.amt.toFixed(4)} NEAR - ${t.action_type} ${t.method_name || ''} to ${t.counterparty?.substring(0,30)}`);
});

// The verification says on-chain is 9.55, computed is 86.12
// So we're missing ~76 NEAR in outflows
// Let me check if these DELETE_ACCOUNT transfers should be counted as outflows

console.log("\n=== Checking system transfers to credz.near ===\n");
const credzWallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("credz.near");
const systemToCredz = db.prepare(`
  SELECT tx_hash, CAST(amount AS REAL)/1e24 as amt
  FROM transactions 
  WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in'
  ORDER BY amt DESC
  LIMIT 20
`).all(credzWallet.id);

let totalSystemToCredz = 0;
systemToCredz.forEach(t => {
  totalSystemToCredz += t.amt;
  console.log(`  ${t.amt.toFixed(4)} NEAR (tx: ${t.tx_hash.substring(0,15)}...)`);
});
console.log(`  Total: ${totalSystemToCredz.toFixed(4)} NEAR`);

// Now the key question: are these DELETE_ACCOUNT refunds from accounts that were funded by challenge-coin-nft?
// If so, they're not outflows FROM challenge-coin-nft, they're refunds TO credz.near

db.close();
