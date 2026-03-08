import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

// Infer tax category from transaction type/method
function inferTaxCategory(tx: any): string {
  const method = (tx.method_name || '').toLowerCase();
  const txType = (tx.tx_type || '').toLowerCase();
  const counterparty = (tx.counterparty || '').toLowerCase();
  
  if (method.includes('stake') || method.includes('deposit_and_stake')) return 'staking';
  if (method.includes('unstake') || method.includes('withdraw')) return 'unstaking';
  if (counterparty.includes('ref-finance') || method.includes('swap')) return 'swap';
  if (counterparty.includes('burrow') || method.includes('supply') || method.includes('borrow')) return 'defi-lending';
  if (counterparty.includes('meta-pool') || counterparty.includes('linear')) return 'liquid-staking';
  if (method.includes('nft') || counterparty.includes('paras') || counterparty.includes('mintbase')) return 'nft';
  if (txType === 'function_call') return 'contract-call';
  if (txType === 'transfer' || method.includes('transfer')) return 'transfer';
  
  return 'uncategorized';
}

// Valid sort fields mapping to actual DB columns
const SORT_FIELD_MAP: Record<string, string> = {
  'timestamp': 't.block_timestamp',
  'tx_type': 't.action_type',
  'asset': "'NEAR'", // Static for now
  'amount': 'CAST(t.amount AS REAL)',
  'tax_category': 't.tax_category',
  'wallet_label': 'w.label',
};

export async function GET(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();
    const { searchParams } = new URL(request.url);
    
    // Pagination
    const page = Math.max(1, parseInt(searchParams.get('page') || '1', 10));
    const limit = Math.min(100, Math.max(10, parseInt(searchParams.get('limit') || '25', 10)));
    const offset = (page - 1) * limit;
    
    // Sorting
    const sortField = searchParams.get('sort') || 'timestamp';
    const sortOrder = searchParams.get('order') === 'asc' ? 'ASC' : 'DESC';
    const sortColumn = SORT_FIELD_MAP[sortField] || 't.block_timestamp';
    
    // Filters
    const fromDate = searchParams.get('from');
    const toDate = searchParams.get('to');
    const txType = searchParams.get('type');
    const category = searchParams.get('category');
    const search = searchParams.get('q');
    const walletFilter = searchParams.get('wallet');
    const addressFilter = searchParams.get('address');
    const minAmount = searchParams.get('minAmount');
    const maxAmount = searchParams.get('maxAmount');

    // Build WHERE clause
    let whereClause = 'WHERE w.user_id = ?';
    const params: (string | number)[] = [auth.userId];

    if (fromDate) {
      const fromTs = new Date(fromDate).getTime() * 1e6; // Convert to nanoseconds
      whereClause += ' AND t.block_timestamp >= ?';
      params.push(fromTs);
    }
    if (toDate) {
      const toTs = new Date(toDate).getTime() * 1e6;
      whereClause += ' AND t.block_timestamp <= ?';
      params.push(toTs);
    }
    if (txType) {
      whereClause += ' AND (t.action_type = ? OR t.method_name = ?)';
      params.push(txType, txType);
    }
    if (category) {
      // Category is inferred, so we need to filter based on patterns
      switch (category) {
        case 'staking':
          whereClause += " AND (t.method_name LIKE '%stake%' AND t.method_name NOT LIKE '%unstake%')";
          break;
        case 'unstaking':
          whereClause += " AND (t.method_name LIKE '%unstake%' OR t.method_name LIKE '%withdraw%')";
          break;
        case 'swap':
          whereClause += " AND (t.counterparty LIKE '%ref-finance%' OR t.method_name LIKE '%swap%')";
          break;
        case 'defi-lending':
          whereClause += " AND (t.counterparty LIKE '%burrow%' OR t.method_name IN ('supply', 'borrow'))";
          break;
        case 'liquid-staking':
          whereClause += " AND (t.counterparty LIKE '%meta-pool%' OR t.counterparty LIKE '%linear%')";
          break;
        case 'nft':
          whereClause += " AND (t.method_name LIKE '%nft%' OR t.counterparty LIKE '%paras%' OR t.counterparty LIKE '%mintbase%')";
          break;
        case 'transfer':
          whereClause += " AND t.action_type = 'TRANSFER'";
          break;
        case 'contract-call':
          whereClause += " AND t.action_type = 'FUNCTION_CALL' AND t.method_name NOT LIKE '%stake%' AND t.method_name NOT LIKE '%swap%'";
          break;
      }
    }
    if (search) {
      whereClause += ' AND (t.tx_hash LIKE ? OR t.counterparty LIKE ? OR t.method_name LIKE ? OR w.account_id LIKE ?)';
      const searchTerm = `%${search}%`;
      params.push(searchTerm, searchTerm, searchTerm, searchTerm);
    }
    if (walletFilter) {
      whereClause += ' AND (w.label LIKE ? OR w.account_id LIKE ?)';
      const walletTerm = `%${walletFilter}%`;
      params.push(walletTerm, walletTerm);
    }
    if (addressFilter) {
      whereClause += ' AND (t.counterparty LIKE ? OR w.account_id LIKE ?)';
      const addrTerm = `%${addressFilter}%`;
      params.push(addrTerm, addrTerm);
    }
    if (minAmount) {
      const minNear = parseFloat(minAmount) * 1e24;
      whereClause += ' AND CAST(t.amount AS REAL) >= ?';
      params.push(minNear);
    }
    if (maxAmount) {
      const maxNear = parseFloat(maxAmount) * 1e24;
      whereClause += ' AND CAST(t.amount AS REAL) <= ?';
      params.push(maxNear);
    }

    // Get total count
    const countResult = await db.prepare(`
      SELECT COUNT(*) as count
      FROM transactions t
      JOIN wallets w ON t.wallet_id = w.id
      ${whereClause}
    `).get(...params) as { count: number };

    // Get transactions with sorting
    const transactions = await db.prepare(`
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
        w.account_id as wallet_address,
        t.tax_category,
        t.category_confidence,
        t.needs_review
      FROM transactions t
      JOIN wallets w ON t.wallet_id = w.id
      ${whereClause}
      ORDER BY ${sortColumn} ${sortOrder}
      LIMIT ? OFFSET ?
    `).all(...params, limit, offset) as any[];

    // Format transactions
    const formattedTx = transactions.map(tx => ({
      id: tx.id,
      tx_hash: tx.tx_hash,
      timestamp: new Date(tx.block_timestamp / 1e6).toISOString(),
      tx_type: tx.tx_type || tx.method_name || 'transfer',
      from_address: tx.direction === 'out' ? tx.wallet_address : tx.counterparty,
      to_address: tx.direction === 'in' ? tx.wallet_address : tx.counterparty,
      asset: 'NEAR',
      amount: tx.amount,
      fee: tx.fee,
      chain: tx.chain,
      wallet_label: tx.wallet_label,
      success: tx.success,
      tax_category: tx.tax_category || inferTaxCategory(tx),
      needs_review: tx.needs_review === 1,
    }));

    // Get distinct types for filters
    const types = await db.prepare(`
      SELECT DISTINCT COALESCE(action_type, method_name, 'transfer') as tx_type
      FROM transactions t 
      JOIN wallets w ON t.wallet_id = w.id 
      WHERE w.user_id = ?
      ORDER BY tx_type
    `).all(auth.userId) as { tx_type: string }[];

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
        assets: ['NEAR'],
        categories: ['transfer', 'staking', 'unstaking', 'swap', 'defi-lending', 'liquid-staking', 'nft', 'contract-call'],
      },
    });
  } catch (error) {
    console.error('Transactions fetch error:', error);
    return NextResponse.json({ error: 'Failed to fetch transactions' }, { status: 500 });
  }
}
