const Database = require('better-sqlite3');
const db = new Database('/home/deploy/neartax/neartax.db');

// Check large transfers
console.log('Large TRANSFER transactions (>10 NEAR):');
const largeTx = db.prepare(`
  SELECT tx_hash, wallet_id, direction, action_type, amount, counterparty, method_name 
  FROM transactions 
  WHERE action_type = 'TRANSFER' 
  AND CAST(amount AS REAL) > 10 
  ORDER BY CAST(amount AS REAL) DESC 
  LIMIT 20
`).all();
largeTx.forEach(t => console.log(t.tx_hash.substring(0,12) + '... ' + t.direction + ' ' + parseFloat(t.amount).toFixed(2) + ' NEAR ' + (t.direction === 'in' ? 'from' : 'to') + ' ' + t.counterparty));

console.log('\n');

// Let's look at the NearBlocks data for one of Aaron's wallets to see if there are delete account records
// First, let's look at what wallets we have
console.log('Wallets by transaction count:');
const walletStats = db.prepare(`
  SELECT w.address, COUNT(t.id) as tx_count
  FROM wallets w
  LEFT JOIN transactions t ON t.wallet_id = w.id
  GROUP BY w.id
  ORDER BY tx_count DESC
  LIMIT 10
`).all();
walletStats.forEach(w => console.log('  ' + w.address + ': ' + w.tx_count + ' txs'));

// Check if any transfers have a pattern suggesting delete account (beneficiary receiving)
console.log('\n');
console.log('Checking for potential delete account transfers (in direction, from .near accounts):');
const potentialDeletes = db.prepare(`
  SELECT tx_hash, counterparty, amount, block_timestamp
  FROM transactions
  WHERE direction = 'in'
  AND action_type = 'TRANSFER'
  AND counterparty LIKE '%.near'
  AND CAST(amount AS REAL) > 1
  ORDER BY CAST(amount AS REAL) DESC
  LIMIT 20
`).all();
potentialDeletes.forEach(t => {
  const date = new Date(t.block_timestamp / 1000000);
  console.log('  ' + date.toISOString().split('T')[0] + ' ' + parseFloat(t.amount).toFixed(4) + ' NEAR from ' + t.counterparty);
});
