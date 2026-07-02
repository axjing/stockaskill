from datetime import datetime
from unittest.mock import patch


class TestDataReadiness:
    @patch("data_readiness.get_stock_pool")
    @patch("data_readiness.sync_symbol_data")
    def test_ensure_symbol_ready_uses_local_cache(
        self,
        mock_sync_symbol_data,
        mock_pool,
    ):
        mock_pool.return_value = [
            {
                "code": "600519",
                "metadata_source": "manual",
                "metadata_status": "active",
                "metadata_completeness": 1.0,
            }
        ]
        mock_sync_symbol_data.return_value = {
            "code": "600519",
            "market": "A",
            "history_before": 400,
            "history_after": 400,
            "history_ready": True,
            "history_covered_through": datetime.now().strftime("%Y-%m-%d"),
            "fundamentals_before": True,
            "fundamentals_after": True,
            "ready": True,
        }

        from data_readiness import ensure_symbol_ready

        result = ensure_symbol_ready("600519", "A", history_days=365)
        assert result["history_ready"] is True
        assert result["fundamentals_after"] is True
        assert result["covered_through"]
        assert result["confidence"]["level"] in {"high", "medium", "low"}
        assert "provenance" in result
        mock_sync_symbol_data.assert_called_once()

    @patch("data_readiness.get_stock_pool")
    @patch("data_readiness.sync_symbol_data")
    def test_ensure_symbol_ready_fetches_missing_data(
        self,
        mock_sync_symbol_data,
        mock_pool,
    ):
        mock_pool.return_value = [
            {
                "code": "600519",
                "metadata_source": "manual",
                "metadata_status": "active",
                "metadata_completeness": 1.0,
            }
        ]
        mock_sync_symbol_data.return_value = {
            "code": "600519",
            "market": "A",
            "history_before": 0,
            "history_after": 365,
            "history_ready": True,
            "history_covered_through": datetime.now().strftime("%Y-%m-%d"),
            "fundamentals_before": False,
            "fundamentals_after": True,
            "ready": True,
        }

        from data_readiness import ensure_symbol_ready

        result = ensure_symbol_ready("600519", "A", history_days=365)
        assert result["history_ready"] is True
        assert result["fundamentals_after"] is True
        assert result["confidence"]["score"] >= 0
        mock_sync_symbol_data.assert_called_once()

    @patch("data_readiness.sync_watchlist_data")
    def test_ensure_watchlist_ready_uses_sync_scope(self, mock_sync_watchlist_data):
        mock_sync_watchlist_data.return_value = {
            "requested": 2,
            "ready": 2,
            "symbols": [],
        }

        from data_readiness import ensure_watchlist_ready

        result = ensure_watchlist_ready("A")
        assert result["requested"] == 2
        mock_sync_watchlist_data.assert_called_once()

    @patch("data_readiness.get_etf_pool")
    def test_ensure_pool_ready_uses_etf_alias_for_fund_market(self, mock_get_etf_pool):
        mock_get_etf_pool.return_value = [{"code": "510300"}]

        from data_readiness import ensure_pool_ready

        result = ensure_pool_ready("FUND")
        assert result == [{"code": "510300"}]
        mock_get_etf_pool.assert_called_once_with()

    @patch("data_readiness.sync_etf_data")
    def test_ensure_etf_ready_uses_etf_sync_scope(self, mock_sync_etf_data):
        mock_sync_etf_data.return_value = {
            "requested": 2,
            "ready": 2,
            "symbols": [
                {"history_covered_through": "2026-07-01"},
                {"history_covered_through": "2026-06-30"},
            ],
        }

        from data_readiness import ensure_etf_ready

        result = ensure_etf_ready(["510300", "159915"], history_days=365)
        assert result["requested"] == 2
        assert result["covered_through"] == "2026-07-01"
        assert result["confidence"]["level"] in {"high", "medium", "low"}
        mock_sync_etf_data.assert_called_once()

    @patch("data_readiness.ensure_etf_ready")
    def test_ensure_fund_screen_ready_delegates_to_etf_ready(
        self,
        mock_ensure_etf_ready,
    ):
        mock_ensure_etf_ready.return_value = {"requested": 1, "ready": 1}

        from data_readiness import ensure_fund_screen_ready

        result = ensure_fund_screen_ready([{"code": "510300"}], history_days=365)
        assert result["requested"] == 1
        mock_ensure_etf_ready.assert_called_once_with(
            ["510300"],
            history_days=365,
            limit=0,
        )

    @patch("data_readiness.ensure_symbols_ready")
    @patch("data_readiness.ensure_pool_ready")
    @patch("data_readiness._cache")
    def test_ensure_backtest_ready_limits_prefetch_batch(
        self,
        mock_cache,
        mock_pool_ready,
        mock_symbols_ready,
    ):
        mock_pool_ready.return_value = [
            {"code": "600001", "total_market_cap": 3},
            {"code": "600002", "total_market_cap": 2},
            {"code": "600003", "total_market_cap": 1},
        ]
        mock_cache.get_daily_price.return_value = []
        mock_cache.get_market_index.return_value = [{"date": "2025-01-01"}] * 1500
        mock_symbols_ready.return_value = {"requested": 2}

        with patch("data_readiness.cfg_get") as mock_cfg:
            mock_cfg.side_effect = lambda key, default=None: {
                "data_readiness.backtest_history_days": 1500,
                "data_readiness.backtest_prefetch_batch": 2,
                "data_readiness.market_index_history_days": 1500,
            }.get(key, default)
            from data_readiness import ensure_backtest_ready

            ensure_backtest_ready("A")

        mock_symbols_ready.assert_called_once()
        args, kwargs = mock_symbols_ready.call_args
        assert args[0] == ["600001", "600002", "600003"]
        assert kwargs["limit"] == 2

    @patch("data_readiness.get_stock_pool")
    def test_build_symbol_quality_summary_uses_metadata(self, mock_pool):
        mock_pool.return_value = [
            {
                "code": "600519",
                "metadata_source": "manual",
                "metadata_status": "active",
                "metadata_completeness": 1.0,
            }
        ]

        from data_readiness import build_symbol_quality_summary

        result = build_symbol_quality_summary(
            "600519",
            "A",
            {
                "history_ready": True,
                "fundamentals_after": True,
                "fundamentals_required": True,
                "covered_through": datetime.now().strftime("%Y-%m-%d"),
                "errors": [],
            },
        )

        assert result["confidence"]["level"] in {"high", "medium"}
        assert result["provenance"]["source"] == "manual"
