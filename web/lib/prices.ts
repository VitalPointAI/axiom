/**
 * CoinGecko price fetcher for NearTax
 */

const COIN_IDS: Record<string, string> = {
  'NEAR': 'near',
  'ETH': 'ethereum',
  'MATIC': 'matic-network',
  'BTC': 'bitcoin',
  'USDC': 'usd-coin',
  'USDT': 'tether',
  'Polygon': 'matic-network',
  'Optimism': 'ethereum', // Use ETH price
};

// Simple in-memory cache
const priceCache: Map<string, { price: number; timestamp: number }> = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

export async function getCurrentPrice(asset: string): Promise<number> {
  const cacheKey = asset.toUpperCase();
  const cached = priceCache.get(cacheKey);
  
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.price;
  }
  
  const coinId = COIN_IDS[cacheKey];
  if (!coinId) {
    return 0;
  }
  
  try {
    const response = await fetch(
      `https://api.coingecko.com/api/v3/simple/price?ids=${coinId}&vs_currencies=usd`,
      { next: { revalidate: 300 } } // Cache for 5 minutes
    );
    
    if (!response.ok) {
      console.error(`CoinGecko API error: ${response.status}`);
      return cached?.price || 0;
    }
    
    const data = await response.json();
    const price = data[coinId]?.usd || 0;
    
    priceCache.set(cacheKey, { price, timestamp: Date.now() });
    
    return price;
  } catch (error) {
    console.error(`Error fetching ${asset} price:`, error);
    return cached?.price || 0;
  }
}

export async function getCurrentPrices(assets: string[]): Promise<Record<string, number>> {
  const uniqueCoins = [...new Set(
    assets.map(a => COIN_IDS[a.toUpperCase()]).filter(Boolean)
  )];
  
  if (uniqueCoins.length === 0) {
    return {};
  }
  
  try {
    const response = await fetch(
      `https://api.coingecko.com/api/v3/simple/price?ids=${uniqueCoins.join(',')}&vs_currencies=usd`,
      { next: { revalidate: 300 } }
    );
    
    if (!response.ok) {
      return {};
    }
    
    const data = await response.json();
    const prices: Record<string, number> = {};
    
    for (const asset of assets) {
      const coinId = COIN_IDS[asset.toUpperCase()];
      if (coinId && data[coinId]?.usd) {
        prices[asset.toUpperCase()] = data[coinId].usd;
        priceCache.set(asset.toUpperCase(), { 
          price: data[coinId].usd, 
          timestamp: Date.now() 
        });
      }
    }
    
    return prices;
  } catch (error) {
    console.error('Error fetching prices:', error);
    return {};
  }
}

// Fallback prices if API fails
export const FALLBACK_PRICES: Record<string, number> = {
  'NEAR': 1.0,
  'ETH': 1800,
  'BTC': 45000,
  'MATIC': 0.80,
  'USDC': 1.0,
  'USDT': 1.0,
};
