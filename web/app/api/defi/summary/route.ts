import { getAuthenticatedUser } from '@/lib/auth';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const db = getDb();
  
  // SECURITY: Get this user's wallet IDs first
  const userWallets = await db.prepare(`
    SELECT id FROM wallets WHERE user_id = $1
  `).all(auth.userId) as { id: number }[];
  
  const walletIds = userWallets.map(w => w.id);
  
  // If no wallets, return empty data
  if (walletIds.length === 0) {
    return NextResponse.json({
      byCategory: [],
      income: [],
      trades: [],
      protocols: [],
      needsReview: 0,
      missingPrices: 0
    });
  }
  
  // Get summary by year and category - FILTERED BY USER WALLETS
  const byCategory = await db.prepare(`
    SELECT 
      to_char(to_timestamp(block_timestamp/1000000000), 'YYYY') as year,
      tax_category,
      protocol,
      COUNT(*) as count,
      SUM(COALESCE(value_usd, 0)) as total_usd,
      SUM(COALESCE(value_cad, 0)) as total_cad
    FROM defi_events
    WHERE wallet_id = ANY($1::int[])
    GROUP BY year, tax_category, protocol
    ORDER BY year DESC, count DESC
  `).all([walletIds]);
  
  // Get income by token (for tax reporting) - FILTERED
  const income = await db.prepare(`
    SELECT 
      to_char(to_timestamp(block_timestamp/1000000000), 'YYYY') as year,
      token_symbol,
      protocol,
      COUNT(*) as count,
      SUM(amount_decimal) as total_tokens,
      SUM(COALESCE(value_usd, 0)) as total_usd,
      SUM(COALESCE(value_cad, 0)) as total_cad
    FROM defi_events
    WHERE tax_category = 'income' AND wallet_id = ANY($1::int[])
    GROUP BY year, token_symbol, protocol
    ORDER BY year DESC, total_tokens DESC
  `).all([walletIds]);
  
  // Get trade count by year - FILTERED
  const trades = await db.prepare(`
    SELECT 
      to_char(to_timestamp(block_timestamp/1000000000), 'YYYY') as year,
      protocol,
      COUNT(*) as count
    FROM defi_events
    WHERE tax_category = 'trade' AND wallet_id = ANY($1::int[])
    GROUP BY year, protocol
    ORDER BY year DESC
  `).all([walletIds]);
  
  // Protocol totals - FILTERED
  const protocols = await db.prepare(`
    SELECT 
      protocol,
      COUNT(*) as count,
      SUM(CASE WHEN tax_category = 'income' THEN 1 ELSE 0 END) as income_count,
      SUM(CASE WHEN tax_category = 'trade' THEN 1 ELSE 0 END) as trade_count
    FROM defi_events
    WHERE wallet_id = ANY($1::int[])
    GROUP BY protocol
  `).all([walletIds]);
  
  // Events needing review - FILTERED
  const reviewResult = await db.prepare(`
    SELECT COUNT(*) as count FROM defi_events WHERE needs_review = TRUE AND wallet_id = ANY($1::int[])
  `).get([walletIds]) as { count: number };
  
  // Events missing prices - FILTERED
  const missingResult = await db.prepare(`
    SELECT COUNT(*) as count FROM defi_events WHERE (value_usd IS NULL OR value_usd = 0) AND wallet_id = ANY($1::int[])
  `).get([walletIds]) as { count: number };
  
  return NextResponse.json({
    byCategory,
    income,
    trades,
    protocols,
    needsReview: Number(reviewResult?.count || 0),
    missingPrices: Number(missingResult?.count || 0)
  });
}
