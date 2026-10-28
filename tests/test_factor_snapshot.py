import math
from contextlib import ExitStack
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from cache import CacheManager
from config import load_config
from data_engine.daily_snapshot import build_factor_daily_snapshot

load_config()

_TODAY = datetime.now().strftime("%Y-%m-%d")


@pytest.fixture
def cache(tmp_path):
    return CacheManager(tmp_path / "snapshot.db")


def _fundamentals(code, pe=10.0, mcap=1e11, roe=12.5):
    return {
        "code": code,
        "market": "A",
        "date": _TODAY,
        "market_cap": mcap,
        "pe_ttm": pe,
        "pe_static": pe,
        "pb": 1.0,
        "ps_ttm": 2.0,
        "pcf_ttm": 5.0,
        "dividend_yield": 3.0,
        "roe": roe,
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


def _kline(days=250):
    end = datetime.now() - timedelta(days=1)
    rows = []
    price = 100.0
    for i in range(days):
        day = (end - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        rows.append(
            {
                "date": day,
                "open": price,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "volume": 1e6,
                "amount": price * 1e6,
            }
        )
        price *= 1.002
    rows.reverse()
    return rows


def _build(cache, codes=None, funds=None, klines=None, pool=None):
    funds = funds or {}
    klines = klines or {}
    with ExitStack() as stack:
        stack.enter_context(
            patch("data_engine.daily_snapshot.get_cache", return_value=cache)
        )
        stack.enter_context(
            patch(
                "data_engine.daily_snapshot.get_fundamentals",
                side_effect=lambda code, market, cached_only=False: funds.get(code, {}),
            )
        )
        stack.enter_context(
            patch(
                "data_engine.daily_snapshot.get_kline",
                side_effect=lambda code, market, days=0, cached_only=False: klines.get(
                    code, []
                ),
            )
        )
        if pool is not None:
            stack.enter_context(
                patch(
                    "data_engine.daily_snapshot.get_stock_pool",
                    return_value=pool,
                )
            )
        if codes is None:
            return build_factor_daily_snapshot(market="A")
        return build_factor_daily_snapshot(market="A", codes=codes)


class TestFactorDailySnapshot:
    def test_build_writes_scored_rows(self, cache):
        funds = {
            "600000": _fundamentals("600000", pe=10.0, mcap=1e11),
            "600001": _fundamentals("600001", pe=30.0, mcap=3e11),
        }
        klines = {"600000": _kline(), "600001": _kline()}
        result = _build(cache, codes=["600000", "600001"], funds=funds, klines=klines)
        assert result["written"] == 2
        assert result["coverage_ratio"] == 1.0
        assert result["skipped_empty"] == 0
        assert result["skipped_bj"] == 0
        rows = cache.get_factor_daily_snapshot(_TODAY, market="A")
        assert len(rows) == 2
        by_code = {row["code"]: row for row in rows}
        for row in rows:
            assert row["has_fundamentals"] == 1
            assert row["has_history"] == 1
            assert 0.0 <= row["composite_score"] <= 100.0
            assert 0.0 <= row["pe_pct"] <= 1.0
            assert 0.0 <= row["size_pct"] <= 1.0
            assert row["f_score"] >= 0
        assert by_code["600001"]["pe_pct"] > by_code["600000"]["pe_pct"]
        assert by_code["600001"]["size_pct"] > by_code["600000"]["size_pct"]
        assert by_code["600001"]["market_cap"] > by_code["600000"]["market_cap"]

    def test_skips_empty_and_bj_codes(self, cache):
        funds = {
            "600000": _fundamentals("600000"),
            "430047": _fundamentals("430047"),
        }
        klines = {"600000": _kline(), "600001": [], "430047": _kline()}
        result = _build(
            cache,
            codes=["600000", "600001", "430047"],
            funds=funds,
            klines=klines,
        )
        assert result["written"] == 1
        assert result["skipped_empty"] == 1
        assert result["skipped_bj"] == 1
        assert result["coverage_ratio"] == round(1 / 3, 4)
        rows = cache.get_factor_daily_snapshot(_TODAY, market="A")
        assert [row["code"] for row in rows] == ["600000"]

    def test_repeat_build_is_idempotent(self, cache):
        funds = {"600000": _fundamentals("600000")}
        klines = {"600000": _kline()}
        codes = ["600000"]
        first = _build(cache, codes=codes, funds=funds, klines=klines)
        second = _build(cache, codes=codes, funds=funds, klines=klines)
        assert first["written"] == 1
        assert second["written"] == 1
        rows = cache.get_factor_daily_snapshot(_TODAY, market="A")
        assert len(rows) == 1

    def test_pool_scope_captures_metadata_flags(self, cache):
        recent = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        pool = [
            {
                "code": "600000",
                "name": "ST Test",
                "sector": "Bank",
                "industry": "Bank",
                "list_date": recent,
                "is_active": 1,
                "total_market_cap": 2e11,
            },
            {
                "code": "000001",
                "name": "Ping An Bank",
                "sector": "Bank",
                "industry": "Bank",
                "list_date": "2000-01-01",
                "is_active": 1,
                "total_market_cap": 5e11,
            },
        ]
        funds = {
            "600000": _fundamentals("600000"),
            "000001": _fundamentals("000001"),
        }
        klines = {"600000": _kline(), "000001": _kline()}
        result = _build(cache, funds=funds, klines=klines, pool=pool)
        assert result["requested"] == 2
        assert result["written"] == 2
        assert result["st_count"] == 1
        assert result["new_listing_count"] == 1
        rows = cache.get_factor_daily_snapshot(_TODAY, market="A")
        by_code = {row["code"]: row for row in rows}
        st_row = by_code["600000"]
        assert st_row["name"] == "ST Test"
        assert st_row["is_st"] == 1
        assert st_row["is_new_listing"] == 1
        assert st_row["sector"] == "Bank"
        assert st_row["log_mcap"] == round(math.log(2e11), 6)
        normal_row = by_code["000001"]
        assert normal_row["is_st"] == 0
        assert normal_row["is_new_listing"] == 0
        assert normal_row["log_mcap"] == round(math.log(5e11), 6)

    def test_empty_scope_returns_zero(self, cache):
        with patch("data_engine.daily_snapshot.get_cache", return_value=cache):
            result = build_factor_daily_snapshot(market="A", codes=[])
        assert result["written"] == 0
        assert result["coverage_ratio"] == 0.0
        assert result["requested"] == 0
        assert cache.get_factor_daily_snapshot(_TODAY, market="A") == []
