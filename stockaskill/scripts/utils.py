"""Utility functions for stock code handling, filtering, and shared helpers.

Provides code normalization (A/HK/US/FUND), market detection, symbol
conversion for AKShare/Xueqiu, ST/new/suspended stock detection, safe
numeric conversion, percentile ranking, and shared utility functions
(_suppress_output, _board).
"""

import os
import sys
from contextlib import contextmanager
from datetime import datetime


@contextmanager
def _suppress_output():
    """Temporarily suppress stdout/stderr to prevent library error leaks."""
    devnull = open(os.devnull, "w")
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = devnull, devnull
    try:
        yield
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        devnull.close()


def _board(code: str, market: str = "A") -> str:
    """Return exchange board label for a stock code.

    Args:
        code: Stock code.
        market: Market identifier ("A", "HK", "US").

    Returns:
        Board name: SH, STAR, SZ, SME, GEM, HK, US, BJ, or SZ.
    """
    c = code.strip()
    if market == "HK":
        return "HK"
    if market == "US":
        return "US"
    if c.startswith("688"):
        return "STAR"
    if c.startswith("60"):
        return "SH"
    if c.startswith("002"):
        return "SME"
    if c.startswith("300"):
        return "GEM"
    if c.startswith("000"):
        return "SZ"
    if c.startswith("8") or c.startswith("4") or c.startswith("92"):
        return "BJ"
    return "SZ"


def contains_any_keyword(text: str, keywords: list[str]) -> bool:
    """Return True when *text* contains any keyword in *keywords*."""
    normalized = text.strip().lower()
    if not normalized:
        return False
    return any(keyword.lower() in normalized for keyword in keywords)


def detect_workflow_intent(
    goal: str,
    code: str = "",
    codes: list[str] | None = None,
) -> str:
    """Classify a workflow intent from bounded user inputs."""
    codes = [item for item in (codes or []) if item]
    normalized = goal.strip().lower()

    if contains_any_keyword(normalized, ["回测", "backtest", "历史表现"]):
        return "backtest_strategy"
    if contains_any_keyword(
        normalized,
        ["主题", "产业链", "价值链", "证据链", "theme", "scarce layer", "卡点"],
    ):
        return "theme_research"
    if contains_any_keyword(normalized, ["同步", "sync", "刷新", "预热", "cache"]):
        return "sync_data"
    if contains_any_keyword(
        normalized,
        ["市场状态", "regime", "risk budget", "风险姿态", "仓位上限", "市场风险"],
    ):
        return "market_check"
    if codes or contains_any_keyword(
        normalized,
        ["组合", "portfolio", "持仓", "建仓", "再平衡", "仓位"],
    ):
        return "build_portfolio"
    if code and contains_any_keyword(
        normalized,
        ["诊断", "deep", "bull", "bear", "失效", "review", "复核"],
    ):
        return "diagnose_symbol"
    if code:
        return "analyze_symbol"
    return "opportunity_scan"


def normalize_code(code: str) -> str:
    """Strip non-digit chars and return pure numeric code."""
    return "".join(c for c in code if c.isdigit())


def normalize_code_for_market(code: str, market: str) -> str:
    """Normalize a symbol while preserving market-specific identity."""
    if market == "US":
        return code.strip().upper()
    digits = normalize_code(code)
    if market == "HK":
        return digits.zfill(5) if digits else digits
    return digits


def detect_market(code: str) -> str:
    """Detect market from stock code.

    Returns 'A', 'HK', 'US', or 'FUND'.
    """
    c = normalize_code(code)
    # Non-numeric codes are US tickers
    if not c:
        return "US"
    # Funds: typically 6 digits starting with 5 or 1 (ETF)
    if len(c) == 6:
        if c.startswith(("51", "56", "58", "15", "16", "18")):
            return "FUND"
    # A shares: 6 digits
    if len(c) == 6:
        return "A"
    # HK stocks: 5 digits
    if len(c) == 5:
        return "HK"
    # US stocks: numeric 5-7 digits (after exhausting A/HK/FUND checks)
    if 5 <= len(c) <= 7:
        return "US"
    return "A"


def code_to_akshare_symbol(code: str, market: str) -> str:
    """Convert code to AKShare-compatible symbol format.

    A-shares: pure digits e.g. "600519"
    HK: "00700" format
    US: ticker string (already handled)
    """
    c = normalize_code(code)
    if market == "A":
        return c
    if market == "HK":
        return c.zfill(5)
    if market == "US":
        return code if not c else c
    return c


def code_to_xq_symbol(code: str, market: str) -> str:
    """Convert to Xueqiu symbol format for financial APIs.

    e.g. "SZ002475", "SH600519", "HK00700"
    """
    c = normalize_code(code)
    if market == "A":
        if c.startswith(("6", "9")):
            return f"SH{c}"
        return f"SZ{c}"
    if market == "HK":
        return f"HK{c.zfill(5)}"
    if market == "US":
        return code if not c else c
    return c


def exchange_suffix(code: str) -> str:
    """Return lowercase exchange suffix for fund flow APIs."""
    c = normalize_code(code)
    if c.startswith(("6", "9")):
        return "sh"
    return "sz"


def is_st(code: str, name: str = "") -> bool:
    """Check if stock is ST (Special Treatment)."""
    n = name.upper()
    return "ST" in n or "*ST" in n


def is_new(list_date: str, threshold_days: int = 60) -> bool:
    """Check if stock is newly listed (< threshold_days).

    Returns True for empty/invalid dates (conservative: treat as new).
    """
    try:
        # Handle formats: "20240101" or "2024-01-01"
        clean = list_date.replace("-", "")
        ld = datetime.strptime(clean, "%Y%m%d")
        return (datetime.now() - ld).days < threshold_days
    except (ValueError, TypeError):
        return True  # conservative: treat unknown as new


def is_suspended(code: str, kline_data: list | None) -> bool:
    """Check if stock appears suspended (no recent trading data)."""
    if not kline_data:
        return True
    # Check if latest trading day is more than 10 days ago
    try:
        latest = (
            kline_data[0].get("date", "")
            if isinstance(kline_data[0], dict)
            else getattr(kline_data[0], "date", "")
        )
        if latest:
            clean = latest.replace("-", "")
            ld = datetime.strptime(clean, "%Y%m%d")
            return (datetime.now() - ld).days > 10
    except (ValueError, IndexError, AttributeError):
        pass
    return False


def safe_float(val: object, default: float = 0.0) -> float:
    """Safely convert to float."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_int(val: object, default: int = 0) -> int:
    """Safely convert to int."""
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def percentile_rank(values: list[float], value: float) -> float:
    """Compute percentile rank of *value* within *values*.

    Returns a float in [0, 1].
    """
    if not values:
        return 0.5
    sorted_vals = sorted(
        v for v in values if v is not None and not (v != v)
    )  # filter NaN
    if not sorted_vals:
        return 0.5
    n = len(sorted_vals)
    count = sum(1 for v in sorted_vals if v < value)
    return count / max(n - 1, 1)
