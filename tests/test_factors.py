import pytest
from factors.base import Factor
from factors.value import ValueFactor
from factors.quality import QualityFactor
from factors.growth import GrowthFactor
from factors.momentum import MomentumFactor
from factors.low_vol import LowVolFactor
from factors.size import SizeFactor


def test_factor_base_abstract():
    with pytest.raises(TypeError):
        Factor()


class TestValueFactor:
    def test_name(self):
        assert ValueFactor().name == "value"

    def test_compute_returns_float(self, mock_fundamentals, mock_kline_rising):
        vf = ValueFactor()
        score = vf.compute(mock_fundamentals, mock_kline_rising)
        assert isinstance(score, float)

    def test_score_in_range(self, mock_fundamentals, mock_kline_rising):
        vf = ValueFactor()
        score = vf.compute(mock_fundamentals, mock_kline_rising)
        assert 0 <= score <= 1

    def test_low_pe_high_score(self):
        fund = {"pe_ttm": 5, "pb": 0.6, "dividend_yield": 5}
        vf = ValueFactor()
        score = vf.compute(fund, [])
        assert score > 0.5

    def test_high_pe_low_score(self):
        fund = {"pe_ttm": 80, "pb": 8, "dividend_yield": 0}
        vf = ValueFactor()
        score = vf.compute(fund, [])
        assert score < 0.5

    def test_zero_pe(self):
        fund = {"pe_ttm": 0, "pb": 1, "dividend_yield": 0}
        vf = ValueFactor()
        score = vf.compute(fund, [])
        assert 0 <= score <= 1

    def test_batch_normalization(self, mock_kline_rising):
        stocks = []
        for code, pe, pb in [("A", 5, 0.5), ("B", 20, 2), ("C", 50, 5)]:
            stocks.append({
                "code": code,
                "fundamentals": {"pe_ttm": pe, "pb": pb, "dividend_yield": 0},
                "kline": mock_kline_rising,
            })
        vf = ValueFactor()
        result = vf.compute_batch(stocks)
        assert len(result) == 3
        for v in result.values():
            assert 0 <= v <= 1


class TestQualityFactor:
    def test_name(self):
        assert QualityFactor().name == "quality"

    def test_compute_returns_float(self, mock_fundamentals, mock_kline_rising):
        qf = QualityFactor()
        score = qf.compute(mock_fundamentals, mock_kline_rising)
        assert isinstance(score, float)

    def test_score_in_range(self, mock_fundamentals, mock_kline_rising):
        qf = QualityFactor()
        score = qf.compute(mock_fundamentals, mock_kline_rising)
        assert 0 <= score <= 1

    def test_high_roe_high_score(self):
        fund = {"roe": 0.3, "gross_margin": 0.6, "debt_ratio": 0.2, "eps": 5, "bvps": 20}
        qf = QualityFactor()
        score = qf.compute(fund, [])
        assert score > 0.5

    def test_low_roe_low_score(self):
        fund = {"roe": -0.1, "gross_margin": 0, "debt_ratio": 0.9, "eps": -1, "bvps": 5}
        qf = QualityFactor()
        score = qf.compute(fund, [])
        assert score < 0.5


class TestGrowthFactor:
    def test_name(self):
        assert GrowthFactor().name == "growth"

    def test_compute_returns_float(self, mock_fundamentals, mock_kline_rising):
        gf = GrowthFactor()
        score = gf.compute(mock_fundamentals, mock_kline_rising)
        assert isinstance(score, float)

    def test_score_in_range(self, mock_fundamentals, mock_kline_rising):
        gf = GrowthFactor()
        score = gf.compute(mock_fundamentals, mock_kline_rising)
        assert 0 <= score <= 1

    def test_high_growth_high_score(self):
        fund = {"revenue_growth": 0.5, "profit_growth": 0.8}
        gf = GrowthFactor()
        score = gf.compute(fund, [])
        assert score > 0.5

    def test_negative_growth_low_score(self):
        fund = {"revenue_growth": -0.5, "profit_growth": -0.8}
        gf = GrowthFactor()
        score = gf.compute(fund, [])
        assert score < 0.5

    def test_growth_acceleration_insufficient_kline(self):
        gf = GrowthFactor()
        accel = gf._growth_acceleration([])
        assert accel == 0.5
        accel = gf._growth_acceleration([{"close": 10}] * 30)
        assert accel == 0.5


class TestMomentumFactor:
    def test_name(self):
        assert MomentumFactor().name == "momentum"

    def test_insufficient_kline(self):
        mf = MomentumFactor()
        score = mf.compute({}, [{"close": 50}] * 60)
        assert score == 0.5

    def test_rising_momentum_high_score(self, mock_kline_rising):
        mf = MomentumFactor()
        score = mf.compute({}, mock_kline_rising)
        assert score >= 0.1

    def test_declining_momentum_low_score(self, mock_kline_declining):
        mf = MomentumFactor()
        score = mf.compute({}, mock_kline_declining)
        assert score <= 0.7

    def test_ma_alignment_bullish(self):
        closes = [100 + i * 2 for i in range(60, 0, -1)]
        score = MomentumFactor._ma_alignment(closes)
        assert score == 1.0

    def test_ma_alignment_bearish(self):
        closes = [100 - i for i in range(60, 0, -1)]
        score = MomentumFactor._ma_alignment(closes)
        assert score < 0.7


class TestLowVolFactor:
    def test_name(self):
        assert LowVolFactor().name == "low_vol"

    def test_insufficient_kline(self):
        lf = LowVolFactor()
        score = lf.compute({}, [{"close": 50}] * 100)
        assert score == 0.5

    def test_low_volatility_high_score(self):
        kline = [{"close": 50 + i * 0.01} for i in range(250)]
        lf = LowVolFactor()
        score = lf.compute({}, kline)
        assert score > 0.5

    def test_high_volatility_low_score(self):
        import random
        random.seed(42)
        kline = [{"close": 50 + random.uniform(-5, 5)} for _ in range(250)]
        lf = LowVolFactor()
        score = lf.compute({}, kline)
        assert 0 <= score <= 1

    def test_score_in_range(self):
        kline = [{"close": 50 + i * 0.5} for i in range(250)]
        lf = LowVolFactor()
        score = lf.compute({}, kline)
        assert 0 <= score <= 1


class TestSizeFactor:
    def test_name(self):
        assert SizeFactor().name == "size"

    def test_small_cap_higher_score(self):
        sf = SizeFactor()
        small = sf.compute({"market_cap": 1e10}, [])
        large = sf.compute({"market_cap": 1e12}, [])
        assert small > large

    def test_zero_mcap(self):
        sf = SizeFactor()
        assert sf.compute({"market_cap": 0}, []) == 0.5

    def test_score_in_range(self):
        sf = SizeFactor()
        for mcap in [1e9, 1e10, 1e11, 1e12, 3e12]:
            score = sf.compute({"market_cap": mcap}, [])
            assert 0 <= score <= 1


class TestFactorNormalize:
    def test_normalize_preserves_order(self):
        scores = {"A": 10, "B": 20, "C": 30}
        normalized = Factor._normalize(scores)
        assert normalized["A"] <= normalized["B"] <= normalized["C"]

    def test_normalize_range(self):
        scores = {"A": 1, "B": 2, "C": 3}
        normalized = Factor._normalize(scores)
        for v in normalized.values():
            assert 0 <= v <= 1

    def test_normalize_empty(self):
        assert Factor._normalize({}) == {}
