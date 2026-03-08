const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

// Check early transactions
const early = db.prepare(`
  SELECT id, block_timestamp, tx_hash, counterparty, amount, asset, source, exchange 
  FROM transactions 
  WHERE block_timestamp > 1000000000000000 
  ORDER BY block_timestamp 
  LIMIT 20
`).all();

console.log("Earliest transactions:");
early.forEach(t => {
  const date = new Date(Number(t.block_timestamp) / 1000000).toISOString().split("T")[0];
  const amt = (Number(t.amount) / 1e24).toFixed(4);
  console.log(date, t.asset || "NEAR", amt, t.source || "chain", t.exchange || "", t.counterparty?.substring(0,30) || "");
});

// Check what dates are missing prices
const missing = db.prepare(`
  SELECT DISTINCT date(block_timestamp/1000000000, "unixepoch") as d
  FROM transactions 
  WHERE block_timestamp > 1000000000000000
  AND (cost_basis_usd IS NULL OR cost_basis_usd = 0)
  ORDER BY d
  LIMIT 50
`).all();
console.log("\nDates missing prices:", missing.map(m => m.d).join(", "));
