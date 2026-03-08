const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Count all transactions with failed receipts
const allFailed = db.prepare(`
  SELECT COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE raw_json LIKE '%receipt_outcome%status%: False%'
`).get();

console.log("Total transactions with failed receipts:");
console.log("  Count:", allFailed.cnt);
console.log("  Total NEAR:", allFailed.total?.toFixed(4) || "0");

// Break down by direction
const byDirection = db.prepare(`
  SELECT direction, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE raw_json LIKE '%receipt_outcome%status%: False%'
  GROUP BY direction
`).all();

console.log("\nBy direction:");
byDirection.forEach(r => {
  console.log(`  ${r.direction}: ${r.cnt} txs, ${r.total?.toFixed(4)} NEAR`);
});

// Check how many are success=1 vs success=0
const bySuccess = db.prepare(`
  SELECT success, COUNT(*) as cnt
  FROM transactions 
  WHERE raw_json LIKE '%receipt_outcome%status%: False%'
  GROUP BY success
`).all();

console.log("\nBy success flag:");
bySuccess.forEach(r => {
  console.log(`  success=${r.success}: ${r.cnt} txs`);
});

// What are the most common counterparties for failed receipts?
const byCounterparty = db.prepare(`
  SELECT counterparty, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE raw_json LIKE '%receipt_outcome%status%: False%'
  GROUP BY counterparty
  ORDER BY total DESC
  LIMIT 10
`).all();

console.log("\nTop counterparties with failed receipts:");
byCounterparty.forEach(r => {
  console.log(`  ${r.counterparty}: ${r.cnt} txs, ${r.total?.toFixed(4)} NEAR`);
});

db.close();
