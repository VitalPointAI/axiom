const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const wallet = db.prepare("SELECT * FROM wallets WHERE account_id = ?").get("vitalpointai1.near");
console.log("Wallet ID:", wallet.id);

// Get ALL transactions for this wallet with full details
const txs = db.prepare(`
  SELECT * FROM transactions WHERE wallet_id = ? ORDER BY id
`).all(wallet.id);

console.log("\nAll transactions:");
txs.forEach(t => {
  console.log({
    id: t.id,
    tx_hash: t.tx_hash?.substring(0, 15),
    direction: t.direction,
    action_type: t.action_type,
    amount_near: (parseFloat(t.amount) / 1e24).toFixed(4),
    counterparty: t.counterparty,
    fee_near: (parseFloat(t.fee || 0) / 1e24).toFixed(6),
  });
});

// Calculate balance
let inflow = 0;
let outflow = 0;
let fees = 0;

txs.forEach(t => {
  const amt = parseFloat(t.amount) / 1e24;
  const fee = parseFloat(t.fee || 0) / 1e24;
  
  if (t.direction === 'in') {
    inflow += amt;
  } else {
    outflow += amt;
  }
  fees += fee;
});

console.log("\nSummary:");
console.log("  Inflow:", inflow.toFixed(4), "NEAR");
console.log("  Outflow:", outflow.toFixed(4), "NEAR");
console.log("  Fees:", fees.toFixed(6), "NEAR");
console.log("  Computed:", (inflow - outflow - fees).toFixed(4), "NEAR");
console.log("  On-chain: 0.002 NEAR");
console.log("  Missing outflow:", (inflow - outflow - fees - 0.002).toFixed(4), "NEAR");

db.close();
