import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  const db = getDb();
  
  // Get summary by year and category
  const byCategoryStmt = await db.prepare(`
    SELECT 
      strftime('%Y', datetime(block_timestamp/1000000000, 'unixepoch')) as year,
      tax_category,
      protocol,
      COUNT(*) as count,
      SUM(COALESCE(value_usd, 0)) as total_usd,
      SUM(COALESCE(value_cad, 0)) as total_cad
    FROM defi_events
    GROUP BY year, tax_category, protocol
    ORDER BY year DESC, count DESC
  `);
  const byCategory = await byCategoryStmt.all();
  
  // Get income by token (for tax reporting)
  const incomeStmt = await db.prepare(`
    SELECT 
      strftime('%Y', datetime(block_timestamp/1000000000, 'unixepoch')) as year,
      token_symbol,
      protocol,
      COUNT(*) as count,
      SUM(amount_decimal) as total_tokens,
      SUM(COALESCE(value_usd, 0)) as total_usd,
      SUM(COALESCE(value_cad, 0)) as total_cad
    FROM defi_events
    WHERE tax_category = 'income'
    GROUP BY year, token_symbol, protocol
    ORDER BY year DESC, total_tokens DESC
  `);
  const income = await incomeStmt.all();
  
  // Get trade count by year
  const tradesStmt = await db.prepare(`
    SELECT 
      strftime('%Y', datetime(block_timestamp/1000000000, 'unixepoch')) as year,
      protocol,
      COUNT(*) as count
    FROM defi_events
    WHERE tax_category = 'trade'
    GROUP BY year, protocol
    ORDER BY year DESC
  `);
  const trades = await tradesStmt.all();
  
  // Protocol totals
  const protocolStmt = await db.prepare(`
    SELECT 
      protocol,
      COUNT(*) as count,
      SUM(CASE WHEN tax_category = 'income' THEN 1 ELSE 0 END) as income_count,
      SUM(CASE WHEN tax_category = 'trade' THEN 1 ELSE 0 END) as trade_count
    FROM defi_events
    GROUP BY protocol
  `);
  const protocols = await protocolStmt.all();
  
  // Events needing review
  const reviewStmt = await db.prepare(`
    SELECT COUNT(*) as count FROM defi_events WHERE needs_review = 1
  `);
  const { count: needsReview } = await reviewStmt.get() as { count: number };
  
  // Events missing prices
  const missingPricesStmt = await db.prepare(`
    SELECT COUNT(*) as count FROM defi_events WHERE value_usd IS NULL OR value_usd = 0
  `);
  const { count: missingPrices } = await missingPricesStmt.get() as { count: number };
  
  return NextResponse.json({
    byCategory,
    income,
    trades,
    protocols,
    needsReview,
    missingPrices
  });
}
