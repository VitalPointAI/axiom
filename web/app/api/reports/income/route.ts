import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

// Income Report for Tax Purposes
// SECURITY: All queries filtered by user_id

export async function GET(request: Request) {
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  
  const db = getDb();
  
  // SECURITY: Get user's wallet IDs
  const userWallets = await db.prepare(`SELECT id FROM wallets WHERE user_id = $1`).all(auth.userId) as { id: number }[];
  const walletIds = userWallets.map(w => w.id);
  
  if (walletIds.length === 0) {
    return NextResponse.json({
      year,
      nearPriceUsd: 0,
      cadRate: 1.35,
      income: {
        staking: { totalNear: 0, totalUsd: 0, totalCad: 0, byValidator: [] },
        defi: { totalUsd: 0, totalCad: 0, byProtocol: [] },
        transfers: { totalCad: 0, totalNear: 0, count: 0 },
        total: { usd: 0, cad: 0 }
      },
      expenses: {
        gasFees: { totalNear: 0, totalUsd: 0, totalCad: 0, count: 0 },
        total: { usd: 0, cad: 0 }
      },
      netIncome: { usd: 0, cad: 0 },
      notes: ['No wallets found for this user']
    });
  }
  
  const yearStart = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
  const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
  
  // Get NEAR price for the year
  const priceResult = await db.prepare(`
    SELECT AVG(price) as avg_price FROM price_cache 
    WHERE coin_id = 'NEAR' AND date LIKE $1
  `).get(`${year}%`) as { avg_price: number } | null;
  const nearPriceUsd = priceResult?.avg_price || 5.0;
  
  // Get CAD rate
  const rateResult = await db.prepare(`
    SELECT AVG(price) as avg_rate FROM price_cache 
    WHERE coin_id = 'CADUSD' AND date LIKE $1
  `).get(`${year}%`) as { avg_rate: number } | null;
  const cadRate = rateResult?.avg_rate ? (1 / rateResult.avg_rate) : 1.35;
  
  // Staking Rewards from staking_income table - FILTERED
  const stakingRewards = await db.prepare(`
    SELECT 
      validator,
      SUM(reward_near) as total_rewards,
      SUM(COALESCE(income_cad, income_usd * $1, 0)) as total_cad,
      COUNT(*) as count
    FROM staking_income
    WHERE tax_year = $2 AND wallet_id = ANY($3::int[])
    GROUP BY validator
    ORDER BY total_rewards DESC
  `).all(cadRate, year, [walletIds]) as Array<{
    validator: string;
    total_rewards: number;
    total_cad: number;
    count: number;
  }>;
  
  const totalStakingNear = stakingRewards.reduce((sum, r) => sum + Number(r.total_rewards || 0), 0);
  const totalStakingCad = stakingRewards.reduce((sum, r) => sum + Number(r.total_cad || 0), 0);
  const totalStakingUsd = totalStakingCad / cadRate;
  
  // DeFi Income - FILTERED
  const defiIncome = await db.prepare(`
    SELECT 
      protocol,
      token_symbol,
      SUM(amount_decimal) as total_amount,
      SUM(COALESCE(value_usd, 0)) as total_usd,
      SUM(COALESCE(value_cad, value_usd * $1, 0)) as total_cad,
      COUNT(*) as count
    FROM defi_events
    WHERE block_timestamp >= $2 AND block_timestamp < $3
    AND tax_category = 'income'
    AND wallet_id = ANY($4::int[])
    GROUP BY protocol, token_symbol
    ORDER BY total_amount DESC
  `).all(cadRate, yearStart, yearEnd, [walletIds]) as Array<{
    protocol: string;
    token_symbol: string;
    total_amount: number;
    total_usd: number;
    total_cad: number;
    count: number;
  }>;
  
  const totalDefiUsd = defiIncome.reduce((sum, r) => sum + Number(r.total_usd || 0), 0);
  const totalDefiCad = defiIncome.reduce((sum, r) => sum + Number(r.total_cad || 0), 0);
  
  // Transfer Income - FILTERED
  const transferIncome = await db.prepare(`
    SELECT 
      SUM(COALESCE(cost_basis_cad, cost_basis_usd * $1, 0)) as total_cad,
      SUM(CAST(amount AS REAL) / 1e24) as total_near,
      COUNT(*) as count
    FROM transactions
    WHERE block_timestamp >= $2 AND block_timestamp < $3
    AND wallet_id = ANY($4::int[])
    AND direction = 'in'
    AND tax_category IN ('transfer_in', 'deposit')
    AND cost_basis_usd > 0
  `).get(cadRate, yearStart, yearEnd, [walletIds]) as {
    total_cad: number;
    total_near: number;
    count: number;
  } | null;
  
  // Expenses (gas fees) - FILTERED
  const expenses = await db.prepare(`
    SELECT 
      SUM(CAST(fee AS REAL) / 1e24) as total_fees_near,
      COUNT(*) as count
    FROM transactions
    WHERE block_timestamp >= $1 AND block_timestamp < $2
    AND wallet_id = ANY($3::int[])
    AND fee IS NOT NULL AND CAST(fee AS REAL) > 0
  `).get(yearStart, yearEnd, [walletIds]) as {
    total_fees_near: number;
    count: number;
  } | null;
  
  const totalFeesNear = Number(expenses?.total_fees_near || 0);
  const totalFeesUsd = totalFeesNear * nearPriceUsd;
  const totalFeesCad = totalFeesUsd * cadRate;
  
  // Summary
  const totalIncomeUsd = totalStakingUsd + totalDefiUsd + (Number(transferIncome?.total_cad || 0) / cadRate);
  const totalIncomeCad = totalStakingCad + totalDefiCad + Number(transferIncome?.total_cad || 0);
  
  return NextResponse.json({
    year,
    nearPriceUsd: Number(nearPriceUsd.toFixed(4)),
    cadRate: Number(cadRate.toFixed(4)),
    income: {
      staking: {
        totalNear: Number(totalStakingNear.toFixed(4)),
        totalUsd: Number(totalStakingUsd.toFixed(2)),
        totalCad: Number(totalStakingCad.toFixed(2)),
        byValidator: stakingRewards.map(r => ({
          validator: r.validator,
          totalRewards: Number(r.total_rewards),
          totalCad: Number(r.total_cad),
          count: r.count
        }))
      },
      defi: {
        totalUsd: Number(totalDefiUsd.toFixed(2)),
        totalCad: Number(totalDefiCad.toFixed(2)),
        byProtocol: defiIncome.map(r => ({
          protocol: r.protocol,
          tokenSymbol: r.token_symbol,
          totalAmount: Number(r.total_amount),
          totalUsd: Number(r.total_usd),
          totalCad: Number(r.total_cad),
          count: r.count
        }))
      },
      transfers: {
        totalCad: Number(transferIncome?.total_cad || 0),
        totalNear: Number(transferIncome?.total_near || 0),
        count: Number(transferIncome?.count || 0)
      },
      total: {
        usd: Number(totalIncomeUsd.toFixed(2)),
        cad: Number(totalIncomeCad.toFixed(2))
      }
    },
    expenses: {
      gasFees: {
        totalNear: Number(totalFeesNear.toFixed(6)),
        totalUsd: Number(totalFeesUsd.toFixed(2)),
        totalCad: Number(totalFeesCad.toFixed(2)),
        count: Number(expenses?.count || 0)
      },
      total: {
        usd: Number(totalFeesUsd.toFixed(2)),
        cad: Number(totalFeesCad.toFixed(2))
      }
    },
    netIncome: {
      usd: Number((totalIncomeUsd - totalFeesUsd).toFixed(2)),
      cad: Number((totalIncomeCad - totalFeesCad).toFixed(2))
    },
    notes: [
      'Staking rewards are taxable income in Canada',
      'DeFi farming rewards are taxable income',
      'Gas fees may be deductible as expenses',
      `Using average NEAR price of $${nearPriceUsd.toFixed(2)} USD for ${year}`,
      `USD/CAD rate: ${cadRate.toFixed(4)}`
    ]
  });
}
