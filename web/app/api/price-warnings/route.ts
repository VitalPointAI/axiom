import { getAuthenticatedUser } from '@/lib/auth';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: Request) {
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { searchParams } = new URL(request.url);
  const warningType = searchParams.get('type');
  const resolved = searchParams.get('resolved') === 'true';
  const page = parseInt(searchParams.get('page') || '1');
  const limit = parseInt(searchParams.get('limit') || '50');
  
  const db = getDb();
  
  // SECURITY: Get this user's wallet IDs first
  const userWallets = await db.prepare(`SELECT id FROM wallets WHERE user_id = $1`).all(auth.userId) as { id: number }[];
  const walletIds = userWallets.map(w => w.id);
  
  if (walletIds.length === 0) {
    return NextResponse.json({ summary: [], transactions: [], total: 0, page, limit, pages: 0 });
  }
  
  // Build query params
  const params: any[] = [[walletIds]];
  let whereClause = 'price_warning IS NOT NULL AND wallet_id = ANY($1::int[])';
  let paramIndex = 2;
  
  if (warningType) {
    whereClause += ` AND price_warning = $${paramIndex}`;
    params.push(warningType);
    paramIndex++;
  }
  
  if (!resolved) {
    whereClause += ' AND (price_resolved IS NULL OR price_resolved != TRUE)';
  }
  
  // Get total count - FILTERED
  const countResult = await db.prepare(`SELECT COUNT(*) as total FROM transactions WHERE ${whereClause}`).get(...params) as { total: number };
  const total = Number(countResult?.total) || 0;
  
  // Get summary by warning type - FILTERED
  const summary = await db.prepare(`
    SELECT price_warning, COUNT(*) as count, SUM(CASE WHEN price_resolved = TRUE THEN 1 ELSE 0 END) as resolved_count
    FROM transactions WHERE price_warning IS NOT NULL AND wallet_id = ANY($1::int[])
    GROUP BY price_warning
  `).all([walletIds]);
  
  // Get transactions - FILTERED
  const offset = (page - 1) * limit;
  const txParams = [...params, limit, offset];
  const transactions = await db.prepare(`
    SELECT t.*, w.account_id as wallet_address, CAST(t.amount AS REAL) / 1e24 as amount_near,
      to_char(to_timestamp(t.block_timestamp/1000000000), 'YYYY-MM-DD HH24:MI:SS') as datetime
    FROM transactions t LEFT JOIN wallets w ON t.wallet_id = w.id
    WHERE ${whereClause}
    ORDER BY t.block_timestamp DESC
    LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
  `).all(...txParams);
  
  return NextResponse.json({ summary, transactions, total, page, limit, pages: Math.ceil(total / limit) });
}

// Resolve a price warning - needs auth check for ownership
export async function POST(request: Request) {
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  
  const body = await request.json();
  const { txId, priceUsd, priceCad, note, action } = body;
  
  const db = getDb();
  
  // SECURITY: Verify transaction belongs to user's wallet
  const txCheck = await db.prepare(`
    SELECT t.id FROM transactions t JOIN wallets w ON t.wallet_id = w.id WHERE t.id = $1 AND w.user_id = $2
  `).get(txId, auth.userId);
  
  if (!txCheck) {
    return NextResponse.json({ error: 'Transaction not found or access denied' }, { status: 403 });
  }
  
  if (action === 'resolve') {
    await db.prepare(`
      UPDATE transactions SET price_manual_usd = $1, price_manual_note = $2, cost_basis_usd = $1, cost_basis_cad = $3, price_resolved = TRUE WHERE id = $4
    `).run(priceUsd, note, priceCad || priceUsd * 1.35, txId);
    return NextResponse.json({ success: true });
  }
  
  if (action === 'mark_spam') {
    await db.prepare(`
      UPDATE transactions SET price_warning = 'spam_token', cost_basis_usd = 0, cost_basis_cad = 0, price_resolved = TRUE, price_manual_note = 'Marked as spam' WHERE id = $1
    `).run(txId);
    return NextResponse.json({ success: true });
  }
  
  if (action === 'bulk_resolve_spam') {
    // SECURITY: Only resolve spam for user's wallets
    const userWallets = await db.prepare(`SELECT id FROM wallets WHERE user_id = $1`).all(auth.userId) as { id: number }[];
    const walletIds = userWallets.map(w => w.id);
    
    if (walletIds.length === 0) {
      return NextResponse.json({ success: true, resolved: 0 });
    }
    
    const result = await db.prepare(`
      UPDATE transactions SET cost_basis_usd = 0, cost_basis_cad = 0, price_resolved = TRUE, price_manual_note = 'Bulk resolved as spam'
      WHERE price_warning = 'spam_token' AND (price_resolved IS NULL OR price_resolved != TRUE) AND wallet_id = ANY($1::int[])
    `).run([walletIds]);
    
    return NextResponse.json({ success: true, resolved: result.rowCount || 0 });
  }
  
  return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
}
