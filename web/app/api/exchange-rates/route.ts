import { NextRequest, NextResponse } from "next/server";

// Cache exchange rates for 1 hour
let cachedRates: Record<string, number> | null = null;
let cacheTime: number = 0;
const CACHE_DURATION = 60 * 60 * 1000; // 1 hour

// Fallback rates if API fails
const FALLBACK_RATES: Record<string, number> = {
  USD: 1,
  CAD: 1.36,
  EUR: 0.92,
  GBP: 0.79,
  AUD: 1.53,
  JPY: 149.5,
  CHF: 0.88,
  CNY: 7.24,
  INR: 83.1,
  KRW: 1320,
  BRL: 4.97,
  MXN: 17.15,
};

async function fetchExchangeRates(): Promise<Record<string, number>> {
  // Try free exchange rate APIs
  const apis = [
    // exchangerate.host (free, no key required)
    async () => {
      const res = await fetch('https://api.exchangerate.host/latest?base=USD', { 
        next: { revalidate: 3600 } 
      });
      const data = await res.json();
      if (data.success && data.rates) {
        return data.rates;
      }
      throw new Error('Invalid response');
    },
    // frankfurter.app (free, no key required)
    async () => {
      const res = await fetch('https://api.frankfurter.app/latest?from=USD', {
        next: { revalidate: 3600 }
      });
      const data = await res.json();
      if (data.rates) {
        return { USD: 1, ...data.rates };
      }
      throw new Error('Invalid response');
    },
  ];

  for (const api of apis) {
    try {
      const rates = await api();
      return rates;
    } catch (error) {
      console.error('Exchange rate API failed:', error);
      continue;
    }
  }

  // All APIs failed, return fallback
  return FALLBACK_RATES;
}

export async function GET(request: NextRequest) {
  try {
    // Check cache
    if (cachedRates && Date.now() - cacheTime < CACHE_DURATION) {
      return NextResponse.json({ 
        rates: cachedRates, 
        cached: true,
        cacheAge: Math.round((Date.now() - cacheTime) / 1000),
      });
    }

    // Fetch fresh rates
    const rates = await fetchExchangeRates();
    
    // Update cache
    cachedRates = rates;
    cacheTime = Date.now();

    return NextResponse.json({ 
      rates,
      cached: false,
    });
  } catch (error: any) {
    console.error('Exchange rates error:', error);
    
    // Return fallback rates on error
    return NextResponse.json({ 
      rates: FALLBACK_RATES,
      error: 'Using fallback rates',
    });
  }
}
