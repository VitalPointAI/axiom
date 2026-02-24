import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  try {
    const cookieStore = await cookies();
    const nearAccountId = cookieStore.get('neartax_session')?.value;

    if (!nearAccountId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();

    // Get user
    const user = db.prepare(`
      SELECT id FROM users WHERE near_account_id = ?
    `).get(nearAccountId) as { id: number } | undefined;

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Get wallets for this user
    const wallets = db.prepare(`
      SELECT id, account_id, chain, label, last_synced_at
      FROM wallets 
      WHERE user_id = ?
    `).all(user.id) as Array<{
      id: number;
      account_id: string;
      chain: string;
      label: string;
      last_synced_at: string;
    }>;

    // Calculate holdings from transactions
    const holdings: Record<string, { amount: number; chain: string }> = {};
    
    for (const wallet of wallets) {
      // Sum up transactions for this wallet
      // Amount is stored as yoctoNEAR string, need to convert
      const txSummary = db.prepare(`
        SELECT 
          direction,
          SUM(CAST(amount AS REAL) / 1e24) as total_near
        FROM transactions
        WHERE wallet_id = ? AND success = 1
        GROUP BY direction
      `).all(wallet.id) as Array<{
        direction: string;
        total_near: number;
      }>;

      let balance = 0;
      for (const row of txSummary) {
        if (row.direction === 'in') {
          balance += row.total_near || 0;
        } else if (row.direction === 'out') {
          balance -= row.total_near || 0;
        }
      }

      const asset = wallet.chain === 'NEAR' ? 'NEAR' : wallet.chain;
      if (!holdings[asset]) {
        holdings[asset] = { amount: 0, chain: wallet.chain };
      }
      holdings[asset].amount += balance;
    }

    // Get staking positions from staking_events
    const stakingPositions = db.prepare(`
      SELECT 
        se.validator_id,
        SUM(CASE WHEN se.event_type = 'deposit' THEN CAST(se.amount AS REAL) / 1e24 ELSE 0 END) as deposits,
        SUM(CASE WHEN se.event_type = 'withdraw' THEN CAST(se.amount AS REAL) / 1e24 ELSE 0 END) as withdrawals,
        SUM(CASE WHEN se.event_type = 'reward' THEN CAST(se.amount AS REAL) / 1e24 ELSE 0 END) as rewards
      FROM staking_events se
      JOIN wallets w ON se.wallet_id = w.id
      WHERE w.user_id = ?
      GROUP BY se.validator_id
    `).all(user.id) as Array<{
      validator_id: string;
      deposits: number;
      withdrawals: number;
      rewards: number;
    }>;

    // Mock prices for now (would fetch from CoinGecko in production)
    const prices: Record<string, number> = {
      'NEAR': 4.50,
      'ETH': 2800,
      'Polygon': 0.85,
      'MATIC': 0.85,
      'Optimism': 2800,
      'USDC': 1.0,
      'USDT': 1.0,
    };

    // Calculate total value
    let totalValue = 0;
    const holdingsWithValue = Object.entries(holdings)
      .filter(([_, data]) => data.amount > 0.001) // Filter dust
      .map(([asset, data]) => {
        const price = prices[asset] || prices[data.chain] || 0;
        const value = data.amount * price;
        totalValue += value;
        return {
          asset,
          amount: data.amount,
          chain: data.chain,
          price,
          value,
        };
      });

    // Calculate staking value
    const stakingWithValue = stakingPositions.map(pos => {
      const staked = pos.deposits - pos.withdrawals;
      const rewards = pos.rewards;
      const nearPrice = prices['NEAR'] || 0;
      const value = (staked + rewards) * nearPrice;
      totalValue += value;
      
      return {
        validator: pos.validator_id,
        staked: staked,
        rewards: rewards,
        value: value,
      };
    }).filter(pos => pos.staked > 0.001); // Filter dust

    return NextResponse.json({
      totalValue,
      change24h: 0, // Would calculate from historical data
      walletCount: wallets.length,
      assetCount: Object.keys(holdings).length,
      holdings: holdingsWithValue.sort((a, b) => b.value - a.value),
      staking: stakingWithValue,
    });
  } catch (error) {
    console.error('Portfolio fetch error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch portfolio' },
      { status: 500 }
    );
  }
}
