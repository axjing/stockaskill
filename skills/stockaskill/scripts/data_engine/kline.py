"""Core data engine: kline module."""

import logging
import threading
from datetime import datetime
from typing import Any, Dict, List

from cache import get_cache
from utils import (
    _suppress_output,
    safe_float,
)

from data_engine.config import (
    _akshare_lock,
    _api_call,
    _is_etf_market,
    _report_no_data,
    _sina_code,
    _try_akshare,
    _try_baostock,
    _try_efinance,
    _try_yfinance,
)
from data_engine.helpers import (
    _detect_quality_flags,
    _estimate_amount,
)

_cache = get_cache()
logger = logging.getLogger(__name__)

# Circuit breaker: after N consecutive AKShare EastMoney failures for A-share
# kline, skip AKShare/efinance for the remainder of the session.
# Both use push2his.eastmoney.com which can block connections at the network
# level (RemoteDisconnected). Baostock is used as the primary source instead.
_akshare_kline_failed = False
_AKSHARE_FAIL_THRESHOLD = 3
_akshare_fail_count = 0
_akshare_fail_lock = threading.Lock()


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
    """Fetch K-line with source-order fallback.

    For A-shares: baostock -> AKShare/EastMoney.
    Baostock is tried first because EastMoney (used by both AKShare and efinance)
    is frequently blocked at the network level (RemoteDisconnected).
    """
    global _akshare_kline_failed, _akshare_fail_count

    # -- A-shares: baostock first (EastMoney often blocked) -----------------
    if market == "A":
        bs = _try_baostock()
        if bs is not None:
            try:
                result = _fetch_kline_bs(code, market, start, end, bs)
                if result:
                    return result
            except Exception as exc:
                logger.debug(
                    "Baostock kline failed for %s: %s, trying fallback", code, exc
                )

        # Try AKShare/EastMoney only if circuit breaker hasn't tripped
        if not _akshare_kline_failed:
            ak = _try_akshare()
            if ak is not None:
                try:
                    result = _fetch_kline_sina(code, market, start, end, ak)
                    if result:
                        with _akshare_fail_lock:
                            _akshare_fail_count = 0
                        return result
                except Exception as exc:
                    logger.debug("AKShare kline failed for %s: %s", code, exc)
                    with _akshare_fail_lock:
                        _akshare_fail_count += 1
                        if _akshare_fail_count >= _AKSHARE_FAIL_THRESHOLD:
                            _akshare_kline_failed = True
                            print(
                                f"[WARN] EastMoney blocked after {_akshare_fail_count} consecutive "
                                f"failures. Skipping AKShare/efinance for remaining A-share kline fetches.",
                                flush=True,
                            )

        # efinance also uses EastMoney -- skip if circuit breaker tripped
        if not _akshare_kline_failed:
            ef = _try_efinance()
            if ef is not None:
                try:
                    result = _fetch_kline_ef(code, market, start, end, ef)
                    if result:
                        return result
                except Exception as exc:
                    logger.debug("efinance kline failed for %s: %s", code, exc)

        # No more A-share fallbacks
        _report_no_data(code, market, "K-line")
        return []

    # -- HK/US: AKShare -> yfinance -----------------------------------------
    ak = _try_akshare()
    if ak is not None:
        try:
            result = _fetch_kline_sina(code, market, start, end, ak)
            if result:
                return result
        except Exception as exc:
            logger.debug(
                "AKShare kline failed for %s (%s): %s, trying fallback",
                code,
                market,
                exc,
            )

    yf = _try_yfinance()
    if yf is not None and market in ("HK", "US"):
        try:
            result = _fetch_kline_yfinance(code, market, start, end, yf)
            if result:
                return result
        except Exception as exc:
            logger.debug("yfinance kline failed for %s: %s", code, exc)
    _report_no_data(code, market, "K-line")
    return []


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
        try:
            with _akshare_lock:
                df = ak.stock_zh_a_daily(
                    symbol=sina_sym,
                    start_date=clean_start,
                    end_date=clean_end,
                    adjust="qfq",
                )
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
    clean_start = start.replace("-", "")
    clean_end = end.replace("-", "")
    df = ef.stock.get_quote_history(
        code,
        klt=101,
        beg=clean_start,
        end=clean_end,
    )
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
        adjustflag="2",  # qfq (forward-adjusted) to match AKShare primary source
    )
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


# -- Fundamentals -----------------------------------------------------------


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
