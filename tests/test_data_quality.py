from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from cache import CacheManager
from config import load_config
from data_engine.data_quality import (
    run_data_quality_check,
    run_data_quality_repair,
)

load_config()

_TODAY = datetime.now().strftime("%Y-%m-%d")


@pytest.fixture
def cache(tmp_path):
    return CacheManager(tmp_path / "dq.db")


def _fin_row(code, report_date):
    return {
        "code": code,
        "market": "A",
        "report_date": report_date,
        "publish_date": report_date,
        "market_cap": 1e11,
        "pe_ttm": 10.0,
        "pe_static": 9.0,
        "pb": 1.0,
        "ps_ttm": 2.0,
        "pcf_ttm": 5.0,
        "dividend_yield": 3.0,
        "roe": 12.5,
        "roa": 5.0,
        "gross_margin": 30.0,
        "net_margin": 15.0,
        "revenue_growth": 10.0,
        "profit_growth": 8.0,
        "debt_ratio": 40.0,
        "current_ratio": 1.5,
        "eps": 1.0,
        "bvps": 8.0,
    }


def _days_ago(days):
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def _seed_prices(cache_obj, code, days, end_date=None, close_at=None):
    if end_date is None:
        end = datetime.now() - timedelta(days=1)
    else:
        end = datetime.strptime(end_date, "%Y-%m-%d")
    rows = []
    for i in range(days):
        day = (end - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        price = close_at(i) if close_at else 10.0 + i * 0.05
        rows.append(
            {
                "market": "A",
                "code": code,
                "date": day,
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price,
                "volume": 1e6,
                "amount": price * 1e6,
                "adj_close": price,
            }
        )
    cache_obj.upsert_daily_price(rows)


def _fresh_report(cache_obj, code, days=10):
    cache_obj.upsert_financial_report([_fin_row(code, _days_ago(days))])


class TestDataQualityCheck:
    def test_clean_symbol_reports_ok_without_audit(self, cache):
        _seed_prices(cache, "600000", 250)
        _fresh_report(cache, "600000")
        with patch("data_engine.data_quality.get_cache", return_value=cache):
            result = run_data_quality_check(market="A", codes=["600000"], limit=10)
        assert result["checked"] == 1
        assert result["ok_count"] == 1
        assert result["light_count"] == 0
        assert result["heavy_count"] == 0
        assert result["symbols"][0]["severity"] == "ok"
        assert cache.get_data_quality_log("600000", "A") == []

    def test_missing_history_and_fundamentals_flagged_heavy(self, cache):
        with patch("data_engine.data_quality.get_cache", return_value=cache):
            result = run_data_quality_check(market="A", codes=["600519"])
        assert result["heavy_count"] == 1
        issues = result["symbols"][0]["issues"]
        assert "missing_history" in issues
        assert "missing_fundamentals" in issues
        rows = cache.get_data_quality_log("600519", "A")
        assert len(rows) == 2
        by_kind = {row["data_kind"]: row for row in rows}
        assert set(by_kind) == {"history", "fundamentals"}
        for row in rows:
            assert row["action"] == "check"
            assert row["status"] == "flagged"
            assert row["severity"] == "heavy"
            assert row["repaired"] == 0
            assert row["retry_after"] in (None, "")
        assert by_kind["fundamentals"]["start_date"] == ""

    def test_kline_gap_severity_tiers(self, cache):
        anchor = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        anchor_dt = datetime.strptime(anchor, "%Y-%m-%d")
        _seed_prices(cache, "600000", 250, end_date=anchor)
        _seed_prices(
            cache,
            "600001",
            250,
            end_date=(anchor_dt - timedelta(days=40)).strftime("%Y-%m-%d"),
        )
        _seed_prices(
            cache,
            "600002",
            250,
            end_date=(anchor_dt - timedelta(days=10)).strftime("%Y-%m-%d"),
        )
        for code in ("600000", "600001", "600002"):
            _fresh_report(cache, code)
        with patch("data_engine.data_quality.get_cache", return_value=cache):
            result = run_data_quality_check(
                market="A", codes=["600000", "600001", "600002"]
            )
        by_code = {s["code"]: s for s in result["symbols"]}
        assert by_code["600000"]["severity"] == "ok"
        assert by_code["600001"]["severity"] == "heavy"
        assert "kline_gap" in by_code["600001"]["issues"]
        assert by_code["600002"]["severity"] == "light"
        assert "kline_gap" in by_code["600002"]["issues"]
        assert result["ok_count"] == 1
        assert result["heavy_count"] == 1
        assert result["light_count"] == 1
        rows = cache.get_data_quality_log("", "A")
        assert len(rows) == 2
        for row in rows:
            assert row["data_kind"] == "history"
            assert row["action"] == "check"
            assert row["end_date"] == anchor

    def test_financial_gap_severity_tiers(self, cache):
        for code in ("600000", "600001", "600002"):
            _seed_prices(cache, code, 250)
        _fresh_report(cache, "600000", days=10)
        _fresh_report(cache, "600001", days=120)
        _fresh_report(cache, "600002", days=400)
        with patch("data_engine.data_quality.get_cache", return_value=cache):
            result = run_data_quality_check(
                market="A", codes=["600000", "600001", "600002"]
            )
        by_code = {s["code"]: s for s in result["symbols"]}
        assert by_code["600000"]["severity"] == "ok"
        assert by_code["600001"]["severity"] == "light"
        assert "financial_gap" in by_code["600001"]["issues"]
        assert by_code["600002"]["severity"] == "heavy"
        assert "financial_gap" in by_code["600002"]["issues"]
        rows = cache.get_data_quality_log("", "A")
        assert len(rows) == 2
        by_code_rows = {row["code"]: row for row in rows}
        assert by_code_rows["600001"]["severity"] == "light"
        assert by_code_rows["600002"]["severity"] == "heavy"
        for row in rows:
            assert row["data_kind"] == "fundamentals"
            assert row["action"] == "check"

    def test_insufficient_history_is_light(self, cache):
        _seed_prices(cache, "600000", 100)
        _fresh_report(cache, "600000")
        with patch("data_engine.data_quality.get_cache", return_value=cache):
            result = run_data_quality_check(market="A", codes=["600000"])
        symbol = result["symbols"][0]
        assert symbol["severity"] == "light"
        assert "insufficient_history" in symbol["issues"]
        assert result["light_count"] == 1
        rows = cache.get_data_quality_log("600000", "A")
        assert len(rows) == 1
        assert rows[0]["severity"] == "light"

    def test_implausible_return_is_heavy(self, cache):
        _seed_prices(
            cache,
            "600000",
            100,
            close_at=lambda i: 20.0 if i == 95 else 10.0,
        )
        _fresh_report(cache, "600000")
        with patch("data_engine.data_quality.get_cache", return_value=cache):
            result = run_data_quality_check(market="A", codes=["600000"])
        symbol = result["symbols"][0]
        assert symbol["severity"] == "heavy"
        assert "implausible_return" in symbol["issues"]
        assert "insufficient_history" in symbol["issues"]
        rows = cache.get_data_quality_log("600000", "A")
        assert len(rows) == 1
        assert "implausible_return" in rows[0]["issue_types"]

    def test_fund_market_audits_nav_kind(self, cache):
        with patch("data_engine.data_quality.get_cache", return_value=cache):
            result = run_data_quality_check(market="FUND", codes=["510300"])
        assert result["heavy_count"] == 1
        assert "missing_history" in result["symbols"][0]["issues"]
        rows = cache.get_data_quality_log("510300", "FUND")
        assert len(rows) == 1
        assert rows[0]["data_kind"] == "nav"
        assert rows[0]["severity"] == "heavy"
        assert rows[0]["action"] == "check"

    def test_pool_scope_respects_limit(self, cache):
        pool = [{"code": "600000", "name": "A"}, {"code": "600001", "name": "B"}]
        with (
            patch("data_engine.data_quality.get_cache", return_value=cache),
            patch("data_engine.data_quality.get_stock_pool", return_value=pool),
        ):
            result = run_data_quality_check(market="A", limit=1)
        assert result["checked"] == 1
        assert len(result["symbols"]) == 1
        assert result["symbols"][0]["code"] == "600000"


class TestDataQualityRepair:
    def test_failed_repair_sets_backoff_and_audits(self, cache):
        stale = _days_ago(400)
        cache.upsert_financial_report([_fin_row("600000", stale)])
        with (
            patch("data_engine.data_quality.get_cache", return_value=cache),
            patch("data_engine.data_quality.get_fundamentals", return_value=True),
        ):
            result = run_data_quality_repair(
                market="A",
                codes=["600000"],
                data_kinds=("fundamentals",),
            )
        assert result["failed_count"] == 1
        assert result["repaired_count"] == 0
        backoff = cache.get_data_quality_backoff("600000", "A", "fundamentals")
        assert backoff is not None
        assert int(backoff["consecutive_failures"]) == 1
        rows = cache.get_data_quality_log("600000", "A")
        assert len(rows) == 1
        row = rows[0]
        assert row["action"] == "repair"
        assert row["status"] == "failed"
        assert row["repaired"] == 0
        assert row["severity"] == "heavy"
        assert row["start_date"] == stale
        assert row["issue_types"] == "financial_gap"
        assert row["error_message"] == ""
        assert row["retry_after"] not in (None, "")

    def test_backoff_skips_second_run(self, cache):
        cache.upsert_financial_report([_fin_row("600000", _days_ago(400))])
        with (
            patch("data_engine.data_quality.get_cache", return_value=cache),
            patch("data_engine.data_quality.get_fundamentals", return_value=True),
        ):
            first = run_data_quality_repair(
                market="A",
                codes=["600000"],
                data_kinds=("fundamentals",),
            )
            second = run_data_quality_repair(
                market="A",
                codes=["600000"],
                data_kinds=("fundamentals",),
            )
        assert first["failed_count"] == 1
        assert second["skipped_backoff"] == 1
        assert second["failed_count"] == 0
        assert len(cache.get_data_quality_log("600000", "A")) == 1

    def test_successful_repair_clears_expired_backoff(self, cache):
        cache.upsert_financial_report([_fin_row("600000", _days_ago(400))])
        expired = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        cache.set_data_quality_backoff("600000", "A", "fundamentals", expired, 1)
        fresh = _days_ago(10)

        def write_fresh(code, market, force_refresh=False):
            cache.upsert_financial_report([_fin_row(code, fresh)])
            return True

        with (
            patch("data_engine.data_quality.get_cache", return_value=cache),
            patch(
                "data_engine.data_quality.get_fundamentals",
                side_effect=write_fresh,
            ),
        ):
            result = run_data_quality_repair(
                market="A",
                codes=["600000"],
                data_kinds=("fundamentals",),
            )
        assert result["repaired_count"] == 1
        assert result["failed_count"] == 0
        assert cache.get_data_quality_backoff("600000", "A", "fundamentals") is None
        rows = cache.get_data_quality_log("600000", "A")
        assert len(rows) == 1
        row = rows[0]
        assert row["action"] == "repair"
        assert row["status"] == "ok"
        assert row["repaired"] == 1
        assert row["retry_after"] in (None, "")

    def test_successful_history_repair_seeds_kline(self, cache):
        def seed_history(code, market, days=0, force_refresh=False):
            _seed_prices(cache, code, 250)
            return True

        with (
            patch("data_engine.data_quality.get_cache", return_value=cache),
            patch("data_engine.data_quality.get_kline", side_effect=seed_history),
        ):
            result = run_data_quality_repair(
                market="A",
                codes=["600000"],
                data_kinds=("history",),
            )
        assert result["repaired_count"] == 1
        assert cache.get_data_quality_backoff("600000", "A", "history") is None
        rows = cache.get_data_quality_log("600000", "A")
        assert len(rows) == 1
        row = rows[0]
        assert row["data_kind"] == "history"
        assert row["status"] == "ok"
        assert row["repaired"] == 1
        assert row["severity"] == "heavy"

    def test_repair_records_source_error(self, cache):
        cache.upsert_financial_report([_fin_row("600000", _days_ago(400))])

        def boom(code, market, force_refresh=False):
            raise RuntimeError("source down")

        with (
            patch("data_engine.data_quality.get_cache", return_value=cache),
            patch("data_engine.data_quality.get_fundamentals", side_effect=boom),
        ):
            result = run_data_quality_repair(
                market="A",
                codes=["600000"],
                data_kinds=("fundamentals",),
            )
        assert result["failed_count"] == 1
        assert result["details"][0]["errors"] == ["fundamentals: source down"]
        rows = cache.get_data_quality_log("600000", "A")
        assert rows[0]["error_message"] == "fundamentals: source down"

    def test_clean_symbols_skipped_without_api_calls(self, cache):
        _seed_prices(cache, "600000", 250)
        _fresh_report(cache, "600000")
        with (
            patch("data_engine.data_quality.get_cache", return_value=cache),
            patch(
                "data_engine.data_quality.get_fundamentals",
                side_effect=AssertionError("no fetch expected"),
            ),
            patch(
                "data_engine.data_quality.get_kline",
                side_effect=AssertionError("no fetch expected"),
            ),
        ):
            result = run_data_quality_repair(
                market="A",
                codes=["600000"],
                data_kinds=("history", "fundamentals"),
            )
        assert result["skipped_clean"] == 1
        assert result["failed_count"] == 0
        assert result["details"] == []
        assert cache.get_data_quality_log("600000", "A") == []

    def test_quota_exhausted_skips_remaining_codes(self, cache):
        for code in ("600000", "600001"):
            cache.upsert_financial_report([_fin_row(code, _days_ago(400))])

        import config as config_mod

        orig_get = config_mod.get

        def fake_get(key, default=None):
            if key == "daily_api_limit":
                return 1
            return orig_get(key, default)

        with (
            patch("data_engine.data_quality.get_cache", return_value=cache),
            patch("data_engine.data_quality.get_fundamentals", return_value=True),
            patch("data_engine.data_quality.cfg_get", side_effect=fake_get),
        ):
            result = run_data_quality_repair(
                market="A",
                codes=["600000", "600001"],
                data_kinds=("fundamentals",),
            )
        assert result["quota_remaining"] == 0
        assert result["failed_count"] == 1
        assert result["skipped_quota"] == 1
        assert result["repaired_count"] == 0
