const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_DECIMALS = 1e24;
const TOLERANCE = 0.5;

async function fetchBalance(accountId) {
  try {
    const resp = await fetch('https://rpc.fastnear.com', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 'dontcare',
        method: 'query',
        params: { request_type: 'view_account', finality: 'final', account_id: accountId },
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

async function verifyWallet(wallet) {
  const onChain = await fetchBalance(wallet.account_id);
  if (onChain === null) return { account: wallet.account_id, status: 'DELETED' };

  // IN: exclude self-transfers AND system gas refunds
  const inSum = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
    FROM transactions 
    WHERE wallet_id = ? 
      AND direction = 'in' 
      AND counterparty != ?
      AND counterparty != 'system'
  `).get(wallet.id, wallet.account_id);

  // DELETE_ACCOUNT beneficiary transfers
  const deleteAccountIn = db.prepare(`
    SELECT COALESCE(SUM(CAST(t1.amount AS REAL)/1e24), 0) as total
    FROM transactions t1
    WHERE t1.wallet_id = ?
      AND t1.direction = 'in'
      AND t1.counterparty = 'system'
      AND EXISTS (
        SELECT 1 FROM transactions t2 
        WHERE t2.tx_hash = t1.tx_hash 
          AND t2.action_type = 'DELETE_ACCOUNT'
      )
  `).get(wallet.id);

  // OUT: exclude self-transfers
  const outSum = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
    FROM transactions 
    WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
  `).get(wallet.id, wallet.account_id);

  // Fees: only for OUT direction
  const fees = db.prepare(`
    SELECT COALESCE(SUM(max_fee), 0) as total FROM (
      SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
      FROM transactions WHERE wallet_id = ? AND direction = 'out' GROUP BY tx_hash
    )
  `).get(wallet.id);

  // DELETE_ACCOUNT outflows
  const deleteAccountOutflows = db.prepare(`
    SELECT COALESCE(SUM(CAST(t2.amount AS REAL)/1e24), 0) as total
    FROM transactions t1
    JOIN transactions t2 ON t1.tx_hash = t2.tx_hash
    WHERE t1.wallet_id = ?
      AND t1.action_type = 'DELETE_ACCOUNT'
      AND t2.direction = 'in'
      AND t2.counterparty = 'system'
      AND t2.wallet_id != t1.wallet_id
  `).get(wallet.id);

  const totalIn = inSum.total + deleteAccountIn.total;
  const computed = totalIn - outSum.total - fees.total - deleteAccountOutflows.total;
  const diff = computed - onChain;
  const status = Math.abs(diff) < TOLERANCE ? '✅' : '❌';

  return {
    account: wallet.account_id,
    onChain: onChain.toFixed(2),
    computed: computed.toFixed(2),
    diff: diff.toFixed(2),
    status,
    details: {
      in: inSum.total.toFixed(2),
      deleteIn: deleteAccountIn.total.toFixed(2),
      out: outSum.total.toFixed(2),
      fees: fees.total.toFixed(4),
      deleteOut: deleteAccountOutflows.total.toFixed(2)
    }
  };
}

async function main() {
  const credz = db.prepare("SELECT id, account_id FROM wallets WHERE account_id LIKE '%credz%' ORDER BY account_id").all();
  
  console.log("CREDZ ECOSYSTEM VERIFICATION\n");
  console.log("=".repeat(80));
  
  let matched = 0, mismatched = 0;
  
  for (const wallet of credz) {
    const result = await verifyWallet(wallet);
    
    if (result.status === 'DELETED') {
      console.log(`${result.account}: DELETED`);
      continue;
    }
    
    if (result.status === '✅') matched++;
    else mismatched++;
    
    console.log(`\n${result.status} ${result.account}`);
    console.log(`   RPC: ${result.onChain} | Computed: ${result.computed} | Diff: ${result.diff}`);
    if (Math.abs(parseFloat(result.diff)) >= TOLERANCE) {
      console.log(`   IN: ${result.details.in} + DeleteIn: ${result.details.deleteIn}`);
      console.log(`   OUT: ${result.details.out} + Fees: ${result.details.fees} + DeleteOut: ${result.details.deleteOut}`);
    }
  }
  
  console.log("\n" + "=".repeat(80));
  console.log(`SUMMARY: ${matched} matched, ${mismatched} mismatched`);
}

main();
