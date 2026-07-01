from datetime import datetime
from unittest.mock import patch

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
        assert _sina_code("510050", "FUND") == "sh510050"

    def test_sina_code_fund_sz(self):
        from data_engine import _sina_code
        assert _sina_code("159915", "FUND") == "sz159915"

    def test_date_str(self):
        from data_engine import _date_str
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

    def test_get_stock_pool_refresh(self):
        with patch("data_engine._cache") as mock_cache:
            mock_cache.pool_needs_refresh.return_value = True
            mock_cache.get_stock_pool.return_value = [
                {"code": "601318", "name": "PingAn", "market": "A"},
            ]

            from data_engine import get_stock_pool

            result = get_stock_pool("A")
            assert len(result) == 1


class TestEnsureStockPoolCandidatesReady:
    def test_uses_cached_history_to_backfill_list_date(self):
        rows = [
            {
                "code": "601318",
                "name": "PingAn",
                "market": "A",
                "sector": "",
                "industry": "",
                "list_date": "",
                "total_market_cap": 0.0,
                "is_active": 1,
                "updated_at": "2025-01-01 00:00:00",
            }
        ]
        with patch("data_engine._cache") as mock_cache:
            mock_cache.get_stock_pool.return_value = rows
            mock_cache.get_daily_price.return_value = [
                {"date": "2025-01-02"},
                {"date": "2007-03-01"},
            ]
            with patch("data_engine._fetch_a_stock_profile_metadata", return_value={}):
                from data_engine import ensure_stock_pool_candidates_ready

                result = ensure_stock_pool_candidates_ready("A", ["601318"])

        assert result["cached_history_backfilled"] == 1
        updated_rows = mock_cache.upsert_stock_pool.call_args.args[0]
        assert updated_rows[0]["list_date"] == "2007-03-01"

    def test_reports_already_ready_candidates(self):
        rows = [
            {
                "code": "601318",
                "name": "PingAn",
                "market": "A",
                "sector": "Finance",
                "industry": "Insurance",
                "list_date": "2007-03-01",
                "total_market_cap": 0.0,
                "is_active": 1,
                "updated_at": "2025-01-01 00:00:00",
            }
        ]
        with patch("data_engine._cache") as mock_cache:
            mock_cache.get_stock_pool.return_value = rows
            from data_engine import ensure_stock_pool_candidates_ready

            result = ensure_stock_pool_candidates_ready("A", ["601318"])

        assert result["already_ready"] == 1
        mock_cache.upsert_stock_pool.assert_not_called()


class TestCrossMarketPoolNormalization:
    def test_fetch_hk_stock_pool_extracts_metadata_and_inactive_status(self):
        hk_df = pd.DataFrame(
            [
                {
                    "代码": "00700",
                    "中文名称": "Tencent",
                    "行业": "Internet",
                    "地区": "Technology",
                    "总市值": "5000000",
                    "状态": "正常",
                },
                {
                    "代码": "00001",
                    "中文名称": "Legacy Delisted",
                    "状态": "Delisted",
                },
            ]
        )
        ak = type("FakeAk", (), {"stock_hk_spot": lambda self: hk_df})()

        with patch("data_engine._cache") as mock_cache:
            mock_cache.record_api_call.return_value = True
            from data_engine import _fetch_hk_stock_pool

            result = _fetch_hk_stock_pool(ak)
        assert result is not None
        assert result.iloc[0]["industry"] == "Internet"
        assert result.iloc[0]["sector"] == "Technology"
        assert result.iloc[0]["total_market_cap"] == 5000000.0
        assert result.iloc[0]["metadata_source"] == "akshare_stock_hk_spot"
        assert result.iloc[0]["metadata_status"] == "active"
        assert result.iloc[0]["metadata_completeness"] == 0.75
        assert result.iloc[1]["is_active"] == 0

    def test_fetch_us_stock_pool_extracts_metadata_and_inactive_status(self):
        us_df = pd.DataFrame(
            [
                {
                    "代码": "AAPL",
                    "名称": "Apple",
                    "所属行业": "Consumer Electronics",
                    "总市值": "3000000",
                    "状态": "Active",
                },
                {
                    "代码": "ZZZZ",
                    "名称": "Suspended Test",
                    "状态": "Suspended",
                },
            ]
        )
        ak = type("FakeAk", (), {"stock_us_spot": lambda self: us_df})()

        with patch("data_engine._cache") as mock_cache:
            mock_cache.record_api_call.return_value = True
            from data_engine import _fetch_us_stock_pool

            result = _fetch_us_stock_pool(ak)
        assert result is not None
        assert result.iloc[0]["industry"] == "Consumer Electronics"
        assert result.iloc[0]["total_market_cap"] == 3000000.0
        assert result.iloc[0]["metadata_source"] == "akshare_stock_us_spot"
        assert result.iloc[1]["metadata_status"] == "suspended"
        assert result.iloc[1]["is_active"] == 0

    def test_ensure_stock_pool_candidates_ready_summarizes_non_a_metadata(self):
        with patch("data_engine._cache") as mock_cache:
            mock_cache.get_stock_pool.return_value = [
                {
                    "code": "AAPL",
                    "metadata_completeness": 0.75,
                    "list_date": "",
                    "total_market_cap": 3.0e12,
                    "is_active": 1,
                },
                {
                    "code": "ZZZZ",
                    "metadata_completeness": 0.25,
                    "list_date": "",
                    "total_market_cap": 0.0,
                    "is_active": 0,
                },
            ]

            from data_engine import ensure_stock_pool_candidates_ready

            result = ensure_stock_pool_candidates_ready("US", ["AAPL", "ZZZZ"])

        assert result["metadata_complete"] == 1
        assert result["metadata_partial"] == 1
        assert result["inactive_count"] == 1


class TestSyncEtfData:
    def test_sync_etf_data_uses_fund_nav_cache_and_scope_state(self):
        with patch("data_engine._cache") as mock_cache, patch(
            "data_engine.get_fund_nav"
        ) as mock_get_fund_nav:
            mock_cache.get_fund_nav.side_effect = [
                [],
                [{"date": "2026-07-01", "nav": 4.0}] * 365,
            ]
            mock_get_fund_nav.return_value = [{"date": "2026-07-01", "nav": 4.0}] * 365

            from data_engine import sync_etf_data

            result = sync_etf_data(["510300"], history_days=365)

        assert result["requested"] == 1
        assert result["ready"] == 1
        assert result["history_fetched_count"] == 1
        assert result["covered_through"] == "2026-07-01"
        mock_get_fund_nav.assert_called_once_with("510300", 365)
        upsert_rows = mock_cache.upsert_sync_state.call_args_list[0].args[0]
        assert upsert_rows[0]["data_kind"] == "nav"

    def test_get_etf_nav_alias_delegates_to_fund_nav(self):
        with patch("data_engine.get_fund_nav") as mock_get_fund_nav:
            mock_get_fund_nav.return_value = [{"date": "2026-07-01", "nav": 4.0}]

            from data_engine import get_etf_nav

            result = get_etf_nav("510300", days=365)

        assert result == [{"date": "2026-07-01", "nav": 4.0}]
        mock_get_fund_nav.assert_called_once_with("510300", 365)
