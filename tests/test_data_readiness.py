from datetime import datetime
from unittest.mock import patch


class TestDataReadiness:
    @patch("data_readiness.get_fundamentals")
    @patch("data_readiness.get_kline")
    @patch("data_readiness._cache")
    def test_ensure_symbol_ready_uses_local_cache(
        self,
        mock_cache,
        mock_get_kline,
        mock_get_fundamentals,
    ):
        mock_cache.get_daily_price.return_value = [{"date": "2025-01-01"}] * 400
        mock_cache.get_latest_factor_snapshot.return_value = {
            "date": datetime.now().strftime("%Y-%m-%d")
        }

        from data_readiness import ensure_symbol_ready

        result = ensure_symbol_ready("600519", "A", history_days=365)
        assert result["history_ready"] is True
        assert result["fundamentals_after"] is True
        mock_get_kline.assert_not_called()
        mock_get_fundamentals.assert_not_called()

    @patch("data_readiness.get_fundamentals")
    @patch("data_readiness.get_kline")
    @patch("data_readiness._cache")
    def test_ensure_symbol_ready_fetches_missing_data(
        self,
        mock_cache,
        mock_get_kline,
        mock_get_fundamentals,
    ):
        mock_cache.get_daily_price.side_effect = [
            [],
            [{"date": "2025-01-01"}] * 365,
        ]
        mock_cache.get_latest_factor_snapshot.side_effect = [None, {
            "date": datetime.now().strftime("%Y-%m-%d")
        }]

        from data_readiness import ensure_symbol_ready

        result = ensure_symbol_ready("600519", "A", history_days=365)
        assert result["history_ready"] is True
        assert result["fundamentals_after"] is True
        mock_get_kline.assert_called_once()
        mock_get_fundamentals.assert_called_once()

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
