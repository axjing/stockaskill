import pytest
from models import (
    Signal, Market, StockInfo, KlineData, FactorSnapshot,
    FactorResult, StrategySignal, Position, Portfolio, FundInfo,
    ThemeCandidate, ThemeLayerFinding, ThemeResearchReport, ThesisPostmortem,
    ThesisRecord, WorkflowManifest, WorkflowManifestStep, WorkflowRecommendation,
    WorkflowRunPlan, WorkflowStep,
)


class TestEnums:
    def test_signal_values(self):
        assert Signal.BUY.value == "BUY"
        assert Signal.SELL.value == "SELL"
        assert Signal.HOLD.value == "HOLD"

    def test_signal_comparison(self):
        assert Signal.BUY == Signal("BUY")
        assert Signal.SELL != Signal.HOLD

    def test_market_values(self):
        assert Market.A.value == "A"
        assert Market.HK.value == "HK"
        assert Market.US.value == "US"
        assert Market.FUND.value == "FUND"


class TestStockInfo:
    def test_minimal(self):
        s = StockInfo(code="601318", name="PingAn", market="A")
        assert s.code == "601318"
        assert s.name == "PingAn"
        assert s.market == "A"
        assert s.is_active is True

    def test_full(self):
        s = StockInfo(
            code="000858", name="Wuliangye", market="A",
            sector="Food", industry="Baijiu",
            list_date="1998-04-27", total_market_cap=5e11,
            is_active=True,
        )
        assert s.sector == "Food"
        assert s.industry == "Baijiu"
        assert s.list_date == "1998-04-27"
        assert s.total_market_cap == 5e11

    def test_default_sector(self):
        s = StockInfo(code="601318", name="Test", market="A")
        assert s.sector == ""


class TestKlineData:
    def test_creation(self):
        k = KlineData(
            date="2025-01-01", open=10.0, high=11.0,
            low=9.5, close=10.5, volume=1e6, amount=1.05e7,
        )
        assert k.date == "2025-01-01"
        assert k.close == 10.5
        assert k.volume == 1e6

    def test_types(self):
        k = KlineData(
            date="2025-01-01", open=10.0, high=11.0,
            low=9.0, close=10.0, volume=1e6, amount=1e7,
        )
        assert isinstance(k.open, float)
        assert isinstance(k.high, float)


class TestFactorSnapshot:
    def test_creation(self):
        fs = FactorSnapshot(
            code="601318", date="2025-01-01",
            pe_ttm=8.5, pb=0.95, roe=0.15,
            market_cap=1.2e12,
        )
        assert fs.code == "601318"
        assert fs.pe_ttm == 8.5
        assert fs.roe == 0.15

    def test_defaults(self):
        fs = FactorSnapshot(code="601318", date="2025-01-01")
        assert fs.market_cap == 0.0
        assert fs.pe_ttm == 0.0
        assert fs.roe == 0.0
        assert fs.dividend_yield == 0.0


class TestFactorResult:
    def test_creation(self):
        fr = FactorResult(name="value", score=0.75, weight=0.18)
        assert fr.name == "value"
        assert fr.score == 0.75
        assert fr.weight == 0.18
        assert fr.detail == {}

    def test_default_detail(self):
        fr = FactorResult(name="value", score=0.5)
        assert fr.detail == {}


class TestStrategySignal:
    def test_creation(self):
        ss = StrategySignal(
            strategy_name="multi_factor", signal=Signal.BUY, score=75,
        )
        assert ss.strategy_name == "multi_factor"
        assert ss.signal == Signal.BUY
        assert ss.score == 75
        assert ss.confidence == 0.5

    def test_with_detail(self):
        ss = StrategySignal(
            strategy_name="deep_value", signal=Signal.BUY, score=80,
            confidence=0.8, detail={"pe": 8.0, "pb": 0.9},
        )
        assert ss.confidence == 0.8
        assert ss.detail["pe"] == 8.0


class TestPosition:
    def test_creation(self):
        p = Position(
            code="601318", name="PingAn", market="A",
            weight=0.15, shares=1000, cost=62.5, current_price=63.0,
        )
        assert p.code == "601318"
        assert p.shares == 1000
        assert p.weight == 0.15

    def test_defaults(self):
        p = Position(code="601318")
        assert p.market == "A"
        assert p.weight == 0.0
        assert p.shares == 0


class TestPortfolio:
    def test_empty_portfolio(self):
        p = Portfolio(name="Test", capital=1000000)
        assert p.name == "Test"
        assert p.capital == 1000000
        assert p.positions == []
        assert p.metrics == {}

    def test_with_positions(self):
        pos = [
            Position(code="601318", name="PingAn", weight=0.4, shares=5000, cost=60.0, current_price=62.0),
            Position(code="000858", name="Wuliangye", weight=0.6, shares=3000, cost=150.0, current_price=155.0),
        ]
        p = Portfolio(name="Test", capital=1000000, positions=pos)
        assert len(p.positions) == 2

    def test_summary_contains_keys(self):
        pos = [Position(code="601318", name="PingAn", weight=0.5, shares=5000, cost=60.0, current_price=62.0)]
        p = Portfolio(name="Test", capital=1000000, positions=pos)
        summary = p.summary()
        assert "Portfolio: Test" in summary
        assert "Capital: 1,000,000" in summary
        assert "601318" in summary

    def test_summary_with_metrics(self):
        pos = [Position(code="601318", name="PingAn", weight=1.0, shares=5000, cost=60.0, current_price=62.0)]
        p = Portfolio(name="Test", capital=1000000, positions=pos, metrics={"sharpe": 1.5, "volatility": 0.2})
        summary = p.summary()
        assert "sharpe" in summary


class TestFundInfo:
    def test_creation(self):
        fi = FundInfo(
            code="510050", name="CSI 300 ETF",
            fund_type="ETF", nav=4.5, acc_nav=4.8,
            scale=5e10, track_index="000300",
        )
        assert fi.code == "510050"
        assert fi.fund_type == "ETF"
        assert fi.nav == 4.5

    def test_defaults(self):
        fi = FundInfo(code="510050", name="Test")
        assert fi.fund_type == ""
        assert fi.scale == 0.0


class TestWorkflowRecommendation:
    def test_to_dict(self):
        recommendation = WorkflowRecommendation(
            intent="opportunity_scan",
            market="A",
            summary="test",
            steps=[
                WorkflowStep(
                    title="step1",
                    command="python stockaskill/scripts/run.py market-regime A",
                    purpose="check posture",
                )
            ],
        )

        payload = recommendation.to_dict()

        assert payload["intent"] == "opportunity_scan"
        assert payload["steps"][0]["title"] == "step1"


class TestWorkflowManifest:
    def test_to_dict(self):
        manifest = WorkflowManifest(
            name="market-regime-daily",
            summary="test",
            steps=[
                WorkflowManifestStep(
                    title="step1",
                    command="python stockaskill/scripts/run.py market-regime --market {market}",
                    purpose="check posture",
                )
            ],
        )

        payload = manifest.to_dict()

        assert payload["name"] == "market-regime-daily"
        assert payload["steps"][0]["title"] == "step1"


class TestWorkflowRunPlan:
    def test_to_dict(self):
        plan = WorkflowRunPlan(
            name="portfolio-review-weekly",
            summary="test",
            description="desc",
            market="A",
            manifest_path="stockaskill/workflows/portfolio-review-weekly.yaml",
            missing_params=["codes"],
            steps=[
                WorkflowManifestStep(
                    title="step1",
                    command="python stockaskill/scripts/run.py portfolio --codes {codes}",
                    purpose="review portfolio",
                )
            ],
        )

        payload = plan.to_dict()

        assert payload["market"] == "A"
        assert payload["missing_params"] == ["codes"]


class TestThesisRecord:
    def test_to_dict_includes_postmortem(self):
        record = ThesisRecord(
            thesis_id="A_601318_20260702_000000",
            code="601318",
            market="A",
            created_at="2026-07-02T00:00:00Z",
            source="diagnose",
            thesis_status="closed",
            signal="BUY",
            score=72.0,
            confidence_level="high",
            confidence_score=0.81,
            summary="test summary",
            postmortem=ThesisPostmortem(
                outcome="win",
                reviewed_at="2026-07-03T00:00:00Z",
                notes="worked",
            ),
        )

        payload = record.to_dict()

        assert payload["postmortem"]["outcome"] == "win"
        assert payload["signal"] == "BUY"


class TestThemeResearchReport:
    def test_to_dict(self):
        report = ThemeResearchReport(
            theme="AI基础设施",
            resolved_theme="ai_infra",
            market="A",
            summary="先看先进封装",
            key_question="卡点在哪一层",
            layers=[
                ThemeLayerFinding(
                    layer="先进封装与测试",
                    scarce_layer="先进封装设备/测试验证",
                    rank=1,
                    score=88.0,
                    why_here="更接近扩产瓶颈",
                    candidates=[
                        ThemeCandidate(
                            code="300001",
                            name="测试公司",
                            layer="先进封装与测试",
                            layer_rank=1,
                            score=75.0,
                            market="A",
                        )
                    ],
                )
            ],
        )

        payload = report.to_dict()

        assert payload["resolved_theme"] == "ai_infra"
        assert payload["layers"][0]["candidates"][0]["code"] == "300001"
