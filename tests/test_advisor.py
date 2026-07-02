from unittest.mock import MagicMock, patch

from cache import CacheManager
from config import load_config

load_config()

mock_pool = [
    {
        "code": "601318",
        "name": "PingAn",
        "market": "A",
        "sector": "Finance",
        "industry": "Insurance",
        "list_date": "2007-03-01",
        "total_market_cap": 1.2e12,
    },
    {
        "code": "000858",
        "name": "Wuliangye",
        "market": "A",
        "sector": "Food",
        "industry": "Baijiu",
        "list_date": "1998-04-27",
        "total_market_cap": 5e11,
    },
]

mock_kline = [
    {
        "date": f"2024-{i // 30 + 1:02d}-{(i % 30) + 1:02d}",
        "open": 60.0,
        "high": 61.0,
        "low": 59.0,
        "close": 60.5,
        "volume": 1e7,
        "amount": 6e8,
    }
    for i in range(250)
]

mock_fundamentals = {
    "code": "601318",
    "date": "2025-01-01",
    "market_cap": 1.2e12,
    "pe_ttm": 8.5,
    "pb": 0.95,
    "dividend_yield": 4.2,
    "roe": 0.15,
    "roa": 0.05,
    "gross_margin": 0.35,
    "net_margin": 0.20,
    "revenue_growth": 0.12,
    "profit_growth": 0.15,
    "debt_ratio": 0.40,
    "current_ratio": 1.5,
    "eps": 8.0,
    "bvps": 50.0,
}


class TestMarketScanner:
    @patch("advisor.scanner.get_stock_pool", return_value=mock_pool)
    @patch("advisor.scanner.ensure_stock_pool_candidates_ready")
    @patch("advisor.scanner.ensure_market_scan_ready")
    @patch("advisor.scanner.CompositeAnalyzer")
    def test_scan_top_returns_list(
        self,
        mock_analyzer,
        mock_ready,
        mock_meta_ready,
        mock_pool_fn,
    ):
        mock_meta_ready.return_value = {
            "requested": 2,
            "already_ready": 2,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 0,
            "missing_market_cap": 0,
            "metadata_complete": 2,
            "metadata_partial": 0,
            "inactive_count": 0,
        }
        mock_ready.return_value = {
            "requested": 2,
            "ready": 2,
            "history_ready": 2,
            "fundamentals_ready": 2,
            "cache_hits": 2,
            "missing_codes": [],
        }
        mock_analyzer.return_value.analyze.return_value = {
            "total_score": 72,
            "factors": {"quality": 0.8},
            "f_score": 6,
        }
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        results = scanner.scan_top("A", top_n=10)
        assert isinstance(results, list)

    @patch("advisor.scanner.get_stock_pool", return_value=mock_pool)
    @patch("advisor.scanner.ensure_stock_pool_candidates_ready")
    @patch("advisor.scanner.ensure_market_scan_ready")
    @patch("advisor.scanner.CompositeAnalyzer")
    def test_scan_top_result_has_keys(
        self,
        mock_analyzer,
        mock_ready,
        mock_meta_ready,
        mock_pool_fn,
    ):
        mock_meta_ready.return_value = {
            "requested": 2,
            "already_ready": 2,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 0,
            "missing_market_cap": 0,
            "metadata_complete": 2,
            "metadata_partial": 0,
            "inactive_count": 0,
        }
        mock_ready.return_value = {
            "requested": 2,
            "ready": 2,
            "history_ready": 2,
            "fundamentals_ready": 2,
            "cache_hits": 2,
            "missing_codes": [],
        }
        mock_analyzer.return_value.analyze.return_value = {
            "total_score": 72,
            "factors": {"quality": 0.8},
            "f_score": 6,
        }
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

    @patch("advisor.scanner.get_stock_pool")
    @patch("advisor.scanner.ensure_stock_pool_candidates_ready")
    @patch("advisor.scanner.ensure_market_scan_ready")
    @patch("advisor.scanner.CompositeAnalyzer")
    def test_scan_top_skips_inactive_symbols(
        self,
        mock_analyzer,
        mock_ready,
        mock_meta_ready,
        mock_pool_fn,
    ):
        mock_pool_fn.return_value = [
            {
                "code": "601318",
                "name": "PingAn",
                "market": "A",
                "sector": "Finance",
                "industry": "Insurance",
                "list_date": "2007-03-01",
                "total_market_cap": 1.2e12,
                "is_active": 1,
            },
            {
                "code": "000001",
                "name": "Delisted Test",
                "market": "A",
                "sector": "Finance",
                "industry": "Bank",
                "list_date": "2001-01-01",
                "total_market_cap": 9e11,
                "is_active": 0,
            },
        ]
        mock_meta_ready.return_value = {
            "requested": 1,
            "already_ready": 1,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 0,
            "missing_market_cap": 0,
            "metadata_complete": 1,
            "metadata_partial": 0,
            "inactive_count": 0,
        }
        mock_ready.return_value = {
            "requested": 1,
            "ready": 1,
            "history_ready": 1,
            "fundamentals_ready": 1,
            "cache_hits": 1,
            "missing_codes": [],
        }
        mock_analyzer.return_value.analyze.return_value = {
            "total_score": 72,
            "factors": {"quality": 0.8},
            "f_score": 6,
        }
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        results = scanner.scan_top("A", top_n=10)

        assert len(results) == 1
        assert results[0]["code"] == "601318"

    @patch("advisor.scanner.get_stock_pool")
    @patch("advisor.scanner.ensure_market_scan_ready")
    @patch("advisor.scanner.CompositeAnalyzer")
    def test_scan_top_prefers_better_metadata_for_hk_us(
        self,
        mock_analyzer,
        mock_ready,
        mock_pool_fn,
    ):
        pool = [
            {
                "code": "AAPL",
                "name": "Apple",
                "market": "US",
                "sector": "Tech",
                "industry": "Hardware",
                "list_date": "2000-01-01",
                "total_market_cap": 3e12,
                "is_active": 1,
                "metadata_completeness": 0.25,
                "metadata_source": "akshare_stock_us_spot",
                "metadata_status": "active",
            },
            {
                "code": "MSFT",
                "name": "Microsoft",
                "market": "US",
                "sector": "Tech",
                "industry": "Software",
                "list_date": "2000-01-01",
                "total_market_cap": 2.8e12,
                "is_active": 1,
                "metadata_completeness": 1.0,
                "metadata_source": "akshare_stock_us_spot",
                "metadata_status": "active",
            },
        ]
        mock_pool_fn.side_effect = [pool, pool]
        mock_ready.return_value = {
            "requested": 2,
            "ready": 2,
            "history_ready": 2,
            "fundamentals_ready": 2,
            "cache_hits": 2,
            "missing_codes": [],
        }
        mock_analyzer.return_value.analyze.return_value = {
            "total_score": 70,
            "factors": {"quality": 0.8},
            "f_score": 6,
        }
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        results = scanner.scan_top("US", top_n=2)

        assert results[0]["code"] == "MSFT"
        assert results[0]["metadata_penalty"] == 0
        assert results[1]["metadata_penalty"] > 0

    @patch("advisor.scanner.get_stock_pool", return_value=[])
    def test_scan_top_empty_pool(self, mock_pool_fn):
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        results = scanner.scan_top("A", top_n=10)
        assert results == []

    @patch("advisor.scanner.get_stock_pool", return_value=mock_pool)
    @patch("advisor.scanner.ensure_stock_pool_candidates_ready")
    @patch("advisor.scanner.ensure_market_scan_ready")
    @patch("advisor.scanner.CompositeAnalyzer")
    def test_scan_sorted_by_score(
        self,
        mock_analyzer,
        mock_ready,
        mock_meta_ready,
        mock_pool_fn,
    ):
        mock_meta_ready.return_value = {
            "requested": 2,
            "already_ready": 2,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 0,
            "missing_market_cap": 0,
            "metadata_complete": 2,
            "metadata_partial": 0,
            "inactive_count": 0,
        }
        mock_ready.return_value = {
            "requested": 2,
            "ready": 2,
            "history_ready": 2,
            "fundamentals_ready": 2,
            "cache_hits": 2,
            "missing_codes": [],
        }
        mock_analyzer.return_value.analyze.side_effect = [
            {"total_score": 90, "factors": {"quality": 0.9}, "f_score": 8},
            {"total_score": 60, "factors": {"quality": 0.6}, "f_score": 5},
        ]
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        results = scanner.scan_top("A", top_n=10)
        if len(results) >= 2:
            scores = [r["total_score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    @patch("advisor.scanner.get_stock_pool", return_value=mock_pool)
    @patch("advisor.scanner.ensure_stock_pool_candidates_ready")
    @patch("advisor.scanner.ensure_market_scan_ready")
    @patch("advisor.scanner.CompositeAnalyzer")
    def test_scan_by_sector(
        self,
        mock_analyzer,
        mock_ready,
        mock_meta_ready,
        mock_pool_fn,
    ):
        mock_meta_ready.return_value = {
            "requested": 2,
            "already_ready": 2,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 0,
            "missing_market_cap": 0,
            "metadata_complete": 2,
            "metadata_partial": 0,
            "inactive_count": 0,
        }
        mock_ready.return_value = {
            "requested": 2,
            "ready": 2,
            "history_ready": 2,
            "fundamentals_ready": 2,
            "cache_hits": 2,
            "missing_codes": [],
        }
        mock_analyzer.return_value.analyze.return_value = {
            "total_score": 72,
            "factors": {"quality": 0.8},
            "f_score": 6,
        }
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        result = scanner.scan_by_sector("A", top_n=5)
        assert isinstance(result, dict)

    @patch("data_engine.get_etf_pool")
    def test_scan_funds_is_etf_only(self, mock_get_etf_pool):
        mock_get_etf_pool.return_value = [
            {"code": "510300", "fund_type": "ETF", "scale": 100.0},
            {"code": "159915", "fund_type": "ETF", "scale": 80.0},
        ]
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()

        assert scanner.scan_funds("LOF", top_n=5) == []
        etfs = scanner.scan_funds("ETF", top_n=5)

        assert [item["code"] for item in etfs] == ["510300", "159915"]

    @patch("advisor.scanner.get_stock_pool")
    @patch("advisor.scanner.ensure_stock_pool_candidates_ready")
    @patch("advisor.scanner.ensure_market_scan_ready")
    @patch("advisor.scanner.CompositeAnalyzer")
    def test_scan_top_keeps_candidates_with_unknown_list_date(
        self,
        mock_analyzer,
        mock_ready,
        mock_meta_ready,
        mock_pool_fn,
    ):
        mock_pool_fn.side_effect = [
            [
                {
                    "code": "601318",
                    "name": "PingAn",
                    "market": "A",
                    "sector": "Finance",
                    "industry": "Insurance",
                    "list_date": "",
                    "total_market_cap": 0.0,
                }
            ],
            [
                {
                    "code": "601318",
                    "name": "PingAn",
                    "market": "A",
                    "sector": "Finance",
                    "industry": "Insurance",
                    "list_date": "",
                    "total_market_cap": 0.0,
                }
            ],
        ]
        mock_meta_ready.return_value = {
            "requested": 1,
            "already_ready": 0,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 1,
            "missing_market_cap": 1,
        }
        mock_ready.return_value = {
            "requested": 1,
            "ready": 1,
            "history_ready": 1,
            "fundamentals_ready": 1,
            "cache_hits": 0,
            "missing_codes": [],
        }
        mock_analyzer.return_value.analyze.return_value = {
            "total_score": 72,
            "factors": {"quality": 0.8},
            "f_score": 6,
        }

        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        results = scanner.scan_top("A", top_n=10)

        assert len(results) == 1
        mock_meta_ready.assert_called_once()

    @patch("advisor.scanner.get_stock_pool")
    @patch("advisor.scanner.get_cache")
    def test_scan_snapshot_reads_cached_rows(
        self,
        mock_cache_factory,
        mock_pool_fn,
        tmp_path,
    ):
        cache = CacheManager(tmp_path / "snapshot.db")
        cache.upsert_market_scan_snapshot(
            [
                {
                    "market": "A",
                    "trade_date": "2026-06-30",
                    "code": "601318",
                    "eligible": 1,
                    "composite_score": 82.1,
                    "f_score": 7,
                    "value_score": 0.7,
                    "quality_score": 0.8,
                    "growth_score": 0.75,
                    "momentum_score": 0.73,
                    "low_vol_score": 0.66,
                    "size_score": 0.54,
                    "has_list_date": 1,
                    "has_fundamentals": 1,
                    "has_history": 1,
                    "is_st": 0,
                    "is_bj": 0,
                    "is_new_listing": 0,
                    "rank_score": 1.0,
                    "ineligible_reason": "",
                    "created_at": "2026-06-30 09:00:00",
                }
            ]
        )
        mock_cache_factory.return_value = cache
        mock_pool_fn.return_value = [
            {
                "code": "601318",
                "name": "PingAn",
                "market": "A",
                "sector": "Finance",
                "industry": "Insurance",
                "list_date": "2007-03-01",
                "total_market_cap": 1.2e12,
            }
        ]

        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        payload = scanner.scan_snapshot("A", top_n=5)

        assert payload["summary"] is not None
        assert payload["results"][0]["code"] == "601318"
        assert payload["results"][0]["name"] == "PingAn"
        assert payload["results"][0]["factors"]["quality"] == 0.8

    def test_print_readiness_summary(self, capsys):
        from advisor.scanner import MarketScanner

        MarketScanner._print_readiness_summary(
            {
                "requested": 3,
                "ready": 2,
                "history_ready": 3,
                "fundamentals_ready": 2,
                "cache_hits": 1,
                "missing_codes": ["000001"],
            }
        )
        output = capsys.readouterr().out
        assert "Candidate readiness: ready=2/3" in output
        assert "Candidate missing data: 000001" in output

    def test_print_pool_metadata_status_includes_completeness(self, capsys):
        from advisor.scanner import MarketScanner

        MarketScanner._print_pool_metadata_status(
            {
                "requested": 3,
                "already_ready": 3,
                "profile_backfilled": 0,
                "cached_history_backfilled": 0,
                "remote_history_backfilled": 0,
                "still_missing_list_date": 0,
                "metadata_complete": 2,
                "metadata_partial": 1,
                "inactive_count": 1,
            }
        )
        output = capsys.readouterr().out
        assert "complete=2" in output
        assert "partial=1" in output
        assert "inactive=1" in output

    def test_print_metadata_quality_summary(self, capsys):
        from advisor.scanner import MarketScanner

        MarketScanner._print_metadata_quality_summary(
            {"complete": 2, "partial": 1, "low": 3},
            label="candidate",
        )
        output = capsys.readouterr().out
        assert "Candidate metadata quality: complete=2, partial=1, low=3" in output

    @patch("advisor.scanner.get_fundamentals")
    @patch("advisor.scanner.get_kline")
    @patch("advisor.scanner.ensure_stock_pool_candidates_ready")
    @patch("advisor.scanner.get_stock_pool")
    @patch("advisor.scanner.get_cache")
    def test_refresh_snapshot_marks_ineligible_reasons(
        self,
        mock_cache_factory,
        mock_pool_fn,
        mock_meta_ready,
        mock_get_kline,
        mock_get_fundamentals,
        tmp_path,
    ):
        cache = CacheManager(tmp_path / "refresh_snapshot.db")
        mock_cache_factory.return_value = cache
        pool = [
            {
                "code": "601318",
                "name": "PingAn",
                "market": "A",
                "sector": "Finance",
                "industry": "Insurance",
                "list_date": "2007-03-01",
                "total_market_cap": 1.2e12,
            },
            {
                "code": "000001",
                "name": "NoDateGap",
                "market": "A",
                "sector": "Finance",
                "industry": "Bank",
                "list_date": "",
                "total_market_cap": 8e11,
            },
            {
                "code": "000002",
                "name": "NoFundamentals",
                "market": "A",
                "sector": "RealEstate",
                "industry": "Developer",
                "list_date": "2005-01-01",
                "total_market_cap": 0.0,
            },
            {
                "code": "000003",
                "name": "ShortBars",
                "market": "A",
                "sector": "Tech",
                "industry": "Software",
                "list_date": "2010-01-01",
                "total_market_cap": 5e11,
            },
        ]
        mock_pool_fn.return_value = pool
        mock_meta_ready.return_value = {
            "requested": 4,
            "already_ready": 3,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 1,
            "missing_market_cap": 1,
        }

        full_history = mock_kline[:250]
        short_history = mock_kline[:100]

        def fake_kline(code, market="A", days=365, cached_only=False):
            if code == "000003":
                return short_history
            return full_history

        def fake_fundamentals(code, market="A", force_refresh=False, cached_only=False):
            if code == "000002":
                return {}
            payload = dict(mock_fundamentals)
            payload["code"] = code
            payload["market_cap"] = 1.2e12 if code == "601318" else 5e11
            return payload

        mock_get_kline.side_effect = fake_kline
        mock_get_fundamentals.side_effect = fake_fundamentals

        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        summary = scanner.refresh_snapshot("A")
        snapshot_rows = cache.get_market_scan_snapshot(
            "A",
            trade_date=summary["trade_date"],
            include_ineligible=True,
        )
        row_by_code = {row["code"]: row for row in snapshot_rows}

        assert summary["eligible_count"] == 1
        assert summary["filtered_count"] == 3
        assert summary["cache_reused_count"] == 1
        assert summary["missing_list_date_count"] == 1
        assert summary["missing_fundamentals_count"] == 1
        assert summary["missing_history_count"] == 1
        assert row_by_code["000001"]["ineligible_reason"] == "missing_list_date"
        assert row_by_code["000002"]["ineligible_reason"] == "missing_fundamentals"
        assert row_by_code["000003"]["ineligible_reason"] == "missing_history"


class TestStockDiagnosis:
    @patch("advisor.diagnosis.ensure_symbol_analysis_ready")
    @patch("advisor.diagnosis.build_symbol_quality_summary")
    @patch("advisor.diagnosis.get_kline", return_value=mock_kline)
    @patch("advisor.diagnosis.get_fundamentals", return_value=mock_fundamentals)
    @patch("advisor.diagnosis.StrategyAggregator")
    @patch("advisor.diagnosis.CompositeAnalyzer")
    @patch("advisor.diagnosis.SentimentAggregator")
    def test_full_report_keys(
        self,
        mock_sent,
        mock_factors,
        mock_strat,
        mock_fund,
        mock_k,
        mock_quality,
        mock_ready,
    ):
        mock_ready.return_value = {
            "history_ready": True,
            "fundamentals_after": True,
            "covered_through": "2026-07-02",
            "errors": [],
        }
        mock_quality.return_value = {
            "confidence": {
                "score": 0.9,
                "level": "high",
                "notes": ["元数据完整度较高"],
            },
            "provenance": {"source": "manual", "scope": "symbol"},
        }
        mock_strat_instance = MagicMock()
        mock_strat_instance.analyze_all.return_value = {
            "final_signal": "BUY",
            "final_score": 72,
            "confidence": 0.7,
            "signals": [],
        }
        mock_strat.return_value = mock_strat_instance

        mock_factors_instance = MagicMock()
        mock_factors_instance.analyze.return_value = {
            "total_score": 72,
            "factors": {},
            "f_score": 6,
        }
        mock_factors.return_value = mock_factors_instance

        mock_sent_instance = MagicMock()
        mock_sent_instance.get_sentiment_report.return_value = {
            "overall_score": 0.6,
            "adjustment_factor": 1.0,
            "stock_sentiment": 0.5,
            "market_sentiment": 0.6,
            "market_breadth": {},
            "guba": {},
        }
        mock_sent.return_value = mock_sent_instance

        from advisor.diagnosis import StockDiagnosis

        diag = StockDiagnosis("601318")
        report = diag.full_report()
        mock_ready.assert_called_once_with("601318", "A")
        assert "final_decision" in report
        assert "strategy" in report
        assert "factors" in report
        assert "sentiment" in report
        assert "technical" in report
        assert "fundamentals" in report
        assert "risks" in report
        assert "adjusted_score" in report
        assert "confidence" in report
        assert "provenance" in report
        assert "bull_case" in report["final_decision"]
        assert "bear_case" in report["final_decision"]
        assert "invalidation_conditions" in report["final_decision"]
        assert report["provenance"]["source"] == "manual"

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
        result = diag._fundamental_health(
            {
                "pe_ttm": 10,
                "pb": 1.0,
                "roe": 0.2,
                "debt_ratio": 0.3,
                "dividend_yield": 3.0,
            }
        )
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

    def test_confidence_assessment_returns_level_and_notes(self):
        from advisor.diagnosis import StockDiagnosis

        diag = StockDiagnosis("601318")
        result = diag._confidence_assessment(
            strategy={"confidence": 0.8},
            technical={"trend": "bullish"},
            fundamentals={"checks": {"valuation": "reasonable"}},
            sentiment={"adjustment_factor": 1.0},
            kline=[{"close": 1.0}] * 150,
        )

        assert result["level"] in {"high", "medium", "low"}
        assert "notes" in result
        assert "checks" in result

    def test_merge_confidence_keeps_data_quality_notes(self):
        from advisor.diagnosis import StockDiagnosis

        diag = StockDiagnosis("601318")
        result = diag._merge_confidence(
            analytical={"score": 0.8, "level": "high", "notes": ["策略一致性较高"]},
            data_quality={
                "score": 0.6,
                "level": "medium",
                "notes": ["元数据完整度较高"],
            },
        )

        assert result["score"] > 0
        assert "元数据完整度较高" in result["notes"]
        assert "data_quality" in result

    def test_final_decision_contains_explicit_cases(self):
        from advisor.diagnosis import StockDiagnosis

        diag = StockDiagnosis("601318")
        result = diag._final_decision(
            strategy={"final_score": 72, "confidence": 0.8},
            sentiment={"adjustment_factor": 1.05},
            factors={"factors": {"quality": 85.0, "momentum": 78.0}},
            risk={"risk_count": 1, "risks": ["high_valuation"], "risk_level": "medium"},
            technical={
                "current_price": 60.0,
                "support_20d": 55.0,
                "trend": "bullish",
            },
            fundamentals={
                "checks": {
                    "profitability": "good",
                    "valuation": "expensive",
                    "leverage": "safe",
                }
            },
            confidence={"score": 0.82, "level": "high"},
        )

        assert result["signal"] == "BUY"
        assert result["confidence_level"] == "high"
        assert result["bull_case"]
        assert result["bear_case"]
        assert result["invalidation_conditions"]
