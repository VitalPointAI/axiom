const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_DECIMALS = 1e24;

async function getOnChainBalance(account) {
  try {
    const res = await fetch('https://rpc.fastnear.com', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 'balance', method: 'query',
        params: { request_type: 'view_account', finality: 'final', account_id: account }
      })
    });
    const data = await res.json();
    return data.result ? parseFloat(data.result.amount) / 1e24 : 0;
  } catch {
    return 0;
  }
}

async function main() {
  // Get user 1's wallets (the test user)
  const session = db.prepare("SELECT u.id FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.expires_at > datetime('now') LIMIT 1").get();
  const userId = session.id;
  console.log("User ID:", userId);

  const wallets = db.prepare("SELECT id, account_id FROM wallets WHERE user_id = ? AND chain = 'NEAR'")
    .all(userId);
  console.log("Wallets:", wallets.length);

  // Get current RPC balances
  let currentOnChain = 0;
  for (const w of wallets) {
    const bal = await getOnChainBalance(w.account_id);
    currentOnChain += bal;
    if (bal > 1) console.log(`  ${w.account_id}: ${bal.toFixed(2)}`);
  }
  console.log("\nTotal On-Chain:", currentOnChain.toFixed(2));

  // Get current staking balance
  const staking = db.prepare(`
    SELECT COALESCE(SUM(CAST(staked_amount as REAL)/1e24), 0) as total
    FROM staking_positions sp
    JOIN wallets w ON sp.wallet_id = w.id
    WHERE w.user_id = ?
  `).get(userId);
  console.log("Staking positions:", staking.total.toFixed(2));

  // Check if staking_positions has data
  const positions = db.prepare(`
    SELECT sp.validator_id, CAST(sp.staked_amount AS REAL)/1e24 as staked, w.account_id
    FROM staking_positions sp
    JOIN wallets w ON sp.wallet_id = w.id
    WHERE w.user_id = ?
  `).all(userId);
  console.log("\nStaking positions detail:");
  positions.forEach(p => console.log(`  ${p.account_id} -> ${p.validator_id}: ${p.staked?.toFixed(2)}`));

  console.log("\nTotal Portfolio NEAR:", (currentOnChain + staking.total).toFixed(2));
}

main();
