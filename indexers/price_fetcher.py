#!/usr/bin/env python3
"""Historical price fetcher using CoinGecko API."""

import requests
import time
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection

# CoinGecko coin IDs
COIN_IDS = {
    'NEAR': 'near',
    'ETH': 'ethereum',
    'MATIC': 'matic-network',
    'BTC': 'bitcoin',
    'USDC': 'usd-coin',
    'USDT': 'tether',
}

# Rate limit: 10-30 requests/minute for free tier
REQUEST_DELAY = 6  # seconds between requests


def get_cached_price(asset: str, date: str) -> float | None:
    """Get price from cache."""
    conn = get_connection()
    row = conn.execute("""
        SELECT price_usd FROM price_cache
        WHERE asset = ? AND date = ?
    """, (asset, date)).fetchone()
    conn.close()
    return row[0] if row else None


def cache_price(asset: str, date: str, price: float):
    """Store price in cache."""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO price_cache (asset, date, price_usd)
        VALUES (?, ?, ?)
    """, (asset, date, price))
    conn.commit()
    conn.close()


def fetch_historical_price(asset: str, timestamp_ns: int) -> float:
    """
    Fetch historical price from CoinGecko.

    Args:
        asset: Asset symbol (NEAR, ETH, etc.)
        timestamp_ns: Unix timestamp in nanoseconds

    Returns:
        Price in USD
    """
    # Convert ns to date string
    timestamp_s = timestamp_ns / 1e9
    dt = datetime.utcfromtimestamp(timestamp_s)
    date_str = dt.strftime('%Y-%m-%d')

    # Check cache first
    cached = get_cached_price(asset, date_str)
    if cached is not None:
        return cached

    # Get CoinGecko ID
    coin_id = COIN_IDS.get(asset.upper())
    if not coin_id:
        print(f"Unknown asset: {asset}")
        return 0.0

    # Fetch from CoinGecko
    date_dmy = dt.strftime('%d-%m-%Y')  # CoinGecko format
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/history?date={date_dmy}"

    try:
        time.sleep(REQUEST_DELAY)  # Rate limiting
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        price = data.get('market_data', {}).get('current_price', {}).get('usd', 0)

        if price:
            cache_price(asset, date_str, price)
            print(f"  {asset} on {date_str}: ${price:.4f}")

        return price
    except Exception as e:
        print(f"  Error fetching {asset} price for {date_str}: {e}")
        return 0.0


def get_current_price(asset: str) -> float:
    """Get current price from CoinGecko."""
    coin_id = COIN_IDS.get(asset.upper())
    if not coin_id:
        return 0.0

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get(coin_id, {}).get('usd', 0)
    except Exception as e:
        print(f"Error fetching current {asset} price: {e}")
        return 0.0


def backfill_transaction_prices():
    """Backfill prices for all transactions missing price data."""
    conn = get_connection()

    # Get transactions needing prices (NEAR transactions)
    txs = conn.execute("""
        SELECT DISTINCT block_timestamp
        FROM transactions
        WHERE block_timestamp IS NOT NULL
        ORDER BY block_timestamp
    """).fetchall()

    print(f"Found {len(txs)} unique timestamps to price")

    for i, (timestamp,) in enumerate(txs):
        if i % 100 == 0:
            print(f"Progress: {i}/{len(txs)}")

        # Just cache the price - we'll use it later
        fetch_historical_price('NEAR', timestamp)

    conn.close()
    print("Done!")


if __name__ == '__main__':
    # Test current prices
    print("Current prices:")
    for asset in ['NEAR', 'ETH', 'BTC']:
        price = get_current_price(asset)
        print(f"  {asset}: ${price:.2f}")

    # Backfill if requested
    if len(sys.argv) > 1 and sys.argv[1] == '--backfill':
        print("\nBackfilling historical prices...")
        backfill_transaction_prices()
