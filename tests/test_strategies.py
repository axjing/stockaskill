import pytest
from unittest.mock import patch

from models import Signal
from config import load_config
from strategies.base import Strategy
from strategies.multi_factor import MultiFactorStrategy
from strategies.deep_value import DeepValueStrategy
from strategies.garp import GARPStrategy
from strategies.ma_trend import MATrendStrategy
from strategies.contrarian import ContrarianStrategy
from strategies.aggregator import StrategyAggregator

load_config()

mock_kline_data = [
    {"date": f"2024-{i//30+1:02d}-{(i%30)+1:02d}", "open": 60.0, "high": 61.0,
     "low": 59.0, "close": 60.5, "volume": 1e7, "amount": 6e8}
    for i in range(250)
]
mock_fundamentals = {
    "code": "601318", "date": "2025-01-01",
    "market_cap": 1.2e12, "pe_ttm": 8.5, "pe_static": 8.0,
    "pb": 0.95, "dividend_yield": 4.2,
    "roe": 0.15, "roa": 0.05,
    "gross_margin": 0.35, "net_margin": 0.20,
    "revenue_growth": 0.12, "profit_growth": 0.15,
    "debt_ratio": 0.40, "current_ratio": 1.5, "eps": 8.0, "bvps": 50.0,
}


@pytest.fixture(autouse=True)
def mock_data():
    with patch("strategies.base.get_kline", return_value=mock_kline_data), \
         patch("strategies.base.get_fundamentals", return_value=mock_fundamentals), \
         patch("factors.composite.get_kline", return_value=mock_kline_data), \
         patch("factors.composite.get_fundamentals", return_value=mock_fundamentals):
        yield


class TestStrategyBase:
    def test_signal_from_score_buy(self):
        assert Strategy._signal_from_score(75) == Signal.BUY
        assert Strategy._signal_from_score(65) == Signal.BUY

    def test_signal_from_score_sell(self):
        assert Strategy._signal_from_score(25) == Signal.SELL
        assert Strategy._signal_from_score(35) == Signal.SELL

    def test_signal_from_score_hold(self):
        assert Strategy._signal_from_score(50) == Signal.HOLD
        assert Strategy._signal_from_score(40) == Signal.HOLD
        assert Strategy._signal_from_score(60) == Signal.HOLD


class TestMultiFactorStrategy:
    def test_name(self):
        assert MultiFactorStrategy().name == "multi_factor"

    def test_analyze_returns_dict(self):
        result = MultiFactorStrategy().analyze("601318")
        assert isinstance(result, dict)
        assert "strategy_name" in result
        assert "signal" in result
        assert "score" in result
        assert "confidence" in result

    def test_signal_is_valid(self):
        result = MultiFactorStrategy().analyze("601318")
        assert result["signal"] in ("BUY", "SELL", "HOLD")

    def test_score_range(self):
        result = MultiFactorStrategy().analyze("601318")
        assert 0 <= result["score"] <= 100


class TestDeepValueStrategy:
    def test_name(self):
        assert DeepValueStrategy().name == "deep_value"

    def test_analyze_returns_dict(self):
        result = DeepValueStrategy().analyze("601318")
        assert isinstance(result, dict)
        assert "detail" in result
        assert "checks" in result["detail"]

    def test_score_range(self):
        result = DeepValueStrategy().analyze("601318")
        assert 0 <= result["score"] <= 100


class TestGARPStrategy:
    def test_name(self):
        assert GARPStrategy().name == "garp"

    def test_analyze_returns_dict(self):
        result = GARPStrategy().analyze("601318")
        assert isinstance(result, dict)
        assert "peg" in result["detail"]
        assert "roe" in result["detail"]

    def test_score_range(self):
        result = GARPStrategy().analyze("601318")
        assert 0 <= result["score"] <= 100


class TestMATrendStrategy:
    def test_name(self):
        assert MATrendStrategy().name == "ma_trend"

    def test_analyze_returns_dict(self):
        result = MATrendStrategy().analyze("601318")
        assert isinstance(result, dict)
        assert "ma5" in result["detail"]
        assert "ma10" in result["detail"]

    def test_score_range(self):
        result = MATrendStrategy().analyze("601318")
        assert 0 <= result["score"] <= 100

    def test_insufficient_data(self):
        with patch("strategies.base.get_kline", return_value=[{"close": 50}] * 30):
            result = MATrendStrategy().analyze("601318")
            assert result["signal"] == "HOLD"
            assert result["score"] == 50


class TestContrarianStrategy:
    def test_name(self):
        assert ContrarianStrategy().name == "contrarian"

    def test_analyze_returns_dict(self):
        result = ContrarianStrategy().analyze("601318")
        assert isinstance(result, dict)
        assert "drawdown_60d" in result["detail"]

    def test_score_range(self):
        result = ContrarianStrategy().analyze("601318")
        assert 0 <= result["score"] <= 100

    def test_insufficient_data(self):
        with patch("strategies.base.get_kline", return_value=[{"close": 50}] * 30):
            result = ContrarianStrategy().analyze("601318")
            assert result["signal"] == "HOLD"
            assert result["score"] == 50


class TestStrategyAggregator:
    def test_analyze_all_returns_dict(self):
        result = StrategyAggregator("601318").analyze_all()
        assert isinstance(result, dict)
        assert "final_signal" in result
        assert "final_score" in result
        assert "confidence" in result
        assert "signals" in result

    def test_final_signal_valid(self):
        result = StrategyAggregator("601318").analyze_all()
        assert result["final_signal"] in ("BUY", "SELL", "HOLD")

    def test_final_score_range(self):
        result = StrategyAggregator("601318").analyze_all()
        assert 0 <= result["final_score"] <= 100

    def test_all_strategies_included(self):
        result = StrategyAggregator("601318").analyze_all()
        names = [s["strategy_name"] for s in result["signals"]]
        assert "multi_factor" in names
        assert "deep_value" in names
        assert "garp" in names
        assert "ma_trend" in names
        assert "contrarian" in names
        assert "alpha_momentum" in names
        assert len(result["signals"]) == 6

    def test_confidence_positive(self):
        result = StrategyAggregator("601318").analyze_all()
        assert 0 <= result["confidence"] <= 1
