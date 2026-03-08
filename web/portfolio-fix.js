const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_DECIMALS = 1e24;

async function fetchBalance(accountId) {
  try {
    const resp = await fetch('https://rpc.fastnear.com', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 'dontcare',
        method: 'query',
        params: {
          request_type: 'view_account',
          finality: 'final',
          account_id: accountId,
        },
      }),
    });
    const data = await resp.json();
    if (data.result) {
      return Number(data.result.amount) / NEAR_DECIMALS;
    }
    return null;
  } catch (e) {
    return null;
  }
}

async function main() {
  // Get all wallets
  const wallets = db.prepare("SELECT id, account_id FROM wallets").all();
  
  console.log("Fetching current RPC balances for all wallets...\n");
  
  let totalRpc = 0;
  const balances = [];
  
  for (const w of wallets) {
    const balance = await fetchBalance(w.account_id);
    if (balance !== null) {
      totalRpc += balance;
      balances.push({ id: w.id, account: w.account_id, balance });
      if (balance > 10) {
        console.log(`${w.account_id}: ${balance.toFixed(2)} NEAR`);
      }
    } else {
      console.log(`${w.account_id}: NOT FOUND (deleted or no funds)`);
    }
  }
  
  console.log(`\n=== TOTAL PORTFOLIO (RPC) ===`);
  console.log(`Total: ${totalRpc.toFixed(2)} NEAR`);
  console.log(`Wallets: ${wallets.length}`);
  
  // Compare with computed
  const computedTotal = db.prepare(`
    SELECT 
      SUM(CASE WHEN LOWER(direction)='in' THEN CAST(amount AS REAL) ELSE 0 END) / ${NEAR_DECIMALS} -
      SUM(CASE WHEN LOWER(direction)='out' THEN CAST(amount AS REAL) ELSE 0 END) / ${NEAR_DECIMALS} -
      SUM(CASE WHEN LOWER(direction)='out' THEN CAST(fee AS REAL) ELSE 0 END) / ${NEAR_DECIMALS} as total
    FROM transactions
  `).get();
  
  console.log(`Computed from txs: ${computedTotal.total.toFixed(2)} NEAR`);
  console.log(`Difference: ${(totalRpc - computedTotal.total).toFixed(2)} NEAR`);
  
  // The issue: internal transfers are double counted
  // Let's check how much is internal transfers
  const internalTransfers = db.prepare(`
    SELECT 
      SUM(CAST(amount AS REAL)) / ${NEAR_DECIMALS} as total
    FROM transactions t
    WHERE EXISTS (SELECT 1 FROM wallets WHERE account_id = t.counterparty)
    AND LOWER(direction) = 'in'
  `).get();
  
  console.log(`\nInternal IN transfers (from tracked wallets): ${internalTransfers.total.toFixed(2)} NEAR`);
}

main();
