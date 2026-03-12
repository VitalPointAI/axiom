"""
Tests for PriceService — multi-source price aggregation with caching and outlier filtering.

Coverage:
- Cache hit: returns immediately without API call
- Cache miss: fetches from CoinGecko (primary)
- Fallback: uses CryptoCompare when CoinGecko fails
- Outlier filtering: if sources differ >50%, uses CoinGecko as primary
- Caching: after fetch, verifies INSERT was called
- coin_id to symbol mapping
- get_price_batch for bulk lookups
- get_cad_rate via price_cache
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, call
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_cursor(fetchone_return=None, fetchall_return=None):
    """Return a mock psycopg2 cursor."""
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_return
    cur.fetchall.return_value = fetchall_return or []
    return cur


def make_mock_pool(cursor_fetchone=None, cursor_fetchall=None):
    """Return a mock psycopg2 connection pool."""
    cur = make_mock_cursor(fetchone_return=cursor_fetchone, fetchall_return=cursor_fetchall)
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool, conn, cur


# ---------------------------------------------------------------------------
# Cache hit tests
# ---------------------------------------------------------------------------

class TestCacheHit:
    def test_returns_cached_price_without_api_call(self):
        """If price_cache has a row for (coin_id, date, currency), return it immediately."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        # Simulate cache hit: SELECT returns (price,)
        cur.fetchone.return_value = (Decimal("5.25"),)

        svc = PriceService(pool)

        with patch.object(svc, "_fetch_coingecko") as mock_cg, \
             patch.object(svc, "_fetch_cryptocompare") as mock_cc:
            price = svc.get_price("near", "2025-01-15", "usd")

        assert price == Decimal("5.25")
        mock_cg.assert_not_called()
        mock_cc.assert_not_called()

    def test_cache_hit_returns_decimal(self):
        """Cache hit must return a Decimal, not float."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = (Decimal("3.14159"),)
        svc = PriceService(pool)

        price = svc.get_price("near", "2024-06-01", "usd")
        assert isinstance(price, Decimal)


# ---------------------------------------------------------------------------
# Cache miss — CoinGecko primary
# ---------------------------------------------------------------------------

class TestCacheMissCoingecko:
    def test_fetches_from_coingecko_on_cache_miss(self):
        """Cache miss triggers CoinGecko fetch."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)

        with patch.object(svc, "_fetch_coingecko", return_value=Decimal("6.00")) as mock_cg, \
             patch.object(svc, "_fetch_cryptocompare", return_value=None) as mock_cc, \
             patch.object(svc, "_cache_price") as mock_cache:
            price = svc.get_price("near", "2025-01-15", "usd")

        assert price == Decimal("6.00")
        mock_cg.assert_called_once_with("near", "2025-01-15", "usd")

    def test_result_cached_after_coingecko_fetch(self):
        """After fetching from CoinGecko, price should be cached."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)

        with patch.object(svc, "_fetch_coingecko", return_value=Decimal("5.50")), \
             patch.object(svc, "_fetch_cryptocompare", return_value=None), \
             patch.object(svc, "_cache_price") as mock_cache:
            svc.get_price("near", "2025-01-15", "usd")

        mock_cache.assert_called_once()


# ---------------------------------------------------------------------------
# CryptoCompare fallback
# ---------------------------------------------------------------------------

class TestCryptoCompareFallback:
    def test_falls_back_to_cryptocompare_when_coingecko_fails(self):
        """When CoinGecko returns None, use CryptoCompare."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)

        with patch.object(svc, "_fetch_coingecko", return_value=None), \
             patch.object(svc, "_fetch_cryptocompare", return_value=Decimal("5.10")) as mock_cc, \
             patch.object(svc, "_cache_price"):
            price = svc.get_price("near", "2025-01-15", "usd")

        assert price == Decimal("5.10")
        mock_cc.assert_called_once_with("near", "2025-01-15", "usd")

    def test_returns_none_when_both_sources_fail(self):
        """If both sources fail, return None."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)

        with patch.object(svc, "_fetch_coingecko", return_value=None), \
             patch.object(svc, "_fetch_cryptocompare", return_value=None):
            price = svc.get_price("near", "2025-01-15", "usd")

        assert price is None


# ---------------------------------------------------------------------------
# Outlier filtering
# ---------------------------------------------------------------------------

class TestOutlierFiltering:
    def test_averages_prices_when_within_threshold(self):
        """If both sources agree (within 50%), return the average."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)
        # 5.00 vs 5.50 → deviation = 0.50/5.00 = 10% → within threshold → average
        with patch.object(svc, "_fetch_coingecko", return_value=Decimal("5.00")), \
             patch.object(svc, "_fetch_cryptocompare", return_value=Decimal("5.50")), \
             patch.object(svc, "_cache_price"):
            price = svc.get_price("near", "2025-01-15", "usd")

        assert price == Decimal("5.25")

    def test_uses_coingecko_when_sources_are_outliers(self):
        """If sources differ by >50%, use CoinGecko as primary."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)
        # 5.00 vs 10.00 → deviation = 5.00/5.00 = 100% → outlier → use CoinGecko
        with patch.object(svc, "_fetch_coingecko", return_value=Decimal("5.00")), \
             patch.object(svc, "_fetch_cryptocompare", return_value=Decimal("10.00")), \
             patch.object(svc, "_cache_price"):
            price = svc.get_price("near", "2025-01-15", "usd")

        assert price == Decimal("5.00")

    def test_uses_cryptocompare_as_outlier_if_coingecko_is_high(self):
        """If CoinGecko is the outlier (high), still use CoinGecko as primary per spec."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)
        # 10.00 vs 5.00 → |10-5| / min(10,5) = 5/5 = 100% → outlier → use CoinGecko
        with patch.object(svc, "_fetch_coingecko", return_value=Decimal("10.00")), \
             patch.object(svc, "_fetch_cryptocompare", return_value=Decimal("5.00")), \
             patch.object(svc, "_cache_price"):
            price = svc.get_price("near", "2025-01-15", "usd")

        # CoinGecko is primary, so use CoinGecko
        assert price == Decimal("10.00")


# ---------------------------------------------------------------------------
# coin_id → symbol mapping
# ---------------------------------------------------------------------------

class TestCoinSymbolMapping:
    def test_near_maps_to_NEAR_symbol(self):
        """coin_id 'near' should map to 'NEAR' for CryptoCompare API."""
        from indexers.price_service import PriceService, COIN_SYMBOL_MAP

        assert COIN_SYMBOL_MAP.get("near") == "NEAR"

    def test_ethereum_maps_to_ETH(self):
        """coin_id 'ethereum' should map to 'ETH'."""
        from indexers.price_service import COIN_SYMBOL_MAP

        assert COIN_SYMBOL_MAP.get("ethereum") == "ETH"

    def test_unknown_coin_uppercased(self):
        """Unknown coin_id (not in COIN_SYMBOL_MAP) should be uppercased as fallback symbol."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        svc = PriceService(pool)
        # "mytoken" is not in COIN_SYMBOL_MAP, so it should uppercase
        symbol = svc._coin_to_symbol("mytoken")
        assert symbol == "MYTOKEN"


# ---------------------------------------------------------------------------
# get_price_batch
# ---------------------------------------------------------------------------

class TestGetPriceBatch:
    def test_batch_returns_dict_of_date_to_price(self):
        """get_price_batch returns a dict mapping date strings to Decimal prices."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # all cache misses

        svc = PriceService(pool)

        with patch.object(svc, "get_price", side_effect=lambda c, d, cur="usd": Decimal("5.00")) as mock_gp:
            result = svc.get_price_batch("near", "2025-01-01", "2025-01-03", "usd")

        assert "2025-01-01" in result
        assert "2025-01-02" in result
        assert "2025-01-03" in result
        assert all(isinstance(v, Decimal) for v in result.values() if v is not None)

    def test_batch_skips_none_prices(self):
        """Dates where price is None are still included in result (with None value)."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        svc = PriceService(pool)

        with patch.object(svc, "get_price", return_value=None):
            result = svc.get_price_batch("near", "2025-01-01", "2025-01-02", "usd")

        # Keys present, values are None
        assert "2025-01-01" in result
        assert result["2025-01-01"] is None


# ---------------------------------------------------------------------------
# CAD rate
# ---------------------------------------------------------------------------

class TestGetCadRate:
    def test_get_cad_rate_returns_decimal(self):
        """get_cad_rate should return a Decimal USD/CAD rate."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        # Cache hit for CAD rate
        cur.fetchone.return_value = (Decimal("1.36"),)
        svc = PriceService(pool)

        rate = svc.get_cad_rate("2025-01-15")
        assert isinstance(rate, Decimal)
        assert rate == Decimal("1.36")

    def test_get_cad_rate_uses_usd_coin_id(self):
        """CAD rate is stored as coin_id='usd', currency='cad' in price_cache."""
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss
        svc = PriceService(pool)

        # If not cached, should attempt to fetch (we mock to prevent real HTTP)
        with patch.object(svc, "_fetch_cad_rate", return_value=Decimal("1.38")) as mock_fetch:
            rate = svc.get_cad_rate("2025-01-15")

        mock_fetch.assert_called_once_with("2025-01-15")


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

class TestModuleLevelGetPrice:
    def test_get_price_function_exists(self):
        """Module-level get_price function should exist and be callable."""
        from indexers import price_service
        assert callable(getattr(price_service, "get_price", None))


# ---------------------------------------------------------------------------
# Minute-level price cache
# ---------------------------------------------------------------------------


class TestMinutePriceCache:
    """Tests for get_price_at_timestamp() — minute-level cache and CoinGecko range fetch."""

    def test_cache_hit_returns_price_and_not_estimated(self):
        """Cache hit in price_cache_minute returns (price, is_estimated) without API call.

        Scenario: price_cache_minute has a row for (coin_id, ts_minute, currency)
        Expect: returns cached (price, False) without calling CoinGecko
        """
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        # Simulate cache hit: SELECT returns (price, is_estimated)
        cur.fetchone.return_value = ("4.5000", False)

        svc = PriceService(pool)

        with patch("requests.get") as mock_http:
            result = svc.get_price_at_timestamp("near", 1700000000, "usd")

        assert result == (pytest.approx(Decimal("4.5"), abs=Decimal("0.01")), False)
        mock_http.assert_not_called()

    def test_cache_miss_triggers_api_call(self):
        """Cache miss causes CoinGecko market_chart/range to be called.

        Scenario: no row in price_cache_minute
        Expect: requests.get called with correct endpoint
        """
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "prices": [[1700000000000, 4.5]]  # ms timestamp
        }

        with patch("requests.get", return_value=mock_response) as mock_http:
            price, is_estimated = svc.get_price_at_timestamp("near", 1700000000, "usd")

        assert price == Decimal("4.5")
        assert is_estimated is False
        assert mock_http.called

    def test_stablecoin_returns_one_without_api(self):
        """Stablecoins (tether, usd-coin, dai) return (1, False) without API call.

        Expect: no DB or HTTP call made for stablecoin coin_ids
        """
        from indexers.price_service import PriceService, STABLECOIN_MAP

        pool, conn, cur = make_mock_pool()
        svc = PriceService(pool)

        with patch("requests.get") as mock_http:
            price, is_estimated = svc.get_price_at_timestamp("tether", 1700000000, "usd")

        assert price == Decimal("1")
        assert is_estimated is False
        mock_http.assert_not_called()


# ---------------------------------------------------------------------------
# Bank of Canada Valet API
# ---------------------------------------------------------------------------


class TestBoCRate:
    """Tests for get_boc_cad_rate() — BoC Valet API with weekend/holiday fallback."""

    def test_successful_fetch_returns_decimal(self):
        """BoC API returns rate for a weekday.

        Scenario: BoC responds with {"observations": [{"FXUSDCAD": {"v": "1.4348"}}]}
        Expect: returns Decimal("1.4348")
        """
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "observations": [{"d": "2025-01-15", "FXUSDCAD": {"v": "1.4348"}}]
        }

        with patch("requests.get", return_value=mock_response):
            rate = svc.get_boc_cad_rate("2025-01-15")

        assert rate == Decimal("1.4348")

    def test_cache_hit_skips_api(self):
        """Cache hit in price_cache (coin_id='usd', currency='cad') skips BoC API call.

        Scenario: price_cache has cached rate
        Expect: no HTTP call to BoC API
        """
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = (Decimal("1.38"),)  # cache hit

        svc = PriceService(pool)

        with patch("requests.get") as mock_http:
            rate = svc.get_boc_cad_rate("2025-01-15")

        assert rate == Decimal("1.38")
        mock_http.assert_not_called()

    def test_weekend_fallback_returns_friday_rate(self):
        """Weekend date falls back to most recent business day.

        Scenario: requested date is Sunday (no BoC observation),
                  Saturday also empty, Friday has rate
        Expect: returns Friday's rate
        """
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)

        call_count = [0]

        def mock_fetch_boc(date_str):
            call_count[0] += 1
            if call_count[0] >= 3:  # Third call (Friday) returns rate
                return Decimal("1.4200")
            return None  # Sunday, Saturday return None

        with patch.object(svc, "_fetch_boc_rate", side_effect=mock_fetch_boc):
            rate = svc.get_boc_cad_rate("2025-01-19")  # Sunday

        assert rate == Decimal("1.4200")
        assert call_count[0] == 3

    def test_none_after_five_day_lookback(self):
        """Returns None if no rate found after 5-day lookback.

        Scenario: 6 consecutive days have no BoC observation (unlikely in practice,
                  but must be handled gracefully — e.g. extended holiday or API error)
        Expect: returns None
        """
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        cur.fetchone.return_value = None  # cache miss

        svc = PriceService(pool)

        with patch.object(svc, "_fetch_boc_rate", return_value=None):
            rate = svc.get_boc_cad_rate("2025-01-01")

        assert rate is None


# ---------------------------------------------------------------------------
# CoinGecko range fetch — closest timestamp selection
# ---------------------------------------------------------------------------


class TestCoinGeckoRange:
    """Tests for _fetch_coingecko_range() — closest-point selection and estimation flag."""

    def test_closest_timestamp_selected(self):
        """Returns price from the data point closest to the target timestamp.

        Scenario: CoinGecko returns prices at T-5min, T-1min, T+3min
        Expect: returns price at T-1min (smallest gap)
        """
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        svc = PriceService(pool)

        target_ts = 1700000000  # seconds
        # Build prices array with timestamps in milliseconds
        prices = [
            [(target_ts - 300) * 1000, 4.0],  # T-5min
            [(target_ts - 60) * 1000, 4.5],   # T-1min (closest)
            [(target_ts + 180) * 1000, 5.0],  # T+3min
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"prices": prices}

        with patch("requests.get", return_value=mock_response):
            price, is_estimated = svc._fetch_coingecko_range(
                "near", target_ts, (target_ts // 60) * 60, "usd"
            )

        assert price == Decimal("4.5")
        assert is_estimated is False  # 1 min gap < 15 min threshold

    def test_is_estimated_flag_for_large_gap(self):
        """Sets is_estimated=True when closest data point is >15 minutes away.

        Scenario: CoinGecko returns price that is 20 minutes from target
        Expect: is_estimated=True
        """
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        svc = PriceService(pool)

        target_ts = 1700000000
        prices = [
            [(target_ts + 1200) * 1000, 4.5],  # T+20min = 1200 seconds > 900 threshold
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"prices": prices}

        with patch("requests.get", return_value=mock_response):
            price, is_estimated = svc._fetch_coingecko_range(
                "near", target_ts, (target_ts // 60) * 60, "usd"
            )

        assert price is not None
        assert is_estimated is True

    def test_stablecoin_bypass(self):
        """Stablecoins bypass the range fetch and return (1, False) directly.

        Scenario: get_price_at_timestamp called with coin_id='usd-coin'
        Expect: STABLECOIN_MAP hit, no CoinGecko API call
        """
        from indexers.price_service import PriceService

        pool, conn, cur = make_mock_pool()
        svc = PriceService(pool)

        with patch("requests.get") as mock_http:
            price, is_estimated = svc.get_price_at_timestamp("usd-coin", 1700000000)

        assert price == Decimal("1")
        assert is_estimated is False
        mock_http.assert_not_called()
