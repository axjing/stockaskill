import pytest
import time
from datetime import datetime, timedelta
from pathlib import Path
from cache import CacheManager

_TODAY = datetime.now().strftime("%Y-%m-%d")
_YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


@pytest.fixture
def cache(tmp_path):
    db_path = tmp_path / "test_cache.db"
    return CacheManager(db_path)


class TestCacheManager:
    def test_init_creates_tables(self, cache):
        with cache._conn() as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [r[0] for r in cur.fetchall()]
        assert "stock_pool" in tables
        assert "daily_price" in tables
        assert "factor_snapshot" in tables
        assert "cache_meta" in tables
        assert "api_usage" in tables
        assert "kv_store" in tables
        assert len(tables) >= 10

    # -- Stock Pool --

    def test_upsert_and_get_stock_pool(self, cache):
        rows = [
            {"code": "601318", "name": "PingAn", "market": "A",
             "sector": "Finance", "industry": "Insurance",
             "list_date": "2007-03-01", "total_market_cap": 1.2e12,
             "is_active": 1, "updated_at": "2025-01-01"},
        ]
        cache.upsert_stock_pool(rows)
        pool = cache.get_stock_pool("A")
        assert len(pool) == 1
        assert pool[0]["code"] == "601318"
        assert pool[0]["name"] == "PingAn"

    def test_stock_pool_empty_market(self, cache):
        pool = cache.get_stock_pool("HK")
        assert pool == []

    def test_pool_needs_refresh_empty(self, cache):
        assert cache.pool_needs_refresh() is True

    # -- Daily Price --

    def test_upsert_and_get_daily_price(self, cache):
        rows = [
            {"code": "601318", "date": "2025-01-02", "open": 60.0,
             "high": 61.0, "low": 59.5, "close": 60.5,
             "volume": 1e7, "amount": 6.05e8, "market": "A"},
            {"code": "601318", "date": "2025-01-03", "open": 60.5,
             "high": 62.0, "low": 60.0, "close": 61.5,
             "volume": 1.2e7, "amount": 7.38e8, "market": "A"},
        ]
        cache.upsert_daily_price(rows)
        prices = cache.get_daily_price("601318")
        assert len(prices) == 2
        assert prices[0]["date"] == "2025-01-03"

    def test_get_daily_price_date_filtered(self, cache):
        rows = [
            {"code": "601318", "date": "2025-01-02", "open": 60.0,
             "high": 61.0, "low": 59.5, "close": 60.5,
             "volume": 1e7, "amount": 6.05e8, "market": "A"},
            {"code": "601318", "date": "2025-01-03", "open": 60.5,
             "high": 62.0, "low": 60.0, "close": 61.5,
             "volume": 1.2e7, "amount": 7.38e8, "market": "A"},
        ]
        cache.upsert_daily_price(rows)
        prices = cache.get_daily_price("601318", "2025-01-02", "2025-01-02")
        assert len(prices) == 1
        assert prices[0]["date"] == "2025-01-02"

    def test_get_latest_date(self, cache):
        rows = [
            {"code": "601318", "date": "2025-01-02", "open": 60.0,
             "high": 61.0, "low": 59.5, "close": 60.5,
             "volume": 1e7, "amount": 6.05e8, "market": "A"},
            {"code": "601318", "date": "2025-01-05", "open": 61.0,
             "high": 62.0, "low": 60.5, "close": 61.5,
             "volume": 1e7, "amount": 6.15e8, "market": "A"},
        ]
        cache.upsert_daily_price(rows)
        latest = cache.get_latest_date("601318")
        assert latest == "2025-01-05"

    def test_get_latest_date_empty(self, cache):
        assert cache.get_latest_date("601318") is None

    # -- Factor Snapshot --

    def test_upsert_and_get_factor_snapshot(self, cache):
        rows = [{
            "code": "601318", "date": "2025-01-01",
            "market_cap": 1.2e12, "pe_ttm": 8.5, "pe_static": 8.0,
            "pb": 0.95, "ps_ttm": 1.5, "pcf_ttm": 5.0,
            "dividend_yield": 4.2, "roe": 0.15, "roa": 0.05,
            "gross_margin": 0.35, "net_margin": 0.20,
            "revenue_growth": 0.12, "profit_growth": 0.15,
            "debt_ratio": 0.40, "current_ratio": 1.5, "eps": 8.0, "bvps": 50.0,
        }]
        cache.upsert_factor_snapshot(rows)
        snap = cache.get_latest_factor_snapshot("601318")
        assert snap is not None
        assert snap["pe_ttm"] == 8.5
        assert snap["pb"] == 0.95

    def test_get_factor_snapshot_missing(self, cache):
        assert cache.get_latest_factor_snapshot("missing") is None

    # -- Computed Factors --

    def test_upsert_and_get_computed_factors(self, cache):
        cache.upsert_computed_factors("601318", "2025-01-01",
                                      {"value": 0.8, "quality": 0.7})
        factors = cache.get_computed_factors("601318", "2025-01-01")
        assert factors["value"] == 0.8
        assert factors["quality"] == 0.7

    def test_computed_factors_empty(self, cache):
        assert cache.get_computed_factors("missing") == {}

    # -- Sentiment --

    def test_upsert_and_get_sentiment(self, cache):
        rows = [{
            "code": "601318", "date": _TODAY,
            "source": "guba", "title": "Test", "url": "",
            "sentiment_score": 0.8,
        }]
        cache.upsert_sentiment(rows)
        sentiments = cache.get_sentiment("601318", days=365)
        assert len(sentiments) >= 1
        assert sentiments[0]["sentiment_score"] == 0.8

    # -- Fund Info --

    def test_upsert_and_get_fund_info(self, cache):
        rows = [{
            "code": "510050", "name": "CSI 300 ETF", "fund_type": "ETF",
            "nav": 4.5, "acc_nav": 4.8, "scale": 5e10,
            "track_index": "000300", "updated_at": "2025-01-01",
        }]
        cache.upsert_fund_info(rows)
        info = cache.get_fund_info("510050")
        assert info is not None
        assert info["name"] == "CSI 300 ETF"
        assert info["fund_type"] == "ETF"

    def test_get_fund_info_missing(self, cache):
        assert cache.get_fund_info("missing") is None

    # -- Fund NAV --

    def test_upsert_and_get_fund_nav(self, cache):
        rows = [
            {"code": "510050", "date": _YESTERDAY, "nav": 4.5, "acc_nav": 4.8},
            {"code": "510050", "date": _TODAY, "nav": 4.55, "acc_nav": 4.85},
        ]
        cache.upsert_fund_nav(rows)
        navs = cache.get_fund_nav("510050", days=365)
        assert len(navs) == 2

    # -- Market Index --

    def test_upsert_and_get_market_index(self, cache):
        rows = [{
            "index_code": "000001", "date": _YESTERDAY,
            "open": 3000, "high": 3050, "low": 2980,
            "close": 3020, "volume": 1e9, "amount": 3e11,
        }]
        cache.upsert_market_index(rows)
        data = cache.get_market_index("000001", days=365)
        assert len(data) >= 1
        assert data[0]["close"] == 3020

    # -- Industry --

    def test_upsert_and_get_industry(self, cache):
        rows = [{
            "code": "601318", "sector": "Finance",
            "industry": "Insurance", "updated_at": "2025-01-01",
        }]
        cache.upsert_industry(rows)
        sector, industry = cache.get_industry("601318")
        assert sector == "Finance"
        assert industry == "Insurance"

    def test_get_industry_missing(self, cache):
        sector, industry = cache.get_industry("missing")
        assert sector == ""
        assert industry == ""

    # -- KV Store --

    def test_kv_set_and_get(self, cache):
        cache.kv_set("test_key", {"a": 1, "b": 2}, ttl=3600)
        val = cache.kv_get("test_key")
        assert val == {"a": 1, "b": 2}

    def test_kv_get_missing(self, cache):
        assert cache.kv_get("nonexistent") is None

    def test_kv_set_str_and_get_str(self, cache):
        cache.kv_set_str("greeting", "hello", ttl=3600)
        val = cache.kv_get_str("greeting")
        assert val == "hello"

    def test_kv_expiry(self, cache):
        cache.kv_set("temp", "value", ttl=0)
        val = cache.kv_get("temp")
        assert val is None

    # -- API Usage --

    def test_record_api_call(self, cache):
        ok = cache.record_api_call("test_api")
        assert ok is True

    def test_api_usage_today(self, cache):
        cache.record_api_call("api_a")
        cache.record_api_call("api_b")
        total = cache.get_api_usage_today()
        assert total == 2

    def test_api_usage_today_empty(self, cache):
        assert cache.get_api_usage_today() == 0
