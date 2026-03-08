import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// Income & Expense Report for Tax Purposes
// Tracks: Staking rewards, DeFi income, other income sources

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  
  const db = getDb();
  
  const yearStart = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
  const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
  
  // Get NEAR price for the year (average or year-end)
  const priceStmt = await db.prepare(`
    SELECT AVG(price) as avg_price FROM price_cache 
    WHERE coin_id = 'NEAR' AND date LIKE ?
  `);
  const priceResult = await priceStmt.get(`${year}%`) as { avg_price: number } | null;
  const nearPriceUsd = priceResult?.avg_price || 5.0;
  const cadRate = 1.38;
  
  // Staking Rewards
  const stakingStmt = await db.prepare(`
    SELECT 
      validator,
      SUM(reward_near) as total_rewards,
      COUNT(*) as count
    FROM staking_rewards
    WHERE block_timestamp >= ? AND block_timestamp < ?
    GROUP BY validator
    ORDER BY total_rewards DESC
  `);
  const stakingRewards = await stakingStmt.all(yearStart, yearEnd) as Array<{
    validator: string;
    total_rewards: number;
    count: number;
  }>;
  
  const totalStakingNear = stakingRewards.reduce((sum, r) => sum + r.total_rewards, 0);
  const totalStakingUsd = totalStakingNear * nearPriceUsd;
  const totalStakingCad = totalStakingUsd * cadRate;
  
  // DeFi Income (farming rewards, interest, etc.)
  const defiIncomeStmt = await db.prepare(`
    SELECT 
      protocol,
      token_symbol,
      SUM(amount_decimal) as total_amount,
      SUM(COALESCE(value_usd, 0)) as total_usd,
      SUM(COALESCE(value_cad, value_usd * 1.38, 0)) as total_cad,
      COUNT(*) as count
    FROM defi_events
    WHERE block_timestamp >= ? AND block_timestamp < ?
    AND tax_category = 'income'
    GROUP BY protocol, token_symbol
    ORDER BY total_amount DESC
  `);
  const defiIncome = await defiIncomeStmt.all(yearStart, yearEnd) as Array<{
    protocol: string;
    token_symbol: string;
    total_amount: number;
    total_usd: number;
    total_cad: number;
    count: number;
  }>;
  
  const totalDefiUsd = defiIncome.reduce((sum, r) => sum + (r.total_usd || 0), 0);
  const totalDefiCad = defiIncome.reduce((sum, r) => sum + (r.total_cad || 0), 0);
  
  // Transfer Income (received transfers that aren't internal)
  const transferIncomeStmt = await db.prepare(`
    SELECT 
      SUM(COALESCE(cost_basis_cad, cost_basis_usd * 1.38, 0)) as total_cad,
      SUM(CAST(amount AS REAL) / 1e24) as total_near,
      COUNT(*) as count
    FROM transactions
    WHERE block_timestamp >= ? AND block_timestamp < ?
    AND direction = 'in'
    AND tax_category IN ('transfer_in', 'deposit')
    AND cost_basis_usd > 0
  `);
  const transferIncome = await transferIncomeStmt.get(yearStart, yearEnd) as {
    total_cad: number;
    total_near: number;
    count: number;
  };
  
  // Expenses (gas fees, transaction costs)
  const expensesStmt = await db.prepare(`
    SELECT 
      SUM(CAST(fee AS REAL) / 1e24) as total_fees_near,
      COUNT(*) as count
    FROM transactions
    WHERE block_timestamp >= ? AND block_timestamp < ?
    AND fee IS NOT NULL AND CAST(fee AS REAL) > 0
  `);
  const expenses = await expensesStmt.get(yearStart, yearEnd) as {
    total_fees_near: number;
    count: number;
  };
  
  const totalFeesNear = expenses?.total_fees_near || 0;
  const totalFeesUsd = totalFeesNear * nearPriceUsd;
  const totalFeesCad = totalFeesUsd * cadRate;
  
  // Summary
  const totalIncomeUsd = totalStakingUsd + totalDefiUsd + (transferIncome?.total_cad || 0) / cadRate;
  const totalIncomeCad = totalStakingCad + totalDefiCad + (transferIncome?.total_cad || 0);
  
  return NextResponse.json({
    year,
    nearPriceUsd,
    cadRate,
    income: {
      staking: {
        totalNear: totalStakingNear,
        totalUsd: totalStakingUsd,
        totalCad: totalStakingCad,
        byValidator: stakingRewards
      },
      defi: {
        totalUsd: totalDefiUsd,
        totalCad: totalDefiCad,
        byProtocol: defiIncome
      },
      transfers: {
        totalCad: transferIncome?.total_cad || 0,
        totalNear: transferIncome?.total_near || 0,
        count: transferIncome?.count || 0
      },
      total: {
        usd: totalIncomeUsd,
        cad: totalIncomeCad
      }
    },
    expenses: {
      gasFees: {
        totalNear: totalFeesNear,
        totalUsd: totalFeesUsd,
        totalCad: totalFeesCad,
        count: expenses?.count || 0
      },
      total: {
        usd: totalFeesUsd,
        cad: totalFeesCad
      }
    },
    netIncome: {
      usd: totalIncomeUsd - totalFeesUsd,
      cad: totalIncomeCad - totalFeesCad
    },
    notes: [
      'Staking rewards are taxable income in Canada',
      'DeFi farming rewards are taxable income',
      'Gas fees may be deductible as expenses',
      'All values in CAD using estimated exchange rates'
    ]
  });
}
