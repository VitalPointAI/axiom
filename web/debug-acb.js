const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Check schema
const schema = db.prepare("SELECT sql FROM sqlite_master WHERE type = ? AND name = ?").get("table", "tax_lots");
console.log("tax_lots schema:", schema?.sql);

// Check sample data  
const lots = db.prepare("SELECT * FROM tax_lots LIMIT 5").all();
console.log("Sample lots:", JSON.stringify(lots, null, 2));

// Check disposal table structure
const dispSchema = db.prepare("SELECT sql FROM sqlite_master WHERE type = ? AND name = ?").get("table", "calculated_disposals");
console.log("calculated_disposals schema:", dispSchema?.sql);

// Check if there are any lots with cost basis
const lotsWithCost = db.prepare("SELECT COUNT(*) as cnt, SUM(cost_basis_cad) as total FROM tax_lots WHERE cost_basis_cad > 0").get();
console.log("Lots with cost basis:", lotsWithCost);
