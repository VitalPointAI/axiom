const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Check credz.near outbound CREATE_ACCOUNT transactions
const credzWallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("credz.near");
const creates = db.prepare(`
  SELECT counterparty, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT' AND direction = 'out'
  GROUP BY counterparty
  ORDER BY total DESC
  LIMIT 15
`).all(credzWallet.id);

console.log("credz.near CREATE_ACCOUNT outflows:");
let totalOut = 0;
creates.forEach(c => {
  console.log(`  ${c.total.toFixed(2)} NEAR -> ${c.counterparty} (${c.cnt}x)`);
  totalOut += c.total;
});
console.log(`\nTotal CREATE_ACCOUNT out from credz.near: ${totalOut.toFixed(2)} NEAR`);

// Check system transfers IN to credz.near (DELETE_ACCOUNT refunds)
const systemIn = db.prepare(`
  SELECT SUM(CAST(amount AS REAL)/1e24) as total, COUNT(*) as cnt
  FROM transactions 
  WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in'
`).get(credzWallet.id);

console.log(`\nSystem transfers IN to credz.near: ${systemIn.total.toFixed(2)} NEAR (${systemIn.cnt}x)`);

// Net flow through sub-accounts
console.log(`\nNet flow: OUT ${totalOut.toFixed(2)} NEAR, back IN ${systemIn.total.toFixed(2)} NEAR`);
console.log(`Difference: ${(totalOut - systemIn.total).toFixed(2)} NEAR (should match sum of current sub-account balances + fees)`);

db.close();
