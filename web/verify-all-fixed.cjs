const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_RPC = 'https://rpc.mainnet.near.org';

async function getBalance(account) {
  try {
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
  } catch {
    return null;
  }
}

const wallets = db.prepare(`
  SELECT id, account_id FROM wallets 
  WHERE chain = 'NEAR' 
    AND account_id NOT LIKE '%.pool%'
    AND account_id NOT LIKE '%.poolv1%'
`).all();

const allWalletIds = wallets.map(w => w.id);

function getComputedBalance(walletId, walletAccount) {
  // Get DELETE_ACCOUNT tx_hashes
  const deleteRows = db.prepare(`
    SELECT tx_hash FROM transactions
    WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT' AND direction = 'out'
  `).all(walletId);
  
  // Calculate DELETE_ACCOUNT outflows
  let deleteAccountOutflows = 0;
  if (deleteRows.length > 0) {
    const txHashes = deleteRows.map(r => r.tx_hash);
    const placeholders = txHashes.map(() => '?').join(',');
    const beneficiaryTransfers = db.prepare(`
      SELECT CAST(amount AS REAL)/1e24 as amt
      FROM transactions
      WHERE tx_hash IN (${placeholders})
        AND counterparty = 'system'
        AND direction = 'in'
        AND wallet_id IN (${allWalletIds.join(',')})
        AND wallet_id != ?
    `).all(...txHashes, walletId);
    
    deleteAccountOutflows = beneficiaryTransfers.reduce((sum, t) => sum + t.amt, 0);
  }
  
  // Get CREATE_ACCOUNT outflows
  const createOut = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions
    WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT' AND direction = 'out'
  `).get(walletId);
  
  // Get regular IN (excluding self-transfers)
  const inSum = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions 
    WHERE wallet_id = ? AND direction = 'in' AND counterparty != ?
  `).get(walletId, walletAccount);
  
  // Get regular OUT (excluding CREATE_ACCOUNT and self-transfers)
  const outSum = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions 
    WHERE wallet_id = ? AND direction = 'out' AND counterparty != ? AND action_type != 'CREATE_ACCOUNT'
  `).get(walletId, walletAccount);
  
  // Unique fees
  const fees = db.prepare(`
    SELECT COALESCE(SUM(max_fee), 0) as total FROM (
      SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
      FROM transactions WHERE wallet_id = ? GROUP BY tx_hash
    )
  `).get(walletId);
  
  const totalOut = outSum.total + deleteAccountOutflows + createOut.total;
  return inSum.total - totalOut - fees.total;
}

async function verify() {
  let matching = 0;
  let mismatched = 0;
  const issues = [];
  
  console.log(`Verifying ${wallets.length} wallets (with DELETE_ACCOUNT fix)...\n`);
  
  for (let i = 0; i < wallets.length; i++) {
    const wallet = wallets[i];
    
    if (i > 0 && i % 10 === 0) {
      await new Promise(r => setTimeout(r, 500));
    }
    
    const onChain = await getBalance(wallet.account_id);
    if (onChain === null) continue;
    
    const computed = getComputedBalance(wallet.id, wallet.account_id);
    const diff = computed - onChain;
    
    const tolerance = 0.5;
    if (Math.abs(diff) < tolerance) {
      matching++;
    } else {
      mismatched++;
      issues.push({
        account: wallet.account_id,
        onChain: onChain.toFixed(4),
        computed: computed.toFixed(4),
        diff: diff.toFixed(4)
      });
    }
    
    if ((i + 1) % 10 === 0 || i === wallets.length - 1) {
      process.stdout.write(`\r  Checked ${i + 1}/${wallets.length} - ✅ ${matching} matching, ❌ ${mismatched} mismatched`);
    }
  }
  
  console.log("\n\n📊 VERIFICATION SUMMARY:");
  console.log(`  ✅ Matching: ${matching}`);
  console.log(`  ❌ Mismatched: ${mismatched}`);
  
  if (issues.length > 0) {
    console.log("\n❌ Mismatched wallets:");
    issues.sort((a, b) => Math.abs(parseFloat(b.diff)) - Math.abs(parseFloat(a.diff)));
    issues.forEach(i => {
      console.log(`  ${i.account}: diff ${i.diff} NEAR`);
    });
  }
}

verify().then(() => db.close());
