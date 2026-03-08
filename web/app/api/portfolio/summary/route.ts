import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// Public portfolio summary - all wallets
const NEARBLOCKS_API = 'https://api.nearblocks.io/v1';
const API_KEY = process.env.NEARBLOCKS_API_KEY || '0F1F69733B684BD48753570B3B9C4B27';

interface WalletBalance {
  account: string;
  liquid: number;
  staked: number;
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
  const db = getDb();
  
  // Get all NEAR wallets
  const wallets = db.prepare(`
    SELECT account_id FROM wallets WHERE chain = 'NEAR'
  `).all() as Array<{ account_id: string }>;
  
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
  
  // Get NEAR price
  let nearPrice = 5.0;
  try {
    const priceResp = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd',
      { next: { revalidate: 300 } }
    );
    const priceData = await priceResp.json();
    nearPrice = priceData.near?.usd || 5.0;
  } catch {}
  
  const cadRate = 1.38;
  const totalNear = totalLiquid + totalStaked;
  const totalUsd = totalNear * nearPrice;
  const totalCad = totalUsd * cadRate;
  
  // Get staking positions from DB
  const stakingStmt = db.prepare(`
    SELECT 
      validator,
      SUM(CASE WHEN event_type = 'deposit_and_stake' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) -
      SUM(CASE WHEN event_type IN ('unstake', 'unstake_all') THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as net_staked
    FROM staking_events
    GROUP BY validator
    HAVING net_staked > 1
    ORDER BY net_staked DESC
  `);
  const stakingPositions = stakingStmt.all() as Array<{ validator: string; net_staked: number }>;
  
  // Get staking rewards
  const rewardsStmt = db.prepare(`
    SELECT SUM(reward_near) as total FROM staking_rewards
  `);
  const rewardsResult = rewardsStmt.get() as { total: number } | null;
  const totalRewards = rewardsResult?.total || 0;
  
  // Get token holdings from FT transactions
  const tokensStmt = db.prepare(`
    SELECT 
      token_symbol,
      SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 18)) ELSE 0 END) -
      SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 18)) ELSE 0 END) as balance
    FROM ft_transactions
    GROUP BY token_symbol
    HAVING balance > 0.01
    ORDER BY balance DESC
    LIMIT 20
  `);
  const tokenHoldings = tokensStmt.all() as Array<{ token_symbol: string; balance: number }>;
  
  // Filter spam tokens
  const validTokens = tokenHoldings.filter(t => 
    !t.token_symbol.includes('🎉') && 
    !t.token_symbol.includes('.com') && 
    !t.token_symbol.includes('.org') &&
    t.token_symbol.length < 20
  );
  
  return NextResponse.json({
    timestamp: new Date().toISOString(),
    
    // Summary
    summary: {
      totalNear,
      totalUsd,
      totalCad,
      nearPrice,
      cadRate,
      walletCount: wallets.length
    },
    
    // Breakdown
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
    
    // Staking details
    staking: {
      positions: stakingPositions,
      totalStaked: stakingPositions.reduce((sum, p) => sum + p.net_staked, 0),
      totalRewardsEarned: totalRewards
    },
    
    // Token holdings
    tokens: validTokens,
    
    // Top wallets
    topWallets: balances
      .filter(b => b.liquid > 1 || b.staked > 1)
      .sort((a, b) => (b.liquid + b.staked) - (a.liquid + a.staked))
      .slice(0, 10)
  });
}
