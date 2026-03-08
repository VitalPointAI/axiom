const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

console.log("=== FINAL ANALYSIS ===\n");

// 1. credz-operations.near: Check if some FUNCTION_CALL IN are being over-counted
const opsWallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("credz-operations.near");

// Check total TRANSFER IN (should match)
const opsTransferIn = db.prepare(`
  SELECT SUM(CAST(amount AS REAL)/1e24) as total, COUNT(*) as cnt
  FROM transactions WHERE wallet_id = ? AND action_type = 'TRANSFER' AND direction = 'in'
`).get(opsWallet.id);

console.log("credz-operations.near:");
console.log(`  TRANSFER IN: ${opsTransferIn.total?.toFixed(4)} NEAR (${opsTransferIn.cnt}x)`);

// Check if these include small amounts from challenge-coin-nft.credz.near (royalties/fees)
const opsFromNft = db.prepare(`
  SELECT SUM(CAST(amount AS REAL)/1e24) as total, COUNT(*) as cnt
  FROM transactions WHERE wallet_id = ? AND counterparty = 'challenge-coin-nft.credz.near' AND direction = 'in'
`).get(opsWallet.id);
console.log(`  IN from challenge-coin-nft: ${opsFromNft.total?.toFixed(4)} NEAR (${opsFromNft.cnt}x)`);

// The 5.79 NEAR discrepancy - check if this might be from accumulated small system refunds
const opsSystemIn = db.prepare(`
  SELECT SUM(CAST(amount AS REAL)/1e24) as total, COUNT(*) as cnt
  FROM transactions WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in'
`).get(opsWallet.id);
console.log(`  System transfers IN: ${opsSystemIn.total?.toFixed(4)} NEAR (${opsSystemIn.cnt}x)`);
console.log(`  If these are OVER-counted as income, might explain the diff\n`);

// 2. relayer.vitalpointai.near: Check NearBlocks for outbound transfers
console.log("relayer.vitalpointai.near:");
console.log("  The contract creates accounts via Promise::transfer()");
console.log("  These outbound transfers are NOT in the /txns endpoint");
console.log("  Need to backfill from /receipts endpoint\n");

// 3. key-recovery.credz.near: Check what's in vs what it received
const keyWallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("key-recovery.credz.near");

// How much came IN via FUNCTION_CALL
const keyFcIn = db.prepare(`
  SELECT SUM(CAST(amount AS REAL)/1e24) as total, COUNT(*) as cnt
  FROM transactions WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL' AND direction = 'in'
`).get(keyWallet.id);
console.log("key-recovery.credz.near:");
console.log(`  FUNCTION_CALL IN: ${keyFcIn.total?.toFixed(4)} NEAR (${keyFcIn.cnt}x)`);

// Check if there's any system transfer IN
const keySystemIn = db.prepare(`
  SELECT SUM(CAST(amount AS REAL)/1e24) as total, COUNT(*) as cnt
  FROM transactions WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in'
`).get(keyWallet.id);
console.log(`  System IN: ${keySystemIn.total?.toFixed(4)} NEAR (${keySystemIn.cnt}x)`);

// Check CREATE_ACCOUNT IN
const keyCreateIn = db.prepare(`
  SELECT SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT' AND direction = 'in'
`).get(keyWallet.id);
console.log(`  CREATE_ACCOUNT IN: ${keyCreateIn.total?.toFixed(4)} NEAR`);

// Total indexed IN
const keyTotalIn = db.prepare(`
  SELECT SUM(CAST(amount AS REAL)/1e24) as total
  FROM transactions WHERE wallet_id = ? AND direction = 'in' AND counterparty != 'key-recovery.credz.near'
`).get(keyWallet.id);
console.log(`  Total indexed IN: ${keyTotalIn.total?.toFixed(4)} NEAR`);
console.log(`  On-chain: 23.2613 NEAR`);
console.log(`  Missing: ~1.08 NEAR (might be gas refunds from contract execution)\n`);

// 4. credz.near: Similar analysis
console.log("credz.near:");
const credzWallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("credz.near");

const credzSystemIn = db.prepare(`
  SELECT SUM(CAST(amount AS REAL)/1e24) as total, COUNT(*) as cnt
  FROM transactions WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in'
`).get(credzWallet.id);
console.log(`  System IN (DELETE_ACCOUNT refunds): ${credzSystemIn.total?.toFixed(4)} NEAR (${credzSystemIn.cnt}x)`);

// Check if all DELETE_ACCOUNT refunds are captured
const credzDeleteRefunds = db.prepare(`
  SELECT tx_hash, CAST(amount AS REAL)/1e24 as amt
  FROM transactions WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in'
  ORDER BY amt DESC LIMIT 5
`).all(credzWallet.id);
console.log(`  Largest system INs: ${credzDeleteRefunds.map(d => d.amt.toFixed(2)).join(', ')}`);

db.close();
