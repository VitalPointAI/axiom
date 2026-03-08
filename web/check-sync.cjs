const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

// Check last sync times per wallet
console.log("=== Last Sync Per Wallet ===");
const lastSyncs = db.prepare(`
  SELECT 
    w.account_id,
    w.chain,
    w.last_synced,
    COUNT(t.id) as tx_count
  FROM wallets w
  LEFT JOIN transactions t ON t.wallet_id = w.id
  WHERE w.user_id = 1
  GROUP BY w.id
  ORDER BY w.last_synced DESC
  LIMIT 15
`).all();
lastSyncs.forEach(s => console.log(s.chain, s.account_id?.substring(0,30), s.last_synced, "txs:", s.tx_count));

// Check cron/sync status
console.log("\n=== ETH Wallets ===");
const evmWallets = db.prepare("SELECT * FROM wallets WHERE chain != NEAR AND chain != exchange AND user_id = 1").all();
console.log(evmWallets);

// Exchange import details
console.log("\n=== Exchange Import Transactions ===");
const exchangeTxSample = db.prepare(`
  SELECT token_symbol, direction, amount, tax_category 
  FROM transactions 
  WHERE exchange = coinsquare
  LIMIT 5
`).all();
console.log(exchangeTxSample);
