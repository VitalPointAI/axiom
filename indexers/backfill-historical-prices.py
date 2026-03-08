#!/usr/bin/env python3
"""
Backfill DeFi events with accurate historical prices from CoinGecko.
Uses transaction timestamp to fetch the price at that specific date.
"""

import psycopg2
import requests
from datetime import datetime, timezone
import time
import sys

# CoinGecko API Key - 30 calls/min, 10k calls/month
COINGECKO_API_KEY = 'CG-yRoEgzCqB1QSKPzBXu2WBEGN'
COINGECKO_HEADERS = {'x-cg-demo-api-key': COINGECKO_API_KEY}

# CoinGecko token ID mapping
COINGECKO_IDS = {
    'wNEAR': 'near',
    'NEAR': 'near',
    'STNEAR': 'staked-near',
    'BRRR': 'burrow',
    'REF': 'ref-finance',
    '$META': 'meta-pool',
    'USDC': 'usd-coin',
    'USDC.e': 'usd-coin',
    'USDT.e': 'tether',
    'DAI': 'dai',
    'ETH': 'ethereum',
    'AURORA': 'aurora-near',
    'SWEAT': 'sweatcoin',
    'mpDAO': 'meta-pool-dao',
    'rNEAR': 'near',  # rNEAR tracks NEAR price
    'ZEC': 'zcash',
}

# Stablecoins - always $1
STABLECOINS = {'USDC', 'USDC.e', 'USDT.e', 'DAI', 'USN'}

# Price cache to avoid redundant API calls
price_cache = {}

def get_historical_price(token_symbol: str, timestamp_ns: int) -> float | None:
    """Fetch historical price from CoinGecko for a specific date."""
    
    # Stablecoins are always $1
    if token_symbol in STABLECOINS:
        return 1.0
    
    coingecko_id = COINGECKO_IDS.get(token_symbol)
    if not coingecko_id:
        print(f"  No CoinGecko ID for {token_symbol}")
        return None
    
    # Convert nanoseconds to date string (DD-MM-YYYY)
    dt = datetime.fromtimestamp(timestamp_ns / 1_000_000_000, tz=timezone.utc)
    date_str = dt.strftime('%d-%m-%Y')
    
    # Check cache
    cache_key = f"{coingecko_id}:{date_str}"
    if cache_key in price_cache:
        return price_cache[cache_key]
    
    # Rate limit: CoinGecko with API key is 30 req/min
    time.sleep(2.1)  # ~28 requests per minute (safe margin)
    
    url = f"https://api.coingecko.com/api/v3/coins/{coingecko_id}/history?date={date_str}"
    
    try:
        resp = requests.get(url, headers=COINGECKO_HEADERS, timeout=30)
        
        if resp.status_code == 429:
            print(f"  Rate limited, waiting 60s...")
            time.sleep(60)
            return get_historical_price(token_symbol, timestamp_ns)
        
        if resp.status_code != 200:
            print(f"  CoinGecko error {resp.status_code} for {token_symbol} on {date_str}")
            return None
        
        data = resp.json()
        
        if 'market_data' not in data or 'current_price' not in data['market_data']:
            print(f"  No price data for {token_symbol} on {date_str}")
            return None
        
        price = data['market_data']['current_price'].get('usd')
        if price:
            price_cache[cache_key] = price
            print(f"  {token_symbol} on {date_str}: ${price:.6f}")
        return price
        
    except Exception as e:
        print(f"  Error fetching {token_symbol}: {e}")
        return None


def get_exchange_rate(conn, timestamp_ns: int) -> float:
    """Get USD/CAD rate from our stored rates."""
    cur = conn.cursor()
    dt = datetime.fromtimestamp(timestamp_ns / 1_000_000_000, tz=timezone.utc)
    date_str = dt.strftime('%Y-%m-%d')
    
    cur.execute("""
        SELECT rate FROM exchange_rate_history 
        WHERE date <= %s 
        ORDER BY date DESC LIMIT 1
    """, (date_str,))
    row = cur.fetchone()
    return row[0] if row else 1.35  # Default fallback


def main():
    conn = psycopg2.connect(
        host='localhost',
        user='neartax',
        password='lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx',
        database='neartax'
    )
    
    print("Fetching DeFi events that need historical prices...")
    print(f"Start time: {datetime.now()}")
    sys.stdout.flush()
    
    cur = conn.cursor()
    
    # Get all events with tokens we can price
    cur.execute("""
        SELECT id, token_symbol, amount_decimal, block_timestamp, price_usd
        FROM defi_events
        WHERE token_symbol IS NOT NULL 
          AND amount_decimal IS NOT NULL
          AND token_symbol NOT LIKE '%%.%%'
          AND token_symbol NOT LIKE '%%com%%'
          AND token_symbol IN ('wNEAR', 'STNEAR', 'BRRR', 'REF', '$META', 'USDC', 'USDC.e', 
                                'DAI', 'ETH', 'AURORA', 'mpDAO', 'rNEAR', 'ZEC', 'SWEAT',
                                'USDT.e', 'USN')
        ORDER BY block_timestamp
    """)
    events = cur.fetchall()
    
    print(f"Found {len(events)} events to update")
    sys.stdout.flush()
    
    # Group by token+date to minimize API calls
    date_token_events = {}
    for event in events:
        event_id, token_symbol, amount, timestamp, _ = event
        dt = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=timezone.utc)
        date_str = dt.strftime('%d-%m-%Y')
        key = f"{token_symbol}:{date_str}"
        if key not in date_token_events:
            date_token_events[key] = []
        date_token_events[key].append(event)
    
    print(f"Unique token+date combinations: {len(date_token_events)}")
    sys.stdout.flush()
    
    updated = 0
    skipped = 0
    
    for i, (key, key_events) in enumerate(date_token_events.items()):
        token_symbol = key.split(':')[0]
        timestamp_ns = key_events[0][3]  # block_timestamp
        
        price = get_historical_price(token_symbol, timestamp_ns)
        
        if price is None:
            skipped += len(key_events)
            continue
        
        # Update all events with this token on this date
        for event in key_events:
            event_id, _, amount, timestamp, _ = event
            value_usd = float(amount) * price if amount else None
            cad_rate = get_exchange_rate(conn, timestamp)
            value_cad = value_usd * cad_rate if value_usd else None
            
            cur.execute("""
                UPDATE defi_events
                SET price_usd = %s, value_usd = %s, value_cad = %s
                WHERE id = %s
            """, (price, value_usd, value_cad, event_id))
            
            updated += 1
        
        conn.commit()
        
        if (i + 1) % 10 == 0:
            print(f"Progress: {i+1}/{len(date_token_events)} combos, {updated} events updated")
            sys.stdout.flush()
    
    conn.commit()
    print(f"\nDone! Updated {updated} events, skipped {skipped}")
    print(f"End time: {datetime.now()}")
    conn.close()


if __name__ == '__main__':
    main()
