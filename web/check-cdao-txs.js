const Database = require('better-sqlite3');
const db = new Database('/home/deploy/neartax/neartax.db');

// Get aaron.near wallet id
const aaronWallet = db.prepare("SELECT id FROM wallets WHERE account_id = 'aaron.near'").get();
console.log('aaron.near wallet_id:', aaronWallet?.id);

if (aaronWallet) {
  // Check for incoming transfers from cdao contracts
  const transfers = db.prepare(`
    SELECT tx_hash, direction, counterparty, action_type, method_name, amount 
    FROM transactions 
    WHERE wallet_id = ? AND counterparty LIKE '%.cdao.near' 
    ORDER BY block_timestamp 
    LIMIT 30
  `).all(aaronWallet.id);
  
  console.log('\nTransactions involving cdao contracts:', transfers.length);
  transfers.forEach(t => {
    const amt = parseFloat(t.amount) / 1e24;
    console.log(t.direction, amt.toFixed(4), 'NEAR', t.action_type, t.method_name || '-', 'counterparty:', t.counterparty);
  });
  
  // Check specifically for incoming TRANSFERs from cdao contracts
  console.log('\n--- Incoming TRANSFERs from cdao ---');
  const incomingTransfers = db.prepare(`
    SELECT tx_hash, direction, counterparty, action_type, amount 
    FROM transactions 
    WHERE wallet_id = ? 
      AND direction = 'in' 
      AND action_type = 'TRANSFER'
      AND counterparty LIKE '%.cdao.near' 
    ORDER BY block_timestamp
  `).all(aaronWallet.id);
  
  console.log('Count:', incomingTransfers.length);
  incomingTransfers.forEach(t => {
    const amt = parseFloat(t.amount) / 1e24;
    console.log(amt.toFixed(4), 'NEAR from', t.counterparty);
  });
}
