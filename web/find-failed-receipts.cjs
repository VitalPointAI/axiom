const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Find all transactions where the receipt failed but we recorded them
const txs = db.prepare(`
  SELECT id, tx_hash, wallet_id, direction, CAST(amount AS REAL)/1e24 as amt, raw_json 
  FROM transactions 
  WHERE success = 1 AND raw_json LIKE '%status%: False%'
  LIMIT 50
`).all();

console.log("Transactions with failed receipts but success=1:", txs.length);

let totalFalsePositive = 0;
txs.forEach(t => {
  // Parse the Python dict format to check receipt_outcome.status
  const match = t.raw_json?.match(/'receipt_outcome':\s*\{[^}]*'status':\s*(True|False)/);
  if (match && match[1] === 'False') {
    console.log(`  ID ${t.id}: ${t.direction} ${t.amt.toFixed(4)} NEAR (tx: ${t.tx_hash.substring(0,15)})`);
    totalFalsePositive += t.amt;
  }
});

console.log("\nTotal overcounted (false positive):", totalFalsePositive.toFixed(4), "NEAR");

// Now check specifically for vitalpointai1.near
const vp1 = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("vitalpointai1.near");
const vp1Txs = db.prepare("SELECT * FROM transactions WHERE wallet_id = ?").all(vp1.id);

console.log("\n\nvitalpointai1.near receipts:");
vp1Txs.forEach(t => {
  const match = t.raw_json?.match(/'receipt_outcome':\s*\{[^}]*'status':\s*(True|False)/);
  const receiptStatus = match ? match[1] : "unknown";
  console.log(`  ${t.direction} ${(parseFloat(t.amount)/1e24).toFixed(4)} NEAR - receipt_status: ${receiptStatus}`);
});

db.close();
