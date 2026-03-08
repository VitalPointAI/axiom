import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getAuthenticatedUser } from "@/lib/auth";

const NEAR_RPC = 'https://rpc.fastnear.com';
const TOLERANCE = 0.5; // NEAR

interface AccountInfo {
  balance: number;
  storageUsage: number;
  storageCost: number;
}

async function getAccountInfo(account: string): Promise<AccountInfo | null> {
  try {
    const res = await fetch(NEAR_RPC, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 'verify', method: 'query',
        params: { request_type: 'view_account', finality: 'final', account_id: account }
      }),
      cache: 'no-store'
    });
    const data = await res.json();
    if (data.result) {
      const storageUsage = data.result.storage_usage || 0;
      return {
        balance: parseFloat(data.result.amount) / 1e24,
        storageUsage,
        storageCost: storageUsage * 1e-5
      };
    }
    return null;
  } catch {
    return null;
  }
}

export async function GET() {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();
    
    // Get user's NEAR wallets (exclude pools)
    console.log("[Verify] userId:", user.userId); const wallets = await db.prepare(`
      SELECT id, account_id 
      FROM wallets 
      WHERE user_id = ? AND chain = 'NEAR' 
        AND account_id NOT LIKE '%.pool%'
        AND account_id NOT LIKE '%.poolv1%'
    `).all(user.userId) as Array<{ id: number; account_id: string }>;

    console.log("[Verify] Found wallets:", wallets.length); if (wallets.length === 0) {
      return NextResponse.json({ wallets: [], summary: { matching: 0, mismatched: 0, total: 0 } });
    }

    const allWalletIds = wallets.map(w => w.id);
    const results: any[] = [];
    let matching = 0;
    let mismatched = 0;

    for (const wallet of wallets) {
      const accountInfo = await getAccountInfo(wallet.account_id);
      if (!accountInfo) continue;

      const onChain = accountInfo.balance;
      const storageCost = accountInfo.storageCost;

      // IN: exclude self-transfers AND system gas refunds
      const inSum = await db.prepare(`
        SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
        FROM transactions 
        WHERE wallet_id = ? 
          AND direction = 'in' 
          AND counterparty != ?
          AND counterparty != 'system'
      `).get(wallet.id, wallet.account_id) as { total: number };

      // DELETE_ACCOUNT beneficiary transfers (system IN linked to DELETE_ACCOUNT)
      const deleteAccountIn = await db.prepare(`
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
      `).get(wallet.id) as { total: number };

      // OUT: exclude self-transfers
      const outSum = await db.prepare(`
        SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
        FROM transactions 
        WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
      `).get(wallet.id, wallet.account_id) as { total: number };

      // Fees: only for OUT direction (we initiated those and paid gas)
      const fees = await db.prepare(`
        SELECT COALESCE(SUM(max_fee), 0) as total FROM (
          SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
          FROM transactions WHERE wallet_id = ? AND direction = 'out' GROUP BY tx_hash
        )
      `).get(wallet.id) as { total: number };

      // DELETE_ACCOUNT outflows: when this wallet was deleted, balance went to beneficiary
      const deleteAccountOutflows = await db.prepare(`
        SELECT COALESCE(SUM(CAST(t2.amount AS REAL)/1e24), 0) as total
        FROM transactions t1
        JOIN transactions t2 ON t1.tx_hash = t2.tx_hash
        WHERE t1.wallet_id = ?
          AND t1.action_type = 'DELETE_ACCOUNT'
          AND t2.direction = 'in'
          AND t2.counterparty = 'system'
          AND t2.wallet_id != t1.wallet_id
      `).get(wallet.id) as { total: number };

      // Compute balance
      const totalIn = inSum.total + deleteAccountIn.total;
      const computed = totalIn - outSum.total - fees.total - deleteAccountOutflows.total;
      const diff = computed - onChain;
      const isMatch = Math.abs(diff) < TOLERANCE;

      if (isMatch) {
        matching++;
      } else {
        mismatched++;
      }

      results.push({
        account: wallet.account_id,
        walletId: wallet.id,
        onChain: Number(onChain.toFixed(4)),
        computed: Number(computed.toFixed(4)),
        diff: Number(diff.toFixed(4)),
        storage: Number(storageCost.toFixed(4)),
        isMatch,
        details: {
          in: Number(inSum.total.toFixed(4)),
          deleteIn: Number(deleteAccountIn.total.toFixed(4)),
          out: Number(outSum.total.toFixed(4)),
          fees: Number(fees.total.toFixed(4)),
          deleteOut: Number(deleteAccountOutflows.total.toFixed(4))
        }
      });
    }

    // Sort by absolute diff descending
    results.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));

    // Calculate totals
    const totals = {
      onChain: results.reduce((sum, w) => sum + w.onChain, 0),
      computed: results.reduce((sum, w) => sum + w.computed, 0),
      storage: results.reduce((sum, w) => sum + w.storage, 0),
      diff: results.reduce((sum, w) => sum + w.diff, 0)
    };

    return NextResponse.json({
      wallets: results,
      totals,
      summary: {
        matching,
        mismatched,
        total: results.length
      }
    });
  } catch (error) {
    console.error('Wallet verification error:', error);
    return NextResponse.json({
      error: 'Failed to verify wallets',
      details: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
}
