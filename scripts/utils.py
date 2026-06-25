"""Utility functions for stock code handling and filtering."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


def normalize_code(code: str) -> str:
    """Strip non-digit chars and return pure numeric code."""
    return "".join(c for c in code if c.isdigit())


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
        return False


def is_suspended(code: str, kline_data: list | None) -> bool:
    """Check if stock appears suspended (no recent trading data)."""
    if not kline_data:
        return True
    # Check if latest trading day is more than 10 days ago
    try:
        latest = kline_data[0].get("date", "") if isinstance(kline_data[0], dict) else getattr(kline_data[0], "date", "")
        if latest:
            clean = latest.replace("-", "")
            ld = datetime.strptime(clean, "%Y%m%d")
            return (datetime.now() - ld).days > 10
    except (ValueError, IndexError, AttributeError):
        pass
    return False


def safe_float(val, default: float = 0.0) -> float:
    """Safely convert to float."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_int(val, default: int = 0) -> int:
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
    sorted_vals = sorted(v for v in values if v is not None and not (v != v))  # filter NaN
    if not sorted_vals:
        return 0.5
    n = len(sorted_vals)
    count = sum(1 for v in sorted_vals if v < value)
    return count / max(n - 1, 1)
