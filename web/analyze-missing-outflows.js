const Database = require('better-sqlite3');
const path = require('path');
const db = new Database(path.join(process.cwd(), '..', 'neartax.db'));

const wallet = db.prepare(`SELECT id FROM wallets WHERE account_id = ?`).get('aaron.near');
const walletId = wallet.id;
const walletAccount = 'aaron.near';

// Get triggered tx hashes
const triggeredTxs = new Set();
db.prepare(`SELECT DISTINCT tx_hash FROM transactions WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL' AND direction = 'out'`).all(walletId).forEach(r => triggeredTxs.add(r.tx_hash));

// Analyze all transactions
const txs = db.prepare(`SELECT * FROM transactions WHERE wallet_id = ?`).all(walletId);

let totalIn = 0, totalOut = 0;
let skippedSelf = 0, skippedSmall = 0, skippedTriggered = 0;
let systemInLarge = [];

for (const tx of txs) {
  const amt = parseFloat(tx.amount) / 1e24;
  
  if (tx.counterparty === walletAccount) {
    skippedSelf += amt;
    continue;
  }
  
  if (tx.direction === 'in') {
    if (tx.counterparty === 'system') {
      if (amt < 0.02) {
        skippedSmall += amt;
        continue;
      }
      if (triggeredTxs.has(tx.tx_hash)) {
        skippedTriggered += amt;
        continue;
      }
      // Large system transfer that's NOT triggered - should investigate
      systemInLarge.push({ amt, tx_hash: tx.tx_hash });
    }
    totalIn += amt;
  } else {
    totalOut += amt;
  }
}

// Fees
const feeRow = db.prepare(`SELECT COALESCE(SUM(max_fee), 0) as total FROM (SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee FROM transactions WHERE wallet_id = ? GROUP BY tx_hash)`).get(walletId);
const fees = feeRow?.total || 0;

const computed = totalIn - totalOut - fees;

console.log('aaron.near breakdown:');
console.log('  Total IN:', totalIn.toFixed(4));
console.log('  Total OUT:', totalOut.toFixed(4));
console.log('  Fees:', fees.toFixed(4));
console.log('  Computed:', computed.toFixed(4));
console.log('  OnChain:', '2.71');
console.log('  Storage:', '0.30');
console.log('  Adj Diff:', (computed - 2.71 - 0.30).toFixed(4));
console.log('');
console.log('Skipped:');
console.log('  Self-transfers:', skippedSelf.toFixed(4));
console.log('  Small system (<0.02):', skippedSmall.toFixed(4));
console.log('  Triggered system:', skippedTriggered.toFixed(4));
console.log('');
console.log('Large non-triggered system IN:', systemInLarge.length, 'txs');
systemInLarge.slice(0, 5).forEach(s => console.log('  ', s.tx_hash.slice(0,20) + '...:', s.amt.toFixed(4)));

// Check if there are uncounted outflows - wNEAR wraps that recorded 0
console.log('\n=== Potential missing outflows ===');

// wNEAR wraps with 0 amount
const wrapTxs = db.prepare(`
  SELECT tx_hash, action_type, CAST(amount AS REAL)/1e24 as amt
  FROM transactions
  WHERE wallet_id = ? AND counterparty = 'wrap.near' AND direction = 'out'
  ORDER BY amt DESC
`).all(walletId);
console.log('wrap.near outflows:');
wrapTxs.slice(0,10).forEach(t => console.log(`  ${t.action_type}: ${t.amt.toFixed(4)} NEAR`));

// Check venear.dao staking
const venearTxs = db.prepare(`
  SELECT counterparty, direction, action_type, CAST(amount AS REAL)/1e24 as amt
  FROM transactions
  WHERE wallet_id = ? AND counterparty LIKE '%venear%'
  ORDER BY amt DESC
`).all(walletId);
console.log('\nvenear transactions:');
venearTxs.slice(0,10).forEach(t => console.log(`  ${t.direction} ${t.action_type} ${t.counterparty}: ${t.amt.toFixed(4)}`));
