import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

// Check if an account is a NEAR account
function isNearAccount(accountId: string): boolean {
  if (accountId.endsWith('.near') || accountId.endsWith('.testnet')) return true;
  if (/^[a-f0-9]{64}$/.test(accountId)) return true;
  if (accountId.includes('.lockup.near')) return true;
  return false;
}

export async function GET() {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();
    
    // Get THIS USER's NEAR wallets only
    const nearWallets = await db.prepare(`
      SELECT account_id, sync_status FROM wallets WHERE user_id = $1
    `).all(auth.userId) as { account_id: string; sync_status: string }[];
    
    // Get THIS USER's EVM wallets
    const evmWallets = await db.prepare(`
      SELECT ew.id, ew.address, ew.chain, COALESCE(ep.status, 'complete') as sync_status
      FROM evm_wallets ew
      LEFT JOIN evm_indexing_progress ep ON ew.id = ep.wallet_id
      WHERE ew.user_id = $1 AND ew.is_owned = TRUE
    `).all(auth.userId) as any[];
    
    // Get THIS USER's XRP wallets
    const xrpWallets = await db.prepare(`
      SELECT id, address FROM xrp_wallets WHERE user_id = $1
    `).all(auth.userId) as any[];
    
    // Count NEAR wallet stats
    const nearStats = {
      total: nearWallets.length,
      synced: nearWallets.filter(w => w.sync_status === 'complete').length,
      inProgress: nearWallets.filter(w => w.sync_status === 'in_progress' || w.sync_status === 'syncing').length,
      error: nearWallets.filter(w => w.sync_status === 'error').length,
      pending: nearWallets.filter(w => w.sync_status === 'pending' || w.sync_status === 'idle' || !w.sync_status).length,
    };
    
    // Count EVM wallet stats
    const evmStats = {
      total: evmWallets.length,
      synced: evmWallets.filter(w => w.sync_status === 'complete').length,
      inProgress: evmWallets.filter(w => w.sync_status === 'in_progress' || w.sync_status === 'syncing').length,
      error: evmWallets.filter(w => w.sync_status === 'error').length,
      pending: evmWallets.filter(w => w.sync_status === 'pending' || !w.sync_status).length,
    };
    
    // Get transaction stats for THIS USER's wallets only
    const nearWalletIds = nearWallets.length > 0 
      ? (await db.prepare(`SELECT id FROM wallets WHERE user_id = $1`).all(auth.userId) as { id: number }[]).map(w => w.id)
      : [];
    
    let txStats = { total: 0, oldest: null, newest: null };
    if (nearWalletIds.length > 0) {
      const stats = await db.prepare(`
        SELECT 
          COUNT(*) as total,
          MIN(block_timestamp) as oldest,
          MAX(block_timestamp) as newest
        FROM transactions
        WHERE wallet_id = ANY($1::int[])
      `).get([nearWalletIds]) as any;
      txStats = stats || txStats;
    }
    
    // Total wallet count
    const totalWallets = nearStats.total + evmStats.total + xrpWallets.length;
    const totalSynced = nearStats.synced + evmStats.synced + xrpWallets.length; // XRP considered synced
    
    // Calculate progress
    const progress = totalWallets > 0 ? Math.round((totalSynced / totalWallets) * 100) : 0;
    
    // Determine overall status
    let status: 'idle' | 'syncing' | 'complete' | 'error' = 'idle';
    if (nearStats.inProgress > 0 || evmStats.inProgress > 0) {
      status = 'syncing';
    } else if (nearStats.error > 0 || evmStats.error > 0) {
      status = 'error';
    } else if (totalSynced === totalWallets && totalWallets > 0) {
      status = 'complete';
    }
    
    return NextResponse.json({
      status,
      progress,
      wallets: {
        total: totalWallets.toString(),
        synced: totalSynced.toString(),
        inProgress: (nearStats.inProgress + evmStats.inProgress).toString(),
        error: (nearStats.error + evmStats.error).toString(),
        pending: (nearStats.pending + evmStats.pending).toString(),
      },
      breakdown: {
        near: nearStats,
        evm: evmStats,
        xrp: { total: xrpWallets.length, synced: xrpWallets.length },
      },
      transactions: {
        total: Number(txStats?.total) || 0,
        dateRange: txStats?.oldest && txStats?.newest
          ? { oldest: txStats.oldest, newest: txStats.newest }
          : null,
      },
      lastChecked: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Sync status error:', error);
    return NextResponse.json({ error: 'Failed to get sync status' }, { status: 500 });
  }
}
