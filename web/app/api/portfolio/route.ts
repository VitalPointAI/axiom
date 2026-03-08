import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getAuthenticatedUser } from "@/lib/auth";

const NEARBLOCKS_API = 'https://api.nearblocks.io/v1';
const API_KEY = process.env.NEARBLOCKS_API_KEY || '0F1F69733B684BD48753570B3B9C4B27';
const PYTH_HERMES_URL = 'https://hermes.pyth.network';
const REF_API_URL = 'https://api.ref.finance';

// Pyth price feed IDs - PRIMARY price source for all supported tokens
const PYTH_FEEDS: Record<string, string> = {
  // Core tokens
  'NEAR': 'c415de8d2eba7db216527dff4b60e8f3a5311c740dadb233e13e12547e226750',
  'ETH': 'ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace',
  'BTC': 'e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43',
  'SOL': 'ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d',
  
  // Stablecoins
  'USDC': 'eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a',
  'USDT': '2b89b9dc8fdf9f34709a5b106b472f0f39bb6ca9ce04b0fd7f2e971688e2e53b',
  'DAI': 'b0948a5e5313200c632b51bb5ca32f6de0d36e9950a942d19751e833f70dabfd',
  
  // NEAR ecosystem
  'AURORA': '2f7c4f738d498585065a4b87b637069ec99474597da7f0ca349ba8ac3ba9cac5',
  
  // Major L1s
  'AVAX': '93da3352f9f1d105fdfe4971cfa80e9dd777bfc5d0f683ebb6e1294b92137bb7',
  'DOT': 'ca3eed9b267293f6595901c734c7525ce8ef49adafe8284606ceb307afa2ca5b',
  'ATOM': 'b00b60f88b03a6a625a8d1c048c3f66653edf217439983d037e7222c4e612819',
  'FIL': '150ac9b959aee0051e4091f0ef5216d941f590e1c5e7f91cf7635b5c11628c0e',
  'XRP': 'ec5d399846a9209f3fe5881d70aae9268c94339ff9817e8d18ff19fa05eea1c8',
  'LTC': '6e3f3fa8253588df9326580180233eb791e03b443a3ba7a1d892e73874e19a54',
  'BNB': '2f95862b045670cd22bee3114c39763a4a08beeb663b145d283c31d7d1101c4f',
  
  // L2s & Scaling
  'ARB': '3fa4252848f9f0a1480be62745a4629d9eb1322aebab8a791e344b3b9c1adcf5',
  'OP': '385f64d993f7b77d8182ed5003d97c60aa3361f3cecfe711544d2d59165e9bdf',
  'MATIC': 'ffd11c5a1cfd42f80afb2df4d9f264c15f956d68153335374ec10722edd70472', // POL
  'POL': 'ffd11c5a1cfd42f80afb2df4d9f264c15f956d68153335374ec10722edd70472',
  
  // DeFi tokens
  'LINK': '8ac0c70fff57e9aefdf5edf44b51d62c2d433653cbb2cf5cc06bb115af04d221',
  'UNI': '78d185a741d07edb3412b09008b7c5cfb9bbbd7d568bf00ba737b456ba171501',
  'AAVE': '2b9ab1e972a281585084148ba1389800799bd4be63b957507db1349314e47445',
  'INJ': '7a5bc1d2b56ad029048cd63964b3ad2776eadf812edc1a43a31406cb54bff592',
  
  // New L1s
  'SUI': '23d7315113f5b1d3ba7a83604c44b94d79f4fd69af77f804fc7f920a6dc65744',
  'SEI': '53614f1cb0c031d4af66c04cb9c756234adad0e1cee85303795091499a4084eb',
  'TIA': '09f7c1d7dfbb7df2b8fe3d3d87ee94a2259d212da4f30c1f0540d066dfa44723',
  'AKT': '4ea5bb4d2f5900cc2e97ba534240950740b4d3b89fe712a94a7304fd2fd92702',
  
  // Cosmos ecosystem
  'OSMO': '5867f5683c757393a0670ef0f701490950fe93fdb006d181c8265a831ac0c5c6',
  
  // Meme coins
  'DOGE': 'dcef50dd0a4cd2dcc17e45df1676dcb336a11a61c69df7a0299b0150c672d25c',
  'SHIB': 'f0d57deca57b3da2fe63a493f4c25925fdfd8edf834b20f93e1f84dbd1504d4a',
  
  // Solana ecosystem
  'JTO': 'b43660a5f790c69354b0729a5ef9d50d68f1df92107540210b9cccba1f947cc2',
  'JUP': '0a0408d619e9380abad35060f9192039ed5042fa6f82301d0e48bb52be830996',
  'PYTH': '0bbf28e9a841a1cc788f6a361b17ca072d0ea3098a1e5df1c3922d06719579ff',
  
  // Wrapped tokens (use base token prices)
  'WBTC': 'e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43', // BTC price
  'WETH': 'ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace', // ETH price
  'wNEAR': 'c415de8d2eba7db216527dff4b60e8f3a5311c740dadb233e13e12547e226750', // NEAR price
  
  // Exchange tokens
  'CRO': '23199c2bcb1303f667e733b9934db9eca5991e765b45f5ed18bc4b231415f2fe',
};
// Spam patterns for fallback filtering (DB is primary source)
const SPAM_PATTERNS = [
  'reward',
  'airdrop', 
  'claim',
  '.com',
  '.org',
  '.net',
  'visit',
  'https://',
];

function isSpamByPattern(symbol: string): boolean {
  const lowerSymbol = symbol.toLowerCase();
  return SPAM_PATTERNS.some(p => lowerSymbol.includes(p.toLowerCase()));
}


// Fetch NEAR price from Pyth (fallback to CoinGecko)
async function getNearPrice(): Promise<number> {
  // Try Pyth first
  try {
    const feedId = PYTH_FEEDS['NEAR'];
    const resp = await fetch(`${PYTH_HERMES_URL}/v2/updates/price/latest?ids[]=${feedId}`, {
      next: { revalidate: 60 }
    });
    if (resp.ok) {
      const data = await resp.json();
      const priceData = data.parsed?.[0]?.price;
      if (priceData) {
        return parseInt(priceData.price) * Math.pow(10, priceData.expo);
      }
    }
  } catch (e) {
    console.error('Pyth price fetch error:', e);
  }
  
  // Fallback to CoinGecko
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd', {
      next: { revalidate: 300 }
    });
    const data = await res.json();
    return data.near?.usd || 0;
  } catch (e) {
    console.error('CoinGecko price fetch error:', e);
    return 0;
  }
}

// Fetch token prices from Ref Finance
async function getRefTokenPrices(): Promise<Record<string, number>> {
  try {
    const resp = await fetch(`${REF_API_URL}/list-token-price`, {
      next: { revalidate: 300 }
    });
    if (!resp.ok) return {};
    
    const data = await resp.json();
    const prices: Record<string, number> = {};
    
    // Known token mappings
    const symbolMap: Record<string, string> = {
      'wrap.near': 'wNEAR',
      'meta-pool.near': 'stNEAR', 
      'linear-protocol.near': 'LiNEAR',
      'token.v2.ref-finance.near': 'REF',
      'f5cfbc74057c610c8ef151a439252680ac68c6dc.factory.bridge.near': 'OCT',
      'token.burrow.near': 'BRRR',
      'token.lonkingnearbackto2024.near': 'LONK',
      'blackdragon.tkn.near': 'BLACKDRAGON',
      'cattoken.near': 'CAT',
    };
    
    for (const [contractId, info] of Object.entries(data)) {
      const priceVal = (info as any)?.price;
      const apiSymbol = (info as any)?.symbol;
      if (priceVal) {
        const price = typeof priceVal === 'string' ? parseFloat(priceVal) : priceVal;
        // Store by contract
        prices[contractId] = price;
        // Store by mapped symbol (from our map)
        if (symbolMap[contractId]) {
          prices[symbolMap[contractId]] = price;
        }
        // Also store by the symbol from API response (both cases)
        if (apiSymbol) {
          prices[apiSymbol] = price;
          prices[apiSymbol.toUpperCase()] = price;
          prices[apiSymbol.toLowerCase()] = price;
        }
      }
    }
    
    return prices;
  } catch (e) {
    console.error('Ref Finance price fetch error:', e);
    return {};
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

// Get liquid balance from NearBlocks API only (staking from DB)
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

export async function GET(request: Request) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

    // Parse query params
    const url = new URL(request.url);
    const hideDust = url.searchParams.get('hideDust') === 'true';
    const dustThreshold = parseFloat(url.searchParams.get('dustThreshold') || '1'); // Default $1

    const db = getDb();

    // Get total wallet count (all chains)
    const totalWalletCount = await db.prepare(`
      SELECT COUNT(*) as count FROM wallets WHERE user_id = ?
    `).get(auth.userId) as { count: number };

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
    // Fetch spam tokens from database
    const dbSpamTokens = await db.prepare(`
      SELECT token_symbol, token_contract FROM spam_tokens
    `).all() as Array<{ token_symbol: string; token_contract: string | null }>;
    
    const spamSymbols = new Set(dbSpamTokens.map(s => s.token_symbol.toLowerCase()));
    const spamContracts = new Set(dbSpamTokens.filter(s => s.token_contract).map(s => s.token_contract!.toLowerCase()));
    
    const tokenHoldings = await db.prepare(`
      SELECT 
        token_symbol,
        MAX(token_contract) as token_contract,
        SUM(CASE WHEN LOWER(direction) = 'in' THEN CAST(amount AS REAL) ELSE -CAST(amount AS REAL) END) / POWER(10, COALESCE(MAX(token_decimals), 24)) as balance
      FROM ft_transactions
      WHERE token_contract != 'aurora' AND wallet_id IN (SELECT id FROM wallets WHERE user_id = ?)
        AND token_symbol NOT IN ('wNEAR', 'stNEAR', 'LiNEAR')
      GROUP BY token_symbol
      HAVING SUM(CASE WHEN LOWER(direction) = 'in' THEN CAST(amount AS REAL) ELSE -CAST(amount AS REAL) END) / POWER(10, COALESCE(MAX(token_decimals), 24)) > 0.01
      ORDER BY SUM(CASE WHEN LOWER(direction) = 'in' THEN CAST(amount AS REAL) ELSE -CAST(amount AS REAL) END) / POWER(10, COALESCE(MAX(token_decimals), 24)) DESC
    `).all(auth.userId) as Array<{ token_symbol: string; token_contract: string; balance: number }>;
    
    // Filter out spam tokens (DB list + pattern matching)
    const filteredTokenHoldings = tokenHoldings.filter(t => {
      const symbolLower = t.token_symbol.toLowerCase();
      const contractLower = (t.token_contract || '').toLowerCase();
      
      // Check DB spam list
      if (spamSymbols.has(symbolLower)) return false;
      if (contractLower && spamContracts.has(contractLower)) return false;
      
      // Check patterns as fallback
      if (isSpamByPattern(t.token_symbol)) return false;
      
      return true;
    });

    // Fetch Pyth prices for major tokens
    async function getPythPrices(symbols: string[]): Promise<Record<string, number>> {
      const prices: Record<string, number> = {};
      const feedIds = symbols.map(s => PYTH_FEEDS[s.toUpperCase()]).filter(Boolean);
      if (feedIds.length === 0) return prices;
      
      try {
        const url = `${PYTH_HERMES_URL}/v2/updates/price/latest?${feedIds.map(id => `ids[]=${id}`).join('&')}`;
        const resp = await fetch(url, { next: { revalidate: 60 } });
        if (resp.ok) {
          const data = await resp.json();
          for (let i = 0; i < symbols.length; i++) {
            const priceData = data.parsed?.[i]?.price;
            if (priceData) {
              prices[symbols[i].toUpperCase()] = parseInt(priceData.price) * Math.pow(10, priceData.expo);
            }
          }
        }
      } catch (e) {
        console.error('Pyth batch fetch error:', e);
      }
      return prices;
    }

    // Fetch prices - Pyth is PRIMARY for all supported tokens, Ref Finance as fallback
    const [nearPrice, cadRate, refPrices, pythPrices] = await Promise.all([
      getNearPrice(),
      getCadRate(),
      getRefTokenPrices(),
      getPythPrices(Object.keys(PYTH_FEEDS))
    ]);

    if (!nearPrice) {
      return NextResponse.json({
        error: 'Price service unavailable',
        totalValue: 0,
        nearPrice: 0
      }, { status: 503 });
    }

    // ========== STAKING FROM DATABASE ==========
    const stakingPositionsRaw = await db.prepare(`
      SELECT 
        w.account_id,
        sp.validator,
        CAST(sp.staked_amount AS NUMERIC) / 1e24 as staked_near
      FROM staking_positions sp
      JOIN wallets w ON sp.wallet_id = w.id
      WHERE w.user_id = ? AND CAST(sp.staked_amount AS NUMERIC) > 0
      ORDER BY CAST(sp.staked_amount AS NUMERIC) DESC
    `).all(auth.userId) as Array<{ account_id: string; validator: string; staked_near: string | number }>;

    // Convert string numbers from PostgreSQL to actual numbers
    const stakingPositions = stakingPositionsRaw.map(p => ({
      account: p.account_id,
      validator: p.validator,
      staked_near: typeof p.staked_near === 'string' ? parseFloat(p.staked_near) : (p.staked_near || 0)
    }));

    const totalStakedNear = stakingPositions.reduce((sum, p) => sum + p.staked_near, 0);

    // ========== LOCKED TOKEN POSITIONS ==========
    const lockedPositions = await db.prepare(`
      SELECT 
        lp.token_symbol,
        lp.token_contract,
        lp.lock_contract,
        lp.lock_type,
        CAST(lp.amount AS NUMERIC) / POWER(10, lp.decimals) as locked_amount
      FROM locked_positions lp
      JOIN wallets w ON lp.wallet_id = w.id
      WHERE w.user_id = ?
    `).all(auth.userId) as Array<{ 
      token_symbol: string; 
      token_contract: string;
      lock_contract: string;
      lock_type: string;
      locked_amount: string | number 
    }>;
    
    // Sum locked amounts by token
    const lockedByToken: Record<string, number> = {};
    for (const lp of lockedPositions) {
      const amount = typeof lp.locked_amount === 'string' ? parseFloat(lp.locked_amount) : lp.locked_amount;
      lockedByToken[lp.token_symbol] = (lockedByToken[lp.token_symbol] || 0) + amount;
    }

    // ========== EXCHANGE HOLDINGS ==========
    const exchangeWallets = await db.prepare(`
      SELECT id, account_id, label 
      FROM wallets 
      WHERE user_id = ? AND chain = 'exchange'
    `).all(auth.userId) as Array<{ id: number; account_id: string; label: string | null }>;

    const exchangesByName: Record<string, { 
      name: string; 
      accountId: string;
      holdings: Array<{ asset: string; balance: number; valueUsd: number }>;
      totalValueUsd: number;
      totalValueCad: number;
    }> = {};

    for (const exWallet of exchangeWallets) {
      const directMovements = await db.prepare(`
        SELECT 
          asset,
          SUM(CASE WHEN UPPER(direction) = 'IN' THEN CAST(amount AS REAL) ELSE -CAST(amount AS REAL) END) as net
        FROM transactions
        WHERE wallet_id = ? AND asset IS NOT NULL AND asset != ''
        GROUP BY asset
      `).all(exWallet.id) as Array<{ asset: string; net: number }>;

      const buyEffects = await db.prepare(`
        SELECT 
          quote_asset as asset,
          SUM(-CAST(quote_amount AS REAL)) as net
        FROM transactions
        WHERE wallet_id = ? AND tax_category = 'buy'
          AND quote_asset IS NOT NULL AND quote_asset != ''
        GROUP BY quote_asset
      `).all(exWallet.id) as Array<{ asset: string; net: number }>;

      const sellEffects = await db.prepare(`
        SELECT 
          quote_asset as asset,
          SUM(CAST(quote_amount AS REAL)) as net
        FROM transactions
        WHERE wallet_id = ? AND tax_category = 'sell'
          AND quote_asset IS NOT NULL AND quote_asset != ''
        GROUP BY quote_asset
      `).all(exWallet.id) as Array<{ asset: string; net: number }>;

      const balances: Record<string, number> = {};
      for (const d of directMovements) {
        balances[d.asset] = (balances[d.asset] || 0) + d.net;
      }
      for (const b of buyEffects) {
        balances[b.asset] = (balances[b.asset] || 0) + b.net;
      }
      for (const s of sellEffects) {
        balances[s.asset] = (balances[s.asset] || 0) + s.net;
      }

      const holdings: Array<{ asset: string; balance: number; valueUsd: number }> = [];
      for (const [asset, balance] of Object.entries(balances)) {
        if (balance > 0.001) {
          let valueUsd = 0;
          let source = 'none';
          
          // Map asset to Pyth key
          const assetUpper = asset.toUpperCase();
          const pythKey = assetUpper === 'WETH' ? 'ETH' : 
                         assetUpper === 'WBTC' ? 'BTC' : 
                         assetUpper === 'WNEAR' ? 'NEAR' : assetUpper;
          
          // Try Pyth first for everything
          if (pythPrices[pythKey]) {
            valueUsd = balance * pythPrices[pythKey];
            source = 'pyth';
          } else if (asset === 'NEAR') {
            valueUsd = balance * nearPrice;
            source = 'pyth';
          } else if (['USD', 'CAD'].includes(asset)) {
            valueUsd = asset === 'CAD' ? balance / cadRate : balance;
            source = 'fiat';
          } else if (refPrices[asset] || refPrices[assetUpper]) {
            valueUsd = balance * (refPrices[asset] || refPrices[assetUpper]);
            source = 'ref';
          }
          holdings.push({ asset, balance, valueUsd });
        }
      }

      if (holdings.length > 0) {
        const displayName = exWallet.label || 
          exWallet.account_id.replace('import:', '')
            .split(/[_-]/).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        
        const totalValueUsd = holdings.reduce((sum, h) => sum + h.valueUsd, 0);
        
        exchangesByName[exWallet.account_id] = {
          name: displayName,
          accountId: exWallet.account_id,
          holdings: holdings.sort((a, b) => b.valueUsd - a.valueUsd),
          totalValueUsd,
          totalValueCad: totalValueUsd * cadRate
        };
      }
    }

    const exchangeTotalUsd = Object.values(exchangesByName)
      .reduce((sum, ex) => sum + ex.totalValueUsd, 0);

    // ========== NEAR WALLET LIQUID BALANCES (FROM API) ==========
    const walletData: { account: string; liquid: number; staked: number }[] = [];
    
    // Fetch liquid balances in batches
    for (let i = 0; i < wallets.length; i += 10) {
      const batch = wallets.slice(i, i + 10);
      const results = await Promise.all(
        batch.map(async (w) => {
          const liquid = await getLiquidBalance(w.account_id);
          return { account: w.account_id, liquid, staked: 0 };
        })
      );
      walletData.push(...results);
    }

    // Calculate totals
    const totalLiquidNear = walletData.reduce((sum, w) => sum + w.liquid, 0);
    const totalNear = totalLiquidNear + totalStakedNear;
    const totalValueUsd = totalNear * nearPrice;
    const totalValueCad = totalValueUsd * cadRate;

    const exchangeAssets = new Set<string>();
    for (const ex of Object.values(exchangesByName)) {
      for (const h of ex.holdings) {
        exchangeAssets.add(h.asset);
      }
    }
    const assetCount = 1 + filteredTokenHoldings.length + exchangeAssets.size;

    // Build holdings: NEAR first (has value), then tokens with prices from Ref
    const nearHolding = {
      symbol: 'NEAR',
      amount: totalNear,
      price: nearPrice,
      value: totalValueUsd
    };
    
    // Map token symbols to their Pyth equivalents
    const PYTH_SYMBOL_MAP: Record<string, string> = {
      // Stablecoins
      'USDC': 'USDC', 'USDC.e': 'USDC', 'usdc': 'USDC',
      'USDT': 'USDT', 'USDt': 'USDT', 'usdt': 'USDT',
      'DAI': 'DAI', 'dai': 'DAI',
      
      // ETH variants
      'ETH': 'ETH', 'WETH': 'ETH', 'eth': 'ETH', 'weth': 'ETH',
      
      // BTC variants
      'BTC': 'BTC', 'WBTC': 'BTC', 'btc': 'BTC', 'wbtc': 'BTC',
      
      // NEAR ecosystem
      'NEAR': 'NEAR', 'wNEAR': 'NEAR', 'near': 'NEAR',
      'AURORA': 'AURORA', 'aurora': 'AURORA',
      
      // L1s
      'SOL': 'SOL', 'sol': 'SOL',
      'AVAX': 'AVAX', 'avax': 'AVAX',
      'DOT': 'DOT', 'dot': 'DOT',
      'ATOM': 'ATOM', 'atom': 'ATOM',
      'FIL': 'FIL', 'fil': 'FIL',
      'XRP': 'XRP', 'xrp': 'XRP',
      'LTC': 'LTC', 'ltc': 'LTC',
      'BNB': 'BNB', 'bnb': 'BNB',
      'AKT': 'AKT', 'akt': 'AKT',
      
      // L2s
      'ARB': 'ARB', 'arb': 'ARB',
      'OP': 'OP', 'op': 'OP',
      'MATIC': 'POL', 'POL': 'POL', 'matic': 'POL',
      
      // DeFi
      'LINK': 'LINK', 'link': 'LINK',
      'UNI': 'UNI', 'uni': 'UNI',
      'AAVE': 'AAVE', 'aave': 'AAVE',
      'INJ': 'INJ', 'inj': 'INJ',
      
      // New L1s
      'SUI': 'SUI', 'sui': 'SUI',
      'SEI': 'SEI', 'sei': 'SEI',
      'TIA': 'TIA', 'tia': 'TIA',
      'OSMO': 'OSMO', 'osmo': 'OSMO',
      
      // Memes
      'DOGE': 'DOGE', 'doge': 'DOGE',
      'SHIB': 'SHIB', 'shib': 'SHIB',
      
      // Solana ecosystem
      'JTO': 'JTO', 'JUP': 'JUP', 'PYTH': 'PYTH',
      
      // Exchange tokens
      'CRO': 'CRO', 'cro': 'CRO',
    };
    
    // Calculate token values using Pyth (priority) -> Ref Finance -> fallback
    const tokenHoldingsWithPrices = filteredTokenHoldings
      .map(t => {
        const symbol = t.token_symbol;
        const contract = t.token_contract;
        const lockedAmount = lockedByToken[symbol] || 0;
        const totalAmount = t.balance + lockedAmount;
        const pythKey = PYTH_SYMBOL_MAP[symbol] || PYTH_SYMBOL_MAP[symbol.toUpperCase()];
        
        // Priority: Pyth price -> Ref price -> 0
        let price = 0;
        let source = 'none';
        
        if (pythKey && pythPrices[pythKey]) {
          price = pythPrices[pythKey];
          source = 'pyth';
        } else {
          // Try multiple symbol variations for Ref
          const refPrice = refPrices[contract]  // Contract first, then symbol fallback
            || refPrices[symbol] 
            || refPrices[symbol.toUpperCase()] 
            || refPrices[symbol.toLowerCase()]
            || 0;
          if (refPrice > 0) {
            price = refPrice;
            source = 'ref';
          }
        }
        
        const value = t.balance * price;
        return {
          symbol,
          contract,
          amount: totalAmount,
          liquid: t.balance,
          locked: lockedAmount,
          price,
          value: totalAmount * price,
          source
        };
      })
      // Sort by value first (tokens with prices), then by amount for the rest
      .sort((a, b) => {
        // If both have value, sort by value
        if (a.value > 0 && b.value > 0) return b.value - a.value;
        // Tokens with value come first
        if (a.value > 0) return -1;
        if (b.value > 0) return 1;
        // Otherwise sort by amount
        return b.amount - a.amount;
      });
    
    // Calculate total token value
    const totalTokenValueUsd = tokenHoldingsWithPrices.reduce((sum, t) => sum + t.value, 0);
    
    // Apply dust filter if enabled
    const filteredTokens = hideDust 
      ? tokenHoldingsWithPrices.filter(t => t.value >= dustThreshold)
      : tokenHoldingsWithPrices;
    
    // Count dust (hidden tokens)
    const dustCount = tokenHoldingsWithPrices.length - filteredTokens.length;
    const dustValue = tokenHoldingsWithPrices
      .filter(t => t.value < dustThreshold)
      .reduce((sum, t) => sum + t.value, 0);
    
    // NEAR first, then tokens sorted by value/amount
    const holdings = [nearHolding, ...filteredTokens.slice(0, 19)];

    // ========== DEFI POSITIONS ==========
    const defiPositionsRaw = await db.prepare(`
      SELECT de.event_type, de.token_symbol, de.token_contract, CAST(de.amount AS NUMERIC) as amount
      FROM defi_events de JOIN wallets w ON de.wallet_id = w.id
      WHERE w.user_id = ? AND de.event_type IN ('supply', 'collateral', 'borrow')
    `).all(auth.userId) as Array<{event_type: string; token_symbol: string; token_contract: string; amount: string | number}>;
    let defiSuppliedUsd = 0, defiCollateralUsd = 0, defiBorrowedUsd = 0;
    const defiPositions: any[] = [];
    for (const pos of defiPositionsRaw) {
      const amount = typeof pos.amount === "string" ? parseFloat(pos.amount) : pos.amount;
      if (amount < 0.001) continue;
      const price = refPrices[pos.token_contract] || refPrices[pos.token_symbol] || 0;
      const valueUsd = amount * price;
      defiPositions.push({ type: pos.event_type, token: pos.token_symbol, amount, price, valueUsd });
      if (pos.event_type === 'supply') defiSuppliedUsd += valueUsd;
      else if (pos.event_type === 'collateral') defiCollateralUsd += valueUsd;
      else if (pos.event_type === 'borrow') defiBorrowedUsd += valueUsd;
    }
    const defiNetValueUsd = defiSuppliedUsd + defiCollateralUsd - defiBorrowedUsd;

    const grandTotalUsd = totalValueUsd + totalTokenValueUsd + exchangeTotalUsd + defiNetValueUsd;
    const grandTotalCad = grandTotalUsd * cadRate;

    const totalWallets = Number(totalWalletCount?.count) || (wallets.length + exchangeWallets.length);

    return NextResponse.json({
      totalValue: totalValueUsd,
      totalValueCad,
      nearPrice,
      nearBalance: totalLiquidNear,
      stakingBalance: totalStakedNear,
      totalNear,
      walletCount: totalWallets,  // Top-level for frontend compatibility
      assetCount,
      holdings,

      stakingPositions: stakingPositions.slice(0, 10).map(p => ({
        account: p.account,
      validator: p.validator,
        staked: p.staked_near
      })),
      
      lockedPositions: lockedPositions.map(lp => ({
        token: lp.token_symbol,
        amount: typeof lp.locked_amount === 'string' ? parseFloat(lp.locked_amount) : lp.locked_amount,
        lockType: lp.lock_type,
        contract: lp.lock_contract
      })),

      exchanges: {
        count: Object.keys(exchangesByName).length,
        list: Object.values(exchangesByName),
        totalValueUsd: exchangeTotalUsd,
        totalValueCad: exchangeTotalUsd * cadRate
      },

      grandTotal: {
        usd: grandTotalUsd,
        cad: grandTotalCad,
        includesExchanges: Object.keys(exchangesByName).length > 0
      },
      
      summary: {
        totalNear,
        totalUsd: totalValueUsd,
        totalCad: totalValueCad,
        nearPrice,
        cadRate,
        walletCount: totalWallets,
        nearWalletCount: wallets.length,
        exchangeWalletCount: exchangeWallets.length,
        tokenCount: filteredTokenHoldings.length,
        hasExchanges: exchangeWallets.length > 0
      },

      defi: {
        positions: defiPositions,
        supplied: defiSuppliedUsd,
        collateral: defiCollateralUsd,
        borrowed: defiBorrowedUsd,
        netValue: defiNetValueUsd
      },

      dust: {
        hidden: hideDust,
        threshold: dustThreshold,
        count: dustCount,
        valueUsd: dustValue
      },

      wallets: walletData.slice(0, 20).map(w => ({
        account: w.account,
        liquid: w.liquid,
        staked: w.staked,
        total: w.liquid + w.staked
      }))
    });
  } catch (error: any) {
    console.error('Portfolio error:', error);
    return NextResponse.json({ error: 'Failed', details: error.message }, { status: 500 });
  }
}
