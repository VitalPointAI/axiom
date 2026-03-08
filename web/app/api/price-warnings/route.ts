import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const warningType = searchParams.get('type');
  const resolved = searchParams.get('resolved') === 'true';
  const page = parseInt(searchParams.get('page') || '1');
  const limit = parseInt(searchParams.get('limit') || '50');
  
  const db = getDb();
  
  // Build query
  let whereClause = 'price_warning IS NOT NULL';
  const params: any[] = [];
  
  if (warningType) {
    whereClause += ' AND price_warning = ?';
    params.push(warningType);
  }
  
  if (!resolved) {
    whereClause += ' AND (price_resolved IS NULL OR price_resolved != 1)';
  }
  
  // Get total count
  const countStmt = db.prepare(`
    SELECT COUNT(*) as total FROM transactions WHERE ${whereClause}
  `);
  const { total } = countStmt.get(...params) as { total: number };
  
  // Get summary by warning type
  const summaryStmt = db.prepare(`
    SELECT 
      price_warning,
      COUNT(*) as count,
      SUM(CASE WHEN price_resolved = 1 THEN 1 ELSE 0 END) as resolved_count
    FROM transactions
    WHERE price_warning IS NOT NULL
    GROUP BY price_warning
  `);
  const summary = summaryStmt.all();
  
  // Get transactions
  const offset = (page - 1) * limit;
  const stmt = db.prepare(`
    SELECT 
      t.*,
      w.account_id as wallet_address,
      CAST(t.amount AS REAL) / 1e24 as amount_near,
      datetime(t.block_timestamp/1000000000, 'unixepoch') as datetime
    FROM transactions t
    LEFT JOIN wallets w ON t.wallet_id = w.id
    WHERE ${whereClause}
    ORDER BY t.block_timestamp DESC
    LIMIT ? OFFSET ?
  `);
  const transactions = stmt.all(...params, limit, offset);
  
  return NextResponse.json({
    summary,
    transactions,
    total,
    page,
    limit,
    pages: Math.ceil(total / limit)
  });
}

// Resolve a price warning
export async function POST(request: Request) {
  const body = await request.json();
  const { txId, priceUsd, priceCad, note, action } = body;
  
  const db = getDb();
  
  if (action === 'resolve') {
    const stmt = db.prepare(`
      UPDATE transactions 
      SET price_manual_usd = ?,
          price_manual_note = ?,
          cost_basis_usd = ?,
          cost_basis_cad = ?,
          price_resolved = 1
      WHERE id = ?
    `);
    stmt.run(priceUsd, note, priceUsd, priceCad || priceUsd * 1.35, txId);
    
    return NextResponse.json({ success: true });
  }
  
  if (action === 'mark_spam') {
    const stmt = db.prepare(`
      UPDATE transactions 
      SET price_warning = 'spam_token',
          cost_basis_usd = 0,
          cost_basis_cad = 0,
          price_resolved = 1,
          price_manual_note = 'Marked as spam'
      WHERE id = ?
    `);
    stmt.run(txId);
    
    return NextResponse.json({ success: true });
  }
  
  if (action === 'bulk_resolve_spam') {
    // Auto-resolve all spam token warnings
    const stmt = db.prepare(`
      UPDATE transactions 
      SET cost_basis_usd = 0,
          cost_basis_cad = 0,
          price_resolved = 1,
          price_manual_note = 'Bulk resolved as spam'
      WHERE price_warning = 'spam_token' AND (price_resolved IS NULL OR price_resolved != 1)
    `);
    const result = stmt.run();
    
    return NextResponse.json({ success: true, resolved: result.changes });
  }
  
  return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
}
