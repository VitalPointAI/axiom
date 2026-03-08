import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year');
  const protocol = searchParams.get('protocol');
  const category = searchParams.get('category');
  const page = parseInt(searchParams.get('page') || '1');
  const limit = parseInt(searchParams.get('limit') || '50');
  
  const db = getDb();
  
  // Build query
  let whereClause = '1=1';
  const params: any[] = [];
  
  if (year) {
    whereClause += ` AND strftime('%Y', datetime(d.block_timestamp/1000000000, 'unixepoch')) = ?`;
    params.push(year);
  }
  
  if (protocol) {
    whereClause += ' AND d.protocol = ?';
    params.push(protocol);
  }
  
  if (category) {
    whereClause += ' AND d.tax_category = ?';
    params.push(category);
  }
  
  // Get total count
  const countStmt = await db.prepare(`
    SELECT COUNT(*) as total FROM defi_events d WHERE ${whereClause}
  `);
  const { total } = await countStmt.get(...params) as { total: number };
  
  // Get events
  const offset = (page - 1) * limit;
  const stmt = await db.prepare(`
    SELECT 
      d.*,
      w.account_id as wallet_address,
      datetime(d.block_timestamp/1000000000, 'unixepoch') as datetime
    FROM defi_events d
    LEFT JOIN wallets w ON d.wallet_id = w.id
    WHERE ${whereClause}
    ORDER BY d.block_timestamp DESC
    LIMIT ? OFFSET ?
  `);
  const events = await stmt.all(...params, limit, offset);
  
  return NextResponse.json({
    events,
    total,
    page,
    limit,
    pages: Math.ceil(total / limit)
  });
}
