const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

console.log("=== Checking Filtered Refunds ===\n");

const wallets = [
  { name: "credz-operations.near", diff: 5.79, issue: "missing outflow" },
  { name: "key-recovery.credz.near", diff: -1.08, issue: "missing inflow" }
];

for (const w of wallets) {
  const wallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get(w.name);
  if (!wallet) continue;
  
  console.log(`\n${w.name} (${w.issue}): ${w.diff} NEAR`);
  
  // Check triggered system refunds (filtered by verification logic)
  // Get FUNCTION_CALL OUT tx_hashes
  const fcTxs = db.prepare(`
    SELECT DISTINCT tx_hash FROM transactions
    WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL' AND direction = 'out'
  `).all(wallet.id);
  
  const triggeredSet = new Set(fcTxs.map(t => t.tx_hash));
  
  // Find system transfers that match these tx_hashes (would be filtered)
  const systemTransfers = db.prepare(`
    SELECT tx_hash, CAST(amount AS REAL)/1e24 as amt
    FROM transactions
    WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in'
  `).all(wallet.id);
  
  let filteredSmall = 0;
  let filteredTriggered = 0;
  let included = 0;
  
  for (const st of systemTransfers) {
    if (st.amt < 0.02) {
      filteredSmall += st.amt;
    } else if (triggeredSet.has(st.tx_hash)) {
      filteredTriggered += st.amt;
    } else {
      included += st.amt;
    }
  }
  
  console.log(`  System transfers IN:`);
  console.log(`    Included (>= 0.02, not triggered): ${included.toFixed(4)} NEAR`);
  console.log(`    Filtered (< 0.02 NEAR): ${filteredSmall.toFixed(4)} NEAR`);
  console.log(`    Filtered (triggered by FUNCTION_CALL): ${filteredTriggered.toFixed(4)} NEAR`);
  console.log(`  Total filtered: ${(filteredSmall + filteredTriggered).toFixed(4)} NEAR`);
  
  if (w.issue === "missing outflow" && (filteredSmall + filteredTriggered) > 0.5) {
    console.log(`  ⚠️  Filtered refunds (${(filteredSmall + filteredTriggered).toFixed(2)}) might explain some of the ${w.diff} NEAR diff!`);
    console.log(`  → These are gas refunds from contract execution, being over-counted as income`);
  }
}

// For key-recovery, check if there are untracked receipt-level transfers IN
console.log("\n\n=== key-recovery.credz.near Receipt Analysis ===");
const keyWallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("key-recovery.credz.near");

// Check the FUNCTION_CALL IN - these include attached deposits
const fcIn = db.prepare(`
  SELECT tx_hash, method_name, counterparty, CAST(amount AS REAL)/1e24 as amt
  FROM transactions 
  WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL' AND direction = 'in'
  ORDER BY amt DESC LIMIT 10
`).all(keyWallet.id);

console.log("\nTop FUNCTION_CALL IN (attached deposits):");
fcIn.forEach(f => console.log(`  ${f.amt.toFixed(4)} NEAR from ${f.counterparty} (${f.method_name})`));

// The missing 1.08 NEAR might be gas refunds from executing owner_store_encrypted_key
// When a contract receives a call with attached deposit, it might refund gas
console.log("\nTheory: Missing 1.08 NEAR is gas refunds from executing 724 FUNCTION_CALLs");
console.log("Average gas refund per call: 1.08 / 724 = 0.0015 NEAR (1.5 mNEAR)");

db.close();
