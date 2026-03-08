import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  
  const db = getDb();
  
  // Get year boundaries (in nanoseconds)
  const yearStart = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
  const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
  
  // Count transactions by category
  const categories = await db.prepare(`
    SELECT 
      tax_category,
      COUNT(*) as count,
      SUM(COALESCE(cost_basis_cad, cost_basis_usd * 1.35, 0)) as total_cad
    FROM transactions
    WHERE block_timestamp >= ? AND block_timestamp < ?
    GROUP BY tax_category
  `).all(yearStart, yearEnd);
  
  // Get staking income for the year (from staking_income table)
  const stakingResult = await db.prepare(`
    SELECT 
      SUM(reward_near) as total_near,
      SUM(income_usd) as total_usd,
      SUM(income_cad) as total_cad
    FROM staking_income
    WHERE tax_year = ?
  `).get(year) as { total_near: number; total_usd: number; total_cad: number } | undefined;
  
  // Get DeFi income for the year
  const defiIncome = await db.prepare(`
    SELECT 
      token_symbol,
      SUM(amount_decimal) as total_tokens,
      SUM(COALESCE(value_cad, value_usd * 1.35, 0)) as total_cad
    FROM defi_events
    WHERE block_timestamp >= ? AND block_timestamp < ?
    AND tax_category = 'income'
    GROUP BY token_symbol
  `).all(yearStart, yearEnd);
  
  // Get trades for the year
  const tradesResult = await db.prepare(`
    SELECT COUNT(*) as count FROM defi_events
    WHERE block_timestamp >= ? AND block_timestamp < ?
    AND tax_category = 'trade'
  `).get(yearStart, yearEnd) as { count: number } | undefined;
  
  // Year-end holdings
  const holdings = await db.prepare(`
    SELECT 
      w.account_id,
      w.chain,
      COUNT(t.id) as tx_count,
      MAX(t.block_timestamp) as last_activity
    FROM wallets w
    LEFT JOIN transactions t ON t.wallet_id = w.id
    WHERE w.chain = 'near'
    GROUP BY w.id
  `).all();
  
  // Capital gains from calculated_disposals
  let capitalGains = { disposal_count: 0, total_proceeds: 0, total_cost_basis: 0, net_gain_loss: 0 };
  try {
    const result = await db.prepare(`
      SELECT 
        COUNT(*) as disposal_count,
        SUM(proceeds_cad) as total_proceeds,
        SUM(acb_cad) as total_cost_basis,
        SUM(gain_loss_cad) as net_gain_loss
      FROM calculated_disposals
      WHERE year = ?
    `).get(year) as any;
    if (result) {
      capitalGains = result;
    }
  } catch (e) {
    // Table might not exist
  }
  
  // Warnings/issues
  const warningsResult = await db.prepare(`
    SELECT COUNT(*) as count FROM transactions
    WHERE block_timestamp >= ? AND block_timestamp < ?
    AND (price_warning IS NOT NULL AND price_resolved != 1)
  `).get(yearStart, yearEnd) as { count: number } | undefined;
  
  // Gas fees paid (deductible expense for investment activity)
  const feesResult = await db.prepare(`
    SELECT 
      COUNT(*) as tx_count,
      SUM(CAST(fee AS REAL) / 1e24) as total_near
    FROM transactions
    WHERE block_timestamp >= ? AND block_timestamp < ?
    AND fee IS NOT NULL AND CAST(fee AS REAL) > 0
  `).get(yearStart, yearEnd) as { tx_count: number; total_near: number } | undefined;
  
  // Get average NEAR price for the year to convert fees to CAD
  const avgPriceResult = await db.prepare(`
    SELECT AVG(cost_basis_cad / (CAST(amount AS REAL) / 1e24)) as avg_price
    FROM transactions
    WHERE block_timestamp >= ? AND block_timestamp < ?
    AND cost_basis_cad > 0 AND CAST(amount AS REAL) > 1e20
  `).get(yearStart, yearEnd) as { avg_price: number } | undefined;
  const avgNearPrice = avgPriceResult?.avg_price || 5.0; // Default $5 CAD if no data
  
  const totalFeesNear = feesResult?.total_near || 0;
  const totalFeesCad = totalFeesNear * avgNearPrice;
  
  return NextResponse.json({
    year,
    categories,
    stakingIncome: {
      near: stakingResult?.total_near || 0,
      usd: stakingResult?.total_usd || 0,
      cad: stakingResult?.total_cad || 0,
    },
    defiIncome,
    trades: tradesResult?.count || 0,
    capitalGains: {
      disposals: capitalGains?.disposal_count || 0,
      proceeds: capitalGains?.total_proceeds || 0,
      costBasis: capitalGains?.total_cost_basis || 0,
      netGainLoss: capitalGains?.net_gain_loss || 0,
    },
    gasFees: {
      transactions: feesResult?.tx_count || 0,
      totalNear: totalFeesNear,
      totalCad: totalFeesCad,
      avgNearPrice: avgNearPrice,
    },
    holdings,
    warnings: warningsResult?.count || 0
  });
}
