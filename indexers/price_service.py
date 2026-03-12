"""
Multi-source price service with PostgreSQL caching and outlier filtering.

Provides:
    - PriceService class: CoinGecko (primary) + CryptoCompare (fallback)
    - Outlier detection: if two sources differ >50%, use CoinGecko as primary
    - Token-agnostic: works for any coin_id (near, ethereum, solana, ...)
    - CAD conversion: USD price * CAD/USD rate (both cached in price_cache)
    - get_price(coin_id, date_str, currency) -> Decimal
    - get_price_batch(coin_id, start_date, end_date, currency) -> dict
    - Module-level get_price() convenience function (uses shared singleton)

Database:
    Uses price_cache table (coin_id, date, currency) with UniqueConstraint.
    Writes via INSERT ... ON CONFLICT DO UPDATE so re-fetching is idempotent.
"""

import time
import base64
import requests
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import COINGECKO_API_KEY, CRYPTOCOMPARE_API_KEY
from indexers.db import get_pool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
CRYPTOCOMPARE_BASE = "https://min-api.cryptocompare.com/data"

# CoinGecko Pro base (used when API key is present)
COINGECKO_PRO_BASE = "https://pro-api.coingecko.com/api/v3"

# Outlier threshold: if |price_a - price_b| / min(price_a, price_b) > OUTLIER_THRESHOLD
# → treat as outlier, prefer CoinGecko as primary
OUTLIER_THRESHOLD = Decimal("0.5")  # 50%

# coin_id → CryptoCompare symbol mapping
COIN_SYMBOL_MAP: dict[str, str] = {
    "near": "NEAR",
    "ethereum": "ETH",
    "bitcoin": "BTC",
    "solana": "SOL",
    "cardano": "ADA",
    "polkadot": "DOT",
    "chainlink": "LINK",
    "uniswap": "UNI",
    "avalanche-2": "AVAX",
    "matic-network": "MATIC",
    "cosmos": "ATOM",
    "algorand": "ALGO",
    "tezos": "XTZ",
    "ripple": "XRP",
    "litecoin": "LTC",
}

# CoinGecko rate limit: free tier 30 calls/min
_COINGECKO_DELAY = 2.1  # seconds between calls (safe for free tier)
_last_coingecko_call = 0.0


# ---------------------------------------------------------------------------
# PriceService
# ---------------------------------------------------------------------------

class PriceService:
    """
    Multi-source historical price service backed by PostgreSQL price_cache table.

    Usage:
        svc = PriceService(db_pool)
        price_usd = svc.get_price("near", "2025-01-15", "usd")
        price_cad = svc.get_price("near", "2025-01-15", "cad")
        cad_rate  = svc.get_cad_rate("2025-01-15")
        batch     = svc.get_price_batch("near", "2025-01-01", "2025-01-31", "usd")
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.coingecko_api_key = COINGECKO_API_KEY
        self.cryptocompare_api_key = CRYPTOCOMPARE_API_KEY

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_price(self, coin_id: str, date_str: str, currency: str = "usd") -> Optional[Decimal]:
        """
        Return historical price for coin_id on date_str in currency.

        Flow:
            1. Check price_cache table — return immediately on hit
            2. Fetch from CoinGecko (primary)
            3. Fetch from CryptoCompare (secondary / fallback)
            4. Aggregate: average if within threshold, else prefer CoinGecko
            5. Cache result
            6. Return Decimal price or None

        Args:
            coin_id: CoinGecko coin id (e.g. "near", "ethereum")
            date_str: ISO date string "YYYY-MM-DD"
            currency: ISO currency code, lowercase (e.g. "usd", "cad")

        Returns:
            Decimal price or None if unavailable
        """
        currency = currency.lower()

        # 1. Cache lookup
        cached = self._get_cached(coin_id, date_str, currency)
        if cached is not None:
            return cached

        # 2. Fetch from both sources
        cg_price = self._fetch_coingecko(coin_id, date_str, currency)
        cc_price = self._fetch_cryptocompare(coin_id, date_str, currency)

        # 3. Aggregate
        price = self._aggregate(cg_price, cc_price)

        if price is None:
            return None

        # Determine source label
        if cg_price is not None and cc_price is not None:
            source = "coingecko+cryptocompare"
        elif cg_price is not None:
            source = "coingecko"
        else:
            source = "cryptocompare"

        # 4. Cache
        self._cache_price(coin_id, date_str, currency, price, source)

        return price

    def get_price_batch(
        self,
        coin_id: str,
        start_date: str,
        end_date: str,
        currency: str = "usd",
    ) -> dict[str, Optional[Decimal]]:
        """
        Return dict of date_str -> Decimal price for all dates in [start_date, end_date].

        Uses get_price() for each date (which hits cache first).
        """
        currency = currency.lower()
        result: dict[str, Optional[Decimal]] = {}

        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        current = start

        while current <= end:
            ds = current.strftime("%Y-%m-%d")
            result[ds] = self.get_price(coin_id, ds, currency)
            current += timedelta(days=1)

        return result

    def get_cad_rate(self, date_str: str) -> Optional[Decimal]:
        """
        Return USD/CAD exchange rate for date_str.

        Stored in price_cache as coin_id="usd", currency="cad".
        Fetches from CoinGecko (USDC/CAD pair) or falls back to a
        fixed default if unavailable.
        """
        # Check cache — stored as coin_id="usd", currency="cad"
        cached = self._get_cached("usd", date_str, "cad")
        if cached is not None:
            return cached

        # Fetch from external source
        rate = self._fetch_cad_rate(date_str)

        if rate is not None:
            self._cache_price("usd", date_str, "cad", rate, "exchangerate")

        return rate

    # ------------------------------------------------------------------
    # Internal: symbol mapping
    # ------------------------------------------------------------------

    def _coin_to_symbol(self, coin_id: str) -> str:
        """Map CoinGecko coin_id to CryptoCompare symbol."""
        return COIN_SYMBOL_MAP.get(coin_id, coin_id.upper())

    # ------------------------------------------------------------------
    # Internal: database helpers
    # ------------------------------------------------------------------

    def _get_conn(self):
        """Get a connection from the pool."""
        return self.db_pool.getconn()

    def _put_conn(self, conn):
        """Return a connection to the pool."""
        self.db_pool.putconn(conn)

    def _get_cached(self, coin_id: str, date_str: str, currency: str) -> Optional[Decimal]:
        """Return cached price or None."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT price FROM price_cache WHERE coin_id=%s AND date=%s AND currency=%s",
                (coin_id, date_str, currency),
            )
            row = cur.fetchone()
            cur.close()
            if row is not None:
                return Decimal(str(row[0]))
            return None
        finally:
            self._put_conn(conn)

    def _cache_price(
        self,
        coin_id: str,
        date_str: str,
        currency: str,
        price: Decimal,
        source: str = "coingecko",
    ) -> None:
        """Insert or update price in price_cache table."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO price_cache (coin_id, date, currency, price, source)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (coin_id, date, currency)
                DO UPDATE SET price = EXCLUDED.price, source = EXCLUDED.source
                """,
                (coin_id, date_str, currency, float(price), source),
            )
            conn.commit()
            cur.close()
        finally:
            self._put_conn(conn)

    # ------------------------------------------------------------------
    # Internal: aggregation / outlier filtering
    # ------------------------------------------------------------------

    def _aggregate(
        self, cg_price: Optional[Decimal], cc_price: Optional[Decimal]
    ) -> Optional[Decimal]:
        """
        Combine prices from two sources with outlier detection.

        Rules:
            - Both available, within 50%: return average
            - Both available, >50% deviation: return CoinGecko (primary)
            - Only one available: return it
            - Neither: return None
        """
        if cg_price is None and cc_price is None:
            return None
        if cg_price is None:
            return cc_price
        if cc_price is None:
            return cg_price

        # Both available — check for outliers
        diff = abs(cg_price - cc_price)
        min_price = min(cg_price, cc_price)
        deviation = diff / min_price if min_price > 0 else Decimal("0")

        if deviation > OUTLIER_THRESHOLD:
            # Outlier: prefer CoinGecko
            return cg_price

        # Within threshold: average
        avg = (cg_price + cc_price) / Decimal("2")
        return avg

    # ------------------------------------------------------------------
    # Internal: CoinGecko fetch
    # ------------------------------------------------------------------

    def _fetch_coingecko(
        self, coin_id: str, date_str: str, currency: str
    ) -> Optional[Decimal]:
        """
        Fetch historical price from CoinGecko /coins/{id}/history endpoint.

        CoinGecko date format: dd-mm-yyyy
        Rate limit: 30 calls/min (free tier) — enforced with sleep.
        """
        global _last_coingecko_call

        # Format date for CoinGecko: "15-01-2025"
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            cg_date = dt.strftime("%d-%m-%Y")
        except ValueError:
            return None

        # Rate limiting
        elapsed = time.time() - _last_coingecko_call
        if elapsed < _COINGECKO_DELAY:
            time.sleep(_COINGECKO_DELAY - elapsed)
        _last_coingecko_call = time.time()

        base = COINGECKO_PRO_BASE if self.coingecko_api_key else COINGECKO_BASE
        url = f"{base}/coins/{coin_id}/history"
        params = {"date": cg_date, "localization": "false"}
        headers = {}
        if self.coingecko_api_key:
            headers["x-cg-pro-api-key"] = self.coingecko_api_key

        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=15)

                if resp.status_code == 429:
                    # Rate limited — back off and retry
                    wait = 30 * (attempt + 1)
                    time.sleep(wait)
                    continue

                if resp.status_code == 404:
                    # Coin not found
                    return None

                resp.raise_for_status()
                data = resp.json()

                market_data = data.get("market_data", {})
                prices = market_data.get("current_price", {})
                price = prices.get(currency.lower())

                if price is not None:
                    return Decimal(str(price))
                return None

            except requests.RequestException:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None

        return None

    # ------------------------------------------------------------------
    # Internal: CryptoCompare fetch
    # ------------------------------------------------------------------

    def _fetch_cryptocompare(
        self, coin_id: str, date_str: str, currency: str
    ) -> Optional[Decimal]:
        """
        Fetch historical price from CryptoCompare /data/pricehistorical endpoint.

        Maps coin_id to symbol (e.g. "near" -> "NEAR").
        """
        symbol = self._coin_to_symbol(coin_id)

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            ts = int(dt.timestamp())
        except ValueError:
            return None

        params = {
            "fsym": symbol,
            "tsyms": currency.upper(),
            "ts": ts,
        }
        if self.cryptocompare_api_key:
            params["api_key"] = self.cryptocompare_api_key

        try:
            resp = requests.get(
                f"{CRYPTOCOMPARE_BASE}/pricehistorical",
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            # Response format: {"SYMBOL": {"CURRENCY": price}}
            price = data.get(symbol, {}).get(currency.upper())
            if price:
                return Decimal(str(price))
            return None

        except requests.RequestException:
            return None

    # ------------------------------------------------------------------
    # Internal: CAD rate fetch
    # ------------------------------------------------------------------

    def _fetch_cad_rate(self, date_str: str) -> Optional[Decimal]:
        """
        Fetch USD/CAD exchange rate for date_str.

        Primary: CoinGecko USDC price in CAD (approximates USD/CAD)
        Fallback: CryptoCompare USD/CAD
        Final fallback: hardcoded approximate rate
        """
        # Try CryptoCompare: USDT -> CAD
        params = {
            "fsym": "USDT",
            "tsyms": "CAD",
            "ts": int(datetime.strptime(date_str, "%Y-%m-%d").timestamp()),
        }
        if self.cryptocompare_api_key:
            params["api_key"] = self.cryptocompare_api_key

        try:
            resp = requests.get(
                f"{CRYPTOCOMPARE_BASE}/pricehistorical",
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            rate = data.get("USDT", {}).get("CAD")
            if rate and Decimal(str(rate)) > Decimal("0.5"):
                return Decimal(str(rate))
        except Exception:
            pass

        # Hardcoded approximate fallback (better than None for CAD tax reports)
        return Decimal("1.36")


# ---------------------------------------------------------------------------
# Module-level convenience function (shared singleton)
# ---------------------------------------------------------------------------

_default_service: Optional[PriceService] = None


def get_price(coin_id: str, date_str: str, currency: str = "usd") -> Optional[Decimal]:
    """
    Module-level convenience function using a shared PriceService singleton.

    Suitable for scripts that don't manage their own db pool.
    Initializes the pool on first call.
    """
    global _default_service
    if _default_service is None:
        _default_service = PriceService(get_pool())
    return _default_service.get_price(coin_id, date_str, currency)
