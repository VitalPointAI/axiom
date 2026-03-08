import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// NearBlocks API for real balances
const NEARBLOCKS_API = 'https://api.nearblocks.io/v1';
const API_KEY = process.env.NEARBLOCKS_API_KEY || '0F1F69733B684BD48753570B3B9C4B27';

interface AccountBalance {
  account: string;
  liquid: number;
  staked: number;
}

async function getAccountBalance(account: string): Promise<AccountBalance | null> {
  try {
    const resp = await fetch(`${NEARBLOCKS_API}/account/${account}`, {
      headers: { Authorization: `Bearer ${API_KEY}` },
      next: { revalidate: 60 } // Cache for 1 minute
    });
    
    if (!resp.ok) return null;
    
    const data = await resp.json();
    const acct = data.account?.[0] || {};
    
    return {
      account,
      liquid: parseFloat(acct.amount || '0') / 1e24,
      staked: parseFloat(acct.staked || '0') / 1e24
    };
  } catch {
    return null;
  }
}

async function getNearPrice(): Promise<number> {
  try {
    const resp = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd',
      { next: { revalidate: 300 } }
    );
    const data = await resp.json();
    return data.near?.usd || 5.0;
  } catch {
    return 5.0;
  }
}

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
      SELECT id, account_id, chain, label
      FROM wallets 
      WHERE user_id = ?
    `).all(user.id) as Array<{
      id: number;
      account_id: string;
      chain: string;
      label: string | null;
    }>;

    // Fetch LIVE balances from NearBlocks
    const nearWallets = wallets.filter(w => w.chain === 'NEAR');
    const balances: AccountBalance[] = [];
    
    // Process in batches of 5 to avoid rate limits
    for (let i = 0; i < nearWallets.length; i += 5) {
      const batch = nearWallets.slice(i, i + 5);
      const results = await Promise.all(
        batch.map(w => getAccountBalance(w.account_id))
      );
      
      for (const result of results) {
        if (result) {
          balances.push(result);
        }
      }
      
      // Small delay between batches
      if (i + 5 < nearWallets.length) {
        await new Promise(r => setTimeout(r, 100));
      }
    }

    // Sum up totals
    let totalLiquid = 0;
    let totalStaked = 0;
    
    for (const bal of balances) {
      totalLiquid += bal.liquid;
      totalStaked += bal.staked;
    }
    
    const totalNear = totalLiquid + totalStaked;
    
    // Get NEAR price
    const nearPrice = await getNearPrice();
    const totalValue = totalNear * nearPrice;

    // Build holdings array
    const holdings = [
      {
        asset: 'NEAR',
        amount: totalLiquid,
        chain: 'NEAR',
        price: nearPrice,
        value: totalLiquid * nearPrice
      }
    ];

    // Build staking array from live data
    const staking = totalStaked > 0.01 ? [{
      validator: 'Various validators',
      staked: totalStaked,
      rewards: 0,
      value: totalStaked * nearPrice
    }] : [];

    // Get detailed staking from DB if available
    const stakingEvents = db.prepare(`
      SELECT 
        validator,
        SUM(CASE WHEN event_type = 'deposit_and_stake' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as staked,
        SUM(CASE WHEN event_type IN ('unstake', 'unstake_all') THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as unstaked
      FROM staking_events
      WHERE wallet_id IN (SELECT id FROM wallets WHERE user_id = ?)
      GROUP BY validator
      HAVING (staked - unstaked) > 0.01
    `).all(user.id) as Array<{ validator: string; staked: number; unstaked: number }>;

    const detailedStaking = stakingEvents.map(s => ({
      validator: s.validator,
      staked: s.staked - s.unstaked,
      rewards: 0,
      value: (s.staked - s.unstaked) * nearPrice
    }));

    // Calculate CAD values
    const cadRate = 1.38;
    const liquidValue = totalLiquid * nearPrice;
    const stakedValue = totalStaked * nearPrice;
    
    return NextResponse.json({
      // Summary
      totalValue,
      totalValueCad: totalValue * cadRate,
      totalNear,
      nearPrice,
      cadRate,
      
      // Breakdown
      liquid: {
        near: totalLiquid,
        usd: liquidValue,
        cad: liquidValue * cadRate
      },
      staked: {
        near: totalStaked,
        usd: stakedValue,
        cad: stakedValue * cadRate
      },
      
      // Metadata
      change24h: 0,
      walletCount: wallets.length,
      assetCount: 1,
      
      // Details
      holdings,
      staking: detailedStaking.length > 0 ? detailedStaking : staking,
      walletBalances: balances.filter(b => b.liquid > 0.1 || b.staked > 0.1).slice(0, 15)
    });
  } catch (error) {
    console.error('Portfolio fetch error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch portfolio' },
      { status: 500 }
    );
  }
}
