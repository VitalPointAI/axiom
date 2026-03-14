#!/usr/bin/env python3
"""
Fetch historical prices and update transactions with cost basis.

Uses CryptoCompare API for NEAR prices.
"""

import sqlite3
import requests
from datetime import datetime, timezone
import time
from typing import Dict
import sys

# CryptoCompare API
CC_API_URL = "https://min-api.cryptocompare.com/data/v2/histohour"

def fetch_near_prices(db_path: str = 'neartax.db') -> Dict[str, float]:
    """Fetch NEAR hourly prices for all dates we need."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get date range from transactions
    cur.execute('''
        SELECT MIN(block_timestamp), MAX(block_timestamp)
        FROM transactions
        WHERE block_timestamp IS NOT NULL
    ''')
    min_ts, max_ts = cur.fetchone()

    if not min_ts or not max_ts:
        print("No transactions found")
        return {}

    min_date = datetime.fromtimestamp(min_ts / 1_000_000_000, tz=timezone.utc)
    max_date = datetime.fromtimestamp(max_ts / 1_000_000_000, tz=timezone.utc)

    print(f"Date range: {min_date.date()} to {max_date.date()}")

    # Fetch prices in chunks (2000 hours = ~83 days per call)
    prices: Dict[str, float] = {}
    current_ts = int(max_date.timestamp())
    end_ts = int(min_date.timestamp())

    while current_ts > end_ts:
        try:
            print(f"Fetching prices before {datetime.fromtimestamp(current_ts, tz=timezone.utc).date()}...")

            params = {
                'fsym': 'NEAR',
                'tsym': 'USD',
                'limit': 2000,
                'toTs': current_ts
            }
            resp = requests.get(CC_API_URL, params=params, timeout=30)
            data = resp.json()

            if data.get('Response') != 'Success':
                print(f"API error: {data.get('Message', 'Unknown error')}")
                break

            price_data = data.get('Data', {}).get('Data', [])
            if not price_data:
                break

            for p in price_data:
                ts = p.get('time')
                price = p.get('close', 0)
                if ts and price > 0:
                    # Store by hour timestamp
                    prices[str(ts)] = price

            # Move to earlier chunk
            earliest_ts = min(p.get('time', current_ts) for p in price_data)
            current_ts = earliest_ts - 3600

            # Rate limit
            time.sleep(0.5)

        except Exception as e:
            print(f"Error fetching prices: {e}")
            break

    print(f"Fetched {len(prices)} hourly prices")

    # Store in price_cache
    cur.execute('DELETE FROM price_cache WHERE coin_id = ?', ('NEAR',))

    for ts_str, price in prices.items():
        ts = int(ts_str)
        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:00')
        cur.execute('''
            INSERT INTO price_cache (coin_id, date, currency, price, fetched_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        ''', ('NEAR', date_str, 'USD', price))

    conn.commit()
    conn.close()

    return prices


def update_transaction_prices(db_path: str = 'neartax.db'):
    """Update transaction cost basis using cached prices."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Load prices into memory for fast lookup
    cur.execute('SELECT date, price FROM price_cache WHERE coin_id = ?', ('NEAR',))
    prices = {}
    for row in cur.fetchall():
        # Parse date and convert to hour timestamp
        try:
            dt = datetime.strptime(row['date'], '%Y-%m-%d %H:%M')
            hour_ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
            prices[hour_ts] = row['price']
        except Exception:
            pass

    print(f"Loaded {len(prices)} prices into memory")

    # Get transactions needing prices
    cur.execute('''
        SELECT id, block_timestamp, amount, direction
        FROM transactions
        WHERE (cost_basis_usd IS NULL OR cost_basis_usd = 0)
        AND block_timestamp IS NOT NULL
        AND CAST(amount AS REAL) > 0
    ''')

    transactions = cur.fetchall()
    print(f"Found {len(transactions)} transactions needing prices")

    updated = 0
    cad_rate = 1.38  # Approximate USD/CAD rate

    for tx in transactions:
        ts = tx['block_timestamp']
        if not ts:
            continue

        # Round to hour
        ts_sec = ts // 1_000_000_000
        hour_ts = (ts_sec // 3600) * 3600

        # Try this hour and nearby hours
        price = prices.get(hour_ts)
        if not price:
            price = prices.get(hour_ts - 3600)
        if not price:
            price = prices.get(hour_ts + 3600)

        if not price:
            continue

        amount_near = float(tx['amount']) / 1e24
        value_usd = amount_near * price
        value_cad = value_usd * cad_rate

        cur.execute('''
            UPDATE transactions
            SET cost_basis_usd = ?,
                cost_basis_cad = ?,
                price_warning = NULL,
                price_resolved = 1
            WHERE id = ?
        ''', (value_usd, value_cad, tx['id']))

        updated += 1

        if updated % 500 == 0:
            print(f"Updated {updated} transactions...")
            conn.commit()

    conn.commit()
    conn.close()

    print(f"Total updated: {updated}")
    return updated


if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'neartax.db'

    print("=== Fetching NEAR prices ===")
    prices = fetch_near_prices(db_path)

    if prices:
        print("\n=== Updating transaction prices ===")
        updated = update_transaction_prices(db_path)
        print(f"\nDone! Updated {updated} transactions")
    else:
        print("No prices fetched - check API connection")
