const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

// Get all Coinsquare transactions to understand patterns
const txs = db.prepare(`
  SELECT id, asset, direction, amount, quote_asset, quote_amount, tax_category 
  FROM transactions 
  WHERE exchange = ?
  ORDER BY block_timestamp
`).all("coinsquare");

console.log("Coinsquare transactions:", txs.length);
txs.forEach(t => console.log(t.id, t.direction, t.asset, t.amount, "->", t.quote_asset, t.quote_amount, "cat:", t.tax_category));
