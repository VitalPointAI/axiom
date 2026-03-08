const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

// Check last sync times per wallet
console.log("=== Last Sync Per Wallet ===");
const lastSyncs = db.prepare(`
  SELECT 
    w.account_id,
    w.chain,
    w.sync_status,
    w.last_synced_at
  FROM wallets w
  WHERE w.user_id = 1
  ORDER BY w.last_synced_at DESC NULLS LAST
  LIMIT 15
`).all();
lastSyncs.forEach(s => console.log(s.chain, s.account_id?.substring(0,35), s.sync_status, s.last_synced_at));

// Check portfolio calculation
console.log("\n=== Portfolio Query Test ===");
const portfolioQuery = db.prepare(`
  SELECT 
    chain,
    COUNT(*) as wallets,
    SUM(CASE WHEN chain = exchange THEN 1 ELSE 0 END) as exchange_wallets
  FROM wallets 
  WHERE user_id = 1 
  GROUP BY chain
`).all();
console.log(portfolioQuery);

// Check if there are EVM transactions at all
console.log("\n=== EVM Transactions ===");
const evmTxs = db.prepare(`
  SELECT chain, COUNT(*) as cnt 
  FROM transactions t
  JOIN wallets w ON t.wallet_id = w.id
  WHERE w.chain IN (ethereum, polygon, cronos)
  GROUP BY w.chain
`).all();
console.log(evmTxs.length === 0 ? "No EVM transactions" : evmTxs);
