import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// Live portfolio from on-chain data via NearBlocks API
const NEARBLOCKS_API = 'https://api.nearblocks.io/v1';
const API_KEY = process.env.NEARBLOCKS_API_KEY || '';

interface WalletBalance {
  account: string;
  liquid: number;
  staked: number;
  total: number;
}

async function getAccountBalance(account: string): Promise<WalletBalance | null> {
  try {
    const resp = await fetch(`${NEARBLOCKS_API}/account/${account}`, {
      headers: { Authorization: `Bearer ${API_KEY}` },
      next: { revalidate: 300 } // Cache for 5 minutes
    });
    
    if (!resp.ok) return null;
    
    const data = await resp.json();
    const acct = data.account?.[0] || {};
    
    const liquid = parseFloat(acct.amount || '0') / 1e24;
    const staked = parseFloat(acct.staked || '0') / 1e24;
    
    return {
      account,
      liquid,
      staked,
      total: liquid + staked
    };
  } catch {
    return null;
  }
}

export async function GET() {
  const db = getDb();
  
  // Get all NEAR wallets
  const stmt = db.prepare(`
    SELECT account_id, label FROM wallets WHERE chain = 'NEAR'
  `);
  const wallets = stmt.all() as Array<{ account_id: string; label: string | null }>;
  
  // Fetch balances in parallel (with rate limiting)
  const balances: WalletBalance[] = [];
  let totalLiquid = 0;
  let totalStaked = 0;
  
  // Process in batches of 10
  for (let i = 0; i < wallets.length; i += 10) {
    const batch = wallets.slice(i, i + 10);
    const results = await Promise.all(
      batch.map(w => getAccountBalance(w.account_id))
    );
    
    for (const result of results) {
      if (result && result.total > 0.01) {
        balances.push(result);
        totalLiquid += result.liquid;
        totalStaked += result.staked;
      }
    }
    
    // Small delay between batches
    if (i + 10 < wallets.length) {
      await new Promise(r => setTimeout(r, 100));
    }
  }
  
  // Sort by total balance
  balances.sort((a, b) => b.total - a.total);
  
  // Get current NEAR price
  let nearPriceUsd = 5.0; // Default
  try {
    const priceResp = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd',
      { next: { revalidate: 300 } }
    );
    const priceData = await priceResp.json();
    nearPriceUsd = priceData.near?.usd || 5.0;
  } catch {
    // Use default
  }
  
  const totalNear = totalLiquid + totalStaked;
  const totalUsd = totalNear * nearPriceUsd;
  const totalCad = totalUsd * 1.38;
  
  return NextResponse.json({
    timestamp: new Date().toISOString(),
    walletsChecked: wallets.length,
    walletsWithBalance: balances.length,
    nearPrice: {
      usd: nearPriceUsd,
      cadRate: 1.38
    },
    totals: {
      liquid: totalLiquid,
      staked: totalStaked,
      total: totalNear,
      valueUsd: totalUsd,
      valueCad: totalCad
    },
    wallets: balances.slice(0, 20) // Top 20 wallets
  });
}
