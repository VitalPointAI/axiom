import { getAuthenticatedUser } from '@/lib/auth';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: Request) {
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  
  const db = getDb();
  
  // SECURITY: Get this user's wallet IDs
  const userWallets = await db.prepare(`
    SELECT id FROM wallets WHERE user_id = $1
  `).all(auth.userId) as { id: number }[];
  const walletIds = userWallets.map(w => w.id);
  
  // If no wallets, return empty data
  if (walletIds.length === 0) {
    return NextResponse.json({
      year,
      categories: [],
      stakingIncome: { near: 0, usd: 0, cad: 0 },
      defiIncome: [],
      trades: 0,
      capitalGains: { disposals: 0, proceeds: 0, costBasis: 0, netGainLoss: 0 },
      gasFees: { transactions: 0, totalNear: 0, totalCad: 0, avgNearPrice: 5 },
      holdings: [],
      warnings: 0
    });
  }
  
  // Get year boundaries (in nanoseconds)
  const yearStart = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
  const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
  
  // Count transactions by category - FILTERED BY USER WALLETS
  const categories = await db.prepare(`
    SELECT 
      tax_category,
      COUNT(*) as count,
      SUM(COALESCE(cost_basis_cad, cost_basis_usd * 1.35, 0)) as total_cad
    FROM transactions
    WHERE block_timestamp >= $1 AND block_timestamp < $2 AND wallet_id = ANY($3::int[])
    GROUP BY tax_category
  `).all(yearStart, yearEnd, [walletIds]);
  
  // Get staking income for the year - FILTERED
  const stakingResult = await db.prepare(`
    SELECT 
      SUM(reward_near) as total_near,
      SUM(income_usd) as total_usd,
      SUM(income_cad) as total_cad
    FROM staking_income
    WHERE tax_year = $1 AND wallet_id = ANY($2::int[])
  `).get(year, [walletIds]) as { total_near: number; total_usd: number; total_cad: number } | undefined;
  
  // Get DeFi income for the year - FILTERED
  const defiIncome = await db.prepare(`
    SELECT 
      token_symbol,
      SUM(amount_decimal) as total_tokens,
      SUM(COALESCE(value_cad, value_usd * 1.35, 0)) as total_cad
    FROM defi_events
    WHERE block_timestamp >= $1 AND block_timestamp < $2 AND wallet_id = ANY($3::int[])
    AND tax_category = 'income'
    GROUP BY token_symbol
  `).all(yearStart, yearEnd, [walletIds]);
  
  // Get trades for the year - FILTERED
  const tradesResult = await db.prepare(`
    SELECT COUNT(*) as count FROM defi_events
    WHERE block_timestamp >= $1 AND block_timestamp < $2 AND wallet_id = ANY($3::int[])
    AND tax_category = 'trade'
  `).get(yearStart, yearEnd, [walletIds]) as { count: number } | undefined;
  
  // Year-end holdings - FILTERED
  const holdings = await db.prepare(`
    SELECT 
      w.account_id,
      w.chain,
      COUNT(t.id) as tx_count,
      MAX(t.block_timestamp) as last_activity
    FROM wallets w
    LEFT JOIN transactions t ON t.wallet_id = w.id
    WHERE w.user_id = $1 AND w.chain = 'NEAR'
    GROUP BY w.id, w.account_id, w.chain
  `).all(auth.userId);
  
  // Capital gains from calculated_disposals - FILTERED via tx_id join to transactions
  let capitalGains = { disposal_count: 0, total_proceeds: 0, total_cost_basis: 0, net_gain_loss: 0 };
  try {
    const result = await db.prepare(`
      SELECT 
        COUNT(*) as disposal_count,
        SUM(cd.proceeds_cad) as total_proceeds,
        SUM(cd.acb_cad) as total_cost_basis,
        SUM(cd.gain_loss_cad) as net_gain_loss
      FROM calculated_disposals cd
      JOIN transactions t ON cd.tx_id = t.id
      WHERE cd.year = $1 AND t.wallet_id = ANY($2::int[])
    `).get(year, [walletIds]) as any;
    if (result) {
      capitalGains = result;
    }
  } catch (e) {
    // Table might not exist or have different schema
    console.error('Error fetching calculated_disposals:', e);
  }
  
  // Warnings/issues - FILTERED (price_resolved is integer, not boolean)
  const warningsResult = await db.prepare(`
    SELECT COUNT(*) as count FROM transactions
    WHERE block_timestamp >= $1 AND block_timestamp < $2 AND wallet_id = ANY($3::int[])
    AND price_warning IS NOT NULL AND (price_resolved IS NULL OR price_resolved = 0)
  `).get(yearStart, yearEnd, [walletIds]) as { count: number } | undefined;
  
  // Gas fees paid - FILTERED
  const feesResult = await db.prepare(`
    SELECT 
      COUNT(*) as tx_count,
      SUM(CAST(fee AS REAL) / 1e24) as total_near
    FROM transactions
    WHERE block_timestamp >= $1 AND block_timestamp < $2 AND wallet_id = ANY($3::int[])
    AND fee IS NOT NULL AND CAST(fee AS REAL) > 0
  `).get(yearStart, yearEnd, [walletIds]) as { tx_count: number; total_near: number } | undefined;
  
  // Get average NEAR price for the year - FILTERED
  const avgPriceResult = await db.prepare(`
    SELECT AVG(cost_basis_cad / (CAST(amount AS REAL) / 1e24)) as avg_price
    FROM transactions
    WHERE block_timestamp >= $1 AND block_timestamp < $2 AND wallet_id = ANY($3::int[])
    AND cost_basis_cad > 0 AND CAST(amount AS REAL) > 1e20
  `).get(yearStart, yearEnd, [walletIds]) as { avg_price: number } | undefined;
  const avgNearPrice = avgPriceResult?.avg_price || 5.0;
  
  const totalFeesNear = feesResult?.total_near || 0;
  const totalFeesCad = totalFeesNear * avgNearPrice;
  
  return NextResponse.json({
    year,
    categories,
    stakingIncome: {
      near: Number(stakingResult?.total_near) || 0,
      usd: Number(stakingResult?.total_usd) || 0,
      cad: Number(stakingResult?.total_cad) || 0,
    },
    defiIncome,
    trades: Number(tradesResult?.count) || 0,
    capitalGains: {
      disposals: Number(capitalGains?.disposal_count) || 0,
      proceeds: Number(capitalGains?.total_proceeds) || 0,
      costBasis: Number(capitalGains?.total_cost_basis) || 0,
      netGainLoss: Number(capitalGains?.net_gain_loss) || 0,
    },
    gasFees: {
      transactions: Number(feesResult?.tx_count) || 0,
      totalNear: totalFeesNear,
      totalCad: totalFeesCad,
      avgNearPrice: avgNearPrice,
    },
    holdings,
    warnings: Number(warningsResult?.count) || 0
  });
}
