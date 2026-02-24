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
      SELECT id, address, chain, label, last_synced_at
      FROM wallets 
      WHERE user_id = ?
    `).all(user.id) as Array<{
      id: number;
      address: string;
      chain: string;
      label: string;
      last_synced_at: string;
    }>;

    // Calculate holdings from transactions
    const holdings: Record<string, { amount: number; chain: string }> = {};
    
    for (const wallet of wallets) {
      const txns = db.prepare(`
        SELECT asset, 
               SUM(CASE WHEN to_address = ? THEN amount ELSE 0 END) as received,
               SUM(CASE WHEN from_address = ? THEN amount ELSE 0 END) as sent
        FROM transactions
        WHERE wallet_id = ?
        GROUP BY asset
      `).all(wallet.address, wallet.address, wallet.id) as Array<{
        asset: string;
        received: number;
        sent: number;
      }>;

      for (const tx of txns) {
        const asset = tx.asset || wallet.chain;
        if (!holdings[asset]) {
          holdings[asset] = { amount: 0, chain: wallet.chain };
        }
        holdings[asset].amount += (tx.received || 0) - (tx.sent || 0);
      }
    }

    // Get staking positions
    const stakingPositions = db.prepare(`
      SELECT 
        validator_id,
        SUM(staked_amount) as total_staked,
        SUM(reward_amount) as total_rewards
      FROM staking_rewards
      WHERE wallet_id IN (SELECT id FROM wallets WHERE user_id = ?)
      GROUP BY validator_id
    `).all(user.id) as Array<{
      validator_id: string;
      total_staked: number;
      total_rewards: number;
    }>;

    // Mock prices for now (would fetch from CoinGecko in production)
    const prices: Record<string, number> = {
      'NEAR': 4.50,
      'ETH': 2800,
      'MATIC': 0.85,
      'USDC': 1.0,
      'USDT': 1.0,
    };

    // Calculate total value
    let totalValue = 0;
    const holdingsWithValue = Object.entries(holdings).map(([asset, data]) => {
      const price = prices[asset] || 0;
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

    // Add staking to total
    for (const pos of stakingPositions) {
      const stakingValue = (pos.total_staked + pos.total_rewards) * (prices['NEAR'] || 0);
      totalValue += stakingValue;
    }

    return NextResponse.json({
      totalValue,
      change24h: 0, // Would calculate from historical data
      walletCount: wallets.length,
      assetCount: Object.keys(holdings).length,
      holdings: holdingsWithValue.sort((a, b) => b.value - a.value),
      staking: stakingPositions.map(pos => ({
        validator: pos.validator_id,
        staked: pos.total_staked,
        rewards: pos.total_rewards,
        value: (pos.total_staked + pos.total_rewards) * (prices['NEAR'] || 0),
      })),
    });
  } catch (error) {
    console.error('Portfolio fetch error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch portfolio' },
      { status: 500 }
    );
  }
}
