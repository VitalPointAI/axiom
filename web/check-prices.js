const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Check if we have prices in price_cache
const prices = db.prepare("SELECT COUNT(*) as cnt, MIN(date) as earliest, MAX(date) as latest FROM price_cache WHERE coin_id = ?").get("NEAR");
console.log("NEAR prices in cache:", prices);

// Sample some prices
const samples = db.prepare("SELECT date, price FROM price_cache WHERE coin_id = ? ORDER BY date DESC LIMIT 5").all("NEAR");
console.log("Sample prices:", samples);
