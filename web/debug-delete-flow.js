const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_DECIMALS = 1e24;

// Find all DELETE_ACCOUNT transactions for ac-sandbox.credz.near
const acWallet = db.prepare("SELECT id, account_id FROM wallets WHERE account_id = ?").get('ac-sandbox.credz.near');
const credzWallet = db.prepare("SELECT id, account_id FROM wallets WHERE account_id = ?").get('credz.near');

console.log("ac-sandbox.credz.near ID:", acWallet.id);
console.log("credz.near ID:", credzWallet.id);

// Get DELETE_ACCOUNT transactions
const deleteTxs = db.prepare(`
  SELECT tx_hash, direction, action_type, counterparty, amount, fee, receipt_id
  FROM transactions 
  WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT'
`).all(acWallet.id);

console.log("\nDELETE_ACCOUNT txs for ac-sandbox.credz.near:");
deleteTxs.forEach(tx => {
  console.log(`  tx_hash: ${tx.tx_hash.slice(0,20)}...`);
  console.log(`  direction: ${tx.direction}, amount: ${Number(tx.amount)/NEAR_DECIMALS}, counterparty: ${tx.counterparty}`);
  
  // Find all transactions with same tx_hash (this should show the beneficiary transfer)
  const linkedTxs = db.prepare(`
    SELECT t.*, w.account_id as wallet_name
    FROM transactions t
    JOIN wallets w ON t.wallet_id = w.id
    WHERE t.tx_hash = ?
    ORDER BY t.wallet_id
  `).all(tx.tx_hash);
  
  console.log("  Linked transactions:");
  linkedTxs.forEach(lt => {
    const amt = Number(lt.amount) / NEAR_DECIMALS;
    console.log(`    ${lt.wallet_name} ${lt.direction} ${lt.action_type}: ${amt.toFixed(4)} NEAR, counterparty=${lt.counterparty}`);
  });
  console.log();
});

// Check if credz.near received the beneficiary transfer
console.log("\n=== Checking credz.near for beneficiary receipt ===");
const credzInFromSubAccounts = db.prepare(`
  SELECT action_type, counterparty, direction, amount, tx_hash
  FROM transactions 
  WHERE wallet_id = ? 
    AND direction = 'in' 
    AND counterparty LIKE '%.credz.near'
  ORDER BY block_timestamp
  LIMIT 20
`).all(credzWallet.id);

console.log("credz.near IN from sub-accounts:");
credzInFromSubAccounts.forEach(tx => {
  const amt = Number(tx.amount) / NEAR_DECIMALS;
  console.log(`  ${tx.action_type} from ${tx.counterparty}: ${amt.toFixed(4)} NEAR`);
});

// Check for system transfers to credz.near
const systemToCredz = db.prepare(`
  SELECT action_type, counterparty, direction, amount, tx_hash
  FROM transactions 
  WHERE wallet_id = ? 
    AND direction = 'in' 
    AND counterparty = 'system'
  ORDER BY CAST(amount AS REAL) DESC
  LIMIT 20
`).all(credzWallet.id);

console.log("\ncredz.near IN from system (top 20 by amount):");
systemToCredz.forEach(tx => {
  const amt = Number(tx.amount) / NEAR_DECIMALS;
  console.log(`  ${tx.action_type}: ${amt.toFixed(4)} NEAR`);
});
