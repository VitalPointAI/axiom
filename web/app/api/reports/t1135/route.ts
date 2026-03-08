import { getAuthenticatedUser } from '@/lib/auth';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// T1135 - Foreign Income Verification Statement
// Required if cost amount of specified foreign property > $100,000 CAD at any time in year

export async function GET(request: Request) {
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  
  const db = getDb();
  
  // SECURITY: Get this user's wallet IDs first
  const userWallets = await db.prepare(`
    SELECT id FROM wallets WHERE user_id = $1
  `).all(auth.userId) as { id: number }[];
  const walletIds = userWallets.map(w => w.id);
  
  // If no wallets, return empty report
  if (walletIds.length === 0) {
    return NextResponse.json({
      year,
      filingRequired: false,
      category: 'Not Required',
      totalMaxCostAmount: 0,
      totalYearEndCost: 0,
      totalIncome: 0,
      totalGainLoss: 0,
      foreignProperty: [],
      walletCount: 0,
      priceData: { avgNearPriceUsd: 0, avgNearPriceCad: 0, usdCadRate: 1.35, source: 'none' },
      notes: ['No wallets found for this user']
    });
  }
  
  const yearStart = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
  const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
  
  // Get actual average NEAR price for the year from price_cache
  const priceResult = await db.prepare(`
    SELECT AVG(price) as avg_price 
    FROM price_cache 
    WHERE coin_id = 'NEAR' AND date LIKE $1
  `).get(`${year}%`) as { avg_price: number | null };
  const avgNearPriceUsd = priceResult?.avg_price || 5.0;
  
  // Get USD/CAD rate from price_cache (stored as CADUSD)
  const rateResult = await db.prepare(`
    SELECT AVG(price) as avg_rate 
    FROM price_cache 
    WHERE coin_id = 'CADUSD' AND date LIKE $1
  `).get(`${year}%`) as { avg_rate: number | null };
  // CADUSD is inverted, so divide 1 by it to get USDCAD
  const usdCadRate = rateResult?.avg_rate ? (1 / rateResult.avg_rate) : 1.35;
  
  const avgNearPriceCad = avgNearPriceUsd * usdCadRate;
  
  // Get user's wallets
  const wallets = await db.prepare(`
    SELECT id, account_id, chain, label FROM wallets WHERE user_id = $1 AND chain = 'NEAR'
  `).all(auth.userId) as Array<{id: number, account_id: string, chain: string, label: string | null}>;
  
  // Calculate max cost during year by checking monthly snapshots - FILTERED
  let maxCostDuringYear = 0;
  for (let month = 1; month <= 12; month++) {
    const monthEnd = new Date(`${year}-${month.toString().padStart(2, '0')}-28T23:59:59Z`).getTime() * 1000000;
    
    const monthlyHoldings = await db.prepare(`
      SELECT 
        COALESCE(SUM(CAST(amount AS REAL) / 1e24), 0) as total_near
      FROM transactions t
      WHERE t.wallet_id = ANY($1::int[])
      AND t.block_timestamp <= $2
      AND t.direction = 'in'
    `).get([walletIds], monthEnd) as { total_near: number };
    
    const monthlyOutflows = await db.prepare(`
      SELECT 
        COALESCE(SUM(CAST(amount AS REAL) / 1e24), 0) as total_near
      FROM transactions t
      WHERE t.wallet_id = ANY($1::int[])
      AND t.block_timestamp <= $2
      AND t.direction = 'out'
    `).get([walletIds], monthEnd) as { total_near: number };
    
    const monthPrice = await db.prepare(`
      SELECT AVG(price) as price 
      FROM price_cache 
      WHERE coin_id = 'NEAR' AND date LIKE $1
    `).get(`${year}-${month.toString().padStart(2, '0')}%`) as { price: number | null };
    
    const monthlyBalance = (monthlyHoldings?.total_near || 0) - (monthlyOutflows?.total_near || 0);
    const monthlyCost = monthlyBalance * (monthPrice?.price || avgNearPriceUsd) * usdCadRate;
    
    if (monthlyCost > maxCostDuringYear) {
      maxCostDuringYear = monthlyCost;
    }
  }
  
  // Get staking income - FILTERED
  const stakingResult = await db.prepare(`
    SELECT 
      COALESCE(SUM(income_cad), SUM(income_usd) * $1, 0) as total_income
    FROM staking_income
    WHERE tax_year = $2 AND wallet_id = ANY($3::int[])
  `).get(usdCadRate, year, [walletIds]) as { total_income: number | null };
  const stakingIncome = Number(stakingResult?.total_income) || 0;
  
  // Get DeFi income - FILTERED
  const defiResult = await db.prepare(`
    SELECT 
      COALESCE(SUM(value_cad), SUM(value_usd) * $1, 0) as total_income
    FROM defi_events
    WHERE block_timestamp >= $2 AND block_timestamp < $3
    AND tax_category = 'income'
    AND wallet_id = ANY($4::int[])
  `).get(usdCadRate, yearStart, yearEnd, [walletIds]) as { total_income: number | null };
  const defiIncome = Number(defiResult?.total_income) || 0;
  
  // Get capital gains/losses - FILTERED via tx_id join
  let capitalGainLoss = 0;
  try {
    const gainsResult = await db.prepare(`
      SELECT 
        COALESCE(SUM(cd.gain_loss_cad), 0) as total_gain_loss
      FROM calculated_disposals cd
      JOIN transactions t ON cd.tx_id = t.id
      WHERE cd.year = $1 AND t.wallet_id = ANY($2::int[])
    `).get(parseInt(year), [walletIds]) as { total_gain_loss: number };
    capitalGainLoss = Number(gainsResult?.total_gain_loss) || 0;
  } catch (e) {
    // Table might be empty or have issues
    console.error('Error fetching capital gains:', e);
  }
  
  // Calculate year-end balance - FILTERED
  const yearEndHoldingsResult = await db.prepare(`
    SELECT 
      COALESCE(SUM(CAST(amount AS REAL) / 1e24), 0) as total_in
    FROM transactions t
    WHERE t.wallet_id = ANY($1::int[])
    AND t.block_timestamp < $2
    AND t.direction = 'in'
  `).get([walletIds], yearEnd) as { total_in: number };
  
  const yearEndOutflowsResult = await db.prepare(`
    SELECT 
      COALESCE(SUM(CAST(amount AS REAL) / 1e24), 0) as total_out
    FROM transactions t
    WHERE t.wallet_id = ANY($1::int[])
    AND t.block_timestamp < $2
    AND t.direction = 'out'
  `).get([walletIds], yearEnd) as { total_out: number };
  
  const yearEndNearBalance = (Number(yearEndHoldingsResult?.total_in) || 0) - (Number(yearEndOutflowsResult?.total_out) || 0);
  const yearEndCostAmount = yearEndNearBalance * avgNearPriceCad;
  
  const foreignProperty = [{
    description: 'Cryptocurrency - NEAR Protocol and tokens',
    country: 'N/A - Decentralized',
    maxCostAmount: Number(maxCostDuringYear.toFixed(2)),
    yearEndCostAmount: Number(yearEndCostAmount.toFixed(2)),
    income: Number((stakingIncome + defiIncome).toFixed(2)),
    gainLoss: Number(capitalGainLoss.toFixed(2)),
  }];
  
  let category = 'Not Required';
  const totalMaxCost = maxCostDuringYear;
  
  if (totalMaxCost > 250000) {
    category = 'Category 4 (>$250,000)';
  } else if (totalMaxCost > 100000) {
    category = 'Category 3 ($100,001 - $250,000)';
  } else if (totalMaxCost > 0) {
    category = 'Under Threshold (<$100,000)';
  }
  
  return NextResponse.json({
    year,
    filingRequired: totalMaxCost > 100000,
    category,
    totalMaxCostAmount: Number(totalMaxCost.toFixed(2)),
    totalYearEndCost: Number(yearEndCostAmount.toFixed(2)),
    totalIncome: Number((stakingIncome + defiIncome).toFixed(2)),
    totalGainLoss: Number(capitalGainLoss.toFixed(2)),
    foreignProperty,
    walletCount: wallets.length,
    priceData: {
      avgNearPriceUsd: Number(avgNearPriceUsd.toFixed(4)),
      avgNearPriceCad: Number(avgNearPriceCad.toFixed(4)),
      usdCadRate: Number(usdCadRate.toFixed(4)),
      source: priceResult?.avg_price ? 'price_cache' : 'fallback',
    },
    notes: [
      'Cryptocurrency held outside Canada is considered specified foreign property',
      'T1135 filing required if cost amount exceeds $100,000 CAD at any point in the year',
      'Report all staking rewards and DeFi income as foreign income',
      `Values calculated using actual NEAR price data (avg $${avgNearPriceUsd.toFixed(2)} USD)`,
      `USD/CAD rate: ${usdCadRate.toFixed(4)}`,
    ]
  });
}
