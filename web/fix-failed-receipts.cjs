const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

console.log("=== Fixing Failed Receipts Bug ===\n");

// Step 1: Count affected transactions
const before = db.prepare(`
  SELECT COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE raw_json LIKE '%receipt_outcome%status%: False%'
`).get();

console.log("Transactions with failed receipts:");
console.log(`  Count: ${before.cnt}`);
console.log(`  Total NEAR: ${before.total?.toFixed(4) || "0"}\n`);

// Step 2: Delete them
const deleteResult = db.prepare(`
  DELETE FROM transactions 
  WHERE raw_json LIKE '%receipt_outcome%status%: False%'
`).run();

console.log(`Deleted: ${deleteResult.changes} transactions\n`);

// Step 3: Verify cleanup
const after = db.prepare(`
  SELECT COUNT(*) as cnt
  FROM transactions 
  WHERE raw_json LIKE '%receipt_outcome%status%: False%'
`).get();

console.log(`Remaining failed receipts: ${after.cnt}`);

// Step 4: Get new total transaction count
const total = db.prepare("SELECT COUNT(*) as cnt FROM transactions").get();
console.log(`Total transactions now: ${total.cnt}`);

db.close();
console.log("\n✅ Cleanup complete!");
