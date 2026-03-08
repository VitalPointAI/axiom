const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_DECIMALS = 1e24;

// Get credz wallets with their current RPC balances
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
      return {
        balance: Number(data.result.amount) / NEAR_DECIMALS,
        storage: data.result.storage_usage
      };
    }
    return { balance: null, storage: 0 };
  } catch (e) {
    return { balance: null, storage: 0 };
  }
}

// Get tracked wallet set
const trackedWallets = new Set(
  db.prepare("SELECT account_id FROM wallets").all().map(w => w.account_id)
);

async function analyzeWallet(wallet) {
  const rpcData = await fetchBalance(wallet.account_id);
  
  // Get external-only transactions (to/from non-tracked accounts)
  const externalStats = db.prepare(`
    SELECT 
      SUM(CASE WHEN LOWER(direction) = 'in' AND counterparty NOT IN (${Array(trackedWallets.size).fill('?').join(',')}) THEN CAST(amount AS REAL) / ${NEAR_DECIMALS} ELSE 0 END) as ext_in,
      SUM(CASE WHEN LOWER(direction) = 'out' AND counterparty NOT IN (${Array(trackedWallets.size).fill('?').join(',')}) THEN CAST(amount AS REAL) / ${NEAR_DECIMALS} ELSE 0 END) as ext_out,
      SUM(CASE WHEN LOWER(direction) = 'out' THEN CAST(fee AS REAL) / ${NEAR_DECIMALS} ELSE 0 END) as fees
    FROM transactions WHERE wallet_id = ?
  `).get([...trackedWallets, ...trackedWallets, wallet.id]);
  
  // Get CREATE_ACCOUNT outflows
  const createAccountOut = db.prepare(`
    SELECT SUM(CAST(amount AS REAL) / ${NEAR_DECIMALS}) as total
    FROM transactions 
    WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT' AND LOWER(direction) = 'out'
  `).get(wallet.id);
  
  // Get DELETE_ACCOUNT beneficiary inflows
  const deleteAccountIn = db.prepare(`
    SELECT SUM(CAST(amount AS REAL) / ${NEAR_DECIMALS}) as total
    FROM transactions 
    WHERE wallet_id = ? AND action_type IN ('DELETE_ACCOUNT', 'TRANSFER') AND LOWER(direction) = 'in'
    AND counterparty IN (SELECT account_id FROM wallets WHERE account_id LIKE '%.credz.near')
  `).get(wallet.id);
  
  // Check for system transfers (gas refunds, storage refunds)
  const systemIn = db.prepare(`
    SELECT SUM(CAST(amount AS REAL) / ${NEAR_DECIMALS}) as total
    FROM transactions 
    WHERE wallet_id = ? AND counterparty = 'system' AND LOWER(direction) = 'in'
  `).get(wallet.id);
  
  const computed = (externalStats.ext_in || 0) - (externalStats.ext_out || 0) - (externalStats.fees || 0);
  const diff = rpcData.balance ? (computed - rpcData.balance) : null;
  
  return {
    account: wallet.account_id,
    rpc_balance: rpcData.balance?.toFixed(4),
    storage_kb: (rpcData.storage / 1000).toFixed(1),
    ext_in: externalStats.ext_in?.toFixed(4),
    ext_out: externalStats.ext_out?.toFixed(4),
    fees: externalStats.fees?.toFixed(4),
    computed: computed.toFixed(4),
    diff: diff?.toFixed(4),
    create_out: createAccountOut.total?.toFixed(4) || '0',
    delete_in: deleteAccountIn.total?.toFixed(4) || '0',
    system_in: systemIn.total?.toFixed(4) || '0'
  };
}

async function main() {
  const credz = db.prepare("SELECT id, account_id FROM wallets WHERE account_id LIKE '%credz%' OR account_id = 'credz.near'").all();
  
  console.log("CREDZ ECOSYSTEM VERIFICATION ANALYSIS\n");
  console.log("=====================================\n");
  
  for (const wallet of credz) {
    const result = await analyzeWallet(wallet);
    console.log(`${result.account}:`);
    console.log(`  RPC Balance: ${result.rpc_balance || 'DELETED'} NEAR (${result.storage_kb} KB storage)`);
    console.log(`  External IN: ${result.ext_in} | External OUT: ${result.ext_out} | Fees: ${result.fees}`);
    console.log(`  Computed: ${result.computed} | Diff: ${result.diff || 'N/A'}`);
    console.log(`  CREATE_ACCOUNT out: ${result.create_out} | DELETE_ACCOUNT in: ${result.delete_in}`);
    console.log(`  System (refunds) in: ${result.system_in}`);
    console.log();
  }
  
  // Check for any DELETE_ACCOUNT transactions
  const deleteAccounts = db.prepare(`
    SELECT t.*, w.account_id
    FROM transactions t
    JOIN wallets w ON t.wallet_id = w.id
    WHERE t.action_type = 'DELETE_ACCOUNT'
    ORDER BY t.block_timestamp DESC
    LIMIT 20
  `).all();
  
  console.log("\n=== DELETE_ACCOUNT TRANSACTIONS ===\n");
  deleteAccounts.forEach(tx => {
    const amount = Number(tx.amount) / NEAR_DECIMALS;
    console.log(`${tx.account_id} ${tx.direction} ${amount.toFixed(4)} NEAR to/from ${tx.counterparty}`);
  });
}

main();
