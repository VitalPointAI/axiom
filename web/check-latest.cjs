const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

// Check latest transactions for main wallet
const latest = db.prepare("SELECT block_timestamp, asset, direction, action_type FROM transactions WHERE wallet_id = 62 ORDER BY block_timestamp DESC LIMIT 5").all();
console.log("Latest vitalpointai.near txs:", latest.map(t => ({
  date: new Date(Number(t.block_timestamp) / 1000000).toISOString(),
  asset: t.asset,
  dir: t.direction,
  action: t.action_type
})));

// Exchange wallet details
const exWallet = db.prepare("SELECT * FROM wallets WHERE chain = ?").all("exchange");
console.log("\nExchange wallets:", exWallet);

// Count exchange transactions
const exTxs = db.prepare("SELECT COUNT(*) as cnt FROM transactions WHERE wallet_id = ?").get(76);
console.log("\nExchange tx count:", exTxs);

// Sample exchange transactions
const exSample = db.prepare("SELECT asset, direction, amount, tax_category FROM transactions WHERE wallet_id = ? LIMIT 5").all(76);
console.log("\nExchange tx sample:", exSample);
