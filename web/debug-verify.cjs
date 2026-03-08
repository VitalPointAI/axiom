const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_RPC = 'https://rpc.mainnet.near.org';

async function getBalance(account) {
  const res = await fetch(NEAR_RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0', id: 'verify', method: 'query',
      params: { request_type: 'view_account', finality: 'final', account_id: account }
    })
  });
  const data = await res.json();
  return data.result ? parseFloat(data.result.amount) / 1e24 : null;
}

const allWalletIds = db.prepare("SELECT id FROM wallets WHERE chain = 'NEAR'").all().map(w => w.id);

async function debugVerify(account) {
  const wallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get(account);
  if (!wallet) return;
  
  const walletId = wallet.id;
  const onChain = await getBalance(account);
  
  console.log(`\n=== ${account} ===`);
  console.log(`On-chain: ${onChain?.toFixed(4)} NEAR`);
  
  // Get DELETE_ACCOUNT tx_hashes
  const deleteRows = db.prepare(`
    SELECT tx_hash FROM transactions
    WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT' AND direction = 'out'
  `).all(walletId);
  
  console.log(`DELETE_ACCOUNT txs: ${deleteRows.length}`);
  
  // Calculate DELETE_ACCOUNT outflows
  let deleteAccountOutflows = 0;
  if (deleteRows.length > 0) {
    const txHashes = deleteRows.map(r => r.tx_hash);
    const placeholders = txHashes.map(() => '?').join(',');
    
    const beneficiaryTransfers = db.prepare(`
      SELECT tx_hash, CAST(amount AS REAL)/1e24 as amt, wallet_id
      FROM transactions
      WHERE tx_hash IN (${placeholders})
        AND counterparty = 'system'
        AND direction = 'in'
        AND wallet_id IN (${allWalletIds.join(',')})
        AND wallet_id != ?
    `).all(...txHashes, walletId);
    
    deleteAccountOutflows = beneficiaryTransfers.reduce((sum, t) => sum + t.amt, 0);
  }
  console.log(`DELETE_ACCOUNT outflows: ${deleteAccountOutflows.toFixed(4)} NEAR`);
  
  // Get CREATE_ACCOUNT outflows  
  const createOut = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions
    WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT' AND direction = 'out'
  `).get(walletId);
  console.log(`CREATE_ACCOUNT outflows: ${createOut.total.toFixed(4)} NEAR`);
  
  // Get regular IN/OUT
  const inSum = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions 
    WHERE wallet_id = ? AND direction = 'in' AND counterparty != ?
  `).get(walletId, account);
  
  const outSum = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions 
    WHERE wallet_id = ? AND direction = 'out' AND counterparty != ? AND action_type != 'CREATE_ACCOUNT'
  `).get(walletId, account);
  
  const fees = db.prepare(`
    SELECT COALESCE(SUM(max_fee), 0) as total FROM (
      SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
      FROM transactions WHERE wallet_id = ? GROUP BY tx_hash
    )
  `).get(walletId);
  
  console.log(`IN (regular): ${inSum.total.toFixed(4)} NEAR`);
  console.log(`OUT (regular, excl CREATE): ${outSum.total.toFixed(4)} NEAR`);
  console.log(`FEES: ${fees.total.toFixed(4)} NEAR`);
  
  const totalOut = outSum.total + deleteAccountOutflows + createOut.total;
  const computed = inSum.total - totalOut - fees.total;
  
  console.log(`\nTotal OUT: ${totalOut.toFixed(4)} NEAR`);
  console.log(`Computed: ${computed.toFixed(4)} NEAR`);
  console.log(`Diff: ${(computed - onChain).toFixed(4)} NEAR`);
}

(async () => {
  await debugVerify("challenge-coin-nft.credz.near");
  db.close();
})();
