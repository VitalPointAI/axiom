import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getAuthenticatedUser } from "@/lib/auth";

const NEAR_RPC = 'https://rpc.fastnear.com';
const ETHERSCAN_V2_URL = 'https://api.etherscan.io/v2/api';
const ETHERSCAN_API_KEY = process.env.ETHERSCAN_API_KEY || '';

// Value-based tolerance: $5 CAD equivalent
const TOLERANCE_CAD = 5;

// Approximate token prices in CAD
const TOKEN_PRICES_CAD: Record<string, number> = {
  'NEAR': 4.50,
  'ETH': 4800,
  'MATIC': 0.80,
  'CRO': 0.15,
};

const CHAIN_IDS: Record<string, number> = {
  'ethereum': 1,
  'polygon': 137,
  'cronos': 25,
  'optimism': 10,
};

const CHAIN_CONFIG: Record<string, { name: string; symbol: string; decimals: number }> = {
  'NEAR': { name: 'NEAR', symbol: 'NEAR', decimals: 24 },
  'ethereum': { name: 'Ethereum', symbol: 'ETH', decimals: 18 },
  'polygon': { name: 'Polygon', symbol: 'MATIC', decimals: 18 },
  'cronos': { name: 'Cronos', symbol: 'CRO', decimals: 18 },
  'optimism': { name: 'Optimism', symbol: 'ETH', decimals: 18 },
};

// Known staking pools
const STAKING_POOLS = [
  'vitalpoint.pool.near',
  'meta-pool.near',
  'zavodil.poolv1.near',
  'epic.poolv1.near',
  'bisontrails.poolv1.near',
  'lux.poolv1.near',
  'figment.poolv1.near',
  'openshards.poolv1.near',
];

async function getNearAccountInfo(account: string): Promise<{ balance: number; storageUsage: number; } | null> {
  try {
    const res = await fetch(NEAR_RPC, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 'verify', method: 'query',
        params: { request_type: 'view_account', finality: 'final', account_id: account }
      }),
      cache: 'no-store'
    });
    const data = await res.json();
    if (data.result) {
      return {
        balance: parseFloat(data.result.amount) / 1e24,
        storageUsage: data.result.storage_usage || 0,
      };
    }
    return null;
  } catch {
    return null;
  }
}

async function getStakedBalance(account: string, pool: string): Promise<number> {
  try {
    const args = Buffer.from(JSON.stringify({ account_id: account })).toString('base64');
    const res = await fetch(NEAR_RPC, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 'staked', method: 'query',
        params: {
          request_type: 'call_function', finality: 'final',
          account_id: pool, method_name: 'get_account', args_base64: args
        }
      }),
      cache: 'no-store'
    });
    const data = await res.json();
    if (data.result?.result) {
      const poolData = JSON.parse(Buffer.from(data.result.result).toString());
      return parseInt(poolData.staked_balance || '0') / 1e24;
    }
    return 0;
  } catch {
    return 0;
  }
}

async function getEVMBalance(address: string, chain: string): Promise<number | null> {
  const chainId = CHAIN_IDS[chain];
  if (!chainId) return null;
  
  try {
    const params = new URLSearchParams({
      chainid: chainId.toString(),
      module: 'account',
      action: 'balance',
      address: address,
      apikey: ETHERSCAN_API_KEY,
    });
    const res = await fetch(`${ETHERSCAN_V2_URL}?${params}`, { cache: 'no-store' });
    const data = await res.json();
    if (data.status === '1') {
      return parseFloat(data.result) / 1e18;
    }
    return null;
  } catch {
    return null;
  }
}

export async function GET(request: Request) {
  try {
    const db = getDb();
    const user = await getAuthenticatedUser();
    
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const chainFilter = searchParams.get('chain') || '';

    const results: Array<{
      account: string;
      label: string | null;
      walletId: number;
      chain: string;
      chainName: string;
      symbol: string;
      liquidBalance: number;
      stakedBalance: number;
      totalBalance: number;
      txCount: number;
      hasStaking: boolean;
      stakingNote?: string;
    }> = [];

    // ========== NEAR WALLETS (filtered by user_id) ==========
    if (!chainFilter || chainFilter.toLowerCase() === 'near') {
      const nearWallets = await db.prepare(`
        SELECT id, account_id, label
        FROM wallets 
        WHERE user_id = $1 AND chain = 'NEAR' 
          AND account_id NOT LIKE '%.pool%'
          AND account_id NOT LIKE '%.poolv1%'
      `).all(user.userId) as Array<{ id: number; account_id: string; label: string | null }>;

      for (const wallet of nearWallets) {
        const accountInfo = await getNearAccountInfo(wallet.account_id);
        if (!accountInfo) continue;

        // Get staked balance from known pools
        let totalStaked = 0;
        const stakingPools: string[] = [];
        
        // Check pools that this wallet has staked with (from staking_positions)
        const positions = await db.prepare(`
          SELECT DISTINCT validator FROM staking_positions WHERE wallet_id = $1
        `).all(wallet.id) as Array<{ validator: string }>;
        
        for (const pos of positions) {
          const staked = await getStakedBalance(wallet.account_id, pos.validator);
          if (staked > 0) {
            totalStaked += staked;
            stakingPools.push(pos.validator);
          }
        }

        // Get transaction count
        const txCount = await db.prepare(`
          SELECT COUNT(*) as count FROM transactions WHERE wallet_id = $1
        `).get(wallet.id) as { count: number };

        results.push({
          account: wallet.account_id,
          label: wallet.label,
          walletId: wallet.id,
          chain: 'NEAR',
          chainName: 'NEAR',
          symbol: 'NEAR',
          liquidBalance: Number(accountInfo.balance.toFixed(4)),
          stakedBalance: Number(totalStaked.toFixed(4)),
          totalBalance: Number((accountInfo.balance + totalStaked).toFixed(4)),
          txCount: Number(txCount.count),
          hasStaking: totalStaked > 0,
          stakingNote: totalStaked > 0 ? `Staked with: ${stakingPools.join(', ')}` : undefined,
        });
      }
    }

    // ========== EVM WALLETS (SECURITY FIX: filtered by user_id) ==========
    if (!chainFilter || !['near'].includes(chainFilter.toLowerCase())) {
      const evmWallets = await db.prepare(`
        SELECT id, address, chain, label
        FROM evm_wallets 
        WHERE user_id = $1 AND is_owned = TRUE
      `).all(user.userId) as Array<{ id: number; address: string; chain: string; label: string | null }>;

      for (const wallet of evmWallets) {
        if (chainFilter && wallet.chain.toLowerCase() !== chainFilter.toLowerCase()) {
          continue;
        }

        const chainConfig = CHAIN_CONFIG[wallet.chain];
        if (!chainConfig) continue;

        const balance = await getEVMBalance(wallet.address, wallet.chain);
        if (balance === null) continue;

        const txCount = await db.prepare(`
          SELECT COUNT(*) as count FROM evm_transactions WHERE wallet_id = $1
        `).get(wallet.id) as { count: number };

        results.push({
          account: wallet.address,
          label: wallet.label,
          walletId: wallet.id,
          chain: wallet.chain,
          chainName: chainConfig.name,
          symbol: chainConfig.symbol,
          liquidBalance: Number(balance.toFixed(6)),
          stakedBalance: 0,
          totalBalance: Number(balance.toFixed(6)),
          txCount: Number(txCount.count),
          hasStaking: false,
        });
      }
    }

    // ========== EXCHANGE ACCOUNTS (filtered by user_id) ==========
    const exchangeWallets = await db.prepare(`
      SELECT id, account_id, label
      FROM wallets 
      WHERE user_id = $1 AND chain = 'exchange'
    `).all(user.userId) as Array<{ id: number; account_id: string; label: string | null }>;

    const exchangeAccounts: Array<{
      account: string;
      label: string | null;
      balances: Record<string, number>;
      totalCad: number;
    }> = [];

    for (const wallet of exchangeWallets) {
      const balances: Record<string, number> = {};
      
      const movements = await db.prepare(`
        SELECT asset, 
          SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) ELSE 0 END) as total_in,
          SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) ELSE 0 END) as total_out
        FROM transactions 
        WHERE wallet_id = $1 AND asset IS NOT NULL
        GROUP BY asset
      `).all(wallet.id) as Array<{ asset: string; total_in: number; total_out: number }>;
      
      for (const m of movements) {
        balances[m.asset] = (balances[m.asset] || 0) + Number(m.total_in) - Number(m.total_out);
      }
      
      const trades = await db.prepare(`
        SELECT tax_category, asset, quote_asset, CAST(quote_amount AS REAL) as quote_amount
        FROM transactions 
        WHERE wallet_id = $1 AND tax_category IN ('BUY', 'SELL') AND quote_asset IS NOT NULL
      `).all(wallet.id) as Array<{ tax_category: string; asset: string; quote_asset: string; quote_amount: number }>;
      
      for (const t of trades) {
        if (t.tax_category === 'BUY') {
          balances[t.quote_asset] = (balances[t.quote_asset] || 0) - Number(t.quote_amount);
        } else if (t.tax_category === 'SELL') {
          balances[t.quote_asset] = (balances[t.quote_asset] || 0) + Number(t.quote_amount);
        }
      }
      
      const filteredBalances: Record<string, number> = {};
      let totalCad = 0;
      
      for (const [asset, amount] of Object.entries(balances)) {
        if (Math.abs(amount) > 0.01) {
          filteredBalances[asset] = Number(amount.toFixed(4));
          if (asset === 'CAD') totalCad += amount;
          else if (asset === 'NEAR') totalCad += amount * 4.5;
          else if (asset === 'BTC') totalCad += amount * 130000;
          else if (asset === 'ETH') totalCad += amount * 4800;
          else if (asset === 'USDC' || asset === 'USDT') totalCad += amount * 1.4;
        }
      }
      
      if (Object.keys(filteredBalances).length > 0) {
        exchangeAccounts.push({
          account: wallet.account_id.replace('import:', ''),
          label: wallet.label,
          balances: filteredBalances,
          totalCad: Number(totalCad.toFixed(2)),
        });
      }
    }

    // Calculate totals
    const nearResults = results.filter(r => r.chain === 'NEAR');
    const evmResults = results.filter(r => r.chain !== 'NEAR');

    const totalNearLiquid = nearResults.reduce((sum, w) => sum + w.liquidBalance, 0);
    const totalNearStaked = nearResults.reduce((sum, w) => sum + w.stakedBalance, 0);
    const totalNear = totalNearLiquid + totalNearStaked;

    return NextResponse.json({
      wallets: results,
      exchangeAccounts,
      summary: {
        total: results.length,
        nearWallets: nearResults.length,
        evmWallets: evmResults.length,
        exchangeAccounts: exchangeAccounts.length,
      },
      totals: {
        nearLiquid: Number(totalNearLiquid.toFixed(4)),
        nearStaked: Number(totalNearStaked.toFixed(4)),
        nearTotal: Number(totalNear.toFixed(4)),
      },
      note: 'Balances shown are real-time on-chain values. Transaction counts are for reference.',
    });
  } catch (error) {
    console.error('Verification error:', error);
    return NextResponse.json({ error: 'Verification failed' }, { status: 500 });
  }
}
