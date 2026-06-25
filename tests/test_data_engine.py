import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from config import load_config

load_config()


class TestDataEngineUtils:
    def test_sina_code_a_sh(self):
        from data_engine import _sina_code
        assert _sina_code("600519", "A") == "sh600519"

    def test_sina_code_a_sz(self):
        from data_engine import _sina_code
        assert _sina_code("002475", "A") == "sz002475"

    def test_sina_code_fund(self):
        from data_engine import _sina_code
        assert _sina_code("510050", "FUND") == "sz510050"

    def test_sina_code_fund_sz(self):
        from data_engine import _sina_code
        assert _sina_code("159915", "FUND") == "sz159915"

    def test_date_str(self):
        from data_engine import _date_str
        from datetime import datetime
        result = _date_str(datetime(2025, 1, 15))
        assert result == "2025-01-15"

    def test_add_days(self):
        from data_engine import _add_days
        result = _add_days("2025-01-15", 5)
        assert result == "2025-01-20"

    def test_add_days_negative(self):
        from data_engine import _add_days
        result = _add_days("2025-01-15", -5)
        assert result == "2025-01-10"


class TestGetKline:
    def test_get_kline_with_cache(self):
        kline_data = [
            {"date": "2025-01-02", "close": 60.0, "open": 59.0,
             "high": 61.0, "low": 58.5, "volume": 1e7, "amount": 6e8},
        ] * 365
        with patch("data_engine._cache") as mock_cache:
            mock_cache.get_daily_price.return_value = kline_data
            mock_cache.record_api_call.return_value = True

            from data_engine import get_kline
            result = get_kline("601318", "A", days=60)
            assert len(result) == 60

    def test_get_kline_empty_cache(self):
        with patch("data_engine._cache") as mock_cache:
            mock_cache.get_daily_price.return_value = []
            mock_cache.get_latest_date.return_value = None
            mock_cache.record_api_call.return_value = True

            from data_engine import get_kline
            result = get_kline("601318", "A", days=60)
            assert result == []


class TestGetFundamentals:
    def test_get_fundamentals_cached(self):
        mock_snapshot = {
            "code": "601318", "date": "2025-01-01",
            "pe_ttm": 8.5, "pb": 0.95,
        }
        with patch("data_engine._cache") as mock_cache:
            mock_cache.get_latest_factor_snapshot.return_value = mock_snapshot
            mock_cache.record_api_call.return_value = True

            from data_engine import get_fundamentals
            result = get_fundamentals("601318")
            assert result["pe_ttm"] == 8.5

    def test_get_fundamentals_no_data(self):
        with patch("data_engine._cache") as mock_cache, patch(
            "data_engine._fetch_fundamentals", return_value=None
        ):
            mock_cache.get_latest_factor_snapshot.return_value = None
            mock_cache.record_api_call.return_value = True

            from data_engine import get_fundamentals
            result = get_fundamentals("601318")
            assert result is None


class TestGetMarketIndex:
    def test_get_market_index_cached(self):
        with patch("data_engine._cache") as mock_cache:
            mock_cache.get_market_index.return_value = [
                {"index_code": "000001", "date": "2025-01-02", "close": 3000},
            ]
            mock_cache.record_api_call.return_value = True

            from data_engine import get_market_index
            result = get_market_index("000001", days=30)
            assert len(result) == 1
            assert result[0]["close"] == 3000

    def test_get_market_index_empty(self):
        with patch("data_engine._cache") as mock_cache:
            mock_cache.get_market_index.return_value = []
            mock_cache.record_api_call.return_value = True

            from data_engine import get_market_index
            result = get_market_index("000001", days=30)
            assert result == []


class TestGetFundPool:
    def test_get_fund_pool_empty(self):
        with patch("data_engine._cache") as mock_cache:
            mock_cache.get_stock_pool.return_value = []
            mock_cache.record_api_call.return_value = True

            from data_engine import get_fund_pool
            result = get_fund_pool()
            assert result == []


class TestGetStockPool:
    def test_get_stock_pool_with_data(self):
        with patch("data_engine._cache") as mock_cache:
            mock_cache.pool_needs_refresh.return_value = False
            mock_cache.get_stock_pool.return_value = [
                {"code": "601318", "name": "PingAn", "market": "A"},
            ]

            from data_engine import get_stock_pool
            result = get_stock_pool("A")
            assert len(result) == 1
            assert result[0]["code"] == "601318"

    def test_get_stock_pool_refresh(self):
        with patch("data_engine._cache") as mock_cache:
            mock_cache.pool_needs_refresh.return_value = True
            mock_cache.get_stock_pool.return_value = [
                {"code": "601318", "name": "PingAn", "market": "A"},
            ]

            from data_engine import get_stock_pool
            result = get_stock_pool("A")
            assert len(result) == 1
