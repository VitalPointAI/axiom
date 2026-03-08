#!/usr/bin/env python3
"""
Historical Price Service for NearTax

Fetches historical prices for NEAR and other tokens using multiple sources:
1. CryptoCompare (primary for major tokens)
2. CoinGecko (backup)
3. Ref Finance (for NEAR ecosystem tokens)
4. DeFiLlama (for DeFi tokens)

Caches prices to SQLite to avoid repeated API calls.

Usage:
    python3 historical_price_service.py [db_path]
"""

import sqlite3
import requests
import json
import time
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
import sys

# API endpoints
CRYPTOCOMPARE_API = "https://min-api.cryptocompare.com/data"
COINGECKO_API = "https://api.coingecko.com/api/v3"
REF_INDEXER = "https://indexer.ref.finance"

# Rate limiting
CRYPTOCOMPARE_RATE_LIMIT = 0.1  # 10 calls per second max
COINGECKO_RATE_LIMIT = 0.5  # 2 calls per second (free tier)

# Bank of Canada API for CAD/USD rates
BOC_API = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD"

# Token symbol mappings for CryptoCompare
CC_SYMBOL_MAP = {
    "NEAR": "NEAR",
    "ETH": "ETH",
    "BTC": "BTC",
    "USDC": "USDC",
    "USDT": "USDT",
    "DAI": "DAI",
    "AURORA": "AURORA",
    "wNEAR": "NEAR",  # wNEAR = NEAR
    "STNEAR": "NEAR",  # stNEAR ≈ NEAR
    "LINEAR": "NEAR",  # LINEAR ≈ NEAR (liquid staking)
}

# CoinGecko ID mappings
CG_ID_MAP = {
    "NEAR": "near",
    "ETH": "ethereum",
    "BTC": "bitcoin",
    "USDC": "usd-coin",
    "USDT": "tether",
    "DAI": "dai",
    "AURORA": "aurora-near",
    "REF": "ref-finance",
    "PARAS": "paras",
    "OCT": "octopus-network",
    "SWEAT": "sweatcoin",
}

# Stablecoins (always $1)
STABLECOINS = {"USDC", "USDT", "DAI", "USN", "USDC.e", "USDT.e"}


class PriceCache:
    """SQLite-backed price cache - uses existing price_cache table schema"""
    
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        # Use existing table schema: coin_id, date, currency, price
    
    def get(self, symbol: str, date: str) -> Optional[float]:
        """Get cached price for symbol on date (YYYY-MM-DD)"""
        cur = self.conn.execute(
            "SELECT price FROM price_cache WHERE coin_id = ? AND date = ? AND currency = 'USD'",
            (symbol.upper(), date)
        )
        row = cur.fetchone()
        return row[0] if row else None
    
    def set(self, symbol: str, date: str, price: float, source: str = "unknown"):
        """Cache price for symbol on date"""
        self.conn.execute("""
            INSERT OR REPLACE INTO price_cache (coin_id, date, currency, price)
            VALUES (?, ?, 'USD', ?)
        """, (symbol.upper(), date, price))
        self.conn.commit()
    
    def get_cached_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM price_cache WHERE currency = 'USD'")
        return cur.fetchone()[0]


class HistoricalPriceService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.cache = PriceCache(db_path)
        self.last_api_call = 0
        
        # Track API calls for rate limiting
        self.cc_calls = 0
        self.cg_calls = 0
    
    def _rate_limit(self, delay: float):
        """Enforce rate limiting between API calls"""
        elapsed = time.time() - self.last_api_call
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self.last_api_call = time.time()
    
    def get_price_cryptocompare(self, symbol: str, date: str) -> Optional[float]:
        """Get historical price from CryptoCompare"""
        cc_symbol = CC_SYMBOL_MAP.get(symbol.upper(), symbol.upper())
        
        # Parse date to timestamp
        dt = datetime.strptime(date, "%Y-%m-%d")
        timestamp = int(dt.replace(tzinfo=timezone.utc).timestamp())
        
        self._rate_limit(CRYPTOCOMPARE_RATE_LIMIT)
        
        url = f"{CRYPTOCOMPARE_API}/pricehistorical"
        params = {
            "fsym": cc_symbol,
            "tsyms": "USD",
            "ts": timestamp
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            self.cc_calls += 1
            
            if resp.status_code == 200:
                data = resp.json()
                price = data.get(cc_symbol, {}).get("USD")
                if price and price > 0:
                    return float(price)
        except Exception as e:
            pass
        
        return None
    
    def get_price_coingecko(self, symbol: str, date: str) -> Optional[float]:
        """Get historical price from CoinGecko"""
        cg_id = CG_ID_MAP.get(symbol.upper())
        if not cg_id:
            return None
        
        # CoinGecko date format: DD-MM-YYYY
        dt = datetime.strptime(date, "%Y-%m-%d")
        cg_date = dt.strftime("%d-%m-%Y")
        
        self._rate_limit(COINGECKO_RATE_LIMIT)
        
        url = f"{COINGECKO_API}/coins/{cg_id}/history"
        params = {"date": cg_date}
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            self.cg_calls += 1
            
            if resp.status_code == 200:
                data = resp.json()
                price = data.get("market_data", {}).get("current_price", {}).get("usd")
                if price and price > 0:
                    return float(price)
        except Exception as e:
            pass
        
        return None
    
    def get_price(self, symbol: str, date: str) -> Optional[Tuple[float, str]]:
        """
        Get historical price for symbol on date.
        Returns (price_usd, source) or None.
        """
        symbol = symbol.upper()
        
        # Stablecoins = $1
        if symbol in STABLECOINS:
            return (1.0, "stablecoin")
        
        # Check cache first
        cached = self.cache.get(symbol, date)
        if cached is not None:
            return (cached, "cache")
        
        # Try CryptoCompare
        price = self.get_price_cryptocompare(symbol, date)
        if price:
            self.cache.set(symbol, date, price, "cryptocompare")
            return (price, "cryptocompare")
        
        # Try CoinGecko as fallback
        price = self.get_price_coingecko(symbol, date)
        if price:
            self.cache.set(symbol, date, price, "coingecko")
            return (price, "coingecko")
        
        return None
    
    def get_near_price(self, date: str) -> Optional[float]:
        """Get NEAR price for a specific date"""
        result = self.get_price("NEAR", date)
        return result[0] if result else None
    
    def batch_get_near_prices(self, dates: List[str]) -> Dict[str, float]:
        """Get NEAR prices for multiple dates efficiently"""
        prices = {}
        unique_dates = sorted(set(dates))
        
        print(f"Fetching NEAR prices for {len(unique_dates)} unique dates...")
        
        for i, date in enumerate(unique_dates):
            result = self.get_price("NEAR", date)
            if result:
                prices[date] = result[0]
            
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(unique_dates)} dates...")
        
        print(f"Got {len(prices)} NEAR prices")
        return prices
    
    def get_cad_rate(self, date: str) -> float:
        """Get CAD/USD exchange rate for date"""
        # Check cache first
        cached = self.cache.get("CADUSD", date)
        if cached:
            return cached
        
        # Fetch from Bank of Canada
        try:
            url = f"{BOC_API}/json"
            params = {
                "start_date": date,
                "end_date": date
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                obs = data.get("observations", [])
                if obs:
                    rate = float(obs[0].get("FXUSDCAD", {}).get("v", 1.35))
                    self.cache.set("CADUSD", date, rate, "boc")
                    return rate
        except Exception:
            pass
        
        return 1.35  # Default fallback
    
    def batch_get_cad_rates(self, dates: List[str]) -> Dict[str, float]:
        """Get CAD rates for multiple dates efficiently"""
        rates = {}
        unique_dates = sorted(set(dates))
        
        # Try to get rates in bulk from Bank of Canada
        if unique_dates:
            try:
                url = f"{BOC_API}/json"
                params = {
                    "start_date": unique_dates[0],
                    "end_date": unique_dates[-1]
                }
                resp = requests.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    for obs in data.get("observations", []):
                        date = obs.get("d")
                        rate = obs.get("FXUSDCAD", {}).get("v")
                        if date and rate:
                            rates[date] = float(rate)
                            self.cache.set("CADUSD", date, float(rate), "boc")
                    print(f"Got {len(rates)} CAD/USD rates from Bank of Canada")
            except Exception as e:
                print(f"Warning: Could not fetch CAD rates: {e}")
        
        # Fill gaps with cached or default
        for date in unique_dates:
            if date not in rates:
                cached = self.cache.get("CADUSD", date)
                if cached:
                    rates[date] = cached
                else:
                    rates[date] = 1.35  # Default
        
        return rates


def price_near_transactions(db_path: str):
    """Price all NEAR transactions that need cost basis"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    service = HistoricalPriceService(db_path)
    
    # Get all dates needing prices
    cur.execute("""
        SELECT DISTINCT date(datetime(block_timestamp/1000000000, 'unixepoch')) as tx_date
        FROM transactions
        WHERE (cost_basis_usd IS NULL OR cost_basis_usd = 0)
        AND block_timestamp IS NOT NULL
        ORDER BY tx_date
    """)
    dates = [row[0] for row in cur.fetchall() if row[0]]
    
    print(f"Found {len(dates)} unique dates needing NEAR prices")
    
    # Batch fetch prices and CAD rates
    prices = service.batch_get_near_prices(dates)
    cad_rates = service.batch_get_cad_rates(dates)
    
    # Update transactions
    print("\nUpdating transaction cost basis...")
    
    cur.execute("""
        SELECT id, amount, block_timestamp
        FROM transactions
        WHERE (cost_basis_usd IS NULL OR cost_basis_usd = 0)
        AND block_timestamp IS NOT NULL
        AND amount IS NOT NULL
    """)
    
    updated = 0
    for row in cur.fetchall():
        tx_id = row["id"]
        amount_raw = row["amount"]
        timestamp = row["block_timestamp"]
        
        # Parse date
        try:
            dt = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
        except:
            continue
        
        price = prices.get(date_str)
        if not price:
            continue
        
        cad_rate = cad_rates.get(date_str, 1.35)
        
        # Calculate cost basis
        try:
            # NEAR amounts are in yoctoNEAR (10^24)
            amount_near = float(amount_raw) / 1e24
            cost_basis_usd = amount_near * price
            cost_basis_cad = cost_basis_usd * cad_rate
            
            conn.execute("""
                UPDATE transactions
                SET cost_basis_usd = ?, cost_basis_cad = ?
                WHERE id = ?
            """, (cost_basis_usd, cost_basis_cad, tx_id))
            
            updated += 1
            
            if updated % 500 == 0:
                print(f"  Updated {updated} transactions...")
                conn.commit()
        except Exception as e:
            pass
    
    conn.commit()
    print(f"\nSuccessfully updated {updated} NEAR transactions")
    print(f"API calls: CryptoCompare={service.cc_calls}, CoinGecko={service.cg_calls}")
    print(f"Price cache now has {service.cache.get_cached_count()} entries")
    
    return updated


def price_ft_transactions(db_path: str):
    """Price FT transactions that are still missing prices"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    service = HistoricalPriceService(db_path)
    
    # Get all dates needing CAD rates first
    cur.execute("""
        SELECT DISTINCT date(datetime(block_timestamp/1000000000, 'unixepoch')) as tx_date
        FROM ft_transactions
        WHERE (price_usd IS NULL OR price_usd = 0)
        AND block_timestamp IS NOT NULL
        ORDER BY tx_date
    """)
    all_dates = [row[0] for row in cur.fetchall() if row[0]]
    cad_rates = service.batch_get_cad_rates(all_dates)
    
    # Get tokens needing prices
    cur.execute("""
        SELECT DISTINCT token_symbol, 
            date(datetime(block_timestamp/1000000000, 'unixepoch')) as tx_date
        FROM ft_transactions
        WHERE (price_usd IS NULL OR price_usd = 0)
        AND token_symbol IS NOT NULL
        AND block_timestamp IS NOT NULL
        ORDER BY token_symbol, tx_date
    """)
    
    token_dates = {}
    for row in cur.fetchall():
        symbol = row[0]
        date = row[1]
        if symbol not in token_dates:
            token_dates[symbol] = []
        token_dates[symbol].append(date)
    
    print(f"Found {len(token_dates)} tokens needing prices")
    
    # Price each token
    updated = 0
    for symbol, dates in token_dates.items():
        print(f"\nProcessing {symbol} ({len(dates)} dates)...")
        
        # Get prices for this token
        prices = {}
        for date in set(dates):
            result = service.get_price(symbol, date)
            if result:
                prices[date] = result[0]
        
        if not prices:
            # Try using NEAR price as proxy for NEAR-related tokens
            if symbol in ["STNEAR", "LINEAR", "wNEAR", "rNEAR"]:
                print(f"  Using NEAR price as proxy for {symbol}")
                for date in set(dates):
                    near_price = service.get_near_price(date)
                    if near_price:
                        prices[date] = near_price
        
        if not prices:
            print(f"  No prices found for {symbol}")
            continue
        
        print(f"  Got {len(prices)} prices for {symbol}")
        
        # Update transactions
        cur.execute("""
            SELECT id, amount, block_timestamp, token_contract
            FROM ft_transactions
            WHERE token_symbol = ?
            AND (price_usd IS NULL OR price_usd = 0)
        """, (symbol,))
        
        for row in cur.fetchall():
            tx_id = row["id"]
            amount_raw = row["amount"]
            timestamp = row["block_timestamp"]
            contract = row["token_contract"]
            
            try:
                dt = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=timezone.utc)
                date_str = dt.strftime("%Y-%m-%d")
            except:
                continue
            
            price = prices.get(date_str)
            if not price:
                continue
            
            cad_rate = cad_rates.get(date_str, 1.35)
            
            # Determine decimals based on token
            decimals = 24  # Default for NEAR ecosystem
            if contract == "17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1":
                decimals = 6  # USDC
            elif contract and contract.endswith(".factory.bridge.near"):
                decimals = 18  # Most bridged tokens
            elif symbol in ["USDC", "USDT"]:
                decimals = 6
            
            try:
                amount_decimal = float(amount_raw) / (10 ** decimals)
                value_usd = amount_decimal * price
                value_cad = value_usd * cad_rate
                
                conn.execute("""
                    UPDATE ft_transactions
                    SET price_usd = ?, value_usd = ?, value_cad = ?
                    WHERE id = ?
                """, (price, value_usd, value_cad, tx_id))
                
                updated += 1
            except Exception as e:
                pass
        
        conn.commit()
    
    print(f"\nSuccessfully updated {updated} FT transactions")
    return updated


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "neartax.db"
    
    print("=" * 60)
    print("Historical Price Service for NearTax")
    print(f"Database: {db_path}")
    print("=" * 60)
    
    # Price NEAR transactions
    print("\n[1/2] Pricing NEAR transactions...")
    near_updated = price_near_transactions(db_path)
    
    # Price FT transactions
    print("\n[2/2] Pricing FT transactions...")
    ft_updated = price_ft_transactions(db_path)
    
    print("\n" + "=" * 60)
    print(f"Complete! Updated {near_updated} NEAR + {ft_updated} FT transactions")
    print("=" * 60)


if __name__ == "__main__":
    main()
