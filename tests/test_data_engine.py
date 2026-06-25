import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from config import load_config
from data_engine import normalize_code, _date_str, _add_days

load_config()


class TestDataEngineHelpers:
    def test_normalize_code(self):
        assert normalize_code("600519") == "600519"
        assert normalize_code("SZ002475") == "002475"

    def test_date_str(self):
        dt = datetime(2025, 1, 15)
        assert _date_str(dt) == "2025-01-15"

    def test_add_days_forward(self):
        result = _add_days("2025-01-01", 5)
        assert result == "2025-01-06"

    def test_add_days_backward(self):
        result = _add_days("2025-01-10", -3)
        assert result == "2025-01-07"

    def test_add_days_invalid_input(self):
        result = _add_days("", 1)
        assert isinstance(result, str)


class TestAPIUsage:
    @patch("cache.CacheManager.record_api_call", return_value=True)
    def test_api_call_decorator_success(self, mock_record):
        from data_engine import _api_call

        @_api_call("test")
        def dummy_func():
            return "ok"

        assert dummy_func() == "ok"

    @patch("cache.CacheManager.record_api_call", return_value=True)
    def test_api_call_decorator_retry(self, mock_record):
        from data_engine import _api_call

        call_count = [0]

        @_api_call("test")
        def failing_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("temporary error")
            return "recovered"

        result = failing_func()
        assert result == "recovered"
        assert call_count[0] == 3

    @patch("cache.CacheManager.record_api_call", return_value=False)
    def test_api_call_limit_exceeded(self, mock_record):
        from data_engine import _api_call

        @_api_call("test")
        def dummy_func():
            return "ok"

        with pytest.raises(RuntimeError, match="Daily API limit"):
            dummy_func()


class TestDataSources:
    def test_try_akshare_missing(self):
        from data_engine import _try_akshare
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "akshare":
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            assert _try_akshare() is None

    def test_try_akshare_present(self):
        from data_engine import _try_akshare
        mock_ak = MagicMock()
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "akshare":
                return mock_ak
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = _try_akshare()
            assert result is mock_ak

    def test_try_efinance_missing(self):
        from data_engine import _try_efinance
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "efinance":
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            assert _try_efinance() is None

    def test_try_baostock_missing(self):
        from data_engine import _try_baostock
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "baostock":
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            assert _try_baostock() is None


class TestSinaCode:
    def test_sina_code_sh(self):
        from data_engine import _sina_code
        assert _sina_code("600519", "A") == "sh600519"
        assert _sina_code("900901", "A") == "sh900901"

    def test_sina_code_sz(self):
        from data_engine import _sina_code
        assert _sina_code("002475", "A") == "sz002475"
        assert _sina_code("300750", "A") == "sz300750"
        assert _sina_code("000001", "A") == "sz000001"

    def test_sina_code_fund(self):
        from data_engine import _sina_code
        assert _sina_code("510050", "FUND") == "sz510050"
        assert _sina_code("159915", "FUND") == "sz159915"

<<<<<<< HEAD
    def test_sina_code_hk(self):
        from data_engine import _sina_code
        assert _sina_code("00700", "HK") == "00700"
=======
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
>>>>>>> 1e809508ea3cc839c82ccac2435f54f6b0e27ed4


class TestGetStockPool:
    @patch("cache.CacheManager.pool_needs_refresh", return_value=False)
    @patch("cache.CacheManager.get_stock_pool", return_value=[{"code": "600519"}])
    def test_returns_cached(self, mock_get, mock_needs):
        from data_engine import get_stock_pool
        pool = get_stock_pool("A")
        assert len(pool) == 1
        assert pool[0]["code"] == "600519"

    @patch("cache.CacheManager.pool_needs_refresh", return_value=True)
    @patch("cache.CacheManager.get_stock_pool", return_value=[{"code": "600519"}])
    @patch("data_engine._try_akshare", return_value=None)
    def test_refresh_no_akshare(self, mock_ak, mock_get, mock_needs):
        from data_engine import get_stock_pool
        pool = get_stock_pool("A")
        assert pool == [{"code": "600519"}]

    @patch("cache.CacheManager.record_api_call", return_value=True)
    def test_fetch_a_stock_pool(self, mock_record):
        from data_engine import _fetch_a_stock_pool
        import pandas as pd
        mock_ak = MagicMock()
        mock_df = pd.DataFrame({"代码": ["600519"], "名称": ["Moutai"]})
        mock_ak.stock_zh_a_spot.return_value = mock_df
        result = _fetch_a_stock_pool(mock_ak)
        assert result is not None
        assert "code" in result.columns


class TestGetFundamentals:
    @patch("cache.CacheManager.get_latest_factor_snapshot", return_value={"code": "600519", "pe_ttm": 10})
    def test_returns_cached(self, mock_snap):
        from data_engine import get_fundamentals
        fund = get_fundamentals("600519")
        assert fund is not None
        assert fund["code"] == "600519"

    @patch("cache.CacheManager.get_latest_factor_snapshot", return_value=None)
    @patch("data_engine._fetch_fundamentals", return_value=None)
    def test_no_data_returns_none(self, mock_fetch, mock_snap):
        from data_engine import get_fundamentals
        fund = get_fundamentals("600519")
        assert fund is None
