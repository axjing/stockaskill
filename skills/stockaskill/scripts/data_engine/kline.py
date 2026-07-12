"""Core data engine: kline module."""

import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from cache import get_cache
from config import get as cfg_get
from utils import (
    _suppress_output,
    normalize_code_for_market,
    safe_float,
)
from data_engine.config import (
    _akshare_lock,
    _api_call,
    _api_limit_exhausted,
    _cold_start_date,
    _has_fresh_snapshot,
    _is_etf_market,
    _latest_cached_date,
    _market_supports_fundamentals,
    _openbb_symbol,
    _report_no_data,
    _sina_code,
    _try_akshare,
    _try_baostock,
    _try_efinance,
    _try_openbb,
    _try_yfinance,
)
from data_engine.helpers import (
    _aggregate_covered_through,
    _backfill_missing_factors,
    _backfill_valuation_from_price,
    _date_str,
    _detect_quality_flags,
    _estimate_amount,
    _safe_parse_date,
    _upsert_scope_sync_state,
    _upsert_symbol_sync_state,
)

_cache = get_cache()
logger = logging.getLogger(__name__)

def get_kline(
    code: str,
    market: str = "A",
    days: int = 365,
    force_refresh: bool = False,
    full_history: bool = False,
    cached_only: bool = False,
) -> List[Dict[str, Any]]:
    """Get K-line data with incremental cache update.

    Delegates to IncrementalCacheFetcher to eliminate duplicated
    cache-first + incremental-fetch logic.
    """
    from incremental_fetcher import get_kline_incremental
    return get_kline_incremental(
        code=code,
        market=market,
        days=days,
        force_refresh=force_refresh,
        full_history=full_history,
        cached_only=cached_only,
        detect_quality=_detect_quality_flags,
    )


def _fetch_kline(code: str, market: str, start: str, end: str) -> List[Dict[str, Any]]:
    """Fetch K-line with true fallback: AKShare -> baostock -> efinance -> yfinance -> OpenBB."""
    ak = _try_akshare()
    if ak is not None:
        try:
            result = _fetch_kline_sina(code, market, start, end, ak)
            if result:
                return result
        except Exception as exc:
            logger.debug("AKShare kline failed for %s: %s, trying fallback", code, exc)
    bs = _try_baostock()
    if bs is not None:
        try:
            result = _fetch_kline_bs(code, market, start, end, bs)
            if result:
                return result
        except Exception as exc:
            logger.debug("Baostock kline failed for %s: %s, trying fallback", code, exc)
    ef = _try_efinance()
    if ef is not None:
        try:
            result = _fetch_kline_ef(code, market, start, end, ef)
            if result:
                return result
        except Exception as exc:
            logger.debug("efinance kline failed for %s: %s", code, exc)
    # yfinance before OpenBB for HK/US — lighter and more stable
    yf = _try_yfinance()
    if yf is not None and market in ("HK", "US"):
        try:
            result = _fetch_kline_yfinance(code, market, start, end, yf)
            if result:
                return result
        except Exception as exc:
            logger.debug("yfinance kline failed for %s: %s", code, exc)
    obb = _try_openbb()
    if obb is not None and market in ("HK", "US"):
        try:
            result = _fetch_kline_openbb(code, market, start, end, obb)
            if result:
                return result
        except Exception as exc:
            logger.debug("OpenBB kline failed for %s: %s", code, exc)
    _report_no_data(code, market, "K-line")
    return []




def _estimate_amount(amount: float, volume: float, close: float, market: str) -> float:
    """Estimate amount (成交额) when missing, using volume × close.

    For A-shares the data source already provides amount correctly.
    For US/HK stocks, AKShare and yfinance don't provide amount.
    Estimate: amount = volume × close (ignoring lot_size which varies by market).
    """
    if amount > 0 and volume > 0 and close > 0:
        return amount
    if volume > 0 and close > 0:
        return round(volume * close, 2)
    return amount


def _detect_quality_flags(rows: List[Dict[str, Any]], market: str) -> List[Dict[str, Any]]:
    """Scan K-line rows for anomalies and attach quality_flags.

    Flags (comma-separated):
    - gap_up: large gap between prev close and today open (>3% for A, >5% for HK/US)
    - gap_down: same but downward
    - zero_vol: trading day but zero volume (suspension indicator)
    - limit_up: hit daily price limit (A-shares only)
    - limit_down: hit daily price limit (A-shares only)
    - data_err: price=0 or close < open/low/high consistency issue
    """
    if not rows:
        return rows
    limit_pct = 0.095 if market == "A" else 0.20

    for i, r in enumerate(rows):
        flags = []
        close = r.get("close", 0) or 0
        open_ = r.get("open", 0) or 0
        high = r.get("high", 0) or 0
        low = r.get("low", 0) or 0
        vol = r.get("volume", 0) or 0

        # Zero volume on non-zero price day = possible suspension
        if close > 0 and vol <= 0:
            flags.append("zero_vol")

        # Price zero = data error
        if close <= 0:
            flags.append("data_err")

        # Gap detection (compare open vs prev close)
        if i + 1 < len(rows):
            prev_close = rows[i + 1].get("close", 0) or 0
            if prev_close > 0 and open_ > 0:
                gap = (open_ - prev_close) / prev_close
                gap_threshold = 0.03 if market == "A" else 0.05
                if gap > gap_threshold:
                    flags.append("gap_up")
                elif gap < -gap_threshold:
                    flags.append("gap_down")

        # Limit hit detection (A-shares only)
        if market == "A" and close > 0:
            # Estimate prior close from current close
            if abs(close - open_) / max(close, 0.001) < 0.001:
                # Flat day — check if at limit
                if open_ > 0 and high > 0:
                    prev_est = open_ / 1.1
                    if prev_est > 0 and (close - prev_est) / prev_est > 0.09:
                        flags.append("limit_up")
                    elif (close - prev_est) / prev_est < -0.09:
                        flags.append("limit_down")

        r["quality_flags"] = ",".join(flags)

    return rows




def _detect_gaps(rows: List[Dict[str, Any]], market: str = "A") -> List[str]:
    """Scan sorted (newest-first) K-line rows for date gaps.

    Returns a list of date strings where a trading day is missing.
    Uses a simple heuristic: if the gap between consecutive dates
    exceeds the expected max gap (1-3 days for weekends/holidays),
    flag the missing dates.

    Only flags gaps > 7 calendar days to avoid false positives
    from holidays/suspensions.
    """
    if len(rows) < 2:
        return []
    gaps = []
    for i in range(len(rows) - 1):
        cur_str = str(rows[i].get("date", "")).strip()
        next_str = str(rows[i + 1].get("date", "")).strip()
        if not cur_str or not next_str:
            continue
        try:
            cur = _safe_parse_date(cur_str)
            nxt = _safe_parse_date(next_str)
            if cur is None or nxt is None:
                continue
            day_diff = (cur - nxt).days
            # Flag only gaps > 7 days (weekend + holiday max ~5)
            if day_diff > 7:
                gaps.append(
                    f"{next_str}..{cur_str} ({day_diff}d gap)"
                )
        except Exception:
            continue
    return gaps


def _normalize_kline_df(
    df, code: str, market: str, adjust_type: str = "qfq"
) -> List[Dict[str, Any]]:
    """Normalize a pandas DataFrame into K-line row dicts.

    Handles both EastMoney (stock_zh_a_hist) and Sina column names.

    Args:
        df: Raw DataFrame from data source.
        code: Stock code.
        market: Market identifier ('A', 'HK', 'US', 'FUND').
        adjust_type: Price adjustment type ('qfq', 'hfq', 'unadjusted', 'yfinance').

    Returns:
        List of normalized K-line row dicts.
    """
    east_cols = {
        "\u65e5\u671f": "date",
        "\u5f00\u76d8": "open",
        "\u6700\u9ad8": "high",
        "\u6700\u4f4e": "low",
        "\u6536\u76d8": "close",
        "\u6210\u4ea4\u91cf": "volume",
        "\u6210\u4ea4\u989d": "amount",
    }
    # Map column names to standard names
    col_map = {}
    for cn, std in east_cols.items():
        if cn in df.columns:
            col_map[cn] = std
    # Handle Sina column names (already lowercase)
    for std in ("date", "open", "high", "low", "close", "volume", "amount"):
        if std in df.columns and std not in col_map.values():
            col_map[std] = std

    if "date" not in col_map.values():
        return []

    df = df.rename(columns=col_map)
    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for _, r in df.iterrows():
        close = safe_float(r.get("close", 0))
        high = safe_float(r.get("high", 0))
        low = safe_float(r.get("low", 0))
        open_ = safe_float(r.get("open", 0))
        date_str = str(r.get("date", ""))

        # Reject rows with invalid prices
        if close <= 0 or open_ <= 0 or high <= 0 or low <= 0:
            continue
        # Reject rows with impossible OHLC relationships
        if high < low:
            continue
        if close > high or close < low:
            continue
        if open_ > high or open_ < low:
            continue
        # Reject rows with future dates
        if date_str > today:
            continue

        rows.append(
            {
                "code": code,
                "date": date_str,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": safe_float(r.get("volume", 0)),
                "amount": _estimate_amount(
                    safe_float(r.get("amount", 0)),
                    safe_float(r.get("volume", 0)),
                    close,
                    market,
                ),
                "market": market,
            }
        )
    return rows


@_api_call("kline")
def _fetch_kline_sina(
    code: str, market: str, start: str, end: str, ak
) -> List[Dict[str, Any]]:
    """Fetch K-line via EastMoney (date-range aware, incremental).

    Uses ak.stock_zh_a_hist() which accepts start_date/end_date,
    avoiding downloading ALL history every time. Falls back to
    stock_zh_a_daily() only when the date-range API fails.
    """
    if market == "A" or _is_etf_market(market):
        # Normalize dates to YYYYMMDD for EastMoney API
        clean_start = start.replace("-", "")
        clean_end = end.replace("-", "")
        try:
            with _akshare_lock:
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=clean_start,
                    end_date=clean_end,
                    adjust="qfq",
                )
            if df is not None and not df.empty:
                return _normalize_kline_df(df, code, market)
        except Exception as exc:
            logger.debug("EastMoney date-range kline failed for %s: %s", code, exc)
        # Fallback: Sina daily returns all history, filter after download.
        # Only pull when cache is empty to avoid full download on every retry.
        sina_sym = _sina_code(code, market)
        cached_fallback = _cache.get_daily_price(code, market)
        if cached_fallback:
            # Cache exists but had a fetch error — use what we have.
            return []
        try:
            with _akshare_lock:
                df = ak.stock_zh_a_daily(symbol=sina_sym, adjust="qfq")
        except Exception:
            df = None
        if df is not None and not df.empty and "date" in df.columns:
            df["date"] = df["date"].astype(str)
            dates_clean = df["date"].str.replace("-", "")
            mask = (dates_clean >= clean_start) & (dates_clean <= clean_end)
            df = df[mask]
            if not df.empty:
                return _normalize_kline_df(df, code, market)
        return []
    elif market == "HK":
        with _suppress_output(capture_exceptions=True):
            with _akshare_lock:
                df = ak.stock_hk_daily(symbol=code, adjust="qfq")
        if df is not None and not df.empty and "date" in df.columns:
            df["date"] = df["date"].astype(str)
            clean_start = start.replace("-", "")
            clean_end = end.replace("-", "")
            dates_clean = df["date"].str.replace("-", "")
            mask = (dates_clean >= clean_start) & (dates_clean <= clean_end)
            df = df[mask]
            if not df.empty:
                return _normalize_kline_df(df, code, market)
        return []
    elif market == "US":
        # US stocks: use raw prices (no adjustment) to avoid negative
        # prices from AKShare's A-share oriented qfq algorithm.
        with _suppress_output(capture_exceptions=True):
            with _akshare_lock:
                df = ak.stock_us_daily(symbol=code.upper(), adjust="")
        if df is not None and not df.empty and "date" in df.columns:
            df["date"] = df["date"].astype(str)
            clean_start = start.replace("-", "")
            clean_end = end.replace("-", "")
            dates_clean = df["date"].str.replace("-", "")
            mask = (dates_clean >= clean_start) & (dates_clean <= clean_end)
            df = df[mask]
            if not df.empty:
                return _normalize_kline_df(df, code, market)
        return []
    return []


@_api_call("kline_ef")
def _fetch_kline_ef(
    code: str, market: str, start: str, end: str, ef
) -> List[Dict[str, Any]]:
    """Fetch K-line from efinance (A-shares only)."""
    if market != "A":
        return []
    df = ef.stock.get_quote_history(code, klt=101)
    if df is None or df.empty:
        return []
    date_col = "\u65e5\u671f"
    if date_col not in df.columns:
        return []
    # Filter to requested date range to avoid returning all history
    df[date_col] = df[date_col].astype(str)
    clean_start = start.replace("-", "")
    clean_end = end.replace("-", "")
    dates_clean = df[date_col].str.replace("-", "")
    mask = (dates_clean >= clean_start) & (dates_clean <= clean_end)
    df = df[mask]
    if df.empty:
        return []
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "code": code,
                "date": str(r.get(date_col, "")),
                "open": safe_float(r.get("\u5f00\u76d8", 0)),
                "high": safe_float(r.get("\u6700\u9ad8", 0)),
                "low": safe_float(r.get("\u6700\u4f4e", 0)),
                "close": safe_float(r.get("\u6536\u76d8", 0)),
                "volume": safe_float(r.get("\u6210\u4ea4\u91cf", 0)),
                "amount": safe_float(r.get("\u6210\u4ea4\u989d", 0)),
                "market": market,
            }
        )
    return rows


@_api_call("kline_bs")
def _fetch_kline_bs(
    code: str, market: str, start: str, end: str, bs
) -> List[Dict[str, Any]]:
    """Fetch K-line from baostock (A-shares only)."""
    if market != "A":
        return []
    if code.startswith("92"):
        prefix = "bj"
    elif code.startswith(("6", "9")):
        prefix = "sh"
    else:
        prefix = "sz"
    rs = bs.query_history_k_data_plus(
        f"{prefix}.{code}",
        "date,open,high,low,close,volume,amount",
        start_date=start,
        end_date=end,
        frequency="d",
        adjustflag="1",  # qfq (forward-adjusted) to match AKShare primary source
    )
    try:
        if rs.error_code != "0":
            return []
        rows = []
        while rs.error_code == "0" and rs.next():
            r = rs.get_row_data()
            rows.append(
                {
                    "code": code,
                    "date": r[0],
                    "open": safe_float(r[1]),
                    "high": safe_float(r[2]),
                    "low": safe_float(r[3]),
                    "close": safe_float(r[4]),
                    "volume": safe_float(r[5]),
                    "amount": safe_float(r[6]),
                    "market": market,
                }
            )
        return rows
    finally:
        try:
            with _suppress_output():
                bs.logout()
        except Exception:
            pass


# -- Fundamentals -----------------------------------------------------------


# -- OpenBB K-line ----------------------------------------------------------


@_api_call("kline_openbb")
def _fetch_kline_openbb(
    code: str,
    market: str,
    start: str,
    end: str,
    obb,
) -> List[Dict[str, Any]]:
    """Fetch K-line from OpenBB (HK/US markets)."""
    symbol = _openbb_symbol(code, market)
    if symbol is None:
        return []
    try:
        df = obb.equity.price.historical(
            symbol=symbol,
            start_date=start,
            end_date=end,
            provider="yfinance",
        ).to_df()
        if df is None or df.empty:
            return []
        df = df.reset_index()
        if "date" not in df.columns:
            date_candidates = [c for c in df.columns if "date" in c.lower()]
            if date_candidates:
                df = df.rename(columns={date_candidates[0]: "date"})
            else:
                return []
        df["date"] = df["date"].astype(str).str.replace("T.*", "", regex=True)
        rows = []
        today = datetime.now().strftime("%Y-%m-%d")
        for _, r in df.iterrows():
            close = safe_float(r.get("close", 0))
            high = safe_float(r.get("high", 0))
            low = safe_float(r.get("low", 0))
            open_ = safe_float(r.get("open", 0))
            date_str = str(r.get("date", ""))

            # Reject rows with invalid prices
            if close <= 0 or open_ <= 0 or high <= 0 or low <= 0:
                continue
            # Reject rows with impossible OHLC relationships
            if high < low or close > high or close < low or open_ > high or open_ < low:
                continue
            # Reject rows with future dates
            if date_str > today:
                continue

            rows.append(
                {
                    "code": code,
                    "date": date_str,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": safe_float(r.get("volume", 0)),
                    "amount": safe_float(r.get("amount", 0)),
                    "market": market,
                }
            )
        return rows
    except Exception:
        return []


def _yfinance_symbol(code: str, market: str) -> str:
    """Convert code + market to a yfinance-compatible symbol."""
    if market == "HK":
        return f"{code.zfill(5)}.HK"
    if market == "US":
        return code.upper().replace(".", "-")
    return code


@_api_call("kline_yf")
def _fetch_kline_yfinance(
    code: str,
    market: str,
    start: str,
    end: str,
    yf,
) -> List[Dict[str, Any]]:
    """Fetch K-line from yfinance (HK/US markets)."""
    symbol = _yfinance_symbol(code, market)
    if market not in ("HK", "US"):
        return []
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end)
        if df is None or df.empty:
            return []
        df = df.reset_index()
        if "Date" not in df.columns:
            return []
        df["date"] = df["Date"].astype(str).str.replace("T.*", "", regex=True)
        rows = []
        today = datetime.now().strftime("%Y-%m-%d")
        for _, r in df.iterrows():
            close = safe_float(r.get("Close", 0))
            high = safe_float(r.get("High", 0))
            low = safe_float(r.get("Low", 0))
            open_ = safe_float(r.get("Open", 0))
            date_str = str(r.get("date", ""))

            # Reject rows with invalid prices
            if close <= 0 or open_ <= 0 or high <= 0 or low <= 0:
                continue
            # Reject rows with impossible OHLC relationships
            if high < low or close > high or close < low or open_ > high or open_ < low:
                continue
            # Reject rows with future dates
            if date_str > today:
                continue

            rows.append(
                {
                    "code": code,
                    "date": date_str,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": safe_float(r.get("Volume", 0)),
                    "amount": 0.0,
                    "market": market,
                }
            )
        return rows
    except Exception:
        return []
