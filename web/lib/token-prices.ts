/**
 * Token Price Service for NearTax
 * 
 * Priority:
 * 1. Pyth Network (major tokens: NEAR, ETH, BTC, AURORA)
 * 2. Ref Finance (NEAR ecosystem tokens)
 * 3. CoinGecko (fallback for others)
 */

// Pyth price feed IDs (hex)
const PYTH_FEEDS: Record<string, string> = {
  'NEAR': 'c415de8d2eba7db216527dff4b60e8f3a5311c740dadb233e13e12547e226750',
  'ETH': 'ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace',
  'BTC': 'e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43',
  'AURORA': '2f7c4f738d498585065a4b87b637069ec99474597da7f0ca349ba8ac3ba9cac5',
  'USDC': 'eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a',
  'USDT': '2b89b9dc8fdf9f34709a5b106b472f0f39bb6ca9ce04b0fd7f2e971688e2e53b',
};

// Ref Finance token contract IDs
const REF_TOKEN_CONTRACTS: Record<string, string> = {
  'wNEAR': 'wrap.near',
  'stNEAR': 'meta-pool.near',
  'LiNEAR': 'linear-protocol.near',
  'REF': 'token.v2.ref-finance.near',
  'OCT': 'f5cfbc74057c610c8ef151a439252680ac68c6dc.factory.bridge.near',
  'AURORA': 'aaaaaa20d9e0e2461697782ef11675f668207961.factory.bridge.near',
};

const PYTH_HERMES_URL = 'https://hermes.pyth.network';
const REF_API_URL = 'https://api.ref.finance';
const COINGECKO_URL = 'https://api.coingecko.com/api/v3';

interface PriceResult {
  symbol: string;
  price: number;
  source: 'pyth' | 'ref' | 'coingecko' | 'stable';
  timestamp: number;
}

// Simple in-memory cache (5 min TTL)
const priceCache = new Map<string, { price: number; source: string; expires: number }>();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Fetch price from Pyth Network
 */
async function fetchPythPrice(symbol: string): Promise<number | null> {
  const feedId = PYTH_FEEDS[symbol.toUpperCase()];
  if (!feedId) return null;

  try {
    const resp = await fetch(`${PYTH_HERMES_URL}/v2/updates/price/latest?ids[]=${feedId}`);
    if (!resp.ok) return null;
    
    const data = await resp.json();
    const priceData = data.parsed?.[0]?.price;
    if (!priceData) return null;

    // Price = price * 10^expo
    const price = parseInt(priceData.price) * Math.pow(10, priceData.expo);
    return price;
  } catch (e) {
    console.error(`Pyth fetch error for ${symbol}:`, e);
    return null;
  }
}

/**
 * Fetch prices from Ref Finance
 */
async function fetchRefPrices(): Promise<Record<string, number>> {
  try {
    const resp = await fetch(`${REF_API_URL}/list-token-price`);
    if (!resp.ok) return {};
    
    const data = await resp.json();
    // Returns { "token_contract_id": { price: "1.23" }, ... }
    const prices: Record<string, number> = {};
    
    for (const [contractId, info] of Object.entries(data)) {
      const priceStr = (info as any)?.price;
      if (priceStr) {
        // Find symbol for this contract
        for (const [symbol, contract] of Object.entries(REF_TOKEN_CONTRACTS)) {
          if (contract === contractId) {
            prices[symbol] = parseFloat(priceStr);
            break;
          }
        }
        // Also store by contract ID for lookup
        prices[contractId] = parseFloat(priceStr);
      }
    }
    
    return prices;
  } catch (e) {
    console.error('Ref Finance fetch error:', e);
    return {};
  }
}

/**
 * Get price for a token (with caching)
 */
export async function getTokenPrice(symbol: string): Promise<PriceResult | null> {
  const upperSymbol = symbol.toUpperCase();
  
  // Check cache first
  const cached = priceCache.get(upperSymbol);
  if (cached && cached.expires > Date.now()) {
    return {
      symbol: upperSymbol,
      price: cached.price,
      source: cached.source as any,
      timestamp: Date.now()
    };
  }

  // Stablecoins
  if (['USDC', 'USDT', 'DAI', 'USN', 'CUSD'].includes(upperSymbol)) {
    const result = { symbol: upperSymbol, price: 1.0, source: 'stable' as const, timestamp: Date.now() };
    priceCache.set(upperSymbol, { price: 1.0, source: 'stable', expires: Date.now() + CACHE_TTL });
    return result;
  }

  // Try Pyth first
  const pythPrice = await fetchPythPrice(upperSymbol);
  if (pythPrice !== null) {
    priceCache.set(upperSymbol, { price: pythPrice, source: 'pyth', expires: Date.now() + CACHE_TTL });
    return { symbol: upperSymbol, price: pythPrice, source: 'pyth', timestamp: Date.now() };
  }

  // Try Ref Finance
  const refPrices = await fetchRefPrices();
  const refPrice = refPrices[upperSymbol] || refPrices[REF_TOKEN_CONTRACTS[upperSymbol]];
  if (refPrice) {
    priceCache.set(upperSymbol, { price: refPrice, source: 'ref', expires: Date.now() + CACHE_TTL });
    return { symbol: upperSymbol, price: refPrice, source: 'ref', timestamp: Date.now() };
  }

  return null;
}

/**
 * Get prices for multiple tokens at once
 */
export async function getTokenPrices(symbols: string[]): Promise<Record<string, PriceResult>> {
  const results: Record<string, PriceResult> = {};
  
  // Batch Pyth requests
  const pythSymbols = symbols.filter(s => PYTH_FEEDS[s.toUpperCase()]);
  const otherSymbols = symbols.filter(s => !PYTH_FEEDS[s.toUpperCase()]);
  
  // Fetch Pyth prices
  if (pythSymbols.length > 0) {
    const feedIds = pythSymbols.map(s => PYTH_FEEDS[s.toUpperCase()]);
    try {
      const url = `${PYTH_HERMES_URL}/v2/updates/price/latest?${feedIds.map(id => `ids[]=${id}`).join('&')}`;
      const resp = await fetch(url);
      if (resp.ok) {
        const data = await resp.json();
        for (let i = 0; i < pythSymbols.length; i++) {
          const priceData = data.parsed?.[i]?.price;
          if (priceData) {
            const price = parseInt(priceData.price) * Math.pow(10, priceData.expo);
            const symbol = pythSymbols[i].toUpperCase();
            results[symbol] = { symbol, price, source: 'pyth', timestamp: Date.now() };
            priceCache.set(symbol, { price, source: 'pyth', expires: Date.now() + CACHE_TTL });
          }
        }
      }
    } catch (e) {
      console.error('Pyth batch fetch error:', e);
    }
  }

  // Fetch Ref prices for remaining
  if (otherSymbols.length > 0) {
    const refPrices = await fetchRefPrices();
    for (const symbol of otherSymbols) {
      const upper = symbol.toUpperCase();
      
      // Stablecoins
      if (['USDC', 'USDT', 'DAI', 'USN', 'CUSD'].includes(upper)) {
        results[upper] = { symbol: upper, price: 1.0, source: 'stable', timestamp: Date.now() };
        continue;
      }
      
      const refPrice = refPrices[upper] || refPrices[REF_TOKEN_CONTRACTS[upper]];
      if (refPrice) {
        results[upper] = { symbol: upper, price: refPrice, source: 'ref', timestamp: Date.now() };
        priceCache.set(upper, { price: refPrice, source: 'ref', expires: Date.now() + CACHE_TTL });
      }
    }
  }

  return results;
}

// Export for use in API routes
export { PYTH_FEEDS, REF_TOKEN_CONTRACTS };
