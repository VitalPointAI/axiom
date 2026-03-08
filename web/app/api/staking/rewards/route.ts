// API Route: /api/staking/rewards/route.ts
// Per-epoch staking rewards with USD/CAD values for tax reporting

import { getAuthenticatedUser } from '@/lib/auth';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

interface EpochReward {
  id: number;
  epoch_id: number;
  epoch_date: string;
  validator_id: string;
  account_id: string;
  reward_near: number;
  reward_usd: number | null;
  reward_cad: number | null;
  near_price_usd: number | null;
  balance_before: string;
  balance_after: string;
}

function formatCsvRow(row: EpochReward): string {
  return [
    row.epoch_date || '',
    row.epoch_id,
    row.account_id,
    row.validator_id,
    row.reward_near?.toFixed(10) || '0',
    row.near_price_usd?.toFixed(4) || '',
    row.reward_usd?.toFixed(2) || '',
    row.reward_cad?.toFixed(2) || ''
  ].join(',');
}

export async function GET(request: Request) {
  // SECURITY: Require authentication
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const year = await searchParams.get('year');
  const walletId = await searchParams.get('wallet_id');
  const validator = await searchParams.get('validator');
  const format = await searchParams.get('format'); // csv or json
  
  const db = getDb();
  
  // Get THIS USER's wallet IDs
  const userWallets = await db.prepare(`
    SELECT id, account_id FROM wallets WHERE user_id = ?
  `).all(auth.userId) as { id: number; account_id: string }[];
  
  const walletIds = userWallets.map(w => w.id);
  const walletMap = new Map(userWallets.map(w => [w.id, w.account_id]));
  
  if (walletIds.length === 0) {
    if (format === 'csv') {
      return new Response('No wallets found', { status: 404 });
    }
    return NextResponse.json({ rewards: [], summary: { total_near: 0, total_usd: 0, total_cad: 0 } });
  }
  
  // Build query conditions
  let conditions = ['wallet_id = ANY($1::int[])'];
  const params: any[] = [walletIds];
  let paramIdx = 2;
  
  if (year) {
    conditions.push(`EXTRACT(YEAR FROM epoch_date) = $${paramIdx}`);
    params.push(parseInt(year));
    paramIdx++;
  }
  
  if (walletId) {
    const wId = parseInt(walletId);
    if (walletIds.includes(wId)) {
      conditions.push(`wallet_id = $${paramIdx}`);
      params.push(wId);
      paramIdx++;
    }
  }
  
  if (validator) {
    conditions.push(`validator_id = $${paramIdx}`);
    params.push(validator);
    paramIdx++;
  }
  
  const whereClause = conditions.join(' AND ');
  
  // Get rewards
  const rewards = await db.prepare(`
    SELECT id, wallet_id, validator_id, epoch_id, epoch_date,
           reward_near, reward_usd, reward_cad, near_price_usd,
           balance_before, balance_after, deposits, withdrawals
    FROM staking_epoch_rewards
    WHERE ${whereClause}
    ORDER BY epoch_date DESC, epoch_id DESC, validator_id
  `).all(...params) as Array<{
    id: number;
    wallet_id: number;
    validator_id: string;
    epoch_id: number;
    epoch_date: string;
    reward_near: number;
    reward_usd: number | null;
    reward_cad: number | null;
    near_price_usd: number | null;
    balance_before: string;
    balance_after: string;
    deposits: string;
    withdrawals: string;
  }>;
  
  // Add account names
  const rewardsWithAccounts = rewards.map(r => ({
    ...r,
    account_id: walletMap.get(r.wallet_id) || `wallet_${r.wallet_id}`
  }));
  
  // CSV export
  if (format === 'csv') {
    const header = 'Date,Epoch,Wallet,Validator,Reward (NEAR),Price (USD),Value (USD),Value (CAD)';
    const rows = rewardsWithAccounts.map(formatCsvRow);
    const csv = [header, ...rows].join('\n');
    
    const filename = year 
      ? `staking_rewards_${year}.csv` 
      : 'staking_rewards_all.csv';
    
    return new Response(csv, {
      headers: {
        'Content-Type': 'text/csv',
        'Content-Disposition': `attachment; filename="${filename}"`
      }
    });
  }
  
  // Calculate summary
  const summary = await db.prepare(`
    SELECT 
      COALESCE(SUM(reward_near), 0) as total_near,
      COALESCE(SUM(reward_usd), 0) as total_usd,
      COALESCE(SUM(reward_cad), 0) as total_cad,
      COUNT(*) as epoch_count,
      MIN(epoch_date) as first_epoch,
      MAX(epoch_date) as last_epoch
    FROM staking_epoch_rewards
    WHERE ${whereClause}
  `).get(...params) as {
    total_near: number;
    total_usd: number;
    total_cad: number;
    epoch_count: number;
    first_epoch: string;
    last_epoch: string;
  };
  
  // By validator summary
  const byValidator = await db.prepare(`
    SELECT 
      validator_id,
      COALESCE(SUM(reward_near), 0) as total_near,
      COALESCE(SUM(reward_usd), 0) as total_usd,
      COALESCE(SUM(reward_cad), 0) as total_cad,
      COUNT(*) as epoch_count
    FROM staking_epoch_rewards
    WHERE ${whereClause}
    GROUP BY validator_id
    ORDER BY total_near DESC
  `).all(...params) as Array<{
    validator_id: string;
    total_near: number;
    total_usd: number;
    total_cad: number;
    epoch_count: number;
  }>;
  
  // By month summary (for charts)
  const byMonth = await db.prepare(`
    SELECT 
      TO_CHAR(epoch_date, 'YYYY-MM') as month,
      COALESCE(SUM(reward_near), 0) as total_near,
      COALESCE(SUM(reward_usd), 0) as total_usd,
      COUNT(*) as epoch_count
    FROM staking_epoch_rewards
    WHERE ${whereClause}
    GROUP BY TO_CHAR(epoch_date, 'YYYY-MM')
    ORDER BY month DESC
  `).all(...params) as Array<{
    month: string;
    total_near: number;
    total_usd: number;
    epoch_count: number;
  }>;
  
  return NextResponse.json({
    rewards: rewardsWithAccounts.slice(0, 500), // Limit to 500 for JSON response
    summary,
    byValidator,
    byMonth,
    totalCount: rewards.length
  });
}
