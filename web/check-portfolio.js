const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const userId = 1;

// Get staking positions - convert from yoctoNEAR
const stakingResult = db.prepare(`
  SELECT SUM(staked_amount) as total_staked
  FROM staking_positions 
  WHERE wallet_id IN (SELECT id FROM wallets WHERE user_id = ?)
`).get(userId);
const stakedNear = Number(stakingResult?.total_staked || 0) / 1e24;
console.log("DB staked balance (NEAR):", stakedNear);

// Check all tables
const tables = db.prepare("SELECT name FROM sqlite_master WHERE type = ?").all("table");
console.log("All tables:", tables.map(t => t.name).join(", "));

// Check portfolio/history values
const hasHistory = tables.some(t => t.name === "portfolio_history");
if (hasHistory) {
  const history = db.prepare(`SELECT * FROM portfolio_history WHERE user_id = ? ORDER BY date DESC LIMIT 2`).all(userId);
  console.log("Recent history:", JSON.stringify(history, null, 2));
} else {
  console.log("No portfolio_history table");
}
