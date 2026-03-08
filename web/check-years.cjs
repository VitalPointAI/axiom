const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

// Get all transactions and count by year in JS
const allTxs = db.prepare("SELECT block_timestamp FROM transactions WHERE block_timestamp > 1000000000000000").all();
const yearCounts = {};
for (const tx of allTxs) {
  const year = new Date(Number(tx.block_timestamp) / 1000000).getFullYear();
  yearCounts[year] = (yearCounts[year] || 0) + 1;
}
console.log("Transactions per year:");
Object.keys(yearCounts).sort().forEach(y => console.log("  " + y + ": " + yearCounts[y].toLocaleString()));

// Check for weird timestamps
const weird = db.prepare("SELECT COUNT(*) as cnt FROM transactions WHERE block_timestamp < 1000000000000000").get();
console.log("\nWeird timestamps (< year 2001):", weird.cnt);

// First and last valid transaction dates
const first = db.prepare("SELECT MIN(block_timestamp) as ts FROM transactions WHERE block_timestamp > 1000000000000000").get();
const last = db.prepare("SELECT MAX(block_timestamp) as ts FROM transactions WHERE block_timestamp > 1000000000000000").get();
console.log("\nDate range:");
console.log("  First:", new Date(Number(first.ts) / 1000000).toISOString());
console.log("  Last:", new Date(Number(last.ts) / 1000000).toISOString());

// Price data
const prices = db.prepare("SELECT MIN(date) as oldest, MAX(date) as newest FROM price_cache").get();
console.log("\nPrice data range:", prices.oldest, "to", prices.newest);
