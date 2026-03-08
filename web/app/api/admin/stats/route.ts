import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getAuthenticatedUser } from "@/lib/auth";

// GET /api/admin/stats - Get admin statistics
export async function GET(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();

    // Get wallet count
    const walletCount = await db.prepare(`
      SELECT COUNT(*) as count FROM wallets WHERE user_id = ?
    `).get(auth.userId) as { count: number };

    // Get transaction count
    const txCount = await db.prepare(`
      SELECT COUNT(*) as count FROM transactions 
      WHERE wallet_id IN (SELECT id FROM wallets WHERE user_id = ?)
    `).get(auth.userId) as { count: number };

    // Get unique token count
    const tokenCount = await db.prepare(`
      SELECT COUNT(DISTINCT token_id) as count FROM ft_transactions 
      WHERE wallet_id IN (SELECT id FROM wallets WHERE user_id = ?)
    `).get(auth.userId) as { count: number };

    // Get last sync time
    const lastSync = await db.prepare(`
      SELECT MAX(last_indexed_at) as last_sync FROM wallets WHERE user_id = ?
    `).get(auth.userId) as { last_sync: string | null };

    return NextResponse.json({
      totalWallets: walletCount.count,
      totalTransactions: txCount.count,
      totalTokens: tokenCount.count,
      lastSync: lastSync.last_sync,
    });
  } catch (error: any) {
    console.error('Admin stats error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
