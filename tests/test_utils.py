from datetime import datetime

from utils import (
    code_to_akshare_symbol,
    code_to_xq_symbol,
    contains_any_keyword,
    detect_market,
    detect_workflow_intent,
    exchange_suffix,
    is_new,
    is_st,
    is_suspended,
    normalize_code,
    normalize_code_for_market,
    percentile_rank,
    safe_float,
    safe_int,
)


class TestNormalizeCode:
    def test_strip_non_digits(self):
        assert normalize_code("600519") == "600519"
        assert normalize_code("SZ002475") == "002475"
        assert normalize_code("SH600519") == "600519"
        assert normalize_code("00700.HK") == "00700"

    def test_empty(self):
        assert normalize_code("") == ""

    def test_with_prefix(self):
        assert normalize_code("sh601318") == "601318"

    def test_market_specific_normalization(self):
        assert normalize_code_for_market("AAPL", "US") == "AAPL"
        assert normalize_code_for_market("700", "HK") == "00700"
        assert normalize_code_for_market("SZ002475", "A") == "002475"


class TestWorkflowIntent:
    def test_contains_any_keyword(self):
        assert contains_any_keyword("需要先看市场状态", ["市场状态", "风险"])
        assert not contains_any_keyword("普通分析", ["回测", "同步"])

    def test_detect_backtest(self):
        assert detect_workflow_intent("请做回测") == "backtest_strategy"

    def test_detect_theme_research(self):
        assert detect_workflow_intent("帮我做AI主题产业链研究") == "theme_research"

    def test_detect_build_portfolio_from_codes(self):
        assert (
            detect_workflow_intent("", codes=["600519", "000858"]) == "build_portfolio"
        )

    def test_detect_diagnose_symbol(self):
        assert (
            detect_workflow_intent("复核 bull bear 逻辑", code="601318")
            == "diagnose_symbol"
        )

    def test_detect_default_scan(self):
        assert detect_workflow_intent("帮我找机会") == "opportunity_scan"


class TestDetectMarket:
    def test_a_share(self):
        assert detect_market("600519") == "A"
        assert detect_market("002475") == "A"
        assert detect_market("300750") == "A"

    def test_hk(self):
        assert detect_market("00700") == "HK"
        assert detect_market("00005") == "HK"
        assert detect_market("09988") == "HK"

    def test_us(self):
        assert detect_market("AAPL") == "US"
        assert detect_market("MSFT") == "US"

    def test_fund(self):
        assert detect_market("510050") == "FUND"
        assert detect_market("159915") == "FUND"
        assert detect_market("511880") == "FUND"

    def test_with_prefix(self):
        assert detect_market("sh601318") == "A"
        assert detect_market("sz002475") == "A"


class TestCodeToAkshareSymbol:
    def test_a_share(self):
        assert code_to_akshare_symbol("600519", "A") == "600519"
        assert code_to_akshare_symbol("002475", "A") == "002475"

    def test_hk(self):
        assert code_to_akshare_symbol("700", "HK") == "00700"
        assert code_to_akshare_symbol("00700", "HK") == "00700"

    def test_us(self):
        assert code_to_akshare_symbol("AAPL", "US") == "AAPL"


class TestCodeToXqSymbol:
    def test_a_share_sh(self):
        assert code_to_xq_symbol("600519", "A") == "SH600519"

    def test_a_share_sz(self):
        assert code_to_xq_symbol("002475", "A") == "SZ002475"
        assert code_to_xq_symbol("300750", "A") == "SZ300750"

    def test_hk(self):
        assert code_to_xq_symbol("00700", "HK") == "HK00700"
        assert code_to_xq_symbol("700", "HK") == "HK00700"

    def test_us(self):
        assert code_to_xq_symbol("AAPL", "US") == "AAPL"


class TestExchangeSuffix:
    def test_sh(self):
        assert exchange_suffix("600519") == "sh"
        assert exchange_suffix("900901") == "sh"

    def test_sz(self):
        assert exchange_suffix("002475") == "sz"
        assert exchange_suffix("300750") == "sz"
        assert exchange_suffix("000001") == "sz"


class TestIsST:
    def test_st_detected(self):
        assert is_st("600123", "*ST Pan") is True
        assert is_st("600123", "ST Pan") is True

    def test_non_st(self):
        assert is_st("600519", "Kweichow Moutai") is False
        assert is_st("601318", "PingAn") is False

    def test_empty_name(self):
        assert is_st("600123", "") is False


class TestIsNew:
    def test_new_stock(self):
        assert is_new("") is True
        assert is_new(datetime.now().strftime("%Y-%m-%d")) is True

    def test_old_stock(self):
        assert is_new("2010-01-01", threshold_days=60) is False
        assert is_new("20100101", threshold_days=60) is False

    def test_recent_stock(self):
        assert is_new(datetime.now().strftime("%Y%m%d"), threshold_days=60) is True


class TestIsSuspended:
    def test_no_data(self):
        assert is_suspended("600519", None) is True
        assert is_suspended("600519", []) is True

    def test_active(self):
        today = datetime.now().strftime("%Y-%m-%d")
        kline = [{"date": today, "close": 100}]
        assert is_suspended("600519", kline) is False

    def test_suspended(self):
        kline = [{"date": "2000-01-01", "close": 100}]
        assert is_suspended("600519", kline) is True


class TestSafeFloat:
    def test_valid(self):
        assert safe_float("12.5") == 12.5
        assert safe_float(42) == 42.0
        assert safe_float("3.14") == 3.14

    def test_invalid(self):
        assert safe_float("abc") == 0.0
        assert safe_float(None) == 0.0
        assert safe_float("", default=1.0) == 1.0

    def test_custom_default(self):
        assert safe_float("bad", default=-1.0) == -1.0


class TestSafeInt:
    def test_valid(self):
        assert safe_int("12") == 12
        assert safe_int(42.7) == 42
        assert safe_int("3.14") == 3

    def test_invalid(self):
        assert safe_int("abc") == 0
        assert safe_int(None) == 0


class TestPercentileRank:
    def test_normal(self):
        values = [1, 2, 3, 4, 5]
        assert percentile_rank(values, 1) == 0.0
        assert percentile_rank(values, 3) == 0.5
        assert percentile_rank(values, 5) == 1.0

    def test_empty(self):
        assert percentile_rank([], 5) == 0.5

    def test_single_value(self):
        assert percentile_rank([5], 5) == 0.0

    def test_with_nan(self):
        values = [1, 2, float("nan"), 4, 5]
        rank = percentile_rank(values, 3)
        assert 0.25 <= rank <= 0.75
