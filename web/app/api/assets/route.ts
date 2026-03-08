import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

const CHAIN_CONFIG: Record<string, { name: string; nativeToken: string }> = {
  'NEAR': { name: 'NEAR', nativeToken: 'NEAR' },
  'near': { name: 'NEAR', nativeToken: 'NEAR' },
  'ethereum': { name: 'Ethereum', nativeToken: 'ETH' },
  'ETH': { name: 'Ethereum', nativeToken: 'ETH' },
  'polygon': { name: 'Polygon', nativeToken: 'MATIC' },
  'Polygon': { name: 'Polygon', nativeToken: 'MATIC' },
  'cronos': { name: 'Cronos', nativeToken: 'CRO' },
  'Cronos': { name: 'Cronos', nativeToken: 'CRO' },
  'xrp': { name: 'XRP Ledger', nativeToken: 'XRP' },
};

// Fetch actual NEAR balance from NearBlocks API
async function fetchNearBalance(accountId: string): Promise<number> {
  try {
    const res = await fetch(`https://api.nearblocks.io/v1/account/${accountId}`, {
      headers: { 'Accept': 'application/json' },
      next: { revalidate: 60 },
    });
    if (!res.ok) return 0;
    const data = await res.json();
    const amount = data?.account?.[0]?.amount;
    if (!amount) return 0;
    return Number(amount) / 1e24;
  } catch {
    return 0;
  }
}

// Fetch FT token balances from NearBlocks
async function fetchFtBalances(accountId: string): Promise<Array<{
  contract: string;
  symbol: string;
  balance: number;
}>> {
  try {
    const res = await fetch(`https://api.nearblocks.io/v1/account/${accountId}/ft`, {
      headers: { 'Accept': 'application/json' },
      next: { revalidate: 60 },
    });
    if (!res.ok) return [];
    const data = await res.json();
    const tokens = data?.inventory?.fts || [];
    return tokens.map((t: any) => ({
      contract: t.contract,
      symbol: t.ft_meta?.symbol || 'UNKNOWN',
      balance: Number(t.amount) / Math.pow(10, t.ft_meta?.decimals || 18),
    })).filter((t: any) => t.balance > 0.0001 && t.contract !== 'aurora');
  } catch {
    return [];
  }
}

export async function GET(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();
    const { searchParams } = new URL(request.url);
    
    const chainFilter = await searchParams.get('chain');
    const assetFilter = await searchParams.get('asset');
    const walletFilter = await searchParams.get('wallet');
    const hideSmall = await searchParams.get('hideSmall') !== 'false';
    const includeSpam = await searchParams.get('includeSpam') === 'true';
    const dateFilter = await searchParams.get('date'); // YYYY-MM-DD format

    // Get spam tokens
    const spamTokens = await db.prepare(`
      SELECT UPPER(token_symbol) as symbol FROM spam_tokens
    `).all() as { symbol: string }[];
    const spamSet = new Set(spamTokens.map(s => s.symbol));

    // Get prices
    const prices = await db.prepare(`
      SELECT DISTINCT ON (UPPER(coin_id)) UPPER(coin_id) as coin_id, price 
      FROM price_cache WHERE currency = 'USD'
      ORDER BY UPPER(coin_id), date DESC
    `).all() as { coin_id: string; price: number }[];
    const priceMap = new Map(prices.map(p => [p.coin_id, Number(p.price)]));

    const holdings: any[] = [];

    // If date filter provided, use snapshots
    if (dateFilter) {
      // Get snapshots for the specified date
      const snapshots = await db.prepare(`
        SELECT 
          bs.wallet_id,
          w.account_id as wallet_address,
          w.label as wallet_label,
          bs.chain,
          bs.token_symbol as asset,
          bs.token_contract as contract,
          bs.balance,
          bs.price_usd,
          bs.balance_usd as value_usd
        FROM balance_snapshots bs
        JOIN wallets w ON bs.wallet_id = w.id
        WHERE w.user_id = $1 AND bs.snapshot_date = $2
        AND bs.balance > 0.0001
      `).all(auth.userId, dateFilter) as any[];

      // Also check XRP snapshots (stored with different wallet_id reference)
      const xrpSnapshots = await db.prepare(`
        SELECT 
          bs.wallet_id,
          xw.address as wallet_address,
          xw.label as wallet_label,
          'xrp' as chain,
          bs.token_symbol as asset,
          bs.token_contract as contract,
          bs.balance,
          bs.price_usd,
          bs.balance_usd as value_usd
        FROM balance_snapshots bs
        JOIN xrp_wallets xw ON bs.wallet_id = xw.id
        WHERE xw.user_id = $1 AND bs.snapshot_date = $2 AND bs.chain = 'xrp'
        AND bs.balance > 0.0001
      `).all(auth.userId, dateFilter) as any[];

      for (const s of [...snapshots, ...xrpSnapshots]) {
        if (!includeSpam && spamSet.has(s.asset?.toUpperCase())) continue;
        
        const price = s.price_usd || priceMap.get(s.asset?.toUpperCase()) || 0;
        holdings.push({
          wallet_id: s.wallet_id,
          wallet_address: s.wallet_address,
          wallet_label: s.wallet_label || s.wallet_address,
          chain: s.chain || 'NEAR',
          asset: s.asset?.toUpperCase() || 'UNKNOWN',
          contract: s.contract,
          balance: Number(s.balance),
          price_usd: price,
          value_usd: Number(s.balance) * price,
        });
      }
    } else {
      // No date filter - fetch live balances
      const nearWallets = await db.prepare(`
        SELECT id, account_id, chain, label FROM wallets 
        WHERE user_id = $1 AND chain = 'NEAR'
      `).all(auth.userId) as any[];

      for (const wallet of nearWallets) {
        const nearBalance = await fetchNearBalance(wallet.account_id);
        if (nearBalance > 0.0001) {
          const price = await priceMap.get('NEAR') || 0;
          holdings.push({
            wallet_id: wallet.id,
            wallet_address: wallet.account_id,
            wallet_label: wallet.label || wallet.account_id,
            chain: 'NEAR',
            asset: 'NEAR',
            balance: nearBalance,
            price_usd: price,
            value_usd: nearBalance * price,
          });
        }

        const ftTokens = await fetchFtBalances(wallet.account_id);
        for (const token of ftTokens) {
          const symbol = token.symbol.toUpperCase();
          if (!includeSpam && spamSet.has(symbol)) continue;
          
          const price = await priceMap.get(symbol) || 0;
          holdings.push({
            wallet_id: wallet.id,
            wallet_address: wallet.account_id,
            wallet_label: wallet.label || wallet.account_id,
            chain: 'NEAR',
            asset: symbol,
            contract: token.contract,
            balance: token.balance,
            price_usd: price,
            value_usd: token.balance * price,
          });
        }
      }

      // EVM wallets (calculated)
      const evmWallets = await db.prepare(`
        SELECT id, address, chain, label FROM evm_wallets WHERE user_id = $1 AND is_owned = true
      `).all(auth.userId) as any[];
      
      if (evmWallets.length > 0) {
        const evmWalletIds = evmWallets.map(w => w.id);
        
        const evmNative = await db.prepare(`
          SELECT w.id as wallet_id, w.address as wallet_address, w.label as wallet_label,
            w.chain as chain,
            CASE w.chain WHEN 'ethereum' THEN 'ETH' WHEN 'ETH' THEN 'ETH'
              WHEN 'polygon' THEN 'MATIC' WHEN 'Polygon' THEN 'MATIC'
              WHEN 'cronos' THEN 'CRO' WHEN 'Cronos' THEN 'CRO' ELSE 'ETH' END as asset,
            SUM(CASE WHEN LOWER(et.from_address) = LOWER(w.address) THEN -CAST(et.value AS NUMERIC) / 1e18
              WHEN LOWER(et.to_address) = LOWER(w.address) THEN CAST(et.value AS NUMERIC) / 1e18 ELSE 0 END) as balance
          FROM evm_transactions et JOIN evm_wallets w ON et.wallet_id = w.id
          WHERE et.wallet_id = ANY($1::int[]) AND et.tx_type IN ('transfer', 'internal')
          GROUP BY w.id, w.address, w.label, w.chain
          HAVING SUM(CASE WHEN LOWER(et.from_address) = LOWER(w.address) THEN -CAST(et.value AS NUMERIC) / 1e18
            WHEN LOWER(et.to_address) = LOWER(w.address) THEN CAST(et.value AS NUMERIC) / 1e18 ELSE 0 END) > 0.0001
        `).all([evmWalletIds]) as any[];

        for (const h of evmNative) {
          const price = await priceMap.get(h.asset) || 0;
          holdings.push({ ...h, balance: Number(h.balance), price_usd: price, value_usd: Number(h.balance) * price });
        }
      }

      // XRP wallets
      const xrpWallets = await db.prepare(`
        SELECT w.id, w.address, w.label, 
          COALESCE(SUM(CASE WHEN t.is_outgoing THEN -t.amount ELSE t.amount END), 0) as balance 
        FROM xrp_wallets w LEFT JOIN xrp_transactions t ON w.id = t.wallet_id 
        WHERE w.user_id = $1 GROUP BY w.id, w.address, w.label
      `).all(auth.userId) as any[];
      
      for (const w of xrpWallets) {
        if (w.balance && Number(w.balance) > 0) {
          const xrpPrice = await priceMap.get('XRP') || 0;
          holdings.push({
            wallet_id: `xrp-${w.id}`,
            wallet_address: w.address,
            wallet_label: w.label || w.address.slice(0, 8),
            chain: 'xrp',
            asset: 'XRP',
            balance: Number(w.balance),
            price_usd: xrpPrice,
            value_usd: Number(w.balance) * xrpPrice,
          });
        }
      }
    }

    // Apply filters
    let filtered = holdings;
    if (chainFilter) filtered = filtered.filter(h => h.chain.toLowerCase() === chainFilter.toLowerCase());
    if (assetFilter) filtered = filtered.filter(h => h.asset.toUpperCase() === assetFilter.toUpperCase());
    if (walletFilter) filtered = filtered.filter(h => 
      h.wallet_address.toLowerCase().includes(walletFilter.toLowerCase()) ||
      (h.wallet_label && h.wallet_label.toLowerCase().includes(walletFilter.toLowerCase()))
    );
    if (hideSmall) filtered = filtered.filter(h => h.value_usd >= 1);

    // Aggregate
    const aggregated = new Map<string, any>();
    for (const h of filtered) {
      const key = `${h.asset}-${h.chain}`;
      if (aggregated.has(key)) {
        const existing = await aggregated.get(key);
        existing.balance += h.balance;
        existing.value_usd += h.value_usd;
        existing.wallets.push({ address: h.wallet_address, label: h.wallet_label, balance: h.balance, value_usd: h.value_usd });
      } else {
        aggregated.set(key, {
          asset: h.asset,
          chain: h.chain,
          chain_name: CHAIN_CONFIG[h.chain]?.name || h.chain,
          balance: h.balance,
          price_usd: h.price_usd,
          value_usd: h.value_usd,
          contract: h.contract,
          is_spam: spamSet.has(h.asset),
          wallets: [{ address: h.wallet_address, label: h.wallet_label, balance: h.balance, value_usd: h.value_usd }],
        });
      }
    }

    const assets = Array.from(aggregated.values()).sort((a, b) => b.value_usd - a.value_usd);
    const totalValueUsd = assets.reduce((sum, a) => sum + a.value_usd, 0);

    // Get available snapshot dates
    const snapshotDates = await db.prepare(`
      SELECT DISTINCT snapshot_date FROM balance_snapshots 
      WHERE wallet_id IN (SELECT id FROM wallets WHERE user_id = $1)
      ORDER BY snapshot_date DESC LIMIT 30
    `).all(auth.userId) as { snapshot_date: string }[];

    return NextResponse.json({
      assets,
      totalValueUsd,
      filters: {
        chains: [...new Set(holdings.map(h => h.chain))].map(c => ({ value: c, label: CHAIN_CONFIG[c]?.name || c })),
        assets: [...new Set(holdings.map(h => h.asset))].sort(),
        wallets: [...new Set(holdings.map(h => h.wallet_label || h.wallet_address))],
      },
      snapshotDates: snapshotDates.map(d => d.snapshot_date),
      isHistorical: !!dateFilter,
    });
  } catch (error) {
    console.error('Assets fetch error:', error);
    return NextResponse.json({ error: 'Failed to fetch assets', details: String(error) }, { status: 500 });
  }
}
