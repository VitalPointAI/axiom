const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

const NEAR_RPC = 'https://rpc.fastnear.com';
const STALE_BLOCK_THRESHOLD = 10_000_000; // ~1 month of blocks

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
      return {
        balance: parseFloat(data.result.amount) / 1e24,
        storageUsage: data.result.storage_usage || 0,
        blockHeight: data.result.block_height || 187000000
      };
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
    
    const rpcResult = await getAccountInfo(wallet.account_id);
    if (rpcResult === null) continue;
    
    const onChain = rpcResult.balance;
    const storageCost = rpcResult.storageUsage * 1e-5; // 1 NEAR per 100KB
    const currentBlock = rpcResult.blockHeight || 187000000;
    
    // Check if data is stale by looking at indexing progress
    const progress = db.prepare(`
      SELECT status, updated_at FROM indexing_progress WHERE wallet_id = ?
    `).get(wallet.id);
    
    // Data is stale if: no progress record, or status not complete, or updated more than 7 days ago
    let isStale = false;
    if (!progress || progress.status !== 'complete') {
      isStale = true;
    } else if (progress.updated_at) {
      const updatedAt = new Date(progress.updated_at);
      const daysSinceUpdate = (Date.now() - updatedAt.getTime()) / (1000 * 60 * 60 * 24);
      isStale = daysSinceUpdate > 7;
    }
    
    // For display, still calculate block age
    const lastBlock = db.prepare(`
      SELECT MAX(block_height) as h FROM transactions WHERE wallet_id = ?
    `).get(wallet.id);
    const blockAge = currentBlock - (lastBlock.h || 0);
    
    // IN: exclude self-transfers AND exclude system gas refunds
    // System gas refunds are your own gas returned, not income
    // ONLY count system IN if it's a DELETE_ACCOUNT beneficiary transfer
    const inSum = db.prepare(`
      SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
      FROM transactions 
      WHERE wallet_id = ? 
        AND direction = 'in' 
        AND counterparty != ?
        AND counterparty != 'system'
    `).get(wallet.id, wallet.account_id);
    
    // DELETE_ACCOUNT beneficiary transfers (system IN linked to DELETE_ACCOUNT)
    // These ARE income if the deleted account wasn't ours
    const deleteAccountIn = db.prepare(`
      SELECT COALESCE(SUM(CAST(t1.amount AS REAL)/1e24), 0) as total
      FROM transactions t1
      WHERE t1.wallet_id = ?
        AND t1.direction = 'in'
        AND t1.counterparty = 'system'
        AND EXISTS (
          SELECT 1 FROM transactions t2 
          WHERE t2.tx_hash = t1.tx_hash 
            AND t2.action_type = 'DELETE_ACCOUNT'
        )
    `).get(wallet.id);
    
    // OUT: exclude self-transfers
    const outSum = db.prepare(`
      SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
      FROM transactions 
      WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
    `).get(wallet.id, wallet.account_id);
    
    // Fees: only for OUT transactions (we initiated those and paid the gas)
    // IN transactions have fees paid by the caller, not us
    const fees = db.prepare(`
      SELECT COALESCE(SUM(max_fee), 0) as total FROM (
        SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
        FROM transactions WHERE wallet_id = ? AND direction = 'out' GROUP BY tx_hash
      )
    `).get(wallet.id);
    
    // DELETE_ACCOUNT outflows: when this wallet's account was deleted,
    // remaining balance went to beneficiary via system transfer
    const deleteAccountOutflows = db.prepare(`
      SELECT COALESCE(SUM(CAST(t2.amount AS REAL)/1e24), 0) as total
      FROM transactions t1
      JOIN transactions t2 ON t1.tx_hash = t2.tx_hash
      WHERE t1.wallet_id = ?
        AND t1.action_type = 'DELETE_ACCOUNT'
        AND t2.direction = 'in'
        AND t2.counterparty = 'system'
        AND t2.wallet_id != t1.wallet_id
    `).get(wallet.id);
    
    // Verification formula:
    // balance = (regular IN + DELETE_ACCOUNT beneficiary IN) - OUT - fees - DELETE_ACCOUNT_outflows
    const totalIn = inSum.total + deleteAccountIn.total;
    const computed = totalIn - outSum.total - fees.total - deleteAccountOutflows.total;
    const diff = computed - onChain;
    
    // Calculate available balance (on-chain minus locked storage)
    const available = onChain - storageCost;
    const diffVsAvailable = computed - available;
    
    // Use total balance for tolerance check (storage is owned NEAR)
    const tolerance = 0.5;
    if (Math.abs(diff) < tolerance) {
      matching++;
    } else {
      mismatched++;
      issues.push({
        account: wallet.account_id,
        onChain: onChain.toFixed(4),
        available: available.toFixed(4),
        computed: computed.toFixed(4),
        diffVsTotal: diff.toFixed(4),
        diffVsAvailable: diffVsAvailable.toFixed(4),
        regularIn: inSum.total.toFixed(4),
        deleteIn: deleteAccountIn.total.toFixed(4),
        out: outSum.total.toFixed(4),
        fees: fees.total.toFixed(4),
        deleteOutflows: deleteAccountOutflows.total.toFixed(4),
        storage: storageCost.toFixed(4),
        isStale,
        blockAge: Math.round(blockAge / 1000000)
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
    const staleIssues = issues.filter(i => i.isStale);
    const freshIssues = issues.filter(i => !i.isStale);
    
    if (freshIssues.length > 0) {
      console.log("\n❌ Mismatched wallets (fresh data):");
      freshIssues.sort((a, b) => Math.abs(parseFloat(b.diffVsAvailable)) - Math.abs(parseFloat(a.diffVsAvailable)));
      freshIssues.forEach(i => {
        console.log(`\n  ${i.account}:`);
        console.log(`    on-chain: ${i.onChain}, storage: ${i.storage}, available: ${i.available}`);
        console.log(`    computed: ${i.computed}`);
        console.log(`    diff vs total: ${i.diffVsTotal}, diff vs available: ${i.diffVsAvailable}`);
        console.log(`    in: ${i.regularIn} (+ ${i.deleteIn} from DELETE_ACCOUNT)`);
        console.log(`    out: ${i.out}, fees: ${i.fees}`);
      });
    }
    
    if (staleIssues.length > 0) {
      console.log("\n⚠️ Mismatched wallets (STALE DATA - needs resync):");
      staleIssues.sort((a, b) => b.blockAge - a.blockAge);
      staleIssues.forEach(i => {
        console.log(`  ${i.account}: ~${i.blockAge}M blocks behind, diff: ${i.diff} NEAR`);
      });
    }
  }
}

verify().then(() => db.close());
