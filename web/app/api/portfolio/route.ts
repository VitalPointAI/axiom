import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getAuthenticatedUser } from "@/lib/auth";

const NEARBLOCKS_API = 'https://api.nearblocks.io/v1';
const API_KEY = process.env.NEARBLOCKS_API_KEY || '0F1F69733B684BD48753570B3B9C4B27';

// Fetch real NEAR price from CoinGecko
async function getNearPrice(): Promise<number> {
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd', {
      next: { revalidate: 300 } // Cache for 5 minutes
    });
    const data = await res.json();
    return data.near?.usd || 0;
  } catch (e) {
    console.error('Price fetch error:', e);
    return 0;
  }
}

// Fetch CAD/USD rate
async function getCadRate(): Promise<number> {
  try {
    const res = await fetch('https://api.exchangerate-api.com/v4/latest/USD');
    const data = await res.json();
    return data.rates?.CAD || 1.38;
  } catch {
    return 1.38;
  }
}

// Use NearBlocks API instead of RPC (better rate limits)
async function getLiquidBalance(account: string): Promise<number> {
  try {
    const resp = await fetch(`${NEARBLOCKS_API}/account/${account}`, {
      headers: { Authorization: `Bearer ${API_KEY}` },
      next: { revalidate: 60 }
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
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

    const db = getDb();

    // Get user wallets (exclude pool contracts)
    const wallets = await db.prepare(`
      SELECT w.id, w.account_id, w.label
      FROM wallets w
      WHERE w.user_id = ? AND w.chain = 'NEAR'
        AND w.account_id NOT LIKE '%.pool%'
        AND w.account_id NOT LIKE '%.poolv1%'
        AND w.account_id != 'meta-pool.near'
        AND w.account_id != 'linear-protocol.near'
        AND w.account_id != 'wrap.near'
      ORDER BY w.account_id
    `).all(auth.userId) as Array<{ id: number; account_id: string; label: string | null }>;

    // Get token holdings from FT transactions
    const tokenHoldings = await db.prepare(`
      SELECT 
        token_symbol,
        SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) ELSE -CAST(amount AS REAL) END) / POWER(10, COALESCE(MAX(token_decimals), 24)) as balance
      FROM ft_transactions
      WHERE wallet_id IN (SELECT id FROM wallets WHERE user_id = ?)
        AND token_symbol NOT IN ('wNEAR', 'stNEAR', 'LiNEAR')
      GROUP BY token_symbol
      HAVING balance > 0.01
      ORDER BY balance DESC
    `).all(auth.userId) as Array<{ token_symbol: string; balance: number }>;

    // Get staking positions from database (includes all validators)
    const stakingData = await db.prepare(`
      SELECT COALESCE(SUM(CAST(staked_amount as REAL)/1e24), 0) as total
      FROM staking_positions sp
      JOIN wallets w ON sp.wallet_id = w.id
      WHERE w.user_id = ?
    `).get(auth.userId) as { total: number };
    const totalStakedNear = stakingData?.total || 0;

    // Get staking breakdown by validator
    const stakingPositions = await db.prepare(`
      SELECT 
        validator,
        SUM(CAST(staked_amount as REAL)/1e24) as net_staked
      FROM staking_positions sp
      JOIN wallets w ON sp.wallet_id = w.id
      WHERE w.user_id = ?
      GROUP BY validator
      HAVING net_staked > 0
      ORDER BY net_staked DESC
    `).all(auth.userId) as Array<{ validator: string; net_staked: number }>;

    // Fetch prices
    const [nearPrice, cadRate] = await Promise.all([
      getNearPrice(),
      getCadRate()
    ]);

    if (nearPrice === 0) {
      return NextResponse.json({ 
        error: 'Could not fetch NEAR price',
        nearPrice: 0
      }, { status: 503 });
    }

    // Fetch liquid NEAR balances via NearBlocks API (batched)
    const walletData: { account: string; liquid: number; staked: number }[] = [];
    
    for (let i = 0; i < wallets.length; i += 10) {
      const batch = wallets.slice(i, i + 10);
      const results = await Promise.all(
        batch.map(async (w) => {
          const liquid = await getLiquidBalance(w.account_id);
          // Get per-wallet staking from DB
          const walletStaking = await db.prepare(`
            SELECT COALESCE(SUM(CAST(staked_amount as REAL)/1e24), 0) as total
            FROM staking_positions WHERE wallet_id = ?
          `).get(w.id) as { total: number };
          return { 
            account: w.account_id, 
            liquid, 
            staked: walletStaking?.total || 0 
          };
        })
      );
      walletData.push(...results);
    }

    // Calculate totals
    const totalLiquidNear = walletData.reduce((sum, w) => sum + w.liquid, 0);
    const totalNear = totalLiquidNear + totalStakedNear;
    const totalValueUsd = totalNear * nearPrice;
    const totalValueCad = totalValueUsd * cadRate;

    // Count unique assets: NEAR + tokens with balance
    const assetCount = 1 + tokenHoldings.length;

    // Format token holdings for display
    const holdings = tokenHoldings.slice(0, 20).map(t => ({
      symbol: t.token_symbol,
      amount: t.balance,
      price: 0,
      value: 0
    }));

    // Add NEAR as the first holding
    holdings.unshift({
      symbol: 'NEAR',
      amount: totalNear,
      price: nearPrice,
      value: totalValueUsd
    });

    return NextResponse.json({
      totalValue: totalValueUsd,
      totalValueCad,
      nearPrice,
      cadRate,
      priceSource: 'coingecko',
      walletCount: wallets.length,
      assetCount,
      
      liquid: {
        near: totalLiquidNear,
        usd: totalLiquidNear * nearPrice,
        cad: totalLiquidNear * nearPrice * cadRate
      },
      staked: {
        near: totalStakedNear,
        usd: totalStakedNear * nearPrice,
        cad: totalStakedNear * nearPrice * cadRate
      },
      tokens: {
        count: tokenHoldings.length,
        usd: 0,
        cad: 0
      },
      
      holdings,
      
      walletBalances: walletData
        .filter(w => w.liquid > 0.01 || w.staked > 0.01)
        .sort((a, b) => (b.liquid + b.staked) - (a.liquid + a.staked))
        .slice(0, 30),
      
      stakingPositions: stakingPositions.slice(0, 10).map(p => ({
        validator: p.validator,
        staked: p.net_staked
      })),
      
      summary: {
        totalNear,
        totalUsd: totalValueUsd,
        walletsWithBalance: walletData.filter(w => w.liquid > 0.01 || w.staked > 0.01).length,
        emptyWallets: walletData.filter(w => w.liquid <= 0.01 && w.staked <= 0.01).length
      }
    });
  } catch (error: any) {
    console.error('Portfolio error:', error);
    return NextResponse.json({ error: 'Failed', details: error?.message }, { status: 500 });
  }
}
