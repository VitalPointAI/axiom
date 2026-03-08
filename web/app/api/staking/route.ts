import { getAuthenticatedUser } from '@/lib/auth';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: Request) {
  // SECURITY: Require authentication
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year');
  
  const db = getDb();
  
  // Get THIS USER's wallet IDs first
  const userWallets = await db.prepare(`
    SELECT id FROM wallets WHERE user_id = $1
  `).all(auth.userId) as { id: number }[];
  
  const walletIds = userWallets.map(w => w.id);
  
  // If user has no wallets, return empty data
  if (walletIds.length === 0) {
    return NextResponse.json({
      summary: [],
      validators: [],
      total: { near: 0, usd: 0, cad: 0 },
      positions: []
    });
  }
  
  // Summary by year - FILTERED BY USER'S WALLETS
  let summary;
  if (year) {
    summary = await db.prepare(`
      SELECT tax_year, 
             SUM(reward_near) as total_near,
             SUM(income_usd) as total_usd,
             SUM(income_cad) as total_cad,
             COUNT(*) as days
      FROM staking_income 
      WHERE tax_year = $1 AND wallet_id = ANY($2::int[])
      GROUP BY tax_year
    `).all(year, [walletIds]);
  } else {
    summary = await db.prepare(`
      SELECT tax_year, 
             SUM(reward_near) as total_near,
             SUM(income_usd) as total_usd,
             SUM(income_cad) as total_cad,
             COUNT(*) as days
      FROM staking_income
      WHERE wallet_id = ANY($1::int[])
      GROUP BY tax_year
      ORDER BY tax_year
    `).all([walletIds]);
  }
  
  // By validator - FILTERED BY USER'S WALLETS
  const byValidator = await db.prepare(`
    SELECT validator,
           SUM(reward_near) as total_near,
           SUM(income_usd) as total_usd,
           SUM(income_cad) as total_cad,
           COUNT(*) as days
    FROM staking_income
    WHERE wallet_id = ANY($1::int[])
    GROUP BY validator
    ORDER BY total_near DESC
  `).all([walletIds]) as Array<{
    validator: string;
    total_near: number;
    total_usd: number;
    total_cad: number;
    days: number;
  }>;
  
  // Total - FILTERED BY USER'S WALLETS
  const total = await db.prepare(`
    SELECT 
      SUM(reward_near) as total_near,
      SUM(income_usd) as total_usd,
      SUM(income_cad) as total_cad
    FROM staking_income
    WHERE wallet_id = ANY($1::int[])
  `).get([walletIds]) as { total_near: number; total_usd: number; total_cad: number } | null;
  
  // Current staking positions - FILTERED BY USER'S WALLETS
  const positions = await db.prepare(`
    SELECT sp.validator, w.account_id, sp.staked_amount
    FROM staking_positions sp
    JOIN wallets w ON sp.wallet_id = w.id
    WHERE sp.wallet_id = ANY($1::int[]) AND CAST(sp.staked_amount AS NUMERIC) > 0
    ORDER BY CAST(sp.staked_amount AS NUMERIC) DESC
  `).all([walletIds]) as Array<{
    validator: string;
    account_id: string;
    staked_amount: string;
  }>;
  
  return NextResponse.json({
    summary,
    validators: byValidator,
    total: {
      near: total?.total_near || 0,
      usd: total?.total_usd || 0,
      cad: total?.total_cad || 0
    },
    positions: positions.map(p => ({
      validator: p.validator,
      account: p.account_id,
      stakedNear: Number(p.staked_amount) / 1e24
    }))
  });
}
