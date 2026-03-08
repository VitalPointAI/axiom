const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_RPC = 'https://rpc.mainnet.near.org';

async function getAccountInfo(account) {
  const res = await fetch(NEAR_RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0', id: 'verify', method: 'query',
      params: { request_type: 'view_account', finality: 'final', account_id: account }
    })
  });
  const data = await res.json();
  if (data.result) {
    return {
      balance: parseFloat(data.result.amount) / 1e24,
      storage: data.result.storage_usage,
      storageCost: data.result.storage_usage * 1e-5,
      hasContract: data.result.code_hash !== '11111111111111111111111111111111'
    };
  }
  return null;
}

const wallets = ["credz-operations.near", "credz.near", "relayer.vitalpointai.near", "key-recovery.credz.near"];
const allWalletIds = db.prepare("SELECT id FROM wallets WHERE chain = 'NEAR'").all().map(w => w.id);

async function investigate(account) {
  const wallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get(account);
  if (!wallet) return;
  
  const info = await getAccountInfo(account);
  
  console.log(`\n${"=".repeat(60)}`);
  console.log(`WALLET: ${account}`);
  console.log(`${"=".repeat(60)}`);
  console.log(`On-chain: ${info.balance.toFixed(4)} NEAR`);
  console.log(`Storage: ${info.storage} bytes = ${info.storageCost.toFixed(4)} NEAR locked`);
  console.log(`Has contract: ${info.hasContract}`);
  
  // Get all transaction types
  const byType = db.prepare(`
    SELECT action_type, direction, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
    FROM transactions WHERE wallet_id = ?
    GROUP BY action_type, direction
    ORDER BY total DESC
  `).all(wallet.id);
  
  console.log(`\nTransaction breakdown:`);
  byType.forEach(t => console.log(`  ${t.direction} ${t.action_type}: ${t.cnt}x, ${t.total?.toFixed(4)} NEAR`));
  
  // Check for receipt-level transfers (contract sending NEAR)
  if (info.hasContract) {
    console.log(`\n⚠️  This is a contract - checking for receipt-level transfers...`);
  }
  
  // Get DELETE_ACCOUNT outflows
  const deleteRows = db.prepare(`
    SELECT tx_hash FROM transactions
    WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT' AND direction = 'out'
  `).all(wallet.id);
  
  let deleteOutflows = 0;
  if (deleteRows.length > 0) {
    const txHashes = deleteRows.map(r => r.tx_hash);
    const placeholders = txHashes.map(() => '?').join(',');
    const transfers = db.prepare(`
      SELECT CAST(amount AS REAL)/1e24 as amt
      FROM transactions
      WHERE tx_hash IN (${placeholders}) AND counterparty = 'system' AND direction = 'in'
        AND wallet_id IN (${allWalletIds.join(',')}) AND wallet_id != ?
    `).all(...txHashes, wallet.id);
    deleteOutflows = transfers.reduce((sum, t) => sum + t.amt, 0);
  }
  console.log(`\nDELETE_ACCOUNT outflows: ${deleteOutflows.toFixed(4)} NEAR (${deleteRows.length} txs)`);
  
  // Calculate computed balance
  const inSum = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions WHERE wallet_id = ? AND direction = 'in' AND counterparty != ?
  `).get(wallet.id, account);
  
  const outSum = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions WHERE wallet_id = ? AND direction = 'out' AND counterparty != ? AND action_type != 'CREATE_ACCOUNT'
  `).get(wallet.id, account);
  
  const createOut = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT' AND direction = 'out'
  `).get(wallet.id);
  
  const fees = db.prepare(`
    SELECT COALESCE(SUM(max_fee), 0) as total FROM (
      SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee FROM transactions WHERE wallet_id = ? GROUP BY tx_hash
    )
  `).get(wallet.id);
  
  const totalOut = outSum.total + deleteOutflows + createOut.total;
  const computed = inSum.total - totalOut - fees.total;
  const diff = computed - info.balance;
  
  console.log(`\nCalculation:`);
  console.log(`  IN: ${inSum.total.toFixed(4)} NEAR`);
  console.log(`  OUT (regular): ${outSum.total.toFixed(4)} NEAR`);
  console.log(`  OUT (CREATE): ${createOut.total.toFixed(4)} NEAR`);
  console.log(`  OUT (DELETE): ${deleteOutflows.toFixed(4)} NEAR`);
  console.log(`  FEES: ${fees.total.toFixed(4)} NEAR`);
  console.log(`  Computed: ${computed.toFixed(4)} NEAR`);
  console.log(`  Diff: ${diff.toFixed(4)} NEAR`);
  
  if (diff > 0) {
    console.log(`\n🔍 MISSING OUTFLOW of ${diff.toFixed(4)} NEAR`);
    
    // Check for large system transfers that might be filtered
    const systemIn = db.prepare(`
      SELECT tx_hash, CAST(amount AS REAL)/1e24 as amt
      FROM transactions WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in'
      ORDER BY amt DESC LIMIT 5
    `).all(wallet.id);
    if (systemIn.length > 0) {
      console.log(`  Large system transfers IN (might be filtered):`);
      systemIn.forEach(s => console.log(`    ${s.amt.toFixed(4)} NEAR`));
    }
    
    // Check for storage deposits
    const storageDeps = db.prepare(`
      SELECT SUM(CAST(amount AS REAL)/1e24) as total, COUNT(*) as cnt
      FROM transactions WHERE wallet_id = ? AND method_name = 'storage_deposit' AND direction = 'out'
    `).get(wallet.id);
    if (storageDeps.total > 0) {
      console.log(`  storage_deposit OUT: ${storageDeps.total.toFixed(4)} NEAR (${storageDeps.cnt}x) - recoverable`);
    }
    
  } else {
    console.log(`\n🔍 MISSING INFLOW of ${Math.abs(diff).toFixed(4)} NEAR`);
    
    // Check for filtered small refunds
    const smallRefunds = db.prepare(`
      SELECT SUM(CAST(amount AS REAL)/1e24) as total, COUNT(*) as cnt
      FROM transactions WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in' AND CAST(amount AS REAL)/1e24 < 0.02
    `).get(wallet.id);
    if (smallRefunds.total > 0) {
      console.log(`  Small system refunds (<0.02): ${smallRefunds.total.toFixed(4)} NEAR (${smallRefunds.cnt}x)`);
    }
  }
}

(async () => {
  for (const w of wallets) {
    await investigate(w);
    await new Promise(r => setTimeout(r, 500));
  }
  db.close();
})();
