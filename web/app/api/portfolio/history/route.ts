import { getAuthenticatedUser } from '@/lib/auth';
import { cookies } from 'next/headers';
import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

const NEARBLOCKS_API = 'https://api.nearblocks.io/v1';
const API_KEY = process.env.NEARBLOCKS_API_KEY || '0F1F69733B684BD48753570B3B9C4B27';

interface DailySnapshot {
  date: string;
  nearBalance: number;
  stakingBalance: number;
  totalNear: number;
  nearPrice: number;
  totalValueUsd: number;
}

async function getLiquidBalance(account: string): Promise<number> {
  try {
    const resp = await fetch(`${NEARBLOCKS_API}/account/${account}`, {
      headers: { Authorization: `Bearer ${API_KEY}` },
      next: { revalidate: 300 }
    });
    if (!resp.ok) return 0;
    const data = await resp.json();
    const acct = data.account?.[0] || {};
    return parseFloat(acct.amount || '0') / 1e24;
  } catch {
    return 0;
  }
}

export async function GET() {
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  try {
    const cookieStore = await cookies();
    const sessionToken = cookieStore.get('neartax_session')?.value;
    if (!sessionToken) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();
    
    // Get user from session
    const session = await db.prepare(`
      SELECT u.id, u.near_account_id
      FROM sessions s
      JOIN users u ON s.user_id = u.id
      WHERE s.id = ? AND s.expires_at > NOW()
    `).get(sessionToken) as { id: number; near_account_id: string } | undefined;

    if (!session) {
      const user = await db.prepare('SELECT id FROM users WHERE near_account_id = ?')
        .get(sessionToken) as { id: number } | undefined;
      if (!user) {
        return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
      }
    }

    const userId = session?.id || (await db.prepare('SELECT id FROM users WHERE near_account_id = ?')
      .get(sessionToken) as { id: number })?.id;

    if (!userId) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    const wallets = await db.prepare("SELECT id, account_id FROM wallets WHERE user_id = ? AND chain = 'NEAR'")
      .all(userId) as Array<{ id: number; account_id: string }>;

    if (wallets.length === 0) {
      return NextResponse.json({ history: [], currentValue: 0, currentNear: 0 });
    }

    const walletIdList = wallets.map(w => w.id);
    const trackedAccounts = new Set(wallets.map(w => w.account_id));
    const trackedAccountsList = Array.from(trackedAccounts);

    // 1. Get current LIQUID balances using NearBlocks API (batched)
    let currentLiquid = 0;
    for (let i = 0; i < wallets.length; i += 10) {
      const batch = wallets.slice(i, i + 10);
      const results = await Promise.all(batch.map(w => getLiquidBalance(w.account_id)));
      currentLiquid += results.reduce((sum, bal) => sum + bal, 0);
    }

    // 2. Get current STAKING balance from database (pool contracts don't show in account balance)
    const stakingData = await db.prepare(`
      SELECT COALESCE(SUM(CAST(staked_amount as REAL)/1e24), 0) as total
      FROM staking_positions sp
      JOIN wallets w ON sp.wallet_id = w.id
      WHERE w.user_id = ?
    `).get(userId) as { total: number };
    const currentStaked = stakingData?.total || 0;

    const currentTotalNear = currentLiquid + currentStaked;

    // 3. Get historical prices
    const prices = await db.prepare(`
      SELECT DATE(date) as date, price 
      FROM price_cache 
      WHERE coin_id = 'NEAR' AND currency = 'USD' 
      ORDER BY date DESC
    `).all() as Array<{ date: string; price: number }>;
    
    const priceMap = new Map(prices.map(p => [p.date, p.price]));
    const latestPrice = prices[0]?.price || 1;

    // 4. Get daily EXTERNAL-ONLY transaction deltas
    const placeholders = walletIdList.map(() => '?').join(',');
    const accountPlaceholders = trackedAccountsList.map(() => '?').join(',');

    const dailyDeltas = await db.prepare(`
      SELECT 
        to_char(to_timestamp(block_timestamp / 1000000000), 'YYYY-MM-DD') as date,
        SUM(CASE 
          WHEN LOWER(direction) = 'in' 
          AND (counterparty IS NULL OR counterparty NOT IN (${accountPlaceholders}))
          THEN CAST(amount AS REAL) / 1e24
          ELSE 0 
        END) as external_in,
        SUM(CASE 
          WHEN LOWER(direction) = 'out' 
          AND (counterparty IS NULL OR counterparty NOT IN (${accountPlaceholders}))
          THEN CAST(amount AS REAL) / 1e24
          ELSE 0 
        END) as external_out,
        SUM(CASE 
          WHEN LOWER(direction) = 'out' 
          THEN CAST(fee AS REAL) / 1e24
          ELSE 0 
        END) as fees
      FROM transactions
      WHERE wallet_id IN (${placeholders})
        AND block_timestamp IS NOT NULL
      GROUP BY to_char(to_timestamp(block_timestamp / 1000000000), 'YYYY-MM-DD')
      ORDER BY date DESC
    `).all([...trackedAccountsList, ...trackedAccountsList, ...walletIdList]) as Array<{
      date: string;
      external_in: number;
      external_out: number;
      fees: number;
    }>;

    // 5. Get staking events deltas per day  
    const stakingDeltas = await db.prepare(`
      SELECT 
        to_char(to_timestamp(block_timestamp / 1000000000), 'YYYY-MM-DD') as date,
        SUM(CASE WHEN event_type IN ('stake', 'deposit_and_stake') THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as staked,
        SUM(CASE WHEN event_type IN ('unstake', 'unstake_all', 'synthetic_unstake', 'withdraw_all') THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as unstaked
      FROM staking_events
      WHERE wallet_id IN (${placeholders})
      GROUP BY to_char(to_timestamp(block_timestamp / 1000000000), 'YYYY-MM-DD')
      ORDER BY date DESC
    `).all(walletIdList) as Array<{
      date: string;
      staked: number;
      unstaked: number;
    }>;

    // Create delta maps
    const txDeltaMap = new Map(dailyDeltas.map(d => [d.date, d]));
    const stakeDeltaMap = new Map(stakingDeltas.map(d => [d.date, d]));

    // 6. Generate history working BACKWARDS from today
    const history: DailySnapshot[] = [];
    
    // Start from current values (liquid from API, staked from DB)
    let runningLiquid = currentLiquid;
    let runningStaked = currentStaked;
    
    // Go back 365 days
    const numDays = 365;
    
    for (let i = 0; i < numDays; i++) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      const dateStr = date.toISOString().split('T')[0];
      
      const nearPrice = priceMap.get(dateStr) || latestPrice;
      const liquidVal = Math.max(0, runningLiquid);
      const stakedVal = Math.max(0, runningStaked);
      const totalNear = liquidVal + stakedVal;
      
      history.push({
        date: dateStr,
        nearBalance: liquidVal,
        stakingBalance: stakedVal,
        totalNear: totalNear,
        nearPrice,
        totalValueUsd: totalNear * nearPrice
      });
      
      // Work backwards: reverse the day's activity
      const txDelta = txDeltaMap.get(dateStr);
      if (txDelta) {
        // Going backwards: subtract today's inflows, add today's outflows
        runningLiquid = runningLiquid - (txDelta.external_in || 0) + (txDelta.external_out || 0) + (txDelta.fees || 0);
      }
      
      const stakeDelta = stakeDeltaMap.get(dateStr);
      if (stakeDelta) {
        // Going backwards: if we staked today, we had that as liquid yesterday
        runningLiquid = runningLiquid + (stakeDelta.staked || 0) - (stakeDelta.unstaked || 0);
        runningStaked = runningStaked - (stakeDelta.staked || 0) + (stakeDelta.unstaked || 0);
      }
    }

    // Reverse to chronological order
    history.reverse();
    
    // Sample to ~100 points for performance
    const step = Math.max(1, Math.floor(history.length / 100));
    const sampledHist = history.filter((_, i) => i % step === 0 || i === history.length - 1);

    const currentValueUsd = currentTotalNear * latestPrice;

    return NextResponse.json({
      history: sampledHist,
      currentValue: currentValueUsd,
      currentNear: currentTotalNear,
      breakdown: {
        liquid: currentLiquid,
        staked: currentStaked,
        nearPrice: latestPrice
      },
      stats: {
        anchor: 'nearblocks+db',
        totalDays: history.length,
        sampledPoints: sampledHist.length,
        trackedWallets: wallets.length
      }
    });
  } catch (error) {
    console.error('Portfolio history error:', error);
    return NextResponse.json({
      error: 'Failed to fetch history',
      details: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
}
