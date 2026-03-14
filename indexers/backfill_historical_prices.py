#!/usr/bin/env python3
"""
Historical Price Backfill for NearTax Holdings Reports

Fetches historical prices from CoinGecko for year-end dates.
"""

import time
import requests
import psycopg2
from datetime import datetime

PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'

# CoinGecko API (has API key for higher rate limits)
COINGECKO_API_KEY = "CG-WS5r2LLsLMDgDN6ZnEimFcrR"  # Demo key
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Map token symbols to CoinGecko IDs
TOKEN_TO_COINGECKO = {
    'NEAR': 'near',
    'WNEAR': 'near',
    'STNEAR': 'near',  # Tracks NEAR
    'RNEAR': 'near',   # Tracks NEAR  
    'ETH': 'ethereum',
    'WETH': 'ethereum',
    'USDC': 'usd-coin',
    'USDC.E': 'usd-coin',
    'USDT': 'tether',
    'USDT.E': 'tether',
    'DAI': 'dai',
    'BTC': 'bitcoin',
    'WBTC': 'wrapped-bitcoin',
    'AURORA': 'aurora-near',
    'REF': 'ref-finance',
    'LINEAR': 'linear-protocol',
    'OCT': 'octopus-network',
    'SWEAT': 'sweatcoin',
    'BRRR': 'burrow',
    'PARAS': 'paras',
    'PEM': 'pembrock-finance',
    'MPDAO': 'meta-pool-dao',
    'KSM': 'kusama',
    'ZEC': 'zcash',
    'CRO': 'crypto-com-chain',
    'TIA': 'celestia',
    'LONK': 'lonk',
    'SHITZU': 'shitzu',
    'BLACKDRAGON': 'black-dragon',
    'NEKO': 'neko-token',
    '$META': 'meta-pool',
    'XRHEA': None,  # No CoinGecko listing
    'ORHEA': None,
    'RHEA': None,
}

# Dates to backfill (year-end for tax reporting)
DATES_TO_BACKFILL = [
    '2023-01-01', '2023-12-31',
    '2024-01-01', '2024-12-31', 
    '2025-01-01', '2025-12-31',
]


def get_historical_price(coin_id: str, date_str: str) -> float | None:
    """Fetch historical price from CoinGecko."""
    # Convert YYYY-MM-DD to DD-MM-YYYY for CoinGecko
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    cg_date = dt.strftime('%d-%m-%Y')
    
    url = f"{COINGECKO_BASE}/coins/{coin_id}/history"
    params = {
        'date': cg_date,
        'localization': 'false'
    }
    headers = {
        'x-cg-demo-api-key': COINGECKO_API_KEY
    }
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 429:
            print("  Rate limited, waiting 60s...")
            time.sleep(60)
            return get_historical_price(coin_id, date_str)
        
        resp.raise_for_status()
        data = resp.json()
        
        market_data = data.get('market_data', {})
        price = market_data.get('current_price', {}).get('usd')
        return price
    except Exception as e:
        print(f"  Error fetching {coin_id} for {date_str}: {e}")
        return None


def backfill_prices():
    """Backfill historical prices for all tokens."""
    conn = psycopg2.connect(PG_CONN)
    cursor = conn.cursor()
    
    # Ensure price_cache table exists with correct schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_cache (
            id SERIAL PRIMARY KEY,
            coin_id TEXT NOT NULL,
            date DATE NOT NULL,
            price REAL,
            source TEXT DEFAULT 'coingecko',
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(coin_id, date)
        )
    """)
    conn.commit()
    
    total_fetched = 0
    
    for symbol, coin_id in TOKEN_TO_COINGECKO.items():
        if not coin_id:
            continue
            
        for date_str in DATES_TO_BACKFILL:
            # Check if we already have this price
            cursor.execute(
                "SELECT price FROM price_cache WHERE coin_id = %s AND date = %s",
                (symbol, date_str)
            )
            existing = cursor.fetchone()
            
            if existing and existing[0]:
                print(f"  {symbol} {date_str}: ${existing[0]:.4f} (cached)")
                continue
            
            print(f"Fetching {symbol} ({coin_id}) for {date_str}...")
            price = get_historical_price(coin_id, date_str)
            
            if price:
                cursor.execute("""
                    INSERT INTO price_cache (coin_id, date, price, source)
                    VALUES (%s, %s, %s, 'coingecko')
                    ON CONFLICT (coin_id, date) DO UPDATE SET price = %s
                """, (symbol, date_str, price, price))
                conn.commit()
                print(f"  {symbol} {date_str}: ${price:.4f}")
                total_fetched += 1
            else:
                print(f"  {symbol} {date_str}: No price found")
            
            # Rate limit: 30 calls/minute for demo key
            time.sleep(2.5)
    
    conn.close()
    print(f"\nDone! Fetched {total_fetched} prices.")


if __name__ == '__main__':
    backfill_prices()
