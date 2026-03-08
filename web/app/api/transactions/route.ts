import { NextRequest, NextResponse } from 'next/server';
import db from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

export async function GET(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const page = Math.max(1, parseInt(searchParams.get('page') || '1'));
    const limit = Math.min(100, Math.max(1, parseInt(searchParams.get('limit') || '25')));
    const sortField = searchParams.get('sort') || 'timestamp';
    const sortOrder = searchParams.get('order')?.toUpperCase() === 'ASC' ? 'ASC' : 'DESC';
    const offset = (page - 1) * limit;

    // Filter params
    const filterType = searchParams.get('type') || '';
    const filterChain = searchParams.get('chain') || '';
    const filterCategory = searchParams.get('category') || '';
    const filterAsset = searchParams.get('asset') || '';
    const searchQuery = searchParams.get('q') || '';
    const fromDate = searchParams.get('from') || '';
    const toDate = searchParams.get('to') || '';

    // Map sort fields to actual columns
    const sortMap: Record<string, string> = {
      'timestamp': 'block_timestamp',
      'amount': 'amount',
      'asset': 'asset',
    };
    const sortColumn = sortMap[sortField] || 'block_timestamp';

    // Get user's wallet IDs
    const wallets = await db.all<{ id: number }>(
      'SELECT id FROM wallets WHERE user_id = $1',
      [auth.userId]
    );
    
    if (wallets.length === 0) {
      return NextResponse.json({ 
        transactions: [], 
        total: 0, 
        page, 
        limit, 
        totalPages: 0,
        filters: { types: [], chains: [], categories: [], assets: [] }
      });
    }

    const walletIds = wallets.map(w => w.id);

    // Build WHERE clause for filters
    const conditions: string[] = ['t.wallet_id = ANY($1::int[])'];
    const params: any[] = [walletIds];
    let paramIndex = 2;

    if (filterType) {
      conditions.push(`COALESCE(t.action_type, t.method_name, 'transfer') = $${paramIndex}`);
      params.push(filterType);
      paramIndex++;
    }

    if (filterCategory) {
      conditions.push(`COALESCE(t.tax_category, 'uncategorized') = $${paramIndex}`);
      params.push(filterCategory);
      paramIndex++;
    }

    if (filterAsset) {
      conditions.push(`COALESCE(t.asset, 'NEAR') = $${paramIndex}`);
      params.push(filterAsset);
      paramIndex++;
    }

    if (filterChain) {
      conditions.push(`UPPER(COALESCE(w.chain, 'NEAR')) = $${paramIndex}`);
      params.push(filterChain.toUpperCase());
      paramIndex++;
    }

    if (searchQuery) {
      conditions.push(`(t.tx_hash ILIKE $${paramIndex} OR t.counterparty ILIKE $${paramIndex} OR t.description ILIKE $${paramIndex})`);
      params.push(`%${searchQuery}%`);
      paramIndex++;
    }

    if (fromDate) {
      // Convert date to timestamp
      const fromTs = new Date(fromDate).getTime() / 1000;
      conditions.push(`(CASE WHEN t.block_timestamp > 1e12 THEN t.block_timestamp / 1e9 ELSE t.block_timestamp END) >= $${paramIndex}`);
      params.push(fromTs);
      paramIndex++;
    }

    if (toDate) {
      // Convert date to end of day timestamp
      const toTs = new Date(toDate + 'T23:59:59').getTime() / 1000;
      conditions.push(`(CASE WHEN t.block_timestamp > 1e12 THEN t.block_timestamp / 1e9 ELSE t.block_timestamp END) <= $${paramIndex}`);
      params.push(toTs);
      paramIndex++;
    }

    const whereClause = conditions.join(' AND ');

    // Fetch transactions with filters
    const transactions = await db.all(`
      SELECT 
        t.id,
        t.tx_hash,
        t.direction,
        t.counterparty,
        COALESCE(t.action_type, t.method_name, 'transfer') as tx_type,
        COALESCE(t.asset, 'NEAR') as asset,
        t.amount,
        t.fee,
        t.block_timestamp,
        t.success,
        t.tax_category,
        t.source,
        t.exchange,
        t.description,
        w.account_id as wallet_address,
        w.label as wallet_label,
        UPPER(COALESCE(w.chain, 'NEAR')) as chain
      FROM transactions t
      JOIN wallets w ON t.wallet_id = w.id
      WHERE ${whereClause}
      ORDER BY ${sortColumn} ${sortOrder}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `, [...params, limit, offset]);

    // Count total with same filters (must join with wallets for chain filter)
    const countResult = await db.get<{ count: string }>(
      `SELECT COUNT(*) as count FROM transactions t JOIN wallets w ON t.wallet_id = w.id WHERE ${whereClause}`,
      params
    );
    const total = parseInt(countResult?.count || '0');

    // Get distinct filter values for dropdowns (across ALL user transactions, not filtered)
    const [typesResult, categoriesResult, assetsResult, chainsResult] = await Promise.all([
      db.all<{ tx_type: string }>(
        `SELECT DISTINCT COALESCE(action_type, method_name, 'transfer') as tx_type 
         FROM transactions 
         WHERE wallet_id = ANY($1::int[]) 
         ORDER BY tx_type`,
        [walletIds]
      ),
      db.all<{ tax_category: string }>(
        `SELECT DISTINCT COALESCE(tax_category, 'uncategorized') as tax_category 
         FROM transactions 
         WHERE wallet_id = ANY($1::int[]) 
         ORDER BY tax_category`,
        [walletIds]
      ),
      db.all<{ asset: string }>(
        `SELECT DISTINCT COALESCE(t.asset, 'NEAR') as asset 
         FROM transactions t
         WHERE t.wallet_id = ANY($1::int[]) 
           AND NOT EXISTS (
             SELECT 1 FROM spam_tokens s 
             WHERE UPPER(s.token_symbol) = UPPER(COALESCE(t.asset, 'NEAR'))
           )
         ORDER BY asset`,
        [walletIds]
      ),
      db.all<{ chain: string }>(
        `SELECT DISTINCT UPPER(COALESCE(w.chain, 'NEAR')) as chain 
         FROM transactions t
         JOIN wallets w ON t.wallet_id = w.id
         WHERE t.wallet_id = ANY($1::int[]) 
         ORDER BY chain`,
        [walletIds]
      ),
    ]);

    const chainLabelMap: Record<string, string> = {
      'NEAR': 'NEAR',
      'ETH': 'Ethereum',
      'ETHEREUM': 'Ethereum',
      'POLYGON': 'Polygon',
      'ARBITRUM': 'Arbitrum',
      'OPTIMISM': 'Optimism',
      'BASE': 'Base',
      'CRONOS': 'Cronos',
      'XRP': 'XRP Ledger',
      'AKASH': 'Akash',
      'EXCHANGE': 'Exchange',
      'near': 'NEAR',
      'ethereum': 'Ethereum',
      'polygon': 'Polygon',
      'optimism': 'Optimism',
      'arbitrum': 'Arbitrum',
      'base': 'Base',
      'exchange': 'Exchange',
    };

    const filters = {
      types: typesResult.map(r => r.tx_type).filter(Boolean),
      categories: categoriesResult.map(r => r.tax_category).filter(Boolean),
      assets: assetsResult.map(r => r.asset).filter(Boolean),
      chains: chainsResult.map(r => ({
        value: r.chain,
        label: chainLabelMap[r.chain] || r.chain
      })).filter(c => c.value),
    };

    // Format transactions
    const formattedTx = transactions.map((tx: any) => {
      const amount = tx.asset === 'NEAR' 
        ? Number(tx.amount) / 1e24 
        : Number(tx.amount);
      const fee = tx.fee ? Number(tx.fee) / 1e24 : 0;
      const timestamp = Number(tx.block_timestamp) > 1e12 
        ? Number(tx.block_timestamp) / 1e9 
        : Number(tx.block_timestamp);
      
      return {
        id: `${tx.chain || 'near'}-${tx.id}`,
        tx_hash: tx.tx_hash,
        from_address: tx.direction === 'out' ? tx.wallet_address : tx.counterparty,
        to_address: tx.direction === 'in' ? tx.wallet_address : tx.counterparty,
        tx_type: tx.tx_type,
        asset: tx.asset,
        amount: amount,
        fee: fee,
        timestamp: new Date(timestamp * 1000).toISOString(),
        success: tx.success,
        chain: tx.chain || 'NEAR',
        chain_name: chainLabelMap[tx.chain] || tx.chain || 'NEAR',
        wallet_label: tx.wallet_label,
        wallet_address: tx.wallet_address,
        tax_category: tx.tax_category || 'uncategorized',
        source: tx.source,
        exchange: tx.exchange,
        description: tx.description,
      };
    });

    return NextResponse.json({
      transactions: formattedTx,
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
      filters,
    });
  } catch (error) {
    console.error('Transactions fetch error:', error);
    return NextResponse.json({ error: 'Failed to fetch transactions' }, { status: 500 });
  }
}
