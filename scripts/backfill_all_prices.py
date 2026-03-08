#!/usr/bin/env python3
"""
Backfill historical prices for NEAR and ETH using CryptoCompare API.
CryptoCompare has better free tier for historical data.
"""

import sqlite3
import requests
from datetime import datetime, timezone, timedelta
import time
import sys

# CryptoCompare API - much better for historical data
CC_API_URL = "https://min-api.cryptocompare.com/data/v2/histoday"

# Approximate CAD rates by year
CAD_RATES = {
    2019: 1.32, 2020: 1.34, 2021: 1.25, 2022: 1.30,
    2023: 1.35, 2024: 1.36, 2025: 1.38, 2026: 1.38,
}


def fetch_historical_prices(symbol: str, from_date: datetime, to_date: datetime) -> dict:
    """Fetch daily prices from CryptoCompare."""
    prices = {}
    
    # CryptoCompare returns up to 2000 days of data
    days_diff = (to_date - from_date).days
    
    print(f"Fetching {symbol} prices from {from_date.date()} to {to_date.date()} ({days_diff} days)")
    
    params = {
        'fsym': symbol,
        'tsym': 'USD',
        'limit': min(days_diff, 2000),
        'toTs': int(to_date.timestamp())
    }
    
    try:
        resp = requests.get(CC_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('Response') == 'Success':
            for item in data.get('Data', {}).get('Data', []):
                ts = item.get('time', 0)
                close = item.get('close', 0)
                if ts and close:
                    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
                    prices[date_str] = close
        
        print(f"  Got {len(prices)} price points for {symbol}")
        
    except Exception as e:
        print(f"Error fetching {symbol} prices: {e}")
    
    return prices


def backfill_prices(db_path: str = '/home/deploy/neartax/neartax.db'):
    """Backfill prices for all tokens."""
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Get date range of transactions
    cur.execute("SELECT MIN(block_timestamp), MAX(block_timestamp) FROM transactions WHERE block_timestamp > 1000000000000000")
    oldest, newest = cur.fetchone()
    
    if not oldest:
        print("No transactions found")
        return
    
    from_date = datetime.fromtimestamp(oldest / 1_000_000_000, tz=timezone.utc)
    to_date = datetime.fromtimestamp(newest / 1_000_000_000, tz=timezone.utc)
    
    print(f"Transaction date range: {from_date.date()} to {to_date.date()}")
    
    # Fetch prices for key tokens
    for symbol in ['ETH', 'NEAR']:
        print(f"\n=== Fetching {symbol} prices ===")
        prices = fetch_historical_prices(symbol, from_date, to_date)
        
        if not prices:
            continue
        
        # Store in price_cache
        inserted = 0
        for date_str, price in prices.items():
            store_date = f"{date_str} 12:00"
            
            # Check if exists
            cur.execute('SELECT id FROM price_cache WHERE coin_id = ? AND date = ?', (symbol, store_date))
            if cur.fetchone():
                continue
            
            cur.execute('''
                INSERT INTO price_cache (coin_id, date, currency, price, fetched_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            ''', (symbol, store_date, 'USD', price))
            inserted += 1
        
        conn.commit()
        print(f"Inserted {inserted} new {symbol} price records")
        
        time.sleep(1)  # Rate limit courtesy
    
    # Also add common stablecoins
    for symbol in ['USDC', 'USDT', 'DAI']:
        print(f"\n=== Adding {symbol} (stablecoin = $1) ===")
        
        current = from_date
        inserted = 0
        while current <= to_date:
            date_str = current.strftime('%Y-%m-%d')
            store_date = f"{date_str} 12:00"
            
            cur.execute('SELECT id FROM price_cache WHERE coin_id = ? AND date = ?', (symbol, store_date))
            if not cur.fetchone():
                cur.execute('''
                    INSERT INTO price_cache (coin_id, date, currency, price, fetched_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                ''', (symbol, store_date, 'USD', 1.0))
                inserted += 1
            
            current += timedelta(days=1)
        
        conn.commit()
        print(f"Inserted {inserted} {symbol} price records ($1.00)")
    
    # Now apply prices to transactions
    print("\n=== Applying prices to transactions ===")
    apply_prices(conn, cur)
    
    conn.close()
    print("\nDone!")


def apply_prices(conn, cur):
    """Apply cached prices to transactions."""
    
    # Load all prices
    cur.execute('SELECT coin_id, date, price FROM price_cache')
    prices = {}
    for row in cur.fetchall():
        coin_id = row[0]
        date_str = row[1].split(' ')[0]
        price = row[2]
        if coin_id not in prices:
            prices[coin_id] = {}
        prices[coin_id][date_str] = price
    
    print(f"Loaded prices: {', '.join(f'{k}({len(v)})' for k, v in prices.items())}")
    
    # Get transactions without prices
    cur.execute('''
        SELECT id, block_timestamp, amount, asset
        FROM transactions
        WHERE (cost_basis_usd IS NULL OR cost_basis_usd = 0)
        AND block_timestamp > 1000000000000000
    ''')
    
    transactions = cur.fetchall()
    print(f"Found {len(transactions)} transactions to price")
    
    updated = 0
    for tx in transactions:
        tx_id, ts, amount, asset = tx
        
        if not ts or not amount:
            continue
        
        # Determine token symbol
        symbol = asset or 'NEAR'
        if symbol in ['gas', '']:
            symbol = 'ETH'  # Gas fees are in ETH
        
        # Normalize symbol
        symbol = symbol.upper()
        if symbol in ['WETH', 'ETHER']:
            symbol = 'ETH'
        if symbol in ['WNEAR', 'STNEAR', 'LINEAR']:
            symbol = 'NEAR'
        
        # Get price
        if symbol not in prices:
            continue
        
        dt = datetime.fromtimestamp(ts / 1_000_000_000, tz=timezone.utc)
        date_str = dt.strftime('%Y-%m-%d')
        year = dt.year
        
        price = prices[symbol].get(date_str)
        if not price:
            # Try nearby dates
            for delta in [-1, 1, -2, 2, -3, 3]:
                nearby = (dt + timedelta(days=delta)).strftime('%Y-%m-%d')
                price = prices[symbol].get(nearby)
                if price:
                    break
        
        if not price:
            continue
        
        # Calculate value
        cad_rate = CAD_RATES.get(year, 1.38)
        
        # Determine decimals based on token
        if symbol in ['ETH', 'DAI', 'USDC', 'USDT']:
            decimals = 18
        else:
            decimals = 24  # NEAR
        
        amount_tokens = float(amount) / (10 ** decimals)
        value_usd = amount_tokens * price
        value_cad = value_usd * cad_rate
        
        # Skip tiny amounts
        if abs(value_usd) < 0.001:
            continue
        
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
    backfill_prices(db_path)
