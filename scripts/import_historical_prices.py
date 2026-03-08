#!/usr/bin/env python3
"""
Import historical NEAR prices from CSV or fetch from alternative sources.

Sources:
1. CSV file with columns: date,price
2. Messari API (free tier)
3. NEAR Protocol historical data
"""

import sqlite3
import requests
from datetime import datetime, timezone, timedelta
import csv
import sys
import time

def import_from_csv(db_path: str, csv_path: str):
    """Import prices from a CSV file with columns: date,price"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        inserted = 0
        
        for row in reader:
            date_str = row.get('date', row.get('Date', ''))
            price = float(row.get('price', row.get('Price', row.get('close', row.get('Close', 0)))))
            
            if not date_str or not price:
                continue
            
            # Normalize date format
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
            except:
                try:
                    dt = datetime.strptime(date_str, '%m/%d/%Y')
                except:
                    continue
            
            store_date = f"{dt.strftime('%Y-%m-%d')} 12:00"
            
            cur.execute('SELECT id FROM price_cache WHERE coin_id = ? AND date = ?', ('NEAR', store_date))
            if not cur.fetchone():
                cur.execute('''
                    INSERT INTO price_cache (coin_id, date, currency, price, fetched_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                ''', ('NEAR', store_date, 'USD', price))
                inserted += 1
        
        conn.commit()
        print(f"Imported {inserted} prices from CSV")
    
    conn.close()


def fetch_from_messari(db_path: str):
    """Fetch historical prices from Messari API (no key required for basic data)"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Messari provides NEAR data from launch
    url = "https://data.messari.io/api/v1/assets/near-protocol/metrics/price/time-series"
    
    # Get oldest date we need
    cur.execute('''
        SELECT MIN(datetime(block_timestamp/1000000000, 'unixepoch'))
        FROM transactions
        WHERE block_timestamp IS NOT NULL
    ''')
    oldest = cur.fetchone()[0]
    print(f"Oldest transaction: {oldest}")
    
    # Fetch price data
    params = {
        'start': '2020-09-01',  # NEAR launch
        'end': '2025-02-23',
        'interval': '1d'
    }
    
    try:
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            values = data.get('data', {}).get('values', [])
            print(f"Got {len(values)} price points from Messari")
            
            inserted = 0
            for val in values:
                # Format: [timestamp_ms, open, high, low, close, volume]
                ts = val[0] / 1000
                close = val[4]
                
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                store_date = f"{dt.strftime('%Y-%m-%d')} 12:00"
                
                cur.execute('SELECT id FROM price_cache WHERE coin_id = ? AND date = ?', ('NEAR', store_date))
                if not cur.fetchone():
                    cur.execute('''
                        INSERT INTO price_cache (coin_id, date, currency, price, fetched_at)
                        VALUES (?, ?, ?, ?, datetime('now'))
                    ''', ('NEAR', store_date, 'USD', close))
                    inserted += 1
            
            conn.commit()
            print(f"Inserted {inserted} new prices from Messari")
        else:
            print(f"Messari API error: {resp.status_code}")
            print(resp.text[:200])
    except Exception as e:
        print(f"Error fetching from Messari: {e}")
    
    conn.close()


def apply_prices_to_transactions(db_path: str):
    """Apply cached prices to all unpriced transactions"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Load prices
    cur.execute('SELECT date, price FROM price_cache WHERE coin_id = ?', ('NEAR',))
    prices = {row['date'].split(' ')[0]: row['price'] for row in cur.fetchall()}
    print(f"Loaded {len(prices)} prices")
    
    # Get unpriced transactions with historical_needed
    cur.execute('''
        SELECT id, block_timestamp, amount
        FROM transactions
        WHERE price_warning = 'historical_needed'
        AND CAST(amount AS REAL) > 0
    ''')
    
    transactions = cur.fetchall()
    print(f"Found {len(transactions)} transactions needing prices")
    
    updated = 0
    cad = 1.38
    
    for tx in transactions:
        dt = datetime.fromtimestamp(tx['block_timestamp'] / 1e9, tz=timezone.utc)
        date_str = dt.strftime('%Y-%m-%d')
        
        price = prices.get(date_str)
        if not price:
            for d in [1, -1, 2, -2, 3, -3, 7, -7]:
                nd = (dt + timedelta(days=d)).strftime('%Y-%m-%d')
                if nd in prices:
                    price = prices[nd]
                    break
        
        if price:
            near = float(tx['amount']) / 1e24
            usd = near * price
            cur.execute('''
                UPDATE transactions 
                SET cost_basis_usd = ?, cost_basis_cad = ?, price_resolved = 1, price_warning = NULL
                WHERE id = ?
            ''', (usd, usd * cad, tx['id']))
            updated += 1
    
    conn.commit()
    print(f"Updated {updated} transactions")
    conn.close()


if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'neartax.db'
    
    if len(sys.argv) > 2 and sys.argv[2].endswith('.csv'):
        # Import from CSV
        import_from_csv(db_path, sys.argv[2])
    else:
        # Try Messari API
        print("Fetching from Messari API...")
        fetch_from_messari(db_path)
    
    # Apply to transactions
    print("\nApplying prices to transactions...")
    apply_prices_to_transactions(db_path)
