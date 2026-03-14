#!/usr/bin/env python3
"""
Historical price fetcher for FMV calculations.

Uses CoinGecko API for prices.
NOTE: Historical prices require CoinGecko API key (free plan available).
      Current prices work without key.

Caches prices to reduce API calls.
"""

import time
import requests
from datetime import datetime
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DATABASE_PATH

# CoinGecko API (free tier, no API key needed)
COINGECKO_API = "https://api.coingecko.com/api/v3"

# Rate limit: 10-50 calls/minute for free tier
RATE_LIMIT_DELAY = 1.5

# Coin ID mappings
COIN_IDS = {
    "NEAR": "near",
    "ETH": "ethereum",
    "BTC": "bitcoin",
    "MATIC": "matic-network",
    "OP": "optimism",
    "USDT": "tether",
    "USDC": "usd-coin",
    "DAI": "dai",
}


class PriceFetcher:
    """Fetch and cache historical prices."""

    def __init__(self, currency="cad"):
        self.currency = currency.lower()
        self.last_request = 0
        self._init_cache()

    def _init_cache(self):
        """Initialize price cache table."""
        db_path = Path(PROJECT_ROOT) / DATABASE_PATH
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin_id TEXT NOT NULL,
                date TEXT NOT NULL,
                currency TEXT NOT NULL,
                price REAL NOT NULL,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(coin_id, date, currency)
            )
        """)
        conn.commit()
        conn.close()

    def _wait_rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request = time.time()

    def _get_cached_price(self, coin_id, date_str):
        """Check cache for price."""
        db_path = Path(PROJECT_ROOT) / DATABASE_PATH
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT price FROM price_cache WHERE coin_id = ? AND date = ? AND currency = ?",
            (coin_id, date_str, self.currency)
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def _cache_price(self, coin_id, date_str, price):
        """Cache a price."""
        db_path = Path(PROJECT_ROOT) / DATABASE_PATH
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT OR REPLACE INTO price_cache (coin_id, date, currency, price) VALUES (?, ?, ?, ?)",
            (coin_id, date_str, self.currency, price)
        )
        conn.commit()
        conn.close()

    def get_historical_price(self, symbol, date):
        """
        Get historical price for a coin on a specific date.

        Args:
            symbol: Coin symbol (e.g., "NEAR", "ETH")
            date: datetime object or string (YYYY-MM-DD)

        Returns:
            Price in configured currency, or None if not found
        """
        # Normalize inputs
        symbol = symbol.upper()
        if isinstance(date, datetime):
            date_str = date.strftime("%Y-%m-%d")
            date_api = date.strftime("%d-%m-%Y")  # CoinGecko format
        else:
            date_str = date
            date_api = datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")

        # Get coin ID
        coin_id = COIN_IDS.get(symbol)
        if not coin_id:
            print(f"  Unknown coin: {symbol}")
            return None

        # Check cache
        cached = self._get_cached_price(coin_id, date_str)
        if cached is not None:
            return cached

        # Fetch from API
        self._wait_rate_limit()

        try:
            url = f"{COINGECKO_API}/coins/{coin_id}/history"
            params = {"date": date_api, "localization": "false"}
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 429:
                print("  Rate limited, waiting...")
                time.sleep(60)
                return self.get_historical_price(symbol, date)

            response.raise_for_status()
            data = response.json()

            market_data = data.get("market_data", {})
            current_price = market_data.get("current_price", {})
            price = current_price.get(self.currency)

            if price:
                self._cache_price(coin_id, date_str, price)
                return price

        except Exception as e:
            print(f"  Error fetching price for {symbol} on {date_str}: {e}")

        return None

    def get_current_price(self, symbol):
        """Get current price for a coin."""
        symbol = symbol.upper()
        coin_id = COIN_IDS.get(symbol)
        if not coin_id:
            return None

        self._wait_rate_limit()

        try:
            url = f"{COINGECKO_API}/simple/price"
            params = {"ids": coin_id, "vs_currencies": self.currency}
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            return data.get(coin_id, {}).get(self.currency)
        except Exception as e:
            print(f"  Error fetching current price for {symbol}: {e}")
            return None


def get_fmv(symbol, date, currency="cad"):
    """
    Convenience function to get Fair Market Value.

    Args:
        symbol: Coin symbol
        date: Date (datetime or string)
        currency: Target currency (default CAD for Canada)

    Returns:
        FMV in target currency
    """
    fetcher = PriceFetcher(currency)
    return fetcher.get_historical_price(symbol, date)


if __name__ == "__main__":
    fetcher = PriceFetcher("cad")

    # Test current price
    print("Current NEAR price (CAD):", fetcher.get_current_price("NEAR"))

    # Test historical price
    test_date = "2024-01-15"
    print(f"NEAR price on {test_date} (CAD):", fetcher.get_historical_price("NEAR", test_date))
