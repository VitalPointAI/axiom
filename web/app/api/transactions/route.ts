import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: NextRequest) {
  try {
    const cookieStore = await cookies();
    const nearAccountId = cookieStore.get('neartax_session')?.value;

    if (!nearAccountId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();

    // Get user
    const user = db.prepare(`
      SELECT id FROM users WHERE near_account_id = ?
    `).get(nearAccountId) as { id: number } | undefined;

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Parse query params
    const { searchParams } = new URL(request.url);
    const page = parseInt(searchParams.get('page') || '1', 10);
    const limit = parseInt(searchParams.get('limit') || '25', 10);
    const offset = (page - 1) * limit;
    
    const fromDate = searchParams.get('from');
    const toDate = searchParams.get('to');
    const txType = searchParams.get('type');
    const asset = searchParams.get('asset');
    const search = searchParams.get('q');

    // Build query
    let whereClause = 'WHERE w.user_id = ?';
    const params: (string | number)[] = [user.id];

    if (fromDate) {
      whereClause += ' AND t.timestamp >= ?';
      params.push(fromDate);
    }
    if (toDate) {
      whereClause += ' AND t.timestamp <= ?';
      params.push(toDate);
    }
    if (txType) {
      whereClause += ' AND t.tx_type = ?';
      params.push(txType);
    }
    if (asset) {
      whereClause += ' AND t.asset = ?';
      params.push(asset);
    }
    if (search) {
      whereClause += ' AND (t.tx_hash LIKE ? OR t.from_address LIKE ? OR t.to_address LIKE ? OR t.notes LIKE ?)';
      const searchTerm = `%${search}%`;
      params.push(searchTerm, searchTerm, searchTerm, searchTerm);
    }

    // Get total count
    const countResult = db.prepare(`
      SELECT COUNT(*) as count
      FROM transactions t
      JOIN wallets w ON t.wallet_id = w.id
      ${whereClause}
    `).get(...params) as { count: number };

    // Get transactions
    const transactions = db.prepare(`
      SELECT 
        t.*,
        w.chain,
        w.label as wallet_label
      FROM transactions t
      JOIN wallets w ON t.wallet_id = w.id
      ${whereClause}
      ORDER BY t.timestamp DESC
      LIMIT ? OFFSET ?
    `).all(...params, limit, offset);

    // Get distinct types and assets for filters
    const types = db.prepare(`
      SELECT DISTINCT tx_type 
      FROM transactions t 
      JOIN wallets w ON t.wallet_id = w.id 
      WHERE w.user_id = ? AND t.tx_type IS NOT NULL
    `).all(user.id) as { tx_type: string }[];

    const assets = db.prepare(`
      SELECT DISTINCT asset 
      FROM transactions t 
      JOIN wallets w ON t.wallet_id = w.id 
      WHERE w.user_id = ? AND t.asset IS NOT NULL
    `).all(user.id) as { asset: string }[];

    return NextResponse.json({
      transactions,
      pagination: {
        page,
        limit,
        total: countResult.count,
        totalPages: Math.ceil(countResult.count / limit),
      },
      filters: {
        types: types.map(t => t.tx_type),
        assets: assets.map(a => a.asset),
      },
    });
  } catch (error) {
    console.error('Transactions fetch error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch transactions' },
      { status: 500 }
    );
  }
}
