const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_DECIMALS = 1e24;

const acWallet = db.prepare("SELECT id, account_id FROM wallets WHERE account_id = ?").get('ac-sandbox.credz.near');
console.log("Testing delete outflow query for ac-sandbox.credz.near (id=%d)\n", acWallet.id);

// The exact query from the verify route
const deleteAccountOutflows = db.prepare(`
  SELECT COALESCE(SUM(CAST(t2.amount AS REAL)/1e24), 0) as total
  FROM transactions t1
  JOIN transactions t2 ON t1.tx_hash = t2.tx_hash
  WHERE t1.wallet_id = ?
    AND t1.action_type = 'DELETE_ACCOUNT'
    AND t2.direction = 'in'
    AND t2.counterparty = 'system'
    AND t2.wallet_id != t1.wallet_id
`).get(acWallet.id);
console.log("deleteAccountOutflows:", deleteAccountOutflows.total.toFixed(4));

// Debug: Show all linked transactions
const linkedDebug = db.prepare(`
  SELECT t1.tx_hash, t1.action_type as t1_action, t2.wallet_id as t2_wallet, 
         t2.direction as t2_direction, t2.counterparty as t2_counterparty, 
         CAST(t2.amount AS REAL)/1e24 as t2_amount
  FROM transactions t1
  JOIN transactions t2 ON t1.tx_hash = t2.tx_hash
  WHERE t1.wallet_id = ?
    AND t1.action_type = 'DELETE_ACCOUNT'
`).all(acWallet.id);
console.log("\nAll linked DELETE_ACCOUNT transactions:");
linkedDebug.forEach(r => {
  console.log(`  t1.action=${r.t1_action}, t2.wallet=${r.t2_wallet}, t2.dir=${r.t2_direction}, t2.counterparty=${r.t2_counterparty}, t2.amount=${r.t2_amount.toFixed(4)}`);
});

// Now check the full verification calculation
const inSum = db.prepare(`
  SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
  FROM transactions 
  WHERE wallet_id = ? 
    AND direction = 'in' 
    AND counterparty != ?
    AND counterparty != 'system'
`).get(acWallet.id, acWallet.account_id);

const outSum = db.prepare(`
  SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
  FROM transactions 
  WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
`).get(acWallet.id, acWallet.account_id);

const fees = db.prepare(`
  SELECT COALESCE(SUM(max_fee), 0) as total FROM (
    SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
    FROM transactions WHERE wallet_id = ? AND direction = 'out' GROUP BY tx_hash
  )
`).get(acWallet.id);

console.log("\n--- Full verification ---");
console.log("IN (excl system):", inSum.total.toFixed(4));
console.log("OUT:", outSum.total.toFixed(4));
console.log("Fees:", fees.total.toFixed(6));
console.log("DELETE outflow:", deleteAccountOutflows.total.toFixed(4));

const computed = inSum.total - outSum.total - fees.total - deleteAccountOutflows.total;
console.log("\nComputed:", computed.toFixed(4));
console.log("Expected RPC:", "0.9999");
console.log("Diff:", (computed - 0.9999).toFixed(4));
