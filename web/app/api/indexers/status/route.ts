import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

export async function GET() {
  // SECURITY: Require authentication
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const db = getDb();

  // Get THIS USER's NEAR wallets with sync status
  const nearWallets = await db.prepare(`
    SELECT 
      w.id,
      w.account_id,
      w.label,
      w.chain,
      COALESCE(w.sync_status, 'pending') as sync_status,
      w.last_synced_at,
      COALESCE(ip.total_fetched, 0) as tx_count,
      ip.last_cursor,
      ip.error_message
    FROM wallets w
    LEFT JOIN indexing_progress ip ON w.id = ip.wallet_id
    WHERE w.user_id = $1
    ORDER BY w.created_at DESC
  `).all(auth.userId) as any[];

  // Get THIS USER's EVM wallets with sync status
  const evmWallets = await db.prepare(`
    SELECT 
      ew.id,
      ew.address as account_id,
      ew.label,
      ew.chain,
      COALESCE(ep.status, 'pending') as sync_status,
      ep.updated_at as last_synced_at,
      COALESCE(ep.total_fetched, 0) as tx_count,
      ep.error_message
    FROM evm_wallets ew
    LEFT JOIN evm_indexing_progress ep ON ew.id = ep.wallet_id
    WHERE ew.user_id = $1 AND ew.is_owned = TRUE
    ORDER BY ew.created_at DESC
  `).all(auth.userId) as any[];

  // Get THIS USER's XRP wallets
  const xrpWallets = await db.prepare(`
    SELECT 
      w.id,
      w.address as account_id,
      w.label,
      'xrp' as chain,
      'complete' as sync_status,
      w.created_at as last_synced_at,
      (SELECT COUNT(*) FROM xrp_transactions WHERE wallet_id = w.id) as tx_count
    FROM xrp_wallets w
    WHERE w.user_id = $1
    ORDER BY w.created_at DESC
  `).all(auth.userId) as any[];

  // Calculate stats
  const allWallets = [...nearWallets, ...evmWallets, ...xrpWallets];
  
  const stats = {
    total: allWallets.length,
    complete: allWallets.filter(w => w.sync_status === 'complete').length,
    syncing: allWallets.filter(w => ['syncing', 'in_progress'].includes(w.sync_status)).length,
    pending: allWallets.filter(w => w.sync_status === 'pending').length,
    error: allWallets.filter(w => w.sync_status === 'error').length,
  };

  const progress = stats.total > 0 
    ? Math.round((stats.complete / stats.total) * 100) 
    : 0;

  return NextResponse.json({
    stats,
    progress,
    wallets: allWallets.map(w => ({
      id: w.id,
      address: w.account_id,
      label: w.label,
      chain: w.chain,
      status: w.sync_status,
      lastSynced: w.last_synced_at,
      txCount: Number(w.tx_count) || 0,
      error: w.error_message,
    })),
    lastChecked: new Date().toISOString(),
  });
}
