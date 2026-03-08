import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

const NEARBLOCKS_API = 'https://api.nearblocks.io/v1';
const API_KEY = process.env.NEARBLOCKS_API_KEY || '0F1F69733B684BD48753570B3B9C4B27';

interface WalletBalance {
  account: string;
  liquid: number;
  staked: number;
}

async function getNearPrice(): Promise<{ price: number; source: string }> {
  try {
    const resp = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd',
      { next: { revalidate: 60 } }
    );
    if (resp.ok) {
      const data = await resp.json();
      if (data.near?.usd && data.near.usd > 0) {
        return { price: data.near.usd, source: 'coingecko' };
      }
    }
  } catch (e) {
    console.warn('CoinGecko price fetch failed:', e);
  }
  
  try {
    const resp = await fetch('https://api.coincap.io/v2/assets/near-protocol');
    if (resp.ok) {
      const data = await resp.json();
      if (data.data?.priceUsd) {
        return { price: parseFloat(data.data.priceUsd), source: 'coincap' };
      }
    }
  } catch (e) {
    console.warn('CoinCap price fetch failed:', e);
  }
  
  console.error('All price sources failed!');
  return { price: 0, source: 'error' };
}

async function getBalance(account: string): Promise<WalletBalance | null> {
  try {
    const resp = await fetch(`${NEARBLOCKS_API}/account/${account}`, {
      headers: { Authorization: `Bearer ${API_KEY}` },
      next: { revalidate: 300 }
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

export async function GET() {
  // SECURITY: Require authentication
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const db = getDb();
  
  // Get THIS USER's NEAR wallets only
  const wallets = await db.prepare(`
    SELECT account_id FROM wallets WHERE user_id = $1 AND chain = 'NEAR'
  `).all(auth.userId) as Array<{ account_id: string }>;
  
  // Fetch price first
  const { price: nearPrice, source: priceSource } = await getNearPrice();
  
  if (nearPrice === 0) {
    return NextResponse.json({
      error: 'Could not fetch NEAR price',
      priceSource,
      walletCount: wallets.length,
      message: 'Please try again in a minute'
    }, { status: 503 });
  }
  
  // Fetch live balances
  const balances: WalletBalance[] = [];
  let totalLiquid = 0;
  let totalStaked = 0;
  
  for (let i = 0; i < wallets.length; i += 10) {
    const batch = wallets.slice(i, i + 10);
    const results = await Promise.all(batch.map(w => getBalance(w.account_id)));
    
    for (const result of results) {
      if (result) {
        balances.push(result);
        totalLiquid += result.liquid;
        totalStaked += result.staked;
      }
    }
    
    if (i + 10 < wallets.length) {
      await new Promise(r => setTimeout(r, 50));
    }
  }
  
  const cadRate = 1.38;
  const totalNear = totalLiquid + totalStaked;
  const totalUsd = totalNear * nearPrice;
  const totalCad = totalUsd * cadRate;
  
  // Get THIS USER's wallet IDs
  const userWalletIds = wallets.length > 0 
    ? (await db.prepare(`SELECT id FROM wallets WHERE user_id = $1`).all(auth.userId) as { id: number }[]).map(w => w.id)
    : [];
  
  // Get staking positions for THIS USER's wallets only
  let stakingPositions: Array<{ validator: string; net_staked: number }> = [];
  let totalRewards = 0;
  
  if (userWalletIds.length > 0) {
    const stakingResult = await db.prepare(`
      SELECT 
        validator,
        SUM(CASE WHEN event_type = 'deposit_and_stake' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) -
        SUM(CASE WHEN event_type IN ('unstake', 'unstake_all') THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as net_staked
      FROM staking_events
      WHERE wallet_id = ANY($1::int[])
      GROUP BY validator
      HAVING SUM(CASE WHEN event_type = 'deposit_and_stake' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) - SUM(CASE WHEN event_type IN ('unstake', 'unstake_all') THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) > 1
      ORDER BY net_staked DESC
    `).all([userWalletIds]) as Array<{ validator: string; net_staked: number }>;
    stakingPositions = stakingResult;
    
    // Get staking rewards for THIS USER
    const rewardsResult = await db.prepare(`
      SELECT SUM(reward_near) as total FROM staking_rewards WHERE wallet_id = ANY($1::int[])
    `).get([userWalletIds]) as { total: number } | null;
    totalRewards = rewardsResult?.total || 0;
  }
  
  // Get token holdings for THIS USER's wallets only
  let tokenHoldings: Array<{ token_symbol: string; balance: number }> = [];
  if (userWalletIds.length > 0) {
    tokenHoldings = await db.prepare(`
      SELECT 
        token_symbol,
        SUM(CASE WHEN LOWER(direction) = 'in' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 18)) ELSE 0 END) -
        SUM(CASE WHEN LOWER(direction) = 'out' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 18)) ELSE 0 END) as balance
      FROM ft_transactions 
      WHERE wallet_id = ANY($1::int[]) AND token_contract != 'aurora'
      GROUP BY token_symbol
      HAVING SUM(CASE WHEN LOWER(direction) = 'in' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 18)) ELSE 0 END) - SUM(CASE WHEN LOWER(direction) = 'out' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 18)) ELSE 0 END) > 0.01
      ORDER BY balance DESC
      LIMIT 20
    `).all([userWalletIds]) as Array<{ token_symbol: string; balance: number }>;
  }
  
  // Filter spam tokens
  const validTokens = tokenHoldings.filter(t => 
    !t.token_symbol.includes('🎉') && 
    !t.token_symbol.includes('.com') && 
    !t.token_symbol.includes('.org') &&
    t.token_symbol.length < 20
  );
  
  return NextResponse.json({
    timestamp: new Date().toISOString(),
    priceSource,
    
    summary: {
      totalNear,
      totalUsd,
      totalCad,
      nearPrice,
      cadRate,
      walletCount: wallets.length
    },
    
    near: {
      liquid: {
        amount: totalLiquid,
        usd: totalLiquid * nearPrice,
        cad: totalLiquid * nearPrice * cadRate
      },
      staked: {
        amount: totalStaked,
        usd: totalStaked * nearPrice,
        cad: totalStaked * nearPrice * cadRate
      }
    },
    
    staking: {
      positions: stakingPositions,
      totalStaked: stakingPositions.reduce((sum, p) => sum + p.net_staked, 0),
      totalRewardsEarned: totalRewards
    },
    
    tokens: validTokens,
    
    topWallets: balances
      .filter(b => b.liquid > 1 || b.staked > 1)
      .sort((a, b) => (b.liquid + b.staked) - (a.liquid + a.staked))
      .slice(0, 10)
  });
}
