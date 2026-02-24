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

    // Build query - transactions linked to user's wallets
    let whereClause = 'WHERE w.user_id = ?';
    const params: (string | number)[] = [user.id];

    if (fromDate) {
      // Convert date to timestamp (seconds since epoch)
      const fromTs = new Date(fromDate).getTime() / 1000 * 1e9; // nanoseconds
      whereClause += ' AND t.block_timestamp >= ?';
      params.push(fromTs);
    }
    if (toDate) {
      const toTs = new Date(toDate).getTime() / 1000 * 1e9;
      whereClause += ' AND t.block_timestamp <= ?';
      params.push(toTs);
    }
    if (txType) {
      whereClause += ' AND t.action_type = ?';
      params.push(txType);
    }
    if (search) {
      whereClause += ' AND (t.tx_hash LIKE ? OR t.counterparty LIKE ? OR t.method_name LIKE ?)';
      const searchTerm = `%${search}%`;
      params.push(searchTerm, searchTerm, searchTerm);
    }

    // Get total count
    const countResult = db.prepare(`
      SELECT COUNT(*) as count
      FROM transactions t
      JOIN wallets w ON t.wallet_id = w.id
      ${whereClause}
    `).get(...params) as { count: number };

    // Get transactions with proper formatting
    const transactions = db.prepare(`
      SELECT 
        t.id,
        t.tx_hash,
        t.wallet_id,
        t.direction,
        t.counterparty,
        t.action_type as tx_type,
        t.method_name,
        CAST(t.amount AS REAL) / 1e24 as amount,
        CAST(t.fee AS REAL) / 1e24 as fee,
        t.block_timestamp,
        t.success,
        w.chain,
        w.label as wallet_label,
        w.account_id as wallet_address
      FROM transactions t
      JOIN wallets w ON t.wallet_id = w.id
      ${whereClause}
      ORDER BY t.block_timestamp DESC
      LIMIT ? OFFSET ?
    `).all(...params, limit, offset) as Array<{
      id: number;
      tx_hash: string;
      wallet_id: number;
      direction: string;
      counterparty: string;
      tx_type: string;
      method_name: string;
      amount: number;
      fee: number;
      block_timestamp: number;
      success: boolean;
      chain: string;
      wallet_label: string;
      wallet_address: string;
    }>;

    // Format transactions for frontend
    const formattedTx = transactions.map(tx => ({
      id: tx.id,
      tx_hash: tx.tx_hash,
      timestamp: new Date(tx.block_timestamp / 1e6).toISOString(), // nanoseconds to ms
      tx_type: tx.tx_type || tx.method_name || 'transfer',
      from_address: tx.direction === 'out' ? tx.wallet_address : tx.counterparty,
      to_address: tx.direction === 'in' ? tx.wallet_address : tx.counterparty,
      asset: 'NEAR',
      amount: tx.amount,
      fee: tx.fee,
      chain: tx.chain,
      wallet_label: tx.wallet_label,
      success: tx.success,
    }));

    // Get distinct types for filters
    const types = db.prepare(`
      SELECT DISTINCT COALESCE(action_type, method_name, 'transfer') as tx_type
      FROM transactions t 
      JOIN wallets w ON t.wallet_id = w.id 
      WHERE w.user_id = ?
    `).all(user.id) as { tx_type: string }[];

    return NextResponse.json({
      transactions: formattedTx,
      pagination: {
        page,
        limit,
        total: countResult.count,
        totalPages: Math.ceil(countResult.count / limit),
      },
      filters: {
        types: types.map(t => t.tx_type).filter(Boolean),
        assets: ['NEAR'], // For now, just NEAR
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
