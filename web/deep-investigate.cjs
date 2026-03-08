const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

console.log("=== CREDZ-OPERATIONS.NEAR ===");
console.log("Issue: +5.79 NEAR missing outflow\n");

const opsWallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("credz-operations.near");

// The FUNCTION_CALL OUT has 21.80 NEAR attached - where does this go?
const fcOut = db.prepare(`
  SELECT counterparty, method_name, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL' AND direction = 'out'
  GROUP BY counterparty, method_name
  ORDER BY total DESC
  LIMIT 10
`).all(opsWallet.id);

console.log("FUNCTION_CALL OUT breakdown:");
fcOut.forEach(f => console.log(`  ${f.total.toFixed(4)} NEAR -> ${f.counterparty} (${f.method_name}) x${f.cnt}`));

// Check if there are any INflows from the same contracts (refunds)
const fcInFromSame = db.prepare(`
  SELECT counterparty, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE wallet_id = ? AND direction = 'in' AND counterparty IN (
    SELECT DISTINCT counterparty FROM transactions WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL' AND direction = 'out'
  )
  GROUP BY counterparty
  ORDER BY total DESC
`).all(opsWallet.id, opsWallet.id);

console.log("\nINflows from same contracts:");
fcInFromSame.forEach(f => console.log(`  ${f.total.toFixed(4)} NEAR <- ${f.counterparty}`));

// Net flow to each contract
console.log("\nNet flow analysis for top contracts:");
const topCounterparties = fcOut.slice(0, 5).map(f => f.counterparty);
for (const cp of topCounterparties) {
  const outTo = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions WHERE wallet_id = ? AND direction = 'out' AND counterparty = ?
  `).get(opsWallet.id, cp);
  
  const inFrom = db.prepare(`
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
    FROM transactions WHERE wallet_id = ? AND direction = 'in' AND counterparty = ?
  `).get(opsWallet.id, cp);
  
  const net = outTo.total - inFrom.total;
  console.log(`  ${cp}: OUT ${outTo.total.toFixed(4)}, IN ${inFrom.total.toFixed(4)}, NET ${net > 0 ? '-' : '+'}${Math.abs(net).toFixed(4)}`);
}

console.log("\n\n=== RELAYER.VITALPOINTAI.NEAR ===");
console.log("Issue: +1.65 NEAR missing outflow (contract)\n");

const relayerWallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("relayer.vitalpointai.near");

// Check FUNCTION_CALL methods
const relayerFc = db.prepare(`
  SELECT method_name, direction, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL'
  GROUP BY method_name, direction
  ORDER BY total DESC
`).all(relayerWallet.id);

console.log("FUNCTION_CALL breakdown:");
relayerFc.forEach(f => console.log(`  ${f.direction} ${f.method_name}: ${f.total.toFixed(4)} NEAR x${f.cnt}`));

// The relayer creates accounts - check if we have those outflows
const relayerTransfersOut = db.prepare(`
  SELECT counterparty, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE wallet_id = ? AND direction = 'out' AND action_type = 'TRANSFER'
  GROUP BY counterparty
`).all(relayerWallet.id);

console.log("\nTRANSFER OUT:");
if (relayerTransfersOut.length === 0) {
  console.log("  None found! This is the missing outflow - contract sends NEAR via Promise::transfer()");
} else {
  relayerTransfersOut.forEach(t => console.log(`  ${t.total.toFixed(4)} NEAR -> ${t.counterparty} x${t.cnt}`));
}

// Check the TRANSFER INs - these might be returns from failed create_account
const relayerTransfersIn = db.prepare(`
  SELECT counterparty, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE wallet_id = ? AND direction = 'in' AND action_type = 'TRANSFER'
  GROUP BY counterparty
  ORDER BY total DESC
  LIMIT 5
`).all(relayerWallet.id);

console.log("\nTRANSFER IN (might include refunds from failed creates):");
relayerTransfersIn.forEach(t => console.log(`  ${t.total.toFixed(4)} NEAR <- ${t.counterparty} x${t.cnt}`));

console.log("\n\n=== KEY-RECOVERY.CREDZ.NEAR ===");
console.log("Issue: -1.08 NEAR missing inflow (contract)\n");

const keyWallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("key-recovery.credz.near");

// Check what FUNCTION_CALL methods are receiving NEAR
const keyFc = db.prepare(`
  SELECT method_name, direction, COUNT(*) as cnt, SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions 
  WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL'
  GROUP BY method_name, direction
  ORDER BY total DESC
`).all(keyWallet.id);

console.log("FUNCTION_CALL breakdown:");
keyFc.forEach(f => console.log(`  ${f.direction} ${f.method_name}: ${f.total.toFixed(4)} NEAR x${f.cnt}`));

// Check if there might be receipt-level transfers IN that we missed
console.log("\nPossible sources of missing 1.08 NEAR inflow:");
console.log("  - Gas refunds from contract execution");
console.log("  - Receipt-level transfers from other contracts");
console.log("  - Storage deposit refunds");

db.close();
