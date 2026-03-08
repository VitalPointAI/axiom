const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Get raw JSON for the relayer transactions
const vp1 = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("vitalpointai1.near");
const txs = db.prepare("SELECT tx_hash, raw_json FROM transactions WHERE wallet_id = ? AND counterparty = 'relayer.vitalpointai.near'").all(vp1.id);

txs.forEach(t => {
  console.log("\n=== TX:", t.tx_hash.substring(0, 20), "===");
  if (t.raw_json) {
    const raw = JSON.parse(t.raw_json);
    // Show relevant parts
    console.log("predecessor:", raw.predecessor_account_id);
    console.log("receiver:", raw.receiver_account_id);
    console.log("actions:", JSON.stringify(raw.actions, null, 2));
    console.log("actions_agg:", raw.actions_agg);
  } else {
    console.log("No raw_json stored");
  }
});

db.close();
