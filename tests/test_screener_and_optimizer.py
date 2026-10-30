"""Tests for DuckDBScreener and TargetPortfolioOptimizer."""

from unittest.mock import MagicMock, patch

from advisor.screener_duckdb import DuckDBScreener
from portfolio.target_optimizer import TargetPortfolioOptimizer


class TestDuckDBScreener:
    """Unit tests for DuckDBScreener."""

    @patch("advisor.screener_duckdb.get_cache")
    def test_screen_momentum(self, mock_get_cache):
        mock_cache = MagicMock()
        mock_engine = MagicMock()
        mock_engine.fetchall.return_value = [
            {
                "code": "600519",
                "name": "贵州茅台",
                "sector": "消费",
                "industry": "白酒",
                "market_cap": 20000.0,
                "latest_date": "2026-10-30",
                "current_price": 1800.0,
                "ret_20d": 0.05,
                "ret_60d": 0.15,
                "ret_120d": 0.25,
                "score": 0.19,
            }
        ]
        mock_cache.engine = mock_engine
        mock_get_cache.return_value = mock_cache

        screener = DuckDBScreener()
        res = screener.screen(market="A", preset="momentum_enhanced", top_n=5)
        assert len(res) == 1
        assert res[0]["code"] == "600519"
        assert res[0]["score"] == 19.0
        assert "ret_60d" in res[0]["metrics"]

    @patch("advisor.screener_duckdb.get_cache")
    def test_screen_low_vol(self, mock_get_cache):
        mock_cache = MagicMock()
        mock_engine = MagicMock()
        mock_engine.fetchall.return_value = [
            {
                "code": "600900",
                "name": "长江电力",
                "sector": "公用事业",
                "industry": "电力",
                "market_cap": 6000.0,
                "latest_date": "2026-10-30",
                "current_price": 28.0,
                "ann_vol": 0.15,
                "score": 6.6,
            }
        ]
        mock_cache.engine = mock_engine
        mock_get_cache.return_value = mock_cache

        screener = DuckDBScreener()
        res = screener.screen(market="A", preset="low_vol", top_n=5)
        assert len(res) == 1
        assert res[0]["code"] == "600900"
        assert res[0]["metrics"]["annualized_vol"] == 15.0


class TestTargetPortfolioOptimizer:
    """Unit tests for TargetPortfolioOptimizer."""

    @patch("portfolio.target_optimizer.DuckDBScreener")
    @patch("portfolio.target_optimizer.get_cache")
    def test_insufficient_candidates(self, mock_get_cache, mock_screener_cls):
        mock_screener = MagicMock()
        mock_screener.screen.return_value = [{"code": "600519", "name": "贵州茅台"}]
        mock_screener_cls.return_value = mock_screener

        opt = TargetPortfolioOptimizer()
        res = opt.optimize(target_cagr=0.08, max_drawdown_limit=0.05, top_k=5)
        assert res["success"] is False
        assert "Candidate pool size" in res["message"]

    @patch("portfolio.target_optimizer.DuckDBScreener")
    @patch("portfolio.target_optimizer.get_cache")
    def test_optimization_success(self, mock_get_cache, mock_screener_cls):
        mock_screener = MagicMock()
        mock_screener.screen.side_effect = [
            [
                {"code": f"60000{i}", "name": f"Stock{i}", "current_price": 10.0}
                for i in range(1, 4)
            ],
            [
                {"code": f"60000{i}", "name": f"Stock{i}", "current_price": 10.0}
                for i in range(4, 7)
            ],
        ]
        mock_screener_cls.return_value = mock_screener

        mock_cache = MagicMock()
        mock_engine = MagicMock()
        mock_rows = []
        for day in range(1, 70):
            d_str = f"2025-01-{day:02d}" if day <= 31 else f"2025-02-{day - 31:02d}"
            for i in range(1, 6):
                # Gentle upward drift for test
                mock_rows.append(
                    {
                        "code": f"60000{i}",
                        "date": d_str,
                        "close": 10.0 + (day * 0.05 * (i % 2 + 1)),
                    }
                )
        mock_engine.fetchall.return_value = mock_rows
        mock_cache.engine = mock_engine
        mock_get_cache.return_value = mock_cache

        opt = TargetPortfolioOptimizer()
        res = opt.optimize(
            target_cagr=0.05,
            max_drawdown_limit=0.10,
            top_k=5,
            market="A",
            lookback_years=2,
        )
        assert res["success"] is True
        assert len(res["allocation"]["holdings"]) == 5
        assert res["performance"]["cagr"] > 0
