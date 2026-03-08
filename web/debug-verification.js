const Database = require('better-sqlite3');
const path = require('path');
const fetch = require('node-fetch');
const db = new Database(path.join(process.cwd(), '..', 'neartax.db'));

const NEAR_RPC = 'https://rpc.fastnear.com';

async function getAccountInfo(account) {
  try {
    const res = await fetch(NEAR_RPC, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 'v', method: 'query',
        params: { request_type: 'view_account', finality: 'final', account_id: account }
      })
    });
    const data = await res.json();
    if (data.result) {
      return {
        balance: parseFloat(data.result.amount) / 1e24,
        storage: data.result.storage_usage * 1e-5
      };
    }
    return null;
  } catch { return null; }
}

async function main() {
  const account = 'challenge-coin-nft.credz.near';
  const wallet = db.prepare(`SELECT id FROM wallets WHERE account_id = ?`).get(account);
  const walletId = wallet.id;
  
  // Get all wallet IDs
  const allWalletIds = db.prepare(`SELECT id FROM wallets`).all().map(w => w.id);
  
  console.log('=== DEBUG: ' + account + ' ===\n');
  
  const info = await getAccountInfo(account);
  console.log('On-chain balance:', info?.balance?.toFixed(4));
  console.log('Storage cost:', info?.storage?.toFixed(4));
  console.log('Available (onChain - storage):', ((info?.balance || 0) - (info?.storage || 0)).toFixed(4));
  
  // Replicate verification logic
  
  // 1. Get triggered tx hashes
  const triggeredTxs = new Set();
  db.prepare(`SELECT DISTINCT tx_hash FROM transactions WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL' AND direction = 'out'`).all(walletId).forEach(r => triggeredTxs.add(r.tx_hash));
  
  // 2. Get DELETE_ACCOUNT tx hashes and find beneficiary transfers
  const deleteAccountTxs = new Set();
  db.prepare(`SELECT tx_hash FROM transactions WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT' AND direction = 'out'`).all(walletId).forEach(r => deleteAccountTxs.add(r.tx_hash));
  
  let deleteAccountOutflows = 0;
  if (deleteAccountTxs.size > 0) {
    const placeholders = Array.from(deleteAccountTxs).map(() => '?').join(',');
    const beneficiaryTransfers = db.prepare(`
      SELECT tx_hash, CAST(amount AS REAL)/1e24 as amt
      FROM transactions
      WHERE tx_hash IN (${placeholders})
        AND counterparty = 'system'
        AND direction = 'in'
        AND wallet_id IN (${allWalletIds.join(',')})
        AND wallet_id != ?
    `).all(...Array.from(deleteAccountTxs), walletId);
    
    for (const t of beneficiaryTransfers) {
      deleteAccountOutflows += t.amt;
    }
  }
  
  console.log('\nDELETE_ACCOUNT outflows found:', deleteAccountOutflows.toFixed(4));
  
  // 3. Get CREATE_ACCOUNT outflows
  const createRow = db.prepare(`SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total FROM transactions WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT' AND direction = 'out'`).get(walletId);
  const createAccountOutflows = createRow?.total || 0;
  console.log('CREATE_ACCOUNT outflows:', createAccountOutflows.toFixed(4));
  
  // 4. Process all transactions
  const txRows = db.prepare(`SELECT tx_hash, counterparty, direction, action_type, CAST(amount AS REAL)/1e24 as amt FROM transactions WHERE wallet_id = ?`).all(walletId);
  
  let totalIn = 0;
  let totalOut = 0;
  const GAS_THRESHOLD = 0.02;
  
  for (const { tx_hash, counterparty, direction, action_type, amt } of txRows) {
    if (counterparty === account) continue;
    
    if (direction === 'in') {
      if (counterparty === 'system') {
        if (amt < GAS_THRESHOLD) continue;
        if (triggeredTxs.has(tx_hash)) continue;
      }
      totalIn += amt;
    } else {
      if (action_type !== 'CREATE_ACCOUNT') {
        totalOut += amt;
      }
    }
  }
  
  // Add DELETE_ACCOUNT and CREATE_ACCOUNT outflows
  totalOut += deleteAccountOutflows;
  totalOut += createAccountOutflows;
  
  // 5. Fees
  const feeRow = db.prepare(`SELECT COALESCE(SUM(max_fee), 0) as total FROM (SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee FROM transactions WHERE wallet_id = ? GROUP BY tx_hash)`).get(walletId);
  const fees = feeRow?.total || 0;
  
  const computed = totalIn - totalOut - fees;
  
  console.log('\n--- Breakdown ---');
  console.log('Total IN:', totalIn.toFixed(4));
  console.log('Total OUT (base):', (totalOut - deleteAccountOutflows - createAccountOutflows).toFixed(4));
  console.log('  + DELETE_ACCOUNT:', deleteAccountOutflows.toFixed(4));
  console.log('  + CREATE_ACCOUNT:', createAccountOutflows.toFixed(4));
  console.log('Total OUT:', totalOut.toFixed(4));
  console.log('Fees:', fees.toFixed(4));
  console.log('Computed:', computed.toFixed(4));
  
  console.log('\n--- Analysis ---');
  console.log('OnChain:', info?.balance?.toFixed(4));
  console.log('Computed:', computed.toFixed(4));
  console.log('Diff (computed - onChain):', (computed - (info?.balance || 0)).toFixed(4));
  
  // The computed should ideally equal onChain
  // If computed > onChain, we're under-counting outflows
  // If computed < onChain, we're under-counting inflows
  
  const diff = computed - (info?.balance || 0);
  if (diff > 0.1) {
    console.log('\n⚠️  UNDER-COUNTING OUTFLOWS by', diff.toFixed(4), 'NEAR');
  } else if (diff < -0.1) {
    console.log('\n⚠️  UNDER-COUNTING INFLOWS by', Math.abs(diff).toFixed(4), 'NEAR');
  } else {
    console.log('\n✅ Within tolerance');
  }
}

main();
