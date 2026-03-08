const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_DECIMALS = 1e24;

// Find ac-sandbox.credz.near
const wallet = db.prepare("SELECT id, account_id FROM wallets WHERE account_id = ?").get('ac-sandbox.credz.near');
console.log("Wallet:", wallet);

// Get ALL transactions for this wallet
const txs = db.prepare(`
  SELECT direction, action_type, counterparty, amount, fee, tx_hash
  FROM transactions 
  WHERE wallet_id = ? 
  ORDER BY block_timestamp
`).all(wallet.id);

console.log("\nAll transactions:");
txs.forEach(tx => {
  const amt = Number(tx.amount) / NEAR_DECIMALS;
  const fee = Number(tx.fee) / NEAR_DECIMALS;
  console.log(`  ${tx.direction.toUpperCase()} ${tx.action_type}: ${amt.toFixed(4)} NEAR, fee=${fee.toFixed(6)}, from/to=${tx.counterparty}`);
});

// Run the same queries as the verify route
console.log("\n--- Verify queries ---");

// IN: exclude self-transfers AND system gas refunds
const inSum = db.prepare(`
  SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
  FROM transactions 
  WHERE wallet_id = ? 
    AND direction = 'in' 
    AND counterparty != ?
    AND counterparty != 'system'
`).get(wallet.id, wallet.account_id);
console.log("inSum (excluding system):", inSum.total.toFixed(4));

// What if we include system?
const inSumWithSystem = db.prepare(`
  SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
  FROM transactions 
  WHERE wallet_id = ? 
    AND direction = 'in' 
    AND counterparty != ?
`).get(wallet.id, wallet.account_id);
console.log("inSum (with system):", inSumWithSystem.total.toFixed(4));

// OUT: exclude self-transfers
const outSum = db.prepare(`
  SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
  FROM transactions 
  WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
`).get(wallet.id, wallet.account_id);
console.log("outSum:", outSum.total.toFixed(4));

// Fees
const fees = db.prepare(`
  SELECT COALESCE(SUM(max_fee), 0) as total FROM (
    SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
    FROM transactions WHERE wallet_id = ? AND direction = 'out' GROUP BY tx_hash
  )
`).get(wallet.id);
console.log("fees:", fees.total.toFixed(6));

// What counterparty does the IN come from?
const inDetails = db.prepare(`
  SELECT direction, counterparty, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE wallet_id = ? AND direction = 'in'
  GROUP BY counterparty
`).all(wallet.id);
console.log("\nIN by counterparty:");
inDetails.forEach(d => console.log(`  ${d.counterparty}: ${d.total.toFixed(4)}`));
