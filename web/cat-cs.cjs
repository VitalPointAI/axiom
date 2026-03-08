const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

// Check direction values
const dirs = db.prepare("SELECT DISTINCT direction FROM transactions WHERE exchange = ?").all("coinsquare");
console.log("Directions:", dirs);

// Categorize
console.log("\nCategorizing...");

// CAD deposits (direction = IN)
let r = db.prepare("UPDATE transactions SET tax_category = ? WHERE exchange = ? AND asset = ? AND UPPER(direction) = ?").run("fiat_deposit", "coinsquare", "CAD", "IN");
console.log("CAD deposits:", r.changes);

// CAD withdrawals (direction = OUT)
r = db.prepare("UPDATE transactions SET tax_category = ? WHERE exchange = ? AND asset = ? AND UPPER(direction) = ?").run("fiat_withdrawal", "coinsquare", "CAD", "OUT");
console.log("CAD withdrawals:", r.changes);

// NEAR buys
r = db.prepare("UPDATE transactions SET tax_category = ? WHERE exchange = ? AND asset = ? AND UPPER(direction) = ?").run("buy", "coinsquare", "NEAR", "IN");
console.log("NEAR buys:", r.changes);

// USDC buys
r = db.prepare("UPDATE transactions SET tax_category = ? WHERE exchange = ? AND asset = ? AND UPPER(direction) = ?").run("buy", "coinsquare", "USDC", "IN");
console.log("USDC buys:", r.changes);

// NEAR sells
r = db.prepare("UPDATE transactions SET tax_category = ? WHERE exchange = ? AND asset = ? AND UPPER(direction) = ?").run("sell", "coinsquare", "NEAR", "OUT");
console.log("NEAR sells:", r.changes);

// USDC sells  
r = db.prepare("UPDATE transactions SET tax_category = ? WHERE exchange = ? AND asset = ? AND UPPER(direction) = ?").run("sell", "coinsquare", "USDC", "OUT");
console.log("USDC sells:", r.changes);

// Summary
const summary = db.prepare("SELECT tax_category, COUNT(*) as cnt FROM transactions WHERE exchange = ? GROUP BY tax_category").all("coinsquare");
console.log("\nSummary:", summary);
