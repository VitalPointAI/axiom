#!/usr/bin/env python3
"""
Backfill historical NEAR prices for staking epoch rewards.
Uses local price_cache first, then falls back to APIs.
"""

import os
import sys
import time
import requests
import psycopg2
from datetime import datetime, timedelta
from collections import defaultdict

# Database connection
DB_URL = "postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax"

def get_db():
    return psycopg2.connect(DB_URL)

def load_cached_prices(cur) -> dict:
    """Load all NEAR prices from price_cache."""
    print("Loading cached NEAR prices...")
    cur.execute("""
        SELECT date, price FROM price_cache 
        WHERE coin_id IN ('NEAR', 'near') AND currency IN ('USD', 'usd')
    """)
    
    prices = {}
    for date_str, price in cur.fetchall():
        # Normalize date format (remove time portion if present)
        date_key = date_str.split(' ')[0] if ' ' in date_str else date_str
        # Convert 'YYYY-MM-DD HH:MM' to 'YYYY-MM-DD'
        prices[date_key] = float(price)
    
    print(f"  Loaded {len(prices)} cached prices")
    return prices

def load_cad_rates(cur) -> dict:
    """Load CAD rates from price_cache."""
    print("Loading cached CAD rates...")
    cur.execute("""
        SELECT date, price FROM price_cache 
        WHERE coin_id = 'CADUSD' AND currency = 'USD'
    """)
    
    rates = {}
    for date_str, rate in cur.fetchall():
        date_key = date_str.split(' ')[0] if ' ' in date_str else date_str
        # This is actually CADUSD so we need inverse for USDCAD
        rates[date_key] = 1.0 / float(rate) if float(rate) > 0 else 1.35
    
    print(f"  Loaded {len(rates)} cached CAD rates")
    return rates

def fetch_missing_prices_coingecko(dates: list[str], existing_prices: dict) -> dict:
    """Fetch missing prices from CoinGecko (with rate limiting)."""
    missing_dates = [d for d in dates if d not in existing_prices]
    
    if not missing_dates:
        return {}
    
    print(f"Fetching {len(missing_dates)} missing prices from CoinGecko...")
    
    new_prices = {}
    for i, date_str in enumerate(missing_dates[:50]):  # Limit to 50 to avoid rate limits
        try:
            # CoinGecko historical price endpoint
            # Format: DD-MM-YYYY
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            cg_date = dt.strftime('%d-%m-%Y')
            
            url = f"https://api.coingecko.com/api/v3/coins/near/history?date={cg_date}&localization=false"
            resp = requests.get(url, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                price = data.get('market_data', {}).get('current_price', {}).get('usd')
                if price:
                    new_prices[date_str] = price
                    print(f"  {date_str}: ${price:.4f}")
            elif resp.status_code == 429:
                print(f"  Rate limited at {i} requests")
                break
            
            time.sleep(1.5)  # Rate limit: ~30 req/min
            
        except Exception as e:
            print(f"  Error for {date_str}: {e}")
    
    return new_prices

def get_nearest_price(target_date: str, prices: dict, max_days: int = 7) -> float:
    """Get the nearest available price for a date."""
    if target_date in prices:
        return prices[target_date]
    
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    
    # Try nearby dates
    for offset in range(1, max_days + 1):
        for delta in [offset, -offset]:
            nearby = (dt + timedelta(days=delta)).strftime('%Y-%m-%d')
            if nearby in prices:
                return prices[nearby]
    
    return None

def get_nearest_rate(target_date: str, rates: dict) -> float:
    """Get the nearest available CAD rate for a date."""
    if target_date in rates:
        return rates[target_date]
    
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    for i in range(1, 14):
        for delta in [i, -i]:
            nearby = (dt + timedelta(days=delta)).strftime('%Y-%m-%d')
            if nearby in rates:
                return rates[nearby]
    
    return 1.35  # Fallback average rate

def main():
    conn = get_db()
    cur = conn.cursor()
    
    # Load cached data
    cached_prices = load_cached_prices(cur)
    cached_rates = load_cad_rates(cur)
    
    # Also fetch CAD rates from Bank of Canada for any missing
    if len(cached_rates) < 1000:
        print("Fetching additional CAD rates from Bank of Canada...")
        try:
            url = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?start_date=2020-01-01"
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for obs in data.get('observations', []):
                    date_str = obs.get('d')
                    rate = obs.get('FXUSDCAD', {}).get('v')
                    if date_str and rate:
                        cached_rates[date_str] = float(rate)
                print(f"  Now have {len(cached_rates)} CAD rates")
        except Exception as e:
            print(f"  Error: {e}")
    
    # Get all epoch rewards missing prices
    print("\nFinding epoch rewards missing prices...")
    cur.execute("""
        SELECT id, epoch_date, reward_near
        FROM staking_epoch_rewards
        WHERE (near_price_usd IS NULL OR near_price_usd = 0)
          AND reward_near > 0
          AND epoch_date IS NOT NULL
        ORDER BY epoch_date
    """)
    
    rows = cur.fetchall()
    print(f"Found {len(rows)} records to backfill")
    
    if not rows:
        print("Nothing to backfill!")
        return
    
    # Get unique dates
    dates_needed = list(set(str(row[1]) for row in rows if row[1]))
    dates_needed.sort()
    
    # Check coverage
    covered = sum(1 for d in dates_needed if d in cached_prices or get_nearest_price(d, cached_prices, 3))
    print(f"Dates covered by cache: {covered}/{len(dates_needed)}")
    
    # Update records
    print("\nUpdating database...")
    updated = 0
    missing_price = 0
    
    for row_id, epoch_date, reward_near in rows:
        date_str = str(epoch_date)
        
        price_usd = get_nearest_price(date_str, cached_prices, 7)
        
        if not price_usd:
            missing_price += 1
            continue
        
        cad_rate = get_nearest_rate(date_str, cached_rates)
        
        reward_usd = float(reward_near) * price_usd
        reward_cad = reward_usd * cad_rate
        price_cad = price_usd * cad_rate
        
        cur.execute("""
            UPDATE staking_epoch_rewards
            SET near_price_usd = %s,
                near_price_cad = %s,
                reward_usd = %s,
                reward_cad = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (price_usd, price_cad, reward_usd, reward_cad, row_id))
        
        updated += 1
        
        if updated % 1000 == 0:
            print(f"  Updated {updated} records...")
            conn.commit()
    
    conn.commit()
    
    # Show remaining gaps
    if missing_price > 0:
        print(f"\n{missing_price} records still missing prices. Checking date ranges...")
        cur.execute("""
            SELECT MIN(epoch_date), MAX(epoch_date), COUNT(*)
            FROM staking_epoch_rewards
            WHERE (near_price_usd IS NULL OR near_price_usd = 0)
              AND reward_near > 0
        """)
        result = cur.fetchone()
        if result and result[2] > 0:
            print(f"  Missing range: {result[0]} to {result[1]} ({result[2]} records)")
    
    cur.close()
    conn.close()
    
    print(f"\n✅ Done! Updated {updated} records, {missing_price} still missing prices")

if __name__ == '__main__':
    main()
