const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Check if the failed transaction is in our DB
const tx = db.prepare("SELECT * FROM transactions WHERE tx_hash LIKE '896pBse2u7gKK6c%'").all();
console.log("Failed tx 896pBse2u7gKK6c in DB:", tx.length > 0 ? "YES" : "NO");
if (tx.length > 0) console.log(tx);

// Check success field for vitalpointai1.near
const vp1 = db.prepare("SELECT id FROM wallets WHERE account_id = ?").get("vitalpointai1.near");
const successCheck = db.prepare("SELECT tx_hash, success, CAST(amount AS REAL)/1e24 as amt FROM transactions WHERE wallet_id = ?").all(vp1.id);
console.log("\nTransaction success flags:");
successCheck.forEach(t => console.log(t.tx_hash.substring(0,15), "success:", t.success, "amt:", t.amt.toFixed(4)));

db.close();
