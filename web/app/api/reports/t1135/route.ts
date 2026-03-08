import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// T1135 - Foreign Income Verification Statement
// Required if cost amount of specified foreign property > $100,000 CAD at any time in year

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  
  const db = getDb();
  
  // For crypto, we need to track:
  // 1. Maximum cost amount during the year
  // 2. Year-end cost amount
  // 3. Income earned (staking, DeFi rewards)
  // 4. Gains/losses from disposition
  
  const yearStart = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
  const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
  
  // Get all wallets
  const walletsStmt = await db.prepare(`
    SELECT id, account_id, chain, label FROM wallets WHERE chain = 'near'
  `);
  const wallets = await walletsStmt.all() as Array<{id: number, account_id: string, chain: string, label: string | null}>;
  
  // For each wallet, calculate cost basis evolution
  const foreignProperty: Array<{
    description: string;
    country: string;
    maxCostAmount: number;
    yearEndCostAmount: number;
    income: number;
    gainLoss: number;
  }> = [];
  
  // Simplified: treat all NEAR holdings as one foreign property
  // In practice, you'd track each token separately
  
  // Get all inflows (cost basis adds)
  const inflowsStmt = await db.prepare(`
    SELECT 
      SUM(COALESCE(cost_basis_cad, cost_basis_usd * 1.35, 0)) as total_cost
    FROM transactions
    WHERE block_timestamp < ?
    AND direction = 'in'
  `);
  const inflowsResult = await inflowsStmt.get(yearEnd) as { total_cost: number | null };
  const totalCostBasis = inflowsResult?.total_cost || 0;
  
  // Get outflows (cost basis reduces)
  const outflowsStmt = await db.prepare(`
    SELECT 
      SUM(COALESCE(cost_basis_cad, cost_basis_usd * 1.35, 0)) as total_cost
    FROM transactions
    WHERE block_timestamp < ?
    AND direction = 'out'
  `);
  const outflowsResult = await outflowsStmt.get(yearEnd) as { total_cost: number | null };
  const totalOutflows = outflowsResult?.total_cost || 0;
  
  // Year-end cost amount (simplified)
  const yearEndCost = Math.max(0, totalCostBasis - totalOutflows);
  
  // Get income from staking
  const stakingStmt = await db.prepare(`
    SELECT SUM(reward_near) as rewards FROM staking_rewards 
    WHERE block_timestamp >= ? AND block_timestamp < ?
  `);
  const stakingResult = await stakingStmt.get(yearStart, yearEnd) as { rewards: number | null };
  
  // Get income from DeFi
  const defiStmt = await db.prepare(`
    SELECT SUM(COALESCE(value_cad, value_usd * 1.35, 0)) as income
    FROM defi_events
    WHERE block_timestamp >= ? AND block_timestamp < ?
    AND tax_category = 'income'
  `);
  const defiResult = await defiStmt.get(yearStart, yearEnd) as { income: number | null };
  
  // Estimate income in CAD (using average NEAR price for the year)
  const avgNearPrice = 5.0; // TODO: Get actual average
  const stakingIncome = (stakingResult?.rewards || 0) * avgNearPrice * 1.35; // CAD
  const defiIncome = defiResult?.income || 0;
  
  foreignProperty.push({
    description: 'Cryptocurrency - NEAR Protocol and tokens',
    country: 'N/A - Decentralized',
    maxCostAmount: yearEndCost * 1.2, // Rough estimate of max during year
    yearEndCostAmount: yearEndCost,
    income: stakingIncome + defiIncome,
    gainLoss: 0 // TODO: Calculate from disposals
  });
  
  // Determine filing category
  let category = 'Not Required';
  const totalMaxCost = foreignProperty.reduce((sum, p) => sum + p.maxCostAmount, 0);
  
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
    totalMaxCostAmount: totalMaxCost,
    totalYearEndCost: foreignProperty.reduce((sum, p) => sum + p.yearEndCostAmount, 0),
    totalIncome: foreignProperty.reduce((sum, p) => sum + p.income, 0),
    foreignProperty,
    walletCount: wallets.length,
    notes: [
      'Cryptocurrency held outside Canada is considered specified foreign property',
      'T1135 filing required if cost amount exceeds $100,000 CAD at any point in the year',
      'Report all staking rewards and DeFi income as foreign income',
      'Values shown in CAD using estimated exchange rates - verify with actual rates'
    ]
  });
}
