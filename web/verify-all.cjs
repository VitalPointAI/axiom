const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_RPC = 'https://rpc.mainnet.near.org';

async function getAccountInfo(account) {
  try {
    const res = await fetch(NEAR_RPC, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 'verify', method: 'query',
        params: { request_type: 'view_account', finality: 'final', account_id: account }
      })
    });
    const data = await res.json();
    if (data.result) {
      return parseFloat(data.result.amount) / 1e24;
    }
    return null;
  } catch {
    return null;
  }
}

// Get all NEAR wallets (excluding pools)
const wallets = db.prepare(`
  SELECT id, account_id FROM wallets 
  WHERE chain = 'NEAR' 
    AND account_id NOT LIKE '%.pool%'
    AND account_id NOT LIKE '%.poolv1%'
`).all();

const allWalletIds = wallets.map(w => w.id);

async function verify() {
  let matching = 0;
  let mismatched = 0;
  const issues = [];
  
  console.log(`Verifying ${wallets.length} wallets...\n`);
  
  for (let i = 0; i < wallets.length; i++) {
    const wallet = wallets[i];
    
    // Rate limiting
    if (i > 0 && i % 10 === 0) {
      await new Promise(r => setTimeout(r, 500));
    }
    
    const onChain = await getAccountInfo(wallet.account_id);
    if (onChain === null) continue;
    
    // Compute balance (simplified - same logic as verify route)
    const inSum = db.prepare(`
      SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
      FROM transactions 
      WHERE wallet_id = ? AND direction = 'in' AND counterparty != ?
    `).get(wallet.id, wallet.account_id);
    
    const outSum = db.prepare(`
      SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
      FROM transactions 
      WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
    `).get(wallet.id, wallet.account_id);
    
    const fees = db.prepare(`
      SELECT COALESCE(SUM(max_fee), 0) as total FROM (
        SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
        FROM transactions WHERE wallet_id = ? GROUP BY tx_hash
      )
    `).get(wallet.id);
    
    const computed = inSum.total - outSum.total - fees.total;
    const diff = computed - onChain;
    
    const tolerance = 0.5;
    if (Math.abs(diff) < tolerance) {
      matching++;
    } else {
      mismatched++;
      issues.push({
        account: wallet.account_id,
        onChain: onChain.toFixed(4),
        computed: computed.toFixed(4),
        diff: diff.toFixed(4)
      });
    }
    
    // Progress
    if ((i + 1) % 10 === 0 || i === wallets.length - 1) {
      process.stdout.write(`\r  Checked ${i + 1}/${wallets.length} - ✅ ${matching} matching, ❌ ${mismatched} mismatched`);
    }
  }
  
  console.log("\n\n📊 VERIFICATION SUMMARY:");
  console.log(`  ✅ Matching: ${matching}`);
  console.log(`  ❌ Mismatched: ${mismatched}`);
  console.log(`  Total: ${wallets.length}`);
  
  if (issues.length > 0) {
    console.log("\n❌ Mismatched wallets:");
    issues.sort((a, b) => Math.abs(parseFloat(b.diff)) - Math.abs(parseFloat(a.diff)));
    issues.forEach(i => {
      console.log(`  ${i.account}: diff ${i.diff} NEAR (on-chain: ${i.onChain}, computed: ${i.computed})`);
    });
  }
}

verify().then(() => db.close());
