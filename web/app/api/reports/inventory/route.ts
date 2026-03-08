import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// Year-end inventory for T1135 reporting
// Tracks holdings at end of each year with cost basis

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  
  const db = getDb();
  
  // Get year-end timestamp (Dec 31 23:59:59 UTC in nanoseconds)
  const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
  
  // Calculate NEAR balance at year end
  // Sum all inflows minus outflows up to year end
  const nearBalanceStmt = await db.prepare(`
    SELECT 
      SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) -
      SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as balance,
      SUM(CASE WHEN direction = 'in' THEN COALESCE(cost_basis_cad, cost_basis_usd * 1.35, 0) ELSE 0 END) -
      SUM(CASE WHEN direction = 'out' THEN COALESCE(cost_basis_cad, cost_basis_usd * 1.35, 0) ELSE 0 END) as cost_basis_cad
    FROM transactions
    WHERE block_timestamp < ?
  `);
  const nearResult = await nearBalanceStmt.get(yearEnd) as { balance: number; cost_basis_cad: number } | null;
  
  // Get FT token balances at year end
  const ftBalanceStmt = await db.prepare(`
    SELECT 
      token_symbol,
      SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 18)) ELSE 0 END) -
      SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 18)) ELSE 0 END) as balance,
      SUM(CASE WHEN direction = 'in' THEN COALESCE(value_cad, value_usd * 1.35, 0) ELSE 0 END) -
      SUM(CASE WHEN direction = 'out' THEN COALESCE(value_cad, value_usd * 1.35, 0) ELSE 0 END) as cost_basis_cad
    FROM ft_transactions
    WHERE block_timestamp < ?
    GROUP BY token_symbol
    HAVING balance > 0.001
  `);
  const ftBalances = await ftBalanceStmt.all(yearEnd) as Array<{ 
    token_symbol: string; 
    balance: number; 
    cost_basis_cad: number 
  }>;
  
  // Get staking positions at year end
  const stakingStmt = await db.prepare(`
    SELECT 
      validator,
      SUM(CASE WHEN event_type = 'stake' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) -
      SUM(CASE WHEN event_type = 'unstake' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as staked_amount
    FROM staking_events
    WHERE block_timestamp < ?
    GROUP BY validator
    HAVING staked_amount > 0
  `);
  const stakingPositions = await stakingStmt.all(yearEnd) as Array<{
    validator: string;
    staked_amount: number;
  }>;
  
  // Get NEAR price at year end for FMV
  const priceStmt = await db.prepare(`
    SELECT price_usd FROM price_cache
    WHERE symbol = 'NEAR' 
    AND timestamp <= ?
    ORDER BY timestamp DESC
    LIMIT 1
  `);
  const priceResult = await priceStmt.get(yearEnd / 1000000) as { price_usd: number } | null;
  const nearPriceUsd = priceResult?.price_usd || 5.0; // Default estimate
  
  // Calculate totals
  const nearBalance = nearResult?.balance || 0;
  const nearCostBasis = nearResult?.cost_basis_cad || 0;
  const totalStaked = stakingPositions.reduce((sum, p) => sum + p.staked_amount, 0);
  const totalNearHoldings = nearBalance + totalStaked;
  
  // Estimate FMV (Fair Market Value) at year end
  const cadRate = 1.35; // Approximate
  const nearFmvCad = totalNearHoldings * nearPriceUsd * cadRate;
  
  // Build inventory items
  const inventory = [
    {
      description: 'NEAR Protocol (liquid)',
      symbol: 'NEAR',
      units: nearBalance,
      costBasisCad: nearCostBasis,
      fmvCad: nearBalance * nearPriceUsd * cadRate,
      pricePerUnit: nearPriceUsd * cadRate
    },
    {
      description: 'NEAR Protocol (staked)',
      symbol: 'NEAR (staked)',
      units: totalStaked,
      costBasisCad: 0, // Would need to track separately
      fmvCad: totalStaked * nearPriceUsd * cadRate,
      pricePerUnit: nearPriceUsd * cadRate
    },
    ...ftBalances
      .filter(t => !t.token_symbol.includes('🎉') && !t.token_symbol.includes('.com') && !t.token_symbol.includes('.org'))
      .map(t => ({
        description: `${t.token_symbol} Token`,
        symbol: t.token_symbol,
        units: t.balance,
        costBasisCad: t.cost_basis_cad,
        fmvCad: 0, // Would need token prices
        pricePerUnit: 0
      }))
  ];
  
  // T1135 filing threshold
  const totalCostBasis = inventory.reduce((sum, i) => sum + i.costBasisCad, 0);
  const totalFmv = inventory.reduce((sum, i) => sum + i.fmvCad, 0);
  
  return NextResponse.json({
    year,
    asOfDate: `${year}-12-31`,
    inventory: inventory.filter(i => i.units > 0),
    stakingPositions,
    summary: {
      totalNearHoldings,
      nearPriceUsd,
      cadRate,
      totalCostBasisCad: totalCostBasis,
      totalFmvCad: totalFmv,
      exceedsT1135Threshold: Math.max(totalCostBasis, totalFmv) > 100000
    },
    notes: [
      'Inventory calculated based on cumulative transactions through year-end',
      'FMV (Fair Market Value) uses approximate year-end prices',
      'Cost basis may be incomplete for transactions without price data',
      'Staked NEAR included in total holdings',
      'Some spam tokens filtered from inventory'
    ]
  });
}
