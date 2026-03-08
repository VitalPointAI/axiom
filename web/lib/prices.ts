// Historical price cache
const priceCache = new Map<string, number>();

export async function getNearPriceForDate(date: string): Promise<number> {
  // Check cache first
  if (priceCache.has(date)) {
    return priceCache.get(date)!;
  }

  try {
    // CoinGecko historical price
    const [year, month, day] = date.split('-');
    const formattedDate = `${day}-${month}-${year}`;
    
    const res = await fetch(
      `https://api.coingecko.com/api/v3/coins/near/history?date=${formattedDate}&localization=false`,
      { next: { revalidate: 86400 } } // Cache for 24h
    );
    
    if (res.ok) {
      const data = await res.json();
      const price = data.market_data?.current_price?.usd || 1.12;
      priceCache.set(date, price);
      return price;
    }
  } catch (e) {
    console.error('Price fetch error for', date, e);
  }
  
  // Fallback - try to estimate based on recent known prices
  // NEAR price roughly: Jan 2026 ~, Feb 2026 ~.15
  const d = new Date(date);
  const now = new Date();
  const monthsAgo = (now.getTime() - d.getTime()) / (30 * 24 * 60 * 60 * 1000);
  
  // Simple linear interpolation (very rough)
  const currentPrice = 1.15;
  const oldPrice = 5.0; // Jan 2026 price
  const estimatedPrice = currentPrice + (monthsAgo * 0.5); // Rough adjustment
  
  const price = Math.min(Math.max(estimatedPrice, 1.0), 6.0);
  priceCache.set(date, price);
  return price;
}

export async function getCurrentNearPrice(): Promise<number> {
  try {
    const res = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd',
      { next: { revalidate: 60 } }
    );
    if (res.ok) {
      const data = await res.json();
      return data.near?.usd || 1.12;
    }
  } catch {}
  
  // Fallback to CoinCap
  try {
    const res = await fetch('https://api.coincap.io/v2/assets/near-protocol');
    if (res.ok) {
      const data = await res.json();
      return parseFloat(data.data?.priceUsd) || 1.12;
    }
  } catch {}
  
  return 1.12;
}
