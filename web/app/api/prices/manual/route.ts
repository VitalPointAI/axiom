import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// Manual price override for transactions

export async function POST(request: Request) {
  const body = await request.json();
  const { transactionId, priceUsd, note } = body;
  
  if (!transactionId || priceUsd === undefined) {
    return NextResponse.json({ error: 'Missing transactionId or priceUsd' }, { status: 400 });
  }
  
  const db = getDb();
  
  // Get transaction
  const txStmt = db.prepare('SELECT id, amount FROM transactions WHERE id = ?');
  const tx = txStmt.get(transactionId) as { id: number; amount: string } | undefined;
  
  if (!tx) {
    return NextResponse.json({ error: 'Transaction not found' }, { status: 404 });
  }
  
  // Calculate value
  const amountNear = parseFloat(tx.amount) / 1e24;
  const valueUsd = amountNear * priceUsd;
  const valueCad = valueUsd * 1.38; // Approximate CAD rate
  
  // Update
  const updateStmt = db.prepare(`
    UPDATE transactions 
    SET cost_basis_usd = ?,
        cost_basis_cad = ?,
        price_manual_usd = ?,
        price_manual_note = ?,
        price_resolved = 1,
        price_warning = NULL
    WHERE id = ?
  `);
  updateStmt.run(valueUsd, valueCad, priceUsd, note || 'Manual override', transactionId);
  
  return NextResponse.json({
    success: true,
    transactionId,
    amountNear,
    priceUsd,
    valueUsd,
    valueCad
  });
}

// Get transactions needing manual price
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const minAmount = parseFloat(searchParams.get('minAmount') || '1');
  const limit = parseInt(searchParams.get('limit') || '50');
  
  const db = getDb();
  
  const stmt = db.prepare(`
    SELECT 
      t.id,
      t.tx_hash,
      t.block_timestamp,
      CAST(t.amount AS REAL) / 1e24 as amount_near,
      t.direction,
      t.action_type,
      datetime(t.block_timestamp/1000000000, 'unixepoch') as datetime,
      w.account_id as wallet
    FROM transactions t
    LEFT JOIN wallets w ON t.wallet_id = w.id
    WHERE t.price_warning = 'historical_needed'
    AND CAST(t.amount AS REAL) / 1e24 >= ?
    ORDER BY CAST(t.amount AS REAL) DESC
    LIMIT ?
  `);
  
  const transactions = stmt.all(minAmount, limit);
  
  // Get count by year
  const yearStmt = db.prepare(`
    SELECT 
      strftime('%Y', datetime(block_timestamp/1000000000, 'unixepoch')) as year,
      COUNT(*) as count
    FROM transactions
    WHERE price_warning = 'historical_needed'
    AND CAST(amount AS REAL) / 1e24 >= ?
    GROUP BY year
    ORDER BY year
  `);
  const byYear = yearStmt.all(minAmount);
  
  return NextResponse.json({
    transactions,
    byYear,
    minAmount,
    total: transactions.length
  });
}
