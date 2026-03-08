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
        jsonrpc: '2.0', id: 'verify', method: 'query',
        params: { request_type: 'view_account', finality: 'final', account_id: account }
      })
    });
    const data = await res.json();
    if (data.result) {
      const su = data.result.storage_usage || 0;
      return {
        balance: parseFloat(data.result.amount) / 1e24,
        storageCost: su * 1e-5
      };
    }
    return { balance: 0, storageCost: 0 };
  } catch (e) {
    return { balance: 0, storageCost: 0 };
  }
}

function getComputedBalance(walletId, walletAccount, allWalletIds) {
  // Get all txs where this wallet has a FUNCTION_CALL out (triggers system refunds)
  const triggeredTxs = new Set();
  const fcRows = db.prepare(`
    SELECT DISTINCT tx_hash FROM transactions
    WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL' AND direction = 'out'
  `).all(walletId);
  fcRows.forEach(r => triggeredTxs.add(r.tx_hash));

  // Get DELETE_ACCOUNT tx_hashes from this wallet
  const deleteAccountTxs = new Set();
  const deleteRows = db.prepare(`
    SELECT tx_hash FROM transactions
    WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT' AND direction = 'out'
  `).all(walletId);
  deleteRows.forEach(r => deleteAccountTxs.add(r.tx_hash));

  // For DELETE_ACCOUNT, find the corresponding system transfer
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

  // Get CREATE_ACCOUNT outflows
  const createAccountOutflows = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions
    WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT' AND direction = 'out'
  `).get(walletId);

  // Get all transactions
  const txRows = db.prepare(`
    SELECT tx_hash, counterparty, direction, action_type, CAST(amount AS REAL)/1e24 as amt
    FROM transactions WHERE wallet_id = ?
  `).all(walletId);

  let totalIn = 0;
  let totalOut = 0;
  const GAS_THRESHOLD = 0.02;

  for (const { tx_hash, counterparty, direction, action_type, amt } of txRows) {
    if (counterparty === walletAccount) continue;
    
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

  totalOut += deleteAccountOutflows;
  totalOut += createAccountOutflows.total;

  // Unique fees
  const feeRow = db.prepare(`
    SELECT COALESCE(SUM(max_fee), 0) as total FROM (
      SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
      FROM transactions WHERE wallet_id = ?
      GROUP BY tx_hash
    )
  `).get(walletId);
  const uniqueFees = feeRow?.total || 0;

  return totalIn - totalOut - uniqueFees;
}

async function main() {
  const wallets = db.prepare(`SELECT id, account_id FROM wallets WHERE chain = 'NEAR' ORDER BY id`).all();
  const allWalletIds = wallets.map(w => w.id);
  
  let matching = 0, mismatched = 0;
  const results = [];
  
  for (const w of wallets) {
    const info = await getAccountInfo(w.account_id);
    const computed = getComputedBalance(w.id, w.account_id, allWalletIds);
    const diff = computed - info.balance;
    const adjustedDiff = diff - info.storageCost;
    const match = Math.abs(adjustedDiff) < 0.1;
    
    if (match) matching++; else mismatched++;
    
    if (!match) {
      results.push({
        account: w.account_id,
        onChain: info.balance.toFixed(2),
        computed: computed.toFixed(2),
        storage: info.storageCost.toFixed(2),
        adjustedDiff: adjustedDiff.toFixed(2)
      });
    }
  }
  
  console.log(`Verification: ${matching} matching, ${mismatched} mismatched`);
  console.log('\nMismatched wallets:');
  results.sort((a, b) => Math.abs(parseFloat(b.adjustedDiff)) - Math.abs(parseFloat(a.adjustedDiff)));
  results.slice(0, 15).forEach(r => {
    console.log(`  ${r.account}: onChain=${r.onChain}, computed=${r.computed}, storage=${r.storage}, adjDiff=${r.adjustedDiff}`);
  });
}

main();
