#!/usr/bin/env python3
"""
Backfill historical NEAR prices for staking epoch rewards.
Uses CryptoCompare API (CoinGecko is blocked).
"""

import time
import requests
import psycopg2
from datetime import datetime, timedelta

# Database connection
DB_URL = "postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax"

# CryptoCompare API (free tier: 100k calls/month)
CRYPTOCOMPARE_API = "https://min-api.cryptocompare.com/data/v2/histoday"

def get_db():
    return psycopg2.connect(DB_URL)

def fetch_near_prices_batch(dates: list[str]) -> dict:
    """Fetch NEAR prices for multiple dates using CryptoCompare histoday endpoint."""
    prices = {}

    # Group dates by month to minimize API calls
    # CryptoCompare histoday returns up to 2000 days of data

    if not dates:
        return prices

    # Get the date range
    min_date = min(dates)
    max_date = max(dates)

    min_dt = datetime.strptime(min_date, '%Y-%m-%d')
    max_dt = datetime.strptime(max_date, '%Y-%m-%d')

    # Calculate days needed
    days_needed = (max_dt - min_dt).days + 1

    print(f"Fetching NEAR prices from {min_date} to {max_date} ({days_needed} days)...")

    # Fetch historical data
    params = {
        'fsym': 'NEAR',
        'tsym': 'USD',
        'limit': min(days_needed, 2000),
        'toTs': int(max_dt.timestamp())
    }

    try:
        resp = requests.get(CRYPTOCOMPARE_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data.get('Response') == 'Success':
            for day in data.get('Data', {}).get('Data', []):
                ts = day['time']
                date_str = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
                # Use close price
                price = day.get('close', 0)
                if price > 0:
                    prices[date_str] = price
            print(f"  Got {len(prices)} price points")
        else:
            print(f"  API error: {data.get('Message', 'Unknown error')}")
    except Exception as e:
        print(f"  Error fetching prices: {e}")

    return prices

def fetch_cad_rates(dates: list[str]) -> dict:
    """Fetch USD/CAD exchange rates from Bank of Canada."""
    rates = {}

    if not dates:
        return rates

    # Bank of Canada Valet API
    min_date = min(dates)
    max_date = max(dates)

    print(f"Fetching CAD rates from {min_date} to {max_date}...")

    url = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json"
    params = {
        'start_date': min_date,
        'end_date': max_date
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for obs in data.get('observations', []):
            date_str = obs.get('d')
            rate_data = obs.get('FXUSDCAD', {})
            rate = float(rate_data.get('v', 0)) if rate_data.get('v') else None
            if date_str and rate:
                rates[date_str] = rate

        print(f"  Got {len(rates)} CAD rates")
    except Exception as e:
        print(f"  Error fetching CAD rates: {e}")

    return rates

def get_nearest_rate(target_date: str, rates: dict) -> float:
    """Get the nearest available rate for a date (handles weekends/holidays)."""
    if target_date in rates:
        return rates[target_date]

    # Try up to 7 days before
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    for i in range(1, 8):
        prev_date = (dt - timedelta(days=i)).strftime('%Y-%m-%d')
        if prev_date in rates:
            return rates[prev_date]

    return 1.35  # Fallback average rate

def main():
    conn = get_db()
    cur = conn.cursor()

    # Get all epoch rewards missing prices
    print("Finding epoch rewards missing prices...")
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

    print(f"Unique dates needed: {len(dates_needed)}")

    # Fetch prices in batches (CryptoCompare can do 2000 at once)
    all_prices = {}
    batch_size = 2000

    for i in range(0, len(dates_needed), batch_size):
        batch = dates_needed[i:i+batch_size]
        prices = fetch_near_prices_batch(batch)
        all_prices.update(prices)
        time.sleep(0.5)  # Rate limit courtesy

    print(f"Total prices fetched: {len(all_prices)}")

    # Fetch CAD rates
    cad_rates = fetch_cad_rates(dates_needed)

    # Update records
    print("Updating database...")
    updated = 0
    missing_price = 0

    for row_id, epoch_date, reward_near in rows:
        date_str = str(epoch_date)

        price_usd = all_prices.get(date_str)
        if not price_usd:
            # Try nearby dates
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            for offset in [1, -1, 2, -2, 3, -3]:
                nearby = (dt + timedelta(days=offset)).strftime('%Y-%m-%d')
                if nearby in all_prices:
                    price_usd = all_prices[nearby]
                    break

        if not price_usd:
            missing_price += 1
            continue

        cad_rate = get_nearest_rate(date_str, cad_rates)

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

        if updated % 500 == 0:
            print(f"  Updated {updated} records...")
            conn.commit()

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nDone! Updated {updated} records, {missing_price} still missing prices")

if __name__ == '__main__':
    main()
