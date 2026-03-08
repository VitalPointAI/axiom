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
      const storageUsage = data.result.storage_usage || 0;
      return {
        balance: parseFloat(data.result.amount) / 1e24,
        storageUsage,
        storageCost: storageUsage * 1e-5,
        hasContract: data.result.code_hash !== '11111111111111111111111111111111'
      };
    }
    return null;
  } catch (e) {
    console.error("RPC error for", account, e.message);
    return null;
  }
}

// Get all wallet IDs for cross-wallet DELETE_ACCOUNT tracking
const allWallets = db.prepare("SELECT id, account_id FROM wallets WHERE chain = 'NEAR'").all();
const allWalletIds = allWallets.map(w => w.id);

const mismatched = ["vpacademy.cdao.near", "key-recovery.credz.near", "aaron.near", "vitalpointai1.near"];

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function analyze() {
  for (const addr of mismatched) {
    await sleep(500); // Rate limit protection
    console.log("\n" + "=".repeat(60));
    console.log("WALLET:", addr);
    console.log("=".repeat(60));
    
    const wallet = db.prepare("SELECT * FROM wallets WHERE account_id = ?").get(addr);
    if (!wallet) { 
      console.log("NOT FOUND");
      continue; 
    }
    
    // Get RPC balance
    const info = await getAccountInfo(addr);
    if (!info) {
      console.log("Could not fetch RPC balance");
      continue;
    }
    
    console.log("\n📊 ON-CHAIN STATE:");
    console.log("  Balance:", info.balance.toFixed(6), "NEAR");
    console.log("  Storage:", info.storageUsage, "bytes =", info.storageCost.toFixed(6), "NEAR locked");
    console.log("  Has Contract:", info.hasContract);
    
    // === COMPUTE BALANCE (same logic as verify route) ===
    
    // Get all txs where this wallet has a FUNCTION_CALL out (triggers system refunds)
    const triggeredTxs = new Set();
    const fcRows = db.prepare(`
      SELECT DISTINCT tx_hash FROM transactions
      WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL' AND direction = 'out'
    `).all(wallet.id);
    fcRows.forEach(r => triggeredTxs.add(r.tx_hash));

    // Get DELETE_ACCOUNT tx_hashes from this wallet
    const deleteAccountTxs = new Set();
    const deleteRows = db.prepare(`
      SELECT tx_hash FROM transactions
      WHERE wallet_id = ? AND action_type = 'DELETE_ACCOUNT' AND direction = 'out'
    `).all(wallet.id);
    deleteRows.forEach(r => deleteAccountTxs.add(r.tx_hash));

    // For DELETE_ACCOUNT, find corresponding system transfers to beneficiaries
    let deleteAccountOutflows = 0;
    if (deleteAccountTxs.size > 0) {
      const placeholders = Array.from(deleteAccountTxs).map(() => '?').join(',');
      const beneficiaryTransfers = db.prepare(`
        SELECT tx_hash, CAST(amount AS REAL)/1e24 as amt, wallet_id
        FROM transactions
        WHERE tx_hash IN (${placeholders})
          AND counterparty = 'system'
          AND direction = 'in'
          AND wallet_id IN (${allWalletIds.join(',')})
          AND wallet_id != ?
      `).all(...Array.from(deleteAccountTxs), wallet.id);
      
      for (const t of beneficiaryTransfers) {
        deleteAccountOutflows += t.amt;
        console.log(`  DELETE_ACCOUNT outflow: ${t.amt.toFixed(4)} NEAR (tx: ${t.tx_hash.substring(0,10)}...)`);
      }
    }

    // Get CREATE_ACCOUNT outflows
    const createAccountOutflows = db.prepare(`
      SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total
      FROM transactions
      WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT' AND direction = 'out'
    `).get(wallet.id);

    // Get all transactions and compute
    const txRows = db.prepare(`
      SELECT tx_hash, counterparty, direction, action_type, CAST(amount AS REAL)/1e24 as amt
      FROM transactions WHERE wallet_id = ?
    `).all(wallet.id);

    let totalIn = 0;
    let totalOut = 0;
    const GAS_THRESHOLD = 0.02;
    
    let filteredSmallRefunds = 0;
    let filteredTriggeredRefunds = 0;

    for (const { tx_hash, counterparty, direction, action_type, amt } of txRows) {
      if (counterparty === addr) continue; // Skip self-transfers
      
      if (direction === 'in') {
        if (counterparty === 'system') {
          if (amt < GAS_THRESHOLD) {
            filteredSmallRefunds += amt;
            continue;
          }
          if (triggeredTxs.has(tx_hash)) {
            filteredTriggeredRefunds += amt;
            continue;
          }
        }
        totalIn += amt;
      } else {
        if (action_type !== 'CREATE_ACCOUNT') {
          totalOut += amt;
        }
      }
    }

    totalOut += deleteAccountOutflows;
    totalOut += createAccountOutflows.total;

    // Unique fees
    const feeRow = db.prepare(`
      SELECT COALESCE(SUM(max_fee), 0) as total FROM (
        SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
        FROM transactions WHERE wallet_id = ?
        GROUP BY tx_hash
      )
    `).get(wallet.id);
    const uniqueFees = feeRow?.total || 0;

    const computed = totalIn - totalOut - uniqueFees;
    const diff = computed - info.balance;

    console.log("\n📈 TRANSACTION TOTALS:");
    console.log("  IN:", totalIn.toFixed(6), "NEAR");
    console.log("  OUT:", totalOut.toFixed(6), "NEAR");
    console.log("    (includes DELETE_ACCOUNT outflows:", deleteAccountOutflows.toFixed(4), "NEAR)");
    console.log("    (includes CREATE_ACCOUNT outflows:", createAccountOutflows.total.toFixed(4), "NEAR)");
    console.log("  FEES:", uniqueFees.toFixed(6), "NEAR");
    console.log("  Filtered small refunds (<0.02):", filteredSmallRefunds.toFixed(6), "NEAR");
    console.log("  Filtered triggered refunds:", filteredTriggeredRefunds.toFixed(6), "NEAR");

    console.log("\n🎯 VERIFICATION:");
    console.log("  Computed:", computed.toFixed(6), "NEAR");
    console.log("  On-Chain:", info.balance.toFixed(6), "NEAR");
    console.log("  Diff:", diff.toFixed(6), "NEAR");
    
    if (diff > 0) {
      console.log("  → OVER-COUNTED (computed > onchain) = missing outflow");
    } else {
      console.log("  → UNDER-COUNTED (computed < onchain) = missing inflow");
    }

    // DIAGNOSE THE DIFFERENCE
    console.log("\n🔍 DIAGNOSIS:");
    
    // Check if storage_deposit transactions exist
    const storageTxs = db.prepare(`
      SELECT SUM(CAST(amount AS REAL)/1e24) as total, COUNT(*) as cnt
      FROM transactions 
      WHERE wallet_id = ? AND method_name = 'storage_deposit' AND direction = 'out'
    `).get(wallet.id);
    
    if (storageTxs.total > 0) {
      console.log("  storage_deposit OUT:", storageTxs.total.toFixed(4), "NEAR (", storageTxs.cnt, "txs)");
      console.log("    → This is recoverable/refundable, tracked as outflow");
    }
    
    // Check if this is a CDAO (might have bond deposits)
    if (addr.includes('.cdao.near')) {
      const bondTxs = db.prepare(`
        SELECT SUM(CAST(amount AS REAL)/1e24) as total
        FROM transactions 
        WHERE wallet_id = ? AND counterparty LIKE '%.cdao.near' AND direction = 'out'
      `).get(wallet.id);
      
      if (bondTxs.total > 0) {
        console.log("  CDAO bond/deposit OUT:", bondTxs.total.toFixed(4), "NEAR");
      }
    }
    
    // Check for untracked system transfers (larger ones that weren't filtered)
    const largeSystemIn = db.prepare(`
      SELECT tx_hash, CAST(amount AS REAL)/1e24 as amt
      FROM transactions 
      WHERE wallet_id = ? AND counterparty = 'system' AND direction = 'in' AND CAST(amount AS REAL)/1e24 >= 0.02
      ORDER BY amt DESC LIMIT 5
    `).all(wallet.id);
    
    if (largeSystemIn.length > 0) {
      console.log("  Large system transfers IN (included):");
      largeSystemIn.forEach(t => console.log("    ", t.amt.toFixed(4), "NEAR"));
    }
    
    // Check recent large transactions
    const recentLarge = db.prepare(`
      SELECT tx_hash, action_type, method_name, counterparty, CAST(amount AS REAL)/1e24 as amt, direction
      FROM transactions 
      WHERE wallet_id = ? AND CAST(amount AS REAL)/1e24 > 0.3
      ORDER BY id DESC LIMIT 8
    `).all(wallet.id);
    
    if (recentLarge.length > 0) {
      console.log("  Large transactions (>0.3 NEAR):");
      recentLarge.forEach(t => {
        console.log(`    ${t.direction.toUpperCase()} ${t.amt.toFixed(4)} ${t.action_type} ${t.method_name || ''} → ${(t.counterparty || '').substring(0,25)}`);
      });
    }
    
    // Check total tx count
    const txCount = db.prepare("SELECT COUNT(*) as cnt FROM transactions WHERE wallet_id = ?").get(wallet.id);
    console.log("\n  Total transactions indexed:", txCount.cnt);
    
    // Check filtered triggered refunds in detail
    if (filteredTriggeredRefunds > 0.5) {
      console.log("\n  ⚠️  Filtered triggered refunds:", filteredTriggeredRefunds.toFixed(4), "NEAR");
      console.log("     These are system transfers on same tx as FUNCTION_CALL");
      
      // Show the triggered refund amounts
      const triggeredDetails = db.prepare(`
        SELECT t.tx_hash, CAST(t.amount AS REAL)/1e24 as amt
        FROM transactions t
        WHERE t.wallet_id = ? AND t.counterparty = 'system' AND t.direction = 'in'
          AND t.tx_hash IN (SELECT DISTINCT tx_hash FROM transactions WHERE wallet_id = ? AND action_type = 'FUNCTION_CALL' AND direction = 'out')
        ORDER BY amt DESC LIMIT 5
      `).all(wallet.id, wallet.id);
      
      triggeredDetails.forEach(t => console.log("    ", t.amt.toFixed(4), "NEAR"));
    }
    
    // Check for staking-related income (rewards)
    const stakingIncome = db.prepare(`
      SELECT SUM(CAST(amount AS REAL)/1e24) as total
      FROM transactions 
      WHERE wallet_id = ? AND direction = 'in' 
        AND (counterparty LIKE '%.pool%' OR counterparty LIKE 'meta-pool.near' OR counterparty LIKE 'linear%')
    `).get(wallet.id);
    
    if (stakingIncome.total > 0) {
      console.log("\n  Staking-related IN:", stakingIncome.total.toFixed(4), "NEAR");
    }
    
    // Final assessment
    console.log("\n📋 ASSESSMENT:");
    const absDiff = Math.abs(diff);
    
    if (absDiff < 0.1) {
      console.log("  ✅ Within acceptable tolerance (0.1 NEAR)");
    } else if (absDiff < 0.5) {
      console.log("  ⚠️  Small discrepancy - likely gas rounding or timing");
    } else {
      console.log("  ❌ Significant discrepancy - needs investigation");
      
      // Try to pinpoint the issue
      if (diff < 0) {
        console.log("     Missing INFLOW of ~", absDiff.toFixed(4), "NEAR");
        
        if (filteredTriggeredRefunds > 0 && Math.abs(absDiff - filteredTriggeredRefunds) < 0.5) {
          console.log("     → Filtered triggered refunds might explain this!");
          console.log("     → Consider: change filter logic to include these?");
        }
        
        if (filteredSmallRefunds > 0 && Math.abs(absDiff - filteredSmallRefunds) < 0.2) {
          console.log("     → Filtered small refunds might explain this");
        }
      } else {
        console.log("     Missing OUTFLOW of ~", absDiff.toFixed(4), "NEAR");
      }
      
      if (info.hasContract && absDiff > 0.5) {
        console.log("     → This is a contract wallet");
        console.log("     → May have receipt-level transfers not captured by /txns");
        console.log("     → Run: backfill_receipts.py for this wallet");
      }
    }
  }
  
  db.close();
}

analyze().catch(console.error);
