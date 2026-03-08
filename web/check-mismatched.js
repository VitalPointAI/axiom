const fetch = require('node-fetch');
const Database = require('better-sqlite3');
const path = require('path');
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

async function main() {
  const wallets = db.prepare(`SELECT id, account_id FROM wallets WHERE chain = 'NEAR' ORDER BY id`).all();
  const allWalletIds = wallets.map(w => w.id);
  
  const mismatched = [];
  
  for (const w of wallets) {
    const info = await getAccountInfo(w.account_id);
    
    // Get computed balance (simplified)
    const txRows = db.prepare(`SELECT direction, counterparty, action_type, CAST(amount AS REAL)/1e24 as amt FROM transactions WHERE wallet_id = ?`).all(w.id);
    let totalIn = 0, totalOut = 0;
    for (const tx of txRows) {
      if (tx.counterparty === w.account_id) continue;
      if (tx.direction === 'in') {
        // Skip small system refunds
        if (tx.counterparty === 'system' && tx.amt < 0.02) continue;
        totalIn += tx.amt;
      } else {
        totalOut += tx.amt;
      }
    }
    
    const feeRow = db.prepare(`SELECT COALESCE(SUM(max_fee), 0) as total FROM (SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee FROM transactions WHERE wallet_id = ? GROUP BY tx_hash)`).get(w.id);
    const fees = feeRow?.total || 0;
    
    const computed = totalIn - totalOut - fees;
    const diff = computed - info.balance;
    const adjustedDiff = diff - info.storageCost;
    
    if (Math.abs(adjustedDiff) >= 0.1) {
      mismatched.push({
        account: w.account_id,
        walletId: w.id,
        onChain: info.balance,
        computed: computed,
        storage: info.storageCost,
        adjustedDiff: adjustedDiff
      });
    }
  }
  
  console.log('Mismatched wallets (after storage adjustment, >0.1 NEAR):');
  mismatched.sort((a, b) => Math.abs(b.adjustedDiff) - Math.abs(a.adjustedDiff));
  mismatched.slice(0, 15).forEach(m => {
    console.log(`  ${m.account}:`);
    console.log(`    onChain=${m.onChain.toFixed(2)}, computed=${m.computed.toFixed(2)}, storage=${m.storage.toFixed(2)}, adjDiff=${m.adjustedDiff.toFixed(2)}`);
  });
  console.log(`\nTotal mismatched: ${mismatched.length}`);
}

main();
