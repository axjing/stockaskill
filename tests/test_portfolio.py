from unittest.mock import patch

import numpy as np
import pytest
from models import Portfolio, Position


class TestPositionSizing:
    def test_kelly_fraction_normal(self):
        from portfolio.position import kelly_fraction
        f = kelly_fraction(0.6, 0.2, 0.1)
        assert 0 < f <= 0.25

    def test_kelly_fraction_zero_win_prob(self):
        from portfolio.position import kelly_fraction
        assert kelly_fraction(0, 0.2, 0.1) == 0.0

    def test_kelly_fraction_capped(self):
        from portfolio.position import kelly_fraction
        f = kelly_fraction(0.9, 5.0, 0.1)
        assert f <= 0.25

    def test_fixed_fraction(self):
        from portfolio.position import fixed_fraction
        size = fixed_fraction(1000000, 0.02, 0.05)
        assert size == 400000

    def test_fixed_fraction_no_stop(self):
        from portfolio.position import fixed_fraction
        size = fixed_fraction(1000000, 0.02, 0)
        assert size == 20000

    def test_compute_position_kelly(self):
        from portfolio.position import compute_position
        pos = compute_position(
            "601318", "PingAn", "A",
            capital=1000000, score=70,
            current_price=60.0, method="kelly",
        )
        assert pos.code == "601318"
        assert pos.shares >= 0
        if pos.shares > 0:
            assert pos.shares % 100 == 0

    def test_compute_position_fixed(self):
        from portfolio.position import compute_position
        pos = compute_position(
            "601318", "PingAn", "A",
            capital=1000000, score=80,
            current_price=60.0, method="fixed",
        )
        assert pos.code == "601318"
        assert pos.shares >= 0

    def test_compute_position_zero_price(self):
        from portfolio.position import compute_position
        pos = compute_position(
            "601318", "PingAn", "A",
            capital=1000000, score=70,
            current_price=0, method="kelly",
        )
        assert pos.shares == 0
        assert pos.weight == 0


class TestAllocator:
    def test_equal_weights(self):
        from portfolio.allocator import equal_weights
        w = equal_weights(4)
        assert len(w) == 4
        assert sum(w) == pytest.approx(1.0)
        assert all(v == 0.25 for v in w)

    def test_equal_weights_zero(self):
        from portfolio.allocator import equal_weights
        assert equal_weights(0) == []

    def test_signal_weighted(self):
        from portfolio.allocator import signal_weighted
        w = signal_weighted([80, 60, 40])
        assert len(w) == 3
        assert sum(w) == pytest.approx(1.0, abs=1e-6)
        assert all(v > 0 for v in w)

    def test_signal_weighted_empty(self):
        from portfolio.allocator import signal_weighted
        assert signal_weighted([]) == []

    def test_signal_weighted_all_zero(self):
        from portfolio.allocator import signal_weighted
        w = signal_weighted([0, 0, 0])
        assert len(w) == 3
        assert sum(w) == pytest.approx(1.0)

    def test_risk_parity_basic(self):
        from portfolio.allocator import risk_parity
        cov = np.array([[0.04, 0.01], [0.01, 0.09]])
        w = risk_parity(cov)
        assert len(w) == 2
        assert sum(w) == pytest.approx(1.0, abs=1e-6)

    def test_risk_parity_single_asset(self):
        from portfolio.allocator import risk_parity
        cov = np.array([[0.04]])
        w = risk_parity(cov)
        assert w == [1.0]

    def test_risk_parity_empty(self):
        from portfolio.allocator import risk_parity
        assert risk_parity(np.array([]).reshape(0, 0)) == []

    def test_min_variance(self):
        from portfolio.allocator import min_variance
        cov = np.array([[0.04, 0.01], [0.01, 0.09]])
        w = min_variance(cov)
        assert len(w) == 2
        assert sum(w) == pytest.approx(1.0, abs=1e-6)

    def test_min_variance_single(self):
        from portfolio.allocator import min_variance
        assert min_variance(np.array([[0.04]])) == [1.0]


class TestRiskMetrics:
    def test_max_drawdown(self):
        from portfolio.risk import RiskMetrics
        returns = [0.01, -0.02, 0.03, -0.05, 0.02, 0.01]
        rm = RiskMetrics(returns)
        dd = rm.max_drawdown()
        assert dd <= 0

    def test_var_95(self):
        from portfolio.risk import RiskMetrics
        returns = [0.01, -0.02, -0.03, -0.01, 0.02, -0.05, 0.01, 0.03]
        rm = RiskMetrics(returns)
        v = rm.var(0.95)
        assert v < 0

    def test_cvar_95(self):
        from portfolio.risk import RiskMetrics
        returns = [0.01, -0.02, -0.03, -0.01, 0.02, -0.05, 0.01, 0.03]
        rm = RiskMetrics(returns)
        cv = rm.cvar(0.95)
        assert cv <= 0

    def test_sharpe_ratio(self):
        from portfolio.risk import RiskMetrics
        returns = [0.001] * 252
        rm = RiskMetrics(returns, risk_free=0.03)
        sr = rm.sharpe_ratio()
        assert isinstance(sr, float)

    def test_sortino_ratio(self):
        from portfolio.risk import RiskMetrics
        returns = [0.001] * 200 + [-0.005] * 52
        rm = RiskMetrics(returns)
        sr = rm.sortino_ratio()
        assert isinstance(sr, float)

    def test_volatility(self):
        from portfolio.risk import RiskMetrics
        returns = [0.01, -0.01, 0.02, -0.02, 0.01]
        rm = RiskMetrics(returns)
        vol = rm.volatility()
        assert vol >= 0

    def test_insufficient_data(self):
        from portfolio.risk import RiskMetrics
        rm = RiskMetrics([0.01])
        assert rm.max_drawdown() == 0.0
        assert rm.var() == 0.0
        assert rm.sharpe_ratio() == 0.0

    def test_summary_keys(self):
        from portfolio.risk import RiskMetrics
        returns = [0.01, -0.02, 0.03, -0.01, 0.02, -0.05, 0.01, 0.03]
        rm = RiskMetrics(returns)
        s = rm.summary()
        expected_keys = {"max_drawdown", "var_95", "cvar_95", "var_99",
                         "cvar_99", "sharpe", "sortino", "volatility"}
        assert expected_keys.issubset(s.keys())


class TestBacktestEngine:
    def test_init(self):
        from portfolio.backtest import BacktestEngine
        bt = BacktestEngine()
        assert bt.initial_capital == 1000000
        assert bt.capital == 1000000
        assert bt.commission == 0.0003

    def test_custom_init(self):
        from portfolio.backtest import BacktestEngine
        bt = BacktestEngine(capital=500000, commission=0.001)
        assert bt.initial_capital == 500000
        assert bt.commission == 0.001

    def test_get_common_dates(self):
        from portfolio.backtest import BacktestEngine
        bt = BacktestEngine()
        kline = {
            "A": [{"date": "2025-01-01"}, {"date": "2025-01-02"}],
            "B": [
                {"date": "2025-01-01"},
                {"date": "2025-01-02"},
                {"date": "2025-01-03"},
            ],
        }
        dates = bt._get_common_dates(kline)
        assert "2025-01-01" in dates
        assert "2025-01-02" in dates
        assert "2025-01-03" not in dates

    def test_run_no_data(self):
        from portfolio.backtest import BacktestEngine
        bt = BacktestEngine()
        result = bt.run([])
        assert "error" in result


class TestPortfolioBuilder:
    @patch("portfolio.builder.ensure_symbol_analysis_ready")
    @patch("portfolio.builder.PortfolioBuilder._get_stock_info")
    @patch("portfolio.builder.get_kline")
    @patch("strategies.aggregator.StrategyAggregator.analyze_all")
    def test_manual_weight_overrides_auto(
        self,
        mock_analyze_all,
        mock_get_kline,
        mock_get_stock_info,
        mock_ready,
    ):
        mock_analyze_all.side_effect = [
            {"final_score": 90},
            {"final_score": 30},
        ]
        mock_get_kline.return_value = [{"close": 1.0}]
        mock_get_stock_info.side_effect = [
            {"name": "A"},
            {"name": "B"},
        ]

        from portfolio.builder import PortfolioBuilder

        builder = PortfolioBuilder("Test", capital=100000)
        builder.add_from_strategy("AAA", weight=0.8)
        builder.add_from_strategy("BBB")

        portfolio = builder.build(method="signal", position_method="fixed")
        weights = {position.code: position.weight for position in portfolio.positions}
        assert weights["AAA"] == pytest.approx(0.8, abs=1e-3)
        assert weights["BBB"] == pytest.approx(0.2, abs=1e-3)

    @patch("portfolio.builder.ensure_symbol_analysis_ready")
    @patch("portfolio.builder.PortfolioBuilder._get_stock_info")
    @patch("portfolio.builder.get_kline")
    @patch("strategies.aggregator.StrategyAggregator.analyze_all")
    def test_capital_fraction_reduces_allocated_weights(
        self,
        mock_analyze_all,
        mock_get_kline,
        mock_get_stock_info,
        mock_ready,
    ):
        mock_analyze_all.side_effect = [
            {"final_score": 80},
            {"final_score": 60},
        ]
        mock_get_kline.return_value = [{"close": 10.0}]
        mock_get_stock_info.side_effect = [
            {"name": "A"},
            {"name": "B"},
        ]

        from portfolio.builder import PortfolioBuilder

        builder = PortfolioBuilder("Risk Budget", capital=100000)
        builder.add_from_strategy("AAA", weight=0.5)
        builder.add_from_strategy("BBB", weight=0.5)

        portfolio = builder.build(
            method="signal",
            position_method="fixed",
            capital_fraction=0.4,
        )
        total_weight = sum(position.weight for position in portfolio.positions)
        assert total_weight == pytest.approx(0.4, abs=1e-3)


class TestRebalancer:
    def test_calendar_rebalance_due(self):
        from portfolio.rebalance import Rebalancer
        rb = Rebalancer(method="calendar", calendar="weekly")
        assert rb._calendar_check("") is True

    def test_calendar_rebalance_not_due(self):
        from portfolio.rebalance import Rebalancer
        rb = Rebalancer(method="calendar", calendar="monthly")
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert rb._calendar_check(recent) is False

    def test_threshold_rebalance(self):
        from portfolio.rebalance import Rebalancer
        rb = Rebalancer(method="threshold", threshold=0.05)
        pos = [Position(code="A", weight=0.6)]
        portfolio = Portfolio(name="Test", positions=pos)
        assert rb._threshold_check(portfolio) is True

    def test_threshold_no_rebalance(self):
        from portfolio.rebalance import Rebalancer
        rb = Rebalancer(method="threshold", threshold=0.05)
        pos = [Position(code="A", weight=0.5), Position(code="B", weight=0.5)]
        portfolio = Portfolio(name="Test", positions=pos)
        assert rb._threshold_check(portfolio) is False

    def test_hybrid_rebalance(self):
        from portfolio.rebalance import Rebalancer
        rb = Rebalancer(method="hybrid")
        portfolio = Portfolio(name="Test", positions=[
            Position(code="A", weight=1.0),
        ])
        assert rb.should_rebalance(portfolio) is True

    def test_rebalance_generates_trades(self):
        from portfolio.rebalance import Rebalancer
        rb = Rebalancer()
        pos = [
            Position(
                code="A",
                name="Stock A",
                weight=0.5,
                shares=1000,
                current_price=100,
            )
        ]
        portfolio = Portfolio(name="Test", positions=pos)
        trades = rb.rebalance(portfolio, {"A": 0.3})
        assert isinstance(trades, list)
