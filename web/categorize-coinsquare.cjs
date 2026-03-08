const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

// Categorize based on pattern:
// CAD IN = fiat_deposit (not taxable)
// CAD OUT = fiat_withdrawal (not taxable)  
// Crypto IN with CAD quote = buy (acquisition - cost basis event)
// Crypto OUT with CAD quote = sell (disposal - taxable event)

const updates = [
  // CAD deposits
  { sql: "UPDATE transactions SET tax_category = fiat_deposit WHERE exchange = coinsquare AND asset = CAD AND direction = IN", desc: "CAD deposits" },
  // CAD withdrawals
  { sql: "UPDATE transactions SET tax_category = fiat_withdrawal WHERE exchange = coinsquare AND asset = CAD AND direction = OUT", desc: "CAD withdrawals" },
  // Crypto buys (NEAR IN)
  { sql: "UPDATE transactions SET tax_category = buy WHERE exchange = coinsquare AND asset = NEAR AND direction = IN", desc: "NEAR buys" },
  // Crypto buys (USDC IN)
  { sql: "UPDATE transactions SET tax_category = buy WHERE exchange = coinsquare AND asset = USDC AND direction = IN", desc: "USDC buys" },
  // Crypto sells (NEAR OUT)  
  { sql: "UPDATE transactions SET tax_category = sell WHERE exchange = coinsquare AND asset = NEAR AND direction = OUT", desc: "NEAR sells" },
  // Crypto sells (USDC OUT)  
  { sql: "UPDATE transactions SET tax_category = sell WHERE exchange = coinsquare AND asset = USDC AND direction = OUT", desc: "USDC sells" },
];

for (const u of updates) {
  const result = db.prepare(u.sql).run();
  console.log(u.desc + ":", result.changes, "updated");
}

// Verify
const remaining = db.prepare("SELECT COUNT(*) as cnt FROM transactions WHERE exchange = coinsquare AND tax_category IS NULL").get();
console.log("\nUncategorized remaining:", remaining.cnt);

// Summary
const summary = db.prepare(`
  SELECT tax_category, COUNT(*) as cnt, 
    SUM(CASE WHEN asset != CAD THEN CAST(amount AS REAL) ELSE 0 END) as crypto_amount,
    SUM(CAST(quote_amount AS REAL)) as cad_value
  FROM transactions 
  WHERE exchange = coinsquare
  GROUP BY tax_category
`).all();
console.log("\nSummary by category:", summary);
