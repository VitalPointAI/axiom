import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const symbol = request.nextUrl.searchParams.get('symbol') || 'NEAR';
  
  try {
    // Try CoinGecko first
    const cgRes = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd',
      { next: { revalidate: 60 } }
    );
    
    if (cgRes.ok) {
      const data = await cgRes.json();
      if (data.near?.usd) {
        return NextResponse.json({ 
          symbol: 'NEAR',
          price: data.near.usd,
          source: 'coingecko'
        });
      }
    }
    
    // Fallback to CoinCap
    const ccRes = await fetch(
      'https://api.coincap.io/v2/assets/near-protocol',
      { next: { revalidate: 60 } }
    );
    
    if (ccRes.ok) {
      const data = await ccRes.json();
      if (data.data?.priceUsd) {
        return NextResponse.json({ 
          symbol: 'NEAR',
          price: parseFloat(data.data.priceUsd),
          source: 'coincap'
        });
      }
    }
    
    return NextResponse.json({ error: 'Unable to fetch price' }, { status: 503 });
  } catch (error) {
    console.error('Price API error:', error);
    return NextResponse.json({ error: 'Price fetch failed' }, { status: 500 });
  }
}
