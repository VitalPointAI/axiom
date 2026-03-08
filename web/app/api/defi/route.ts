import { getAuthenticatedUser } from '@/lib/auth';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: Request) {
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year');
  const protocol = searchParams.get('protocol');
  const category = searchParams.get('category');
  const page = parseInt(searchParams.get('page') || '1');
  const limit = parseInt(searchParams.get('limit') || '50');
  
  const db = getDb();
  
  // Get THIS USER's wallet IDs first
  const userWallets = await db.prepare(`
    SELECT id FROM wallets WHERE user_id = $1
  `).all(auth.userId) as { id: number }[];
  
  const walletIds = userWallets.map(w => w.id);
  
  if (walletIds.length === 0) {
    return NextResponse.json({
      events: [],
      total: 0,
      page,
      limit,
      pages: 0,
      filters: { years: [], protocols: [], categories: [] }
    });
  }
  
  // Build query with user wallet filter
  let whereClause = 'd.wallet_id = ANY($1::int[])';
  const params: any[] = [[walletIds]];
  let paramIndex = 2;
  
  if (year) {
    whereClause += ` AND to_char(to_timestamp(d.block_timestamp/1000000000), 'YYYY') = $${paramIndex}`;
    params.push(year);
    paramIndex++;
  }
  
  if (protocol) {
    whereClause += ` AND d.protocol = $${paramIndex}`;
    params.push(protocol);
    paramIndex++;
  }
  
  if (category) {
    whereClause += ` AND d.tax_category = $${paramIndex}`;
    params.push(category);
    paramIndex++;
  }
  
  // Get total count
  const countResult = await db.prepare(`
    SELECT COUNT(*) as total FROM defi_events d WHERE ${whereClause}
  `).get(...params) as { total: number };
  const total = Number(countResult?.total) || 0;
  
  // Get events
  const offset = (page - 1) * limit;
  const events = await db.prepare(`
    SELECT 
      d.*,
      w.account_id as wallet_address,
      to_char(to_timestamp(d.block_timestamp/1000000000), 'YYYY-MM-DD HH24:MI:SS') as datetime
    FROM defi_events d
    JOIN wallets w ON d.wallet_id = w.id
    WHERE ${whereClause}
    ORDER BY d.block_timestamp DESC
    LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
  `).all(...params, limit, offset) as any[];
  
  // Get filter options - FILTERED BY USER'S WALLETS
  const filterParams = [[walletIds]];
  
  const years = await db.prepare(`
    SELECT DISTINCT to_char(to_timestamp(block_timestamp/1000000000), 'YYYY') as year
    FROM defi_events 
    WHERE wallet_id = ANY($1::int[])
    ORDER BY year DESC
  `).all(...filterParams) as Array<{ year: string }>;
  
  const protocols = await db.prepare(`
    SELECT DISTINCT protocol FROM defi_events 
    WHERE wallet_id = ANY($1::int[]) AND protocol IS NOT NULL
    ORDER BY protocol
  `).all(...filterParams) as Array<{ protocol: string }>;
  
  const categories = await db.prepare(`
    SELECT DISTINCT tax_category FROM defi_events 
    WHERE wallet_id = ANY($1::int[]) AND tax_category IS NOT NULL
    ORDER BY tax_category
  `).all(...filterParams) as Array<{ tax_category: string }>;
  
  return NextResponse.json({
    events,
    total,
    page,
    limit,
    pages: Math.ceil(total / limit),
    filters: {
      years: years.map(y => y.year),
      protocols: protocols.map(p => p.protocol),
      categories: categories.map(c => c.tax_category)
    }
  });
}
