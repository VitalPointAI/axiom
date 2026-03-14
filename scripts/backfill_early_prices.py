#!/usr/bin/env python3
"""
Backfill NEAR prices for 2019-2020 using CoinGecko historical API.
"""

import sqlite3
import requests
from datetime import datetime, timezone, timedelta
import time
import sys

CG_API_URL = "https://api.coingecko.com/api/v3"
NEAR_ID = "near"

def fetch_historical_price(date_str: str) -> float | None:
    """Fetch NEAR price for a specific date (dd-mm-yyyy format for CoinGecko)."""
    url = f"{CG_API_URL}/coins/{NEAR_ID}/history"
    params = {'date': date_str, 'localization': 'false'}
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        
        if resp.status_code == 429:
            print("Rate limited, waiting 60s...")
            time.sleep(60)
            return fetch_historical_price(date_str)  # Retry
        
        if resp.status_code == 404:
            return None  # NEAR didn't exist yet
        
        resp.raise_for_status()
        data = resp.json()
        
        market_data = data.get('market_data', {})
        price = market_data.get('current_price', {}).get('usd')
        return price
    except Exception as e:
        print(f"Error fetching {date_str}: {e}")
        return None


def backfill_early_prices(db_path: str = '/home/deploy/neartax/neartax.db'):
    """Fetch and store daily NEAR prices from Oct 2019 through Sep 2020."""
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # NEAR mainnet launched Oct 2020, but there were testnet prices before
    # Let's start from when we have transactions
    cur.execute("SELECT MIN(block_timestamp) FROM transactions WHERE block_timestamp > 1000000000000000")
    oldest = cur.fetchone()[0]
    
    if oldest:
        start_date = datetime.fromtimestamp(oldest / 1_000_000_000, tz=timezone.utc).date()
    else:
        start_date = datetime(2019, 10, 1).date()
    
    # Get the earliest date we already have prices for
    cur.execute("SELECT MIN(date) FROM price_cache WHERE coin_id = 'NEAR'")
    earliest_cached = cur.fetchone()[0]
    
    if earliest_cached:
        end_date = datetime.strptime(earliest_cached.split(' ')[0], '%Y-%m-%d').date()
    else:
        end_date = datetime.now(timezone.utc).date()
    
    print(f"Backfilling prices from {start_date} to {end_date}")
    print(f"Earliest cached price: {earliest_cached}")
    
    # Find dates we need prices for (from transactions)
    cur.execute("""
        SELECT DISTINCT date(block_timestamp/1000000000, 'unixepoch') as tx_date
        FROM transactions 
        WHERE block_timestamp > 1000000000000000
        ORDER BY tx_date
    """)
    tx_dates = set(row[0] for row in cur.fetchall())
    print(f"Found {len(tx_dates)} unique transaction dates")
    
    # Check which dates we're missing prices for
    cur.execute("SELECT DISTINCT substr(date, 1, 10) FROM price_cache WHERE coin_id = 'NEAR'")
    cached_dates = set(row[0] for row in cur.fetchall())
    
    missing_dates = sorted(tx_dates - cached_dates)
    print(f"Missing prices for {len(missing_dates)} dates")
    
    if not missing_dates:
        print("No missing price dates!")
        conn.close()
        return
    
    # Fetch missing prices (rate limited)
    inserted = 0
    for i, date_str in enumerate(missing_dates):
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        except Exception:
            continue
            
        # Convert to CoinGecko format (dd-mm-yyyy)
        cg_date = date_obj.strftime('%d-%m-%Y')
        
        print(f"[{i+1}/{len(missing_dates)}] Fetching {date_str}...", end=' ', flush=True)
        
        price = fetch_historical_price(cg_date)
        
        if price:
            store_date = f"{date_str} 12:00"
            cur.execute('''
                INSERT OR REPLACE INTO price_cache (coin_id, date, currency, price, fetched_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            ''', ('NEAR', store_date, 'USD', price))
            inserted += 1
            print(f"${price:.4f}")
            conn.commit()
        else:
            print("no data (NEAR may not have existed)")
        
        # Rate limit: ~10 calls per minute for free tier
        time.sleep(7)
    
    print(f"\nInserted {inserted} price records")
    
    # Now apply prices to transactions
    print("\nApplying prices to transactions...")
    apply_prices(conn, cur)
    
    conn.close()


def apply_prices(conn, cur):
    """Apply cached prices to transactions that are missing cost_basis."""
    
    # Load all prices
    cur.execute('SELECT date, price FROM price_cache WHERE coin_id = ?', ('NEAR',))
    prices = {}
    for row in cur.fetchall():
        date_str = row[0].split(' ')[0]
        prices[date_str] = row[1]
    
    print(f"Loaded {len(prices)} daily prices")
    
    # Get USD/CAD rate for each year (approximate)
    cad_rates = {
        '2019': 1.32,
        '2020': 1.34,
        '2021': 1.25,
        '2022': 1.30,
        '2023': 1.35,
        '2024': 1.36,
        '2025': 1.38,
        '2026': 1.38,
    }
    
    # Update transactions
    cur.execute('''
        SELECT id, block_timestamp, amount
        FROM transactions
        WHERE (cost_basis_usd IS NULL OR cost_basis_usd = 0)
        AND block_timestamp > 1000000000000000
        AND CAST(amount AS REAL) > 0
    ''')
    
    transactions = cur.fetchall()
    print(f"Found {len(transactions)} transactions to price")
    
    updated = 0
    for tx in transactions:
        tx_id, ts, amount = tx
        
        dt = datetime.fromtimestamp(ts / 1_000_000_000, tz=timezone.utc)
        date_str = dt.strftime('%Y-%m-%d')
        year = dt.strftime('%Y')
        
        price = prices.get(date_str)
        if not price:
            # Try nearby dates
            for delta in [-1, 1, -2, 2, -3, 3, -7, 7]:
                nearby = (dt + timedelta(days=delta)).strftime('%Y-%m-%d')
                price = prices.get(nearby)
                if price:
                    break
        
        if not price:
            continue
        
        cad_rate = cad_rates.get(year, 1.38)
        amount_near = float(amount) / 1e24
        value_usd = amount_near * price
        value_cad = value_usd * cad_rate
        
        cur.execute('''
            UPDATE transactions
            SET cost_basis_usd = ?,
                cost_basis_cad = ?,
                price_warning = NULL,
                price_resolved = 1
            WHERE id = ?
        ''', (value_usd, value_cad, tx_id))
        
        updated += 1
    
    conn.commit()
    print(f"Updated {updated} transactions with prices")


if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else '/home/deploy/neartax/neartax.db'
    backfill_early_prices(db_path)
