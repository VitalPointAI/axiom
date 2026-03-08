const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// First check the schema
const cols = db.prepare("PRAGMA table_info(wallets)").all();
console.log("Wallet columns:", cols.map(c => c.name).join(", "));

const mismatched = ["vpacademy.cdao.near", "key-recovery.credz.near", "aaron.near", "vitalpointai1.near"];

for (const addr of mismatched) {
  console.log("\n========================================");
  console.log("WALLET:", addr);
  console.log("========================================");
  
  // Find wallet by account_id
  const wallet = db.prepare("SELECT * FROM wallets WHERE account_id = ?").get(addr);
  if (!wallet) { 
    console.log("NOT FOUND");
    continue; 
  }
  
  // Get RPC balance and storage
  const rpc = db.prepare("SELECT * FROM rpc_balances WHERE wallet_id = ? ORDER BY fetched_at DESC LIMIT 1").get(wallet.id);
  const rpcBalance = rpc?.available_balance ? Number(rpc.available_balance) / 1e24 : 0;
  const storageBytes = rpc?.storage_usage || 0;
  const storageCost = storageBytes * 1e-5;
  
  console.log("\nRPC Balance:", rpcBalance.toFixed(6), "NEAR");
  console.log("Storage Usage:", storageBytes, "bytes");
  console.log("Storage Cost:", storageCost.toFixed(6), "NEAR (locked, NOT outflow)");
  
  // Get the wallet account ID for self-transfer exclusion
  const walletAddr = wallet.account_id;
  
  // Calculate IN/OUT/FEES
  const inSum = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) as total 
    FROM transactions 
    WHERE wallet_id = ? AND direction = 'in' AND counterparty != ?
  `).get(wallet.id, walletAddr);
  
  const outSum = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) as total 
    FROM transactions 
    WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
  `).get(wallet.id, walletAddr);
  
  // Unique fees (MAX per tx_hash to avoid double counting)
  const fees = db.prepare(`
    SELECT COALESCE(SUM(max_fee), 0) as total FROM (
      SELECT MAX(CAST(fee AS REAL)) as max_fee FROM transactions 
      WHERE wallet_id = ? AND fee > 0 GROUP BY tx_hash
    )
  `).get(wallet.id);
  
  console.log("\nTransaction Totals:");
  console.log("  IN:", inSum.total.toFixed(6), "NEAR");
  console.log("  OUT:", outSum.total.toFixed(6), "NEAR");
  console.log("  FEES:", fees.total.toFixed(6), "NEAR");
  
  const computed = inSum.total - outSum.total - fees.total;
  const diff = computed - rpcBalance;
  
  console.log("\nComputed Balance:", computed.toFixed(6), "NEAR");
  console.log("On-Chain Balance:", rpcBalance.toFixed(6), "NEAR");
  console.log("Difference:", diff.toFixed(6), "NEAR");
  
  if (diff > 0) {
    console.log("  -> We computed MORE than on-chain = MISSING OUTFLOW");
  } else {
    console.log("  -> We computed LESS than on-chain = MISSING INFLOW");
  }
  
  // Check if storage explains it
  if (Math.abs(Math.abs(diff) - storageCost) < 0.01) {
    console.log("\n⚠️  STORAGE EXPLAINS THE DIFFERENCE!");
    console.log("    diff ≈ storage_cost");
  }
  
  // Check storage_deposit transactions
  const storageTxs = db.prepare(`
    SELECT tx_hash, method_name, CAST(amount AS REAL) as amount, direction, counterparty
    FROM transactions 
    WHERE wallet_id = ? AND method_name LIKE '%storage%'
    ORDER BY timestamp DESC LIMIT 10
  `).all(wallet.id);
  
  if (storageTxs.length > 0) {
    console.log("\nStorage-related transactions:");
    let storageOut = 0;
    storageTxs.forEach(t => {
      console.log("  ", t.method_name, t.direction, t.amount.toFixed(4), "NEAR ->", t.counterparty?.substring(0,25));
      if (t.direction === 'out') storageOut += t.amount;
    });
    console.log("  Total storage_deposit OUT:", storageOut.toFixed(4), "NEAR");
  }
  
  // Check system transfers
  const systemTxs = db.prepare(`
    SELECT tx_hash, CAST(amount AS REAL) as amount, direction, action_type
    FROM transactions 
    WHERE wallet_id = ? AND counterparty = 'system'
    ORDER BY amount DESC LIMIT 10
  `).all(wallet.id);
  
  if (systemTxs.length > 0) {
    console.log("\nSystem transfers (potential gas refunds):");
    let systemIn = 0;
    systemTxs.forEach(t => {
      console.log("  ", t.action_type, t.direction, t.amount.toFixed(6), "NEAR");
      if (t.direction === 'in') systemIn += t.amount;
    });
    console.log("  Total system IN:", systemIn.toFixed(6), "NEAR");
  }
  
  // Check if there are filtered small refunds
  const smallRefunds = db.prepare(`
    SELECT COUNT(*) as cnt, SUM(CAST(amount AS REAL)) as total
    FROM transactions 
    WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in' AND CAST(amount AS REAL) < 0.02
  `).get(wallet.id);
  
  if (smallRefunds.cnt > 0) {
    console.log("\nSmall system refunds (<0.02 NEAR):", smallRefunds.cnt, "txs totaling", smallRefunds.total.toFixed(6), "NEAR");
  }
  
  // Check CREATE_ACCOUNT funding
  const createAccounts = db.prepare(`
    SELECT tx_hash, CAST(amount AS REAL) as amount, direction, counterparty
    FROM transactions 
    WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT'
  `).all(wallet.id);
  
  if (createAccounts.length > 0) {
    console.log("\nCREATE_ACCOUNT transactions:");
    createAccounts.forEach(t => {
      console.log("  ", t.direction, t.amount.toFixed(4), "NEAR", "counterparty:", t.counterparty);
    });
  }
  
  // Recent large transactions for context
  const recentLarge = db.prepare(`
    SELECT tx_hash, action_type, method_name, counterparty, CAST(amount AS REAL) as amount, direction
    FROM transactions 
    WHERE wallet_id = ? AND CAST(amount AS REAL) > 0.5
    ORDER BY timestamp DESC LIMIT 5
  `).all(wallet.id);
  
  if (recentLarge.length > 0) {
    console.log("\nRecent large transactions (>0.5 NEAR):");
    recentLarge.forEach(t => {
      console.log("  ", t.direction.toUpperCase(), t.amount.toFixed(4), t.action_type, t.method_name || "", "->", t.counterparty?.substring(0,25));
    });
  }
}

db.close();
