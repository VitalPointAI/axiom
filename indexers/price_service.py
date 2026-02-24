#!/usr/bin/env python3
"""Historical price service using CryptoCompare API."""

import time
import requests
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection

# CryptoCompare API (free tier)
CRYPTOCOMPARE_BASE = "https://min-api.cryptocompare.com/data/v2"

# Token symbol mapping
TOKEN_SYMBOLS = {
    "NEAR": "NEAR",
    "near": "NEAR",
    "wrap.near": "NEAR",  # wNEAR
    "ETH": "ETH",
    "USDC": "USDC",
    "USDT": "USDT",
}

# Price cache to avoid redundant API calls
_price_cache = {}


def get_hourly_price(token: str, timestamp_ns: int, currency: str = "USD") -> float | None:
    """
    Get the closing price of a token at a specific hour.
    
    Args:
        token: Token symbol (e.g., "NEAR", "ETH")
        timestamp_ns: Nanosecond timestamp from NEAR blockchain
        currency: Target currency (USD, CAD, etc.)
    
    Returns:
        Price in target currency, or None if not found
    """
    # Convert nanoseconds to seconds
    timestamp_sec = int(timestamp_ns) // 1_000_000_000 if timestamp_ns > 1e12 else int(timestamp_ns)
    
    # Round to hour boundary
    hour_ts = (timestamp_sec // 3600) * 3600
    
    # Map token to CryptoCompare symbol
    symbol = TOKEN_SYMBOLS.get(token, token.upper())
    
    # Check cache
    cache_key = f"{symbol}_{hour_ts}_{currency}"
    if cache_key in _price_cache:
        return _price_cache[cache_key]
    
    # Fetch from API - try hourly first, fall back to daily for old data
    try:
        # Try hourly data
        url = f"{CRYPTOCOMPARE_BASE}/histohour"
        params = {
            "fsym": symbol,
            "tsym": currency,
            "limit": 1,
            "toTs": hour_ts + 3600
        }
        
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("Response") == "Success":
            prices = data.get("Data", {}).get("Data", [])
            for p in reversed(prices):
                price = p.get("close")
                if price:
                    _price_cache[cache_key] = price
                    return price
        
        # Fall back to daily if hourly not available
        url = f"{CRYPTOCOMPARE_BASE}/histoday"
        day_ts = (timestamp_sec // 86400) * 86400
        params = {
            "fsym": symbol,
            "tsym": currency,
            "limit": 1,
            "toTs": day_ts + 86400
        }
        
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("Response") == "Success":
            prices = data.get("Data", {}).get("Data", [])
            for p in reversed(prices):
                price = p.get("close")
                if price:
                    _price_cache[cache_key] = price
                    return price
        
        return None
        
    except Exception as e:
        print(f"Error fetching price for {symbol} at {hour_ts}: {e}")
        return None


# Alias for backward compatibility
def get_daily_price(token: str, timestamp_ns: int, currency: str = "USD") -> float | None:
    """Alias for get_hourly_price (now uses hourly granularity)."""
    return get_hourly_price(token, timestamp_ns, currency)


def get_price_at_block(block_timestamp: int, token: str = "NEAR", currency: str = "USD") -> float | None:
    """Get price at a specific block timestamp."""
    return get_daily_price(token, block_timestamp, currency)


def add_cost_basis_column():
    """Add cost_basis_usd column to transactions table if not exists."""
    conn = get_connection()
    try:
        conn.execute("ALTER TABLE transactions ADD COLUMN cost_basis_usd REAL")
        conn.commit()
        print("Added cost_basis_usd column")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            pass  # Column already exists
        else:
            raise
    finally:
        conn.close()


def backfill_prices(batch_size: int = 100, delay: float = 0.15):
    """
    Backfill cost basis for all transactions missing prices.
    
    Uses hourly prices - price at the specific hour of transaction.
    """
    add_cost_basis_column()
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get transactions without cost basis
    cur.execute("""
        SELECT id, block_timestamp, amount, action_type
        FROM transactions 
        WHERE cost_basis_usd IS NULL 
        AND amount IS NOT NULL 
        AND CAST(amount AS INTEGER) > 0
        ORDER BY block_timestamp
    """)
    
    rows = cur.fetchall()
    total = len(rows)
    print(f"Backfilling prices for {total} transactions (hourly granularity)...")
    
    updated = 0
    last_hour = None
    last_price = None
    api_calls = 0
    
    for i, (tx_id, timestamp, amount, action_type) in enumerate(rows):
        # Convert amount from yoctoNEAR to NEAR
        try:
            near_amount = int(amount) / 1e24
        except (ValueError, TypeError):
            continue
        
        if near_amount <= 0:
            continue
        
        # Get hour boundary
        ts_sec = int(timestamp) // 1_000_000_000 if timestamp and int(timestamp) > 1e12 else (int(timestamp) if timestamp else 0)
        hour_ts = (ts_sec // 3600) * 3600
        
        # Reuse price for same hour
        if hour_ts == last_hour and last_price is not None:
            price = last_price
        else:
            price = get_hourly_price("NEAR", timestamp)
            last_hour = hour_ts
            last_price = price
            api_calls += 1
            if api_calls % 10 == 0:
                time.sleep(delay)  # Rate limit every 10 calls
        
        if price:
            cost_basis = near_amount * price
            conn.execute(
                "UPDATE transactions SET cost_basis_usd = ? WHERE id = ?",
                (cost_basis, tx_id)
            )
            updated += 1
        
        if (i + 1) % batch_size == 0:
            conn.commit()
            print(f"  Progress: {i+1}/{total} ({updated} priced, {api_calls} API calls)")
    
    conn.commit()
    conn.close()
    
    print(f"Done! Updated {updated}/{total} transactions with cost basis ({api_calls} API calls)")
    return updated


if __name__ == "__main__":
    # Test
    print("Testing price service...")
    
    # Test current price
    now = int(time.time())
    price = get_daily_price("NEAR", now * 1_000_000_000)
    print(f"NEAR price today: ${price}")
    
    # Test historical price (Jan 1, 2024)
    jan_2024 = 1704067200 * 1_000_000_000
    price = get_daily_price("NEAR", jan_2024)
    print(f"NEAR price Jan 1 2024: ${price}")
    
    # Backfill if run directly
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--backfill":
        backfill_prices()
