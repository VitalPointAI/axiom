const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

// Check import transactions
const importTxs = db.prepare("SELECT COUNT(*) as cnt, exchange FROM transactions WHERE exchange IS NOT NULL GROUP BY exchange").all();
console.log("Exchange transactions:", importTxs);

// Latest NEAR tx timestamp
const latestNear = db.prepare("SELECT MAX(block_timestamp) as latest FROM transactions WHERE wallet_id IN (SELECT id FROM wallets WHERE chain = ?)", ).get("NEAR");
const latestDate = latestNear?.latest ? new Date(latestNear.latest / 1000000).toISOString() : "none";
console.log("\nLatest NEAR tx:", latestDate);

// Latest ETH tx
const latestEth = db.prepare("SELECT MAX(block_timestamp) as latest FROM transactions WHERE wallet_id IN (SELECT id FROM wallets WHERE chain = ?)").get("ethereum");
const latestEthDate = latestEth?.latest ? new Date(latestEth.latest / 1000000).toISOString() : "none";
console.log("Latest ETH tx:", latestEthDate);

// Wallets with transactions
const portfolioWallets = db.prepare("SELECT w.id, w.account_id, w.chain, COUNT(t.id) as tx_count FROM wallets w LEFT JOIN transactions t ON t.wallet_id = w.id WHERE w.user_id = 1 GROUP BY w.id HAVING tx_count > 0 ORDER BY tx_count DESC LIMIT 10").all();
console.log("\nTop wallets by tx count:", portfolioWallets.map(w => ({id: w.id, chain: w.chain, account: w.account_id.substring(0,30), txs: w.tx_count})));

// Holdings from import
const importHoldings = db.prepare(`
  SELECT 
    t.token_symbol,
    SUM(CASE WHEN direction = in THEN CAST(amount AS REAL) ELSE -CAST(amount AS REAL) END) as balance
  FROM transactions t
  WHERE t.exchange IS NOT NULL
  GROUP BY t.token_symbol
  HAVING balance > 0.001
`).all();
console.log("\nImport holdings:", importHoldings);
