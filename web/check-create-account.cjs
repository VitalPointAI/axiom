const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const wallet = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("challenge-coin-nft.credz.near");

// Get all CREATE_ACCOUNT transactions
const creates = db.prepare(`
  SELECT tx_hash, direction, counterparty, CAST(amount AS REAL)/1e24 as amt, raw_json
  FROM transactions 
  WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT'
  ORDER BY id
`).all(wallet.id);

console.log(`Found ${creates.length} CREATE_ACCOUNT transactions:\n`);

creates.forEach((c, i) => {
  console.log(`${i+1}. TX: ${c.tx_hash.substring(0, 20)}...`);
  console.log(`   Direction: ${c.direction}, Amount: ${c.amt.toFixed(4)} NEAR`);
  console.log(`   Counterparty: ${c.counterparty}`);
  
  // Parse raw_json to see the actual structure
  if (c.raw_json && i < 3) {  // Only show first 3 for brevity
    try {
      // Handle Python dict format
      const rawStr = c.raw_json.replace(/'/g, '"').replace(/None/g, 'null').replace(/True/g, 'true').replace(/False/g, 'false');
      const raw = JSON.parse(rawStr);
      console.log(`   predecessor: ${raw.predecessor_account_id}`);
      console.log(`   receiver: ${raw.receiver_account_id}`);
    } catch (e) {
      console.log(`   (couldn't parse raw_json)`);
    }
  }
  console.log();
});

db.close();
