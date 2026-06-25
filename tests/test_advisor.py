import pytest
from unittest.mock import patch, MagicMock
from config import load_config

load_config()

mock_pool = [
    {"code": "601318", "name": "PingAn", "market": "A",
     "sector": "Finance", "industry": "Insurance",
     "list_date": "2007-03-01", "total_market_cap": 1.2e12},
    {"code": "000858", "name": "Wuliangye", "market": "A",
     "sector": "Food", "industry": "Baijiu",
     "list_date": "1998-04-27", "total_market_cap": 5e11},
]

mock_kline = [
    {"date": f"2024-{i//30+1:02d}-{(i%30)+1:02d}",
     "open": 60.0, "high": 61.0, "low": 59.0, "close": 60.5,
     "volume": 1e7, "amount": 6e8}
    for i in range(250)
]

mock_fundamentals = {
    "code": "601318", "date": "2025-01-01",
    "market_cap": 1.2e12, "pe_ttm": 8.5, "pb": 0.95,
    "dividend_yield": 4.2, "roe": 0.15, "roa": 0.05,
    "gross_margin": 0.35, "net_margin": 0.20,
    "revenue_growth": 0.12, "profit_growth": 0.15,
    "debt_ratio": 0.40, "current_ratio": 1.5, "eps": 8.0, "bvps": 50.0,
}


class TestMarketScanner:
    @patch("advisor.scanner.get_stock_pool", return_value=mock_pool)
    @patch("advisor.scanner.get_kline", return_value=mock_kline)
    @patch("advisor.scanner.get_fundamentals", return_value=mock_fundamentals)
    def test_scan_top_returns_list(self, mock_fund, mock_k, mock_pool_fn):
        from advisor.scanner import MarketScanner
        scanner = MarketScanner()
        results = scanner.scan_top("A", top_n=10)
        assert isinstance(results, list)

    @patch("advisor.scanner.get_stock_pool", return_value=mock_pool)
    @patch("advisor.scanner.get_kline", return_value=mock_kline)
    @patch("advisor.scanner.get_fundamentals", return_value=mock_fundamentals)
    def test_scan_top_result_has_keys(self, mock_fund, mock_k, mock_pool_fn):
        from advisor.scanner import MarketScanner
        scanner = MarketScanner()
        results = scanner.scan_top("A", top_n=10)
        if results:
            item = results[0]
            assert "code" in item
            assert "name" in item
            assert "total_score" in item
            assert "factors" in item
            assert "f_score" in item

    @patch("advisor.scanner.get_stock_pool", return_value=[])
    def test_scan_top_empty_pool(self, mock_pool_fn):
        from advisor.scanner import MarketScanner
        scanner = MarketScanner()
        results = scanner.scan_top("A", top_n=10)
        assert results == []

    @patch("advisor.scanner.get_stock_pool", return_value=mock_pool)
    @patch("advisor.scanner.get_kline", return_value=mock_kline)
    @patch("advisor.scanner.get_fundamentals", return_value=mock_fundamentals)
    def test_scan_sorted_by_score(self, mock_fund, mock_k, mock_pool_fn):
        from advisor.scanner import MarketScanner
        scanner = MarketScanner()
        results = scanner.scan_top("A", top_n=10)
        if len(results) >= 2:
            scores = [r["total_score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    @patch("advisor.scanner.get_stock_pool", return_value=mock_pool)
    @patch("advisor.scanner.get_kline", return_value=mock_kline)
    @patch("advisor.scanner.get_fundamentals", return_value=mock_fundamentals)
    def test_scan_by_sector(self, mock_fund, mock_k, mock_pool_fn):
        from advisor.scanner import MarketScanner
        scanner = MarketScanner()
        result = scanner.scan_by_sector("A", top_n=5)
        assert isinstance(result, dict)


class TestStockDiagnosis:
    @patch("advisor.diagnosis.get_kline", return_value=mock_kline)
    @patch("advisor.diagnosis.get_fundamentals", return_value=mock_fundamentals)
    @patch("advisor.diagnosis.StrategyAggregator")
    @patch("advisor.diagnosis.CompositeAnalyzer")
    @patch("advisor.diagnosis.SentimentAggregator")
    def test_full_report_keys(self, mock_sent, mock_factors, mock_strat,
                              mock_fund, mock_k):
        mock_strat_instance = MagicMock()
        mock_strat_instance.analyze_all.return_value = {
            "final_signal": "BUY", "final_score": 72, "confidence": 0.7,
            "signals": [],
        }
        mock_strat.return_value = mock_strat_instance

        mock_factors_instance = MagicMock()
        mock_factors_instance.analyze.return_value = {
            "total_score": 72, "factors": {}, "f_score": 6,
        }
        mock_factors.return_value = mock_factors_instance

        mock_sent_instance = MagicMock()
        mock_sent_instance.get_sentiment_report.return_value = {
            "overall_score": 0.6, "adjustment_factor": 1.0,
            "stock_sentiment": 0.5, "market_sentiment": 0.6,
            "market_breadth": {}, "guba": {},
        }
        mock_sent.return_value = mock_sent_instance

        from advisor.diagnosis import StockDiagnosis
        diag = StockDiagnosis("601318")
        report = diag.full_report()
        assert "final_decision" in report
        assert "strategy" in report
        assert "factors" in report
        assert "sentiment" in report
        assert "technical" in report
        assert "fundamentals" in report
        assert "risks" in report
        assert "adjusted_score" in report

    def test_technical_analysis_insufficient(self):
        from advisor.diagnosis import StockDiagnosis
        diag = StockDiagnosis("601318")
        result = diag._technical_analysis([{"close": 50}] * 30)
        assert "status" in result
        assert result["status"] == "insufficient_data"

    def test_technical_analysis_sufficient(self):
        kline = [{"close": 50 + i * 0.5} for i in range(120)]
        from advisor.diagnosis import StockDiagnosis
        diag = StockDiagnosis("601318")
        result = diag._technical_analysis(kline)
        assert "current_price" in result
        assert "ma5" in result
        assert "rsi_14" in result
        assert "trend" in result

    def test_fundamental_health_no_data(self):
        from advisor.diagnosis import StockDiagnosis
        diag = StockDiagnosis("601318")
        result = diag._fundamental_health({})
        assert "status" in result
        assert result["status"] == "no_data"

    def test_fundamental_health_checks(self):
        from advisor.diagnosis import StockDiagnosis
        diag = StockDiagnosis("601318")
        result = diag._fundamental_health({
            "pe_ttm": 10, "pb": 1.0, "roe": 0.2,
            "debt_ratio": 0.3, "dividend_yield": 3.0,
        })
        assert "checks" in result
        assert result["checks"]["valuation"] == "reasonable"
        assert result["checks"]["profitability"] == "good"

    def test_risk_assessment_low_risk(self):
        from advisor.diagnosis import StockDiagnosis
        diag = StockDiagnosis("601318")
        fund = {"debt_ratio": 0.3, "profit_growth": 0.1, "pe_ttm": 15}
        kline = [{"close": 50 + i * 0.1} for i in range(60)]
        result = diag._risk_assessment(fund, kline)
        assert result["risk_level"] in ("low", "medium")

    def test_risk_assessment_high_risk(self):
        from advisor.diagnosis import StockDiagnosis
        diag = StockDiagnosis("601318")
        fund = {"debt_ratio": 0.8, "profit_growth": -0.5, "pe_ttm": 80}
        kline = [{"close": 50} for _ in range(60)]
        for i in range(60):
            kline[i]["close"] = 50 + (i % 3 - 1) * 5
        result = diag._risk_assessment(fund, kline)
        assert result["risk_level"] == "high"

    def test_rsi_oversold(self):
        from advisor.diagnosis import StockDiagnosis
        diag = StockDiagnosis("601318")
        closes = list(range(71, 101))
        rsi = diag._compute_rsi(closes, 14)
        assert rsi < 50

    def test_rsi_overbought(self):
        from advisor.diagnosis import StockDiagnosis
        diag = StockDiagnosis("601318")
        closes = list(range(100, 70, -1))
        rsi = diag._compute_rsi(closes, 14)
        assert rsi > 50

    def test_rsi_insufficient_data(self):
        from advisor.diagnosis import StockDiagnosis
        diag = StockDiagnosis("601318")
        rsi = diag._compute_rsi([50, 51], 14)
        assert rsi == 50.0
