import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

const NEARBLOCKS_API = 'https://api.nearblocks.io/v1';
const API_KEY = process.env.NEARBLOCKS_API_KEY || '';

interface WalletBalance {
  account: string;
  label: string | null;
  liquid: number;
  staked: number;
  total: number;
}

async function getAccountBalance(account: string, label: string | null): Promise<WalletBalance | null> {
  try {
    const resp = await fetch(`${NEARBLOCKS_API}/account/${account}`, {
      headers: { Authorization: `Bearer ${API_KEY}` },
      next: { revalidate: 300 }
    });
    
    if (!resp.ok) return null;
    
    const data = await resp.json();
    const acct = data.account?.[0] || {};
    
    const liquid = parseFloat(acct.amount || '0') / 1e24;
    const staked = parseFloat(acct.staked || '0') / 1e24;
    
    return { account, label, liquid, staked, total: liquid + staked };
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
    SELECT account_id, label FROM wallets WHERE user_id = $1 AND chain = 'NEAR'
  `).all(auth.userId) as Array<{ account_id: string; label: string | null }>;
  
  // Fetch balances in parallel
  const balances: WalletBalance[] = [];
  let totalLiquid = 0;
  let totalStaked = 0;
  
  for (let i = 0; i < wallets.length; i += 10) {
    const batch = wallets.slice(i, i + 10);
    const results = await Promise.all(
      batch.map(w => getAccountBalance(w.account_id, w.label))
    );
    
    for (const result of results) {
      if (result) {
        balances.push(result);
        totalLiquid += result.liquid;
        totalStaked += result.staked;
      }
    }
    
    if (i + 10 < wallets.length) {
      await new Promise(r => setTimeout(r, 100));
    }
  }
  
  return NextResponse.json({
    timestamp: new Date().toISOString(),
    walletCount: wallets.length,
    totalLiquid,
    totalStaked,
    totalNear: totalLiquid + totalStaked,
    wallets: balances.sort((a, b) => b.total - a.total)
  });
}
