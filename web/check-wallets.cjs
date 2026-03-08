const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

console.log("=== Import Wallets ===");
const importWallets = db.prepare("SELECT id, account_id, chain, label FROM wallets WHERE user_id = 1 AND account_id LIKE ?").all("import:%");
console.log(importWallets);

console.log("\n=== All Wallet Chains ===");
const chains = db.prepare("SELECT chain, COUNT(*) as cnt FROM wallets WHERE user_id = 1 GROUP BY chain").all();
console.log(chains);

console.log("\n=== Transaction sources ===");
const sources = db.prepare("SELECT DISTINCT source, exchange FROM transactions WHERE source IS NOT NULL OR exchange IS NOT NULL LIMIT 20").all();
console.log(sources);

console.log("\n=== Wallet verification query filter ===");
// Check what the verify route filters on
const verifyWallets = db.prepare("SELECT chain, COUNT(*) as cnt FROM wallets WHERE user_id = 1 AND chain NOT LIKE ? GROUP BY chain").all("import:%");
console.log(verifyWallets);
