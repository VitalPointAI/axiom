#!/usr/bin/env python3
"""
Fetch NEAR prices from CoinGecko (more generous free tier).

CoinGecko free API: 10-30 calls/minute
"""

import sqlite3
import requests
from datetime import datetime, timezone, timedelta
import time
import sys

# CoinGecko API (no key needed for basic endpoints)
CG_API_URL = "https://api.coingecko.com/api/v3"

# NEAR coin ID on CoinGecko
NEAR_ID = "near"


def fetch_daily_prices(db_path: str = 'neartax.db', days: int = 365):
    """
    Fetch daily NEAR prices from CoinGecko.

    Free tier supports market_chart endpoint with up to 1 year of daily data.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Fetch market chart (daily prices)
    url = f"{CG_API_URL}/coins/{NEAR_ID}/market_chart"
    params = {
        'vs_currency': 'usd',
        'days': days,
        'interval': 'daily'
    }

    print(f"Fetching {days} days of NEAR prices from CoinGecko...")

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Error fetching prices: {e}")
        return 0

    prices = data.get('prices', [])
    print(f"Got {len(prices)} price points")

    # Store in price_cache
    inserted = 0
    for ts_ms, price in prices:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        date_str = dt.strftime('%Y-%m-%d 12:00')  # Use noon as daily representative

        # Check if exists
        cur.execute('SELECT id FROM price_cache WHERE coin_id = ? AND date = ?', ('NEAR', date_str))
        if cur.fetchone():
            continue

        cur.execute('''
            INSERT INTO price_cache (coin_id, date, currency, price, fetched_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        ''', ('NEAR', date_str, 'USD', price))
        inserted += 1

    conn.commit()
    print(f"Inserted {inserted} new price records")

    # Now fetch older prices year by year using historical endpoint
    # Get the oldest transaction date
    cur.execute('SELECT MIN(block_timestamp) FROM transactions WHERE block_timestamp IS NOT NULL')
    oldest = cur.fetchone()[0]

    if oldest:
        oldest_date = datetime.fromtimestamp(oldest / 1_000_000_000, tz=timezone.utc).date()
        today = datetime.now(timezone.utc).date()
        one_year_ago = today - timedelta(days=365)

        if oldest_date < one_year_ago:
            print(f"\nNeed older prices from {oldest_date} to {one_year_ago}")
            print("Fetching historical prices (rate limited)...")

            # Fetch daily historical prices (10 calls/min limit)
            current_date = one_year_ago
            calls = 0

            while current_date > oldest_date and calls < 60:  # Limit to 60 calls
                date_str = current_date.strftime('%d-%m-%Y')

                try:
                    url = f"{CG_API_URL}/coins/{NEAR_ID}/history"
                    params = {'date': date_str}
                    resp = requests.get(url, params=params, timeout=30)

                    if resp.status_code == 429:
                        print("Rate limited, waiting 60s...")
                        time.sleep(60)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                    market_data = data.get('market_data', {})
                    price = market_data.get('current_price', {}).get('usd')

                    if price:
                        store_date = current_date.strftime('%Y-%m-%d 12:00')
                        cur.execute('''
                            INSERT OR REPLACE INTO price_cache (coin_id, date, currency, price, fetched_at)
                            VALUES (?, ?, ?, ?, datetime('now'))
                        ''', ('NEAR', store_date, 'USD', price))
                        inserted += 1

                        if calls % 10 == 0:
                            print(f"  {current_date}: ${price:.4f}")
                            conn.commit()

                except Exception as e:
                    print(f"Error for {current_date}: {e}")

                calls += 1
                current_date -= timedelta(days=7)  # Sample weekly to reduce API calls
                time.sleep(6)  # Stay under rate limit

            conn.commit()

    conn.close()
    return inserted


def apply_prices_to_transactions(db_path: str = 'neartax.db'):
    """Apply cached prices to transactions."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Load all prices
    cur.execute('SELECT date, price FROM price_cache WHERE coin_id = ?', ('NEAR',))
    prices = {}
    for row in cur.fetchall():
        try:
            # Parse date string
            date_str = row['date'].split(' ')[0]  # Just the date part
            prices[date_str] = row['price']
        except Exception:
            pass

    print(f"Loaded {len(prices)} daily prices")

    # Get transactions without prices
    cur.execute('''
        SELECT id, block_timestamp, amount
        FROM transactions
        WHERE (cost_basis_usd IS NULL OR cost_basis_usd = 0)
        AND block_timestamp IS NOT NULL
        AND CAST(amount AS REAL) > 0
    ''')

    transactions = cur.fetchall()
    print(f"Found {len(transactions)} transactions to price")

    updated = 0
    cad_rate = 1.38

    for tx in transactions:
        ts = tx['block_timestamp']
        if not ts:
            continue

        dt = datetime.fromtimestamp(ts / 1_000_000_000, tz=timezone.utc)
        date_str = dt.strftime('%Y-%m-%d')

        price = prices.get(date_str)
        if not price:
            # Try nearby dates
            for delta in [-1, 1, -2, 2, -3, 3]:
                nearby = (dt + timedelta(days=delta)).strftime('%Y-%m-%d')
                price = prices.get(nearby)
                if price:
                    break

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

    conn.commit()
    conn.close()

    print(f"Updated {updated} transactions")
    return updated


if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'neartax.db'

    print("=== Fetching NEAR prices from CoinGecko ===\n")
    fetch_daily_prices(db_path, days=365)

    print("\n=== Applying prices to transactions ===\n")
    updated = apply_prices_to_transactions(db_path)

    print(f"\nDone! Updated {updated} transactions with prices")
