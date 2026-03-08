const Database = require('better-sqlite3');
const path = require('path');
const db = new Database(path.join(process.cwd(), '..', 'neartax.db'));

// Check credz.near for incoming transfers from challenge-coin-nft.credz.near
const credz = db.prepare(`SELECT id FROM wallets WHERE account_id = ?`).get('credz.near');

// Get transfers FROM challenge-coin-nft.credz.near TO credz.near
const transfers = db.prepare(`
  SELECT tx_hash, action_type, CAST(amount AS REAL)/1e24 as amt, counterparty
  FROM transactions
  WHERE wallet_id = ? AND counterparty = 'challenge-coin-nft.credz.near' AND direction = 'in'
  ORDER BY amt DESC
`).all(credz.id);

console.log('Transfers from challenge-coin-nft.credz.near to credz.near:');
let total = 0;
transfers.forEach(t => {
  console.log(`  ${t.action_type}: ${t.amt.toFixed(4)} (${t.tx_hash.slice(0,15)})`);
  total += t.amt;
});
console.log('Total:', total.toFixed(4));

// Get DELETE_ACCOUNT tx_hashes from challenge-coin-nft.credz.near
const challengeWallet = db.prepare(`SELECT id FROM wallets WHERE account_id = ?`).get('challenge-coin-nft.credz.near');
const deleteTxHashes = db.prepare(`
  SELECT tx_hash FROM transactions
  WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT'
`).all(challengeWallet.id).map(r => r.tx_hash);

console.log('\nDELETE_ACCOUNT tx hashes:', deleteTxHashes.length);

// Check if any of these tx_hashes appear in credz.near transactions
if (deleteTxHashes.length > 0) {
  const placeholders = deleteTxHashes.map(() => '?').join(',');
  const matchingTxs = db.prepare(`
    SELECT tx_hash, action_type, counterparty, direction, CAST(amount AS REAL)/1e24 as amt
    FROM transactions
    WHERE wallet_id = ? AND tx_hash IN (${placeholders})
  `).all(credz.id, ...deleteTxHashes);

  console.log('Matching transactions in credz.near for DELETE tx_hashes:');
  let beneficiaryTotal = 0;
  matchingTxs.forEach(t => {
    console.log(`  ${t.direction} ${t.action_type} from ${t.counterparty}: ${t.amt.toFixed(4)}`);
    if (t.direction === 'in') beneficiaryTotal += t.amt;
  });
  console.log('Beneficiary total received:', beneficiaryTotal.toFixed(4));
}

// Check system transfers to credz.near
const systemTransfers = db.prepare(`
  SELECT tx_hash, CAST(amount AS REAL)/1e24 as amt
  FROM transactions
  WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in'
  ORDER BY amt DESC
  LIMIT 20
`).all(credz.id);

console.log('\nLarge system transfers to credz.near:');
systemTransfers.slice(0, 10).forEach(t => console.log(`  ${t.tx_hash.slice(0,20)}: ${t.amt.toFixed(4)}`));
