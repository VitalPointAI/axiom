const Database = require("better-sqlite3");
const db = new Database("/home/deploy/neartax/neartax.db");

// Check NEAR transactions with no price
const sample = db.prepare(`
  SELECT id, block_timestamp, amount, asset 
  FROM transactions 
  WHERE (cost_basis_usd IS NULL OR cost_basis_usd = 0) 
  AND (asset IS NULL OR asset = "NEAR")
  AND CAST(amount AS REAL) > 0
  LIMIT 5
`).all();

console.log("Sample NEAR transactions without prices:");
sample.forEach(t => {
  const amt = (Number(t.amount) / 1e24).toFixed(4);
  const date = new Date(Number(t.block_timestamp) / 1000000).toISOString().split("T")[0];
  console.log("  id:", t.id, "date:", date, "amount:", amt, "NEAR");
});

// Check if dates have prices
console.log("\nChecking price availability:");
for (const t of sample) {
  const date = new Date(Number(t.block_timestamp) / 1000000).toISOString().split("T")[0];
  const price = db.prepare("SELECT price FROM price_cache WHERE coin_id = ? AND date LIKE ?").get("NEAR", date + "%");
  console.log("  ", date, price ? "$" + price.price.toFixed(2) : "NO PRICE");
}
