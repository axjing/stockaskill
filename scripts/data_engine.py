"""Core data engine: AKShare (Sina primary) with caching and fallbacks."""

import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from cache import get_cache
from config import get as cfg_get

_akshare_lock = threading.RLock()
from utils import (  # noqa: E402
    normalize_code,
    safe_float,
)

_cache = get_cache()
logger = logging.getLogger(__name__)


# -- Retry / rate-limit decorator -------------------------------------------


def _api_call(api_name: str):
    """Decorator: rate-limit + exponential backoff + usage tracking."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            if not _cache.record_api_call(api_name):
                raise RuntimeError(f"Daily API limit reached for {api_name}")
            retry_max = cfg_get("retry_max", 3)
            retry_base = cfg_get("retry_base", 2)
            interval = cfg_get("request_interval", [0.5, 2.0])
            for attempt in range(retry_max):
                try:
                    time.sleep(interval[0])
                    result = func(*args, **kwargs)
                    return result
                except Exception:
                    if attempt == retry_max - 1:
                        raise
                    delay = min(retry_base**attempt * 2, 30)
                    time.sleep(delay)
            return None

        return wrapper

    return decorator


# -- Data source: AKShare (primary) -----------------------------------------


def _try_akshare() -> Optional[Any]:
    """Import AKShare, return module or None."""
    try:
        import akshare as ak

        return ak
    except ImportError:
        return None


def _try_efinance() -> Optional[Any]:
    """Import efinance, return module or None."""
    try:
        import efinance as ef

        return ef
    except ImportError:
        return None


def _try_baostock() -> Optional[Any]:
    """Import baostock, return module or None."""
    try:
        import baostock as bs

        bs.login()
        return bs
    except ImportError:
        return None


# -- Helpers ----------------------------------------------------------------


def _sina_code(code: str, market: str = "A") -> str:
    """Convert code to Sina format."""
    """Convert code to Sina format: sh601318, sz002475, sh510300."""
    code = normalize_code(code)
    if market in ("A", "FUND"):
        if code.startswith(("5", "6", "9")):
            return f"sh{code}"
        return f"sz{code}"
    return code


# -- Stock pool -------------------------------------------------------------


def get_stock_pool(
    market: str = "A", force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """Get stock pool for a market. Returns cached data, refreshes if needed."""
    if force_refresh or _cache.pool_needs_refresh():
        _refresh_stock_pool(market)
    return _cache.get_stock_pool(market)


def _refresh_stock_pool(market: str) -> None:
    """Fetch full stock pool from API and cache it."""
    ak = _try_akshare()
    if ak is None:
        print(
            "[WARN] akshare not installed, cannot refresh stock pool. "
            "Run: pip install akshare"
        )
        return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if market == "A":
            df = _fetch_a_stock_pool(ak)
        elif market == "HK":
            df = _fetch_hk_stock_pool(ak)
        elif market == "US":
            df = _fetch_us_stock_pool(ak)
        elif market == "FUND":
            df = _fetch_fund_pool_df(ak)
            if df is not None and not df.empty:
                pool_rows = []
                for _, r in df.iterrows():
                    pool_rows.append(
                        {
                            "code": normalize_code(str(r.get("code", ""))),
                            "name": str(r.get("name", "")),
                            "market": "FUND",
                            "sector": "",
                            "industry": str(r.get("fund_type", "ETF")),
                            "list_date": "",
                            "total_market_cap": safe_float(
                                r.get("total_market_cap", 0)
                            ),
                            "is_active": 1,
                            "updated_at": now,
                        }
                    )
                _cache.upsert_stock_pool(pool_rows)
            return
        else:
            return
        if df is not None and not df.empty:
            rows = []
            for _, r in df.iterrows():
                raw_code = str(r.get("code", ""))
                rows.append(
                    {
                        "code": normalize_code(raw_code),
                        "name": str(r.get("name", "")),
                        "market": market,
                        "sector": str(r.get("sector", "")),
                        "industry": str(r.get("industry", "")),
                        "list_date": str(r.get("list_date", "")),
                        "total_market_cap": safe_float(r.get("total_market_cap", 0)),
                        "is_active": 1,
                        "updated_at": now,
                    }
                )
            _cache.upsert_stock_pool(rows)
    except Exception as exc:
        print(f"[WARN] Failed to refresh stock pool for {market}: {exc}")


@_api_call("stock_pool_a")
def _fetch_a_stock_pool(ak) -> Optional[pd.DataFrame]:
    """Fetch A-share pool via EastMoney (richer data). Falls back to Sina."""
    try:
        df = ak.stock_zh_a_spot_em()
        col_map = {
            "\u4ee3\u7801": "code",
            "\u540d\u79f0": "name",
            "\u603b\u5e02\u503c": "total_market_cap",
            "\u884c\u4e1a": "industry",
            "\u5730\u533a": "sector",
            "\u5e02\u76c8\u7387\u52a8\u6001": "pe_ttm",
        }
        df = df.rename(columns=col_map)
        df["list_date"] = ""
        df["total_market_cap"] = df["total_market_cap"].fillna(0).astype(float)
        if "industry" not in df.columns:
            df["industry"] = ""
        if "sector" not in df.columns:
            df["sector"] = ""
        print(f"Fetch A-share pool via EM ({len(df)} stocks)")
        return df
    except Exception:
        print("EM pool failed, fallback to stock_info_a_code_name.")
        df = ak.stock_info_a_code_name()
        df["industry"] = ""
        df["sector"] = ""
        df["list_date"] = ""
        df["total_market_cap"] = 0.0
        return df


@_api_call("stock_pool_hk")
def _fetch_hk_stock_pool(ak) -> Optional[pd.DataFrame]:
    """Fetch HK pool via Sina."""
    df = ak.stock_hk_spot()
    col_map = {
        "\u4ee3\u7801": "code",
        "\u4e2d\u6587\u540d\u79f0": "name",
    }
    df = df.rename(columns=col_map)
    df["industry"] = ""
    df["sector"] = ""
    df["list_date"] = ""
    df["total_market_cap"] = 0.0
    return df


@_api_call("stock_pool_us")
def _fetch_us_stock_pool(ak) -> Optional[pd.DataFrame]:
    """Fetch US pool via Sina."""
    df = ak.stock_us_spot()
    col_map = {
        "\u4ee3\u7801": "code",
        "\u540d\u79f0": "name",
    }
    df = df.rename(columns=col_map)
    df["industry"] = ""
    df["sector"] = ""
    df["list_date"] = ""
    df["total_market_cap"] = 0.0
    return df


@_api_call("fund_pool")
def _fetch_fund_pool_df(ak) -> Optional[pd.DataFrame]:
    """Fetch ETF/fund pool via EastMoney."""
    df = ak.fund_etf_spot_em()
    col_map = {
        "\u4ee3\u7801": "code",
        "\u540d\u79f0": "name",
        "\u6700\u65b0\u4ef7": "nav",
        "\u603b\u5e02\u503c": "total_market_cap",
    }
    df = df.rename(columns=col_map)
    df["fund_type"] = "ETF"
    return df


# -- K-line data ------------------------------------------------------------


def get_kline(
    code: str,
    market: str = "A",
    days: int = 365,
    force_refresh: bool = False,
    full_history: bool = False,
    cached_only: bool = False,
) -> List[Dict[str, Any]]:
    """Get K-line data with incremental cache update. Graceful degradation.

    Args:
        code: Stock code.
        market: Market identifier.
        days: Number of trading days to return.
        force_refresh: Force re-fetch from upstream.
        full_history: Fetch all available history from API (overrides days for fetch
        range).
        cached_only: If True, skip API calls and return cached data only.

    Returns:
        List of K-line dicts (newest first).
    """
    code = normalize_code(code)
    cached = _cache.get_daily_price(code)
    if cached_only:
        return cached[:days] if cached else []
    if cached and not force_refresh and not full_history and len(cached) >= days:
        return cached[:days]

    if full_history:
        start = "20000101"
    elif cached:
        latest = cached[0].get("date", "")
        if latest:
            start = _add_days(latest, -30)
        else:
            start = _date_str(datetime.now() - timedelta(days=days + 30))
    else:
        latest = _cache.get_latest_date(code) or ""
        if latest:
            start = _add_days(latest, -30)
        else:
            start = _date_str(datetime.now() - timedelta(days=days + 30))

    end = _date_str(datetime.now())
    _ = max(days, 1500) if full_history else days
    try:
        new_data = _fetch_kline(code, market, start, end)
        if new_data:
            _cache.upsert_daily_price(new_data)
            cached = _cache.get_daily_price(code)
    except Exception as exc:
        logger.warning("get_kline fetch failed for %s: %s", code, exc)

    return cached[:days] if cached else []


def _fetch_kline(code: str, market: str, start: str, end: str) -> List[Dict[str, Any]]:
    """Fetch K-line: Sina first, then baostock, then efinance."""
    ak = _try_akshare()
    if ak is not None:
        return _fetch_kline_sina(code, market, start, end, ak)
    bs = _try_baostock()
    if bs is not None:
        return _fetch_kline_bs(code, market, start, end, bs)
    ef = _try_efinance()
    if ef is not None:
        return _fetch_kline_ef(code, market, start, end, ef)
    return []


@_api_call("kline")
def _fetch_kline_sina(
    code: str, market: str, start: str, end: str, ak
) -> List[Dict[str, Any]]:
    """Fetch K-line via Sina (daily, all history, then filter)."""
    if market == "FUND":
        try:
            df = ak.fund_etf_hist_sina(symbol=_sina_code(code, market))
        except Exception:
            df = ak.stock_zh_a_daily(symbol=_sina_code(code, market), adjust="qfq")
    elif market == "A":
        df = ak.stock_zh_a_daily(symbol=_sina_code(code, market), adjust="qfq")
    elif market == "HK":
        df = ak.stock_hk_daily(symbol=code, adjust="qfq")
    elif market == "US":
        df = ak.stock_us_daily(symbol=code.upper(), adjust="qfq")
    else:
        return []

    if df is None or df.empty:
        return []

    # Filter to date range
    df["date"] = df["date"].astype(str)
    clean_start = start.replace("-", "")
    clean_end = end.replace("-", "")
    dates_clean = df["date"].str.replace("-", "")
    mask = (dates_clean >= clean_start) & (dates_clean <= clean_end)
    df = df[mask]

    if df.empty:
        return []

    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "code": code,
                "date": str(r.get("date", "")),
                "open": safe_float(r.get("open", 0)),
                "high": safe_float(r.get("high", 0)),
                "low": safe_float(r.get("low", 0)),
                "close": safe_float(r.get("close", 0)),
                "volume": safe_float(r.get("volume", 0)),
                "amount": safe_float(r.get("amount", 0)),
                "market": market,
            }
        )
    return rows


@_api_call("kline_ef")
def _fetch_kline_ef(
    code: str, market: str, start: str, end: str, ef
) -> List[Dict[str, Any]]:
    """Fetch K-line from efinance (A-shares only)."""
    if market != "A":
        return []
    try:
        df = ef.stock.get_quote_history(code, klt=101)
        if df is None or df.empty:
            return []
        rows = []
        for _, r in df.iterrows():
            rows.append(
                {
                    "code": code,
                    "date": str(r.get("\u65e5\u671f", "")),
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
    except Exception:
        return []


@_api_call("kline_bs")
def _fetch_kline_bs(
    code: str, market: str, start: str, end: str, bs
) -> List[Dict[str, Any]]:
    """Fetch K-line from baostock (A-shares only)."""
    if market != "A":
        return []
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    rs = bs.query_history_k_data_plus(
        f"{prefix}.{code}",
        "date,open,high,low,close,volume,amount",
        start_date=start,
        end_date=end,
        frequency="d",
        adjustflag="2",
    )
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


def get_fundamentals(
    code: str,
    market: str = "A",
    force_refresh: bool = False,
    cached_only: bool = False,
) -> Optional[Dict[str, Any]]:
    """Get latest fundamental snapshot. Graceful degradation."""
    code = normalize_code(code)
    cached = _cache.get_latest_factor_snapshot(code)
    if cached_only:
        return cached
    if cached and not force_refresh:
        return cached
    try:
        snapshot = _fetch_fundamentals(code, market)
        if snapshot:
            _cache.upsert_factor_snapshot([snapshot])
            return snapshot
    except Exception as exc:
        logger.warning("get_fundamentals fetch failed for %s: %s", code, exc)
    return cached


def _fetch_fundamentals(code: str, market: str) -> Optional[Dict[str, Any]]:
    """Fetch fundamentals from available source."""
    ak = _try_akshare()
    if ak is not None:
        return _fetch_fundamentals_ak(code, market, ak)
    return None


@_api_call("fundamentals")
def _fetch_fundamentals_ak(code: str, market: str, ak) -> Optional[Dict[str, Any]]:
    """Fetch fundamentals via Sina financial abstract."""
    try:
        if market == "A":
            df = ak.stock_financial_report_sina(symbol=code, name="主要指标")
        elif market == "HK":
            df = ak.stock_financial_hk_report_em(symbol=code)
        elif market == "US":
            df = ak.stock_financial_us_report_em(symbol=code)
        else:
            return None
        if df is None or df.empty or len(df.columns) < 3:
            return None
        today = datetime.now().strftime("%Y-%m-%d")
        result = {
            "code": code,
            "date": today,
            "market_cap": 0.0,
            "pe_ttm": 0.0,
            "pe_static": 0.0,
            "pb": 0.0,
            "ps_ttm": 0.0,
            "pcf_ttm": 0.0,
            "dividend_yield": 0.0,
            "roe": 0.0,
            "roa": 0.0,
            "gross_margin": 0.0,
            "net_margin": 0.0,
            "revenue_growth": 0.0,
            "profit_growth": 0.0,
            "debt_ratio": 0.0,
            "current_ratio": 0.0,
            "eps": 0.0,
            "bvps": 0.0,
        }
        # Build lookup: indicator name -> value (latest quarterly column)
        latest_col = df.columns[2]  # first date column
        for i in range(len(df)):
            name = str(df.iloc[i, 1])
            val = df.iloc[i][latest_col]
            if val is None or (isinstance(val, float) and (val != val)):
                continue
            v = safe_float(val)
            # 主要指标 section
            if name == "\u57fa\u672c\u6bcf\u80a1\u6536\u76ca":
                result["eps"] = v
            elif name == "\u6bcf\u80a1\u51c0\u8d44\u4ea7":
                result["bvps"] = v
            elif name == "\u51c0\u8d44\u4ea7\u6536\u76ca\u7387(ROE)":
                result["roe"] = v / 100.0
            elif name == "\u6bdb\u5229\u7387":
                result["gross_margin"] = v / 100.0
            elif name == "\u9500\u552e\u51c0\u5229\u7387":
                result["net_margin"] = v / 100.0
            elif name == "\u8d44\u4ea7\u8d1f\u503a\u7387":
                result["debt_ratio"] = v / 100.0
            elif name == "\u8425\u4e1a\u6536\u5165\u589e\u957f\u7387":
                result["revenue_growth"] = v / 100.0
            elif name == (
                "\u5f52\u5c5e\u6bcd\u516c\u53f8\u51c0\u5229\u6da6\u589e\u957f\u7387"
            ):
                result["profit_growth"] = v / 100.0
            elif name == "\u6d41\u52a8\u6bd4\u7387":
                result["current_ratio"] = v
        return result
    except Exception:
        return None


# -- Fund data --------------------------------------------------------------


def get_fund_pool(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Get ETF/fund pool. Auto-refreshes if cache is empty or expired."""
    if force_refresh:
        _refresh_fund_pool()
    funds = _cache.get_stock_pool("FUND")
    if not funds:
        with _cache._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM fund_info")
            funds = [dict(r) for r in cur.fetchall()]
    # Auto-refresh if pool is empty (same behavior as get_stock_pool)
    if not funds:
        _refresh_fund_pool()
        funds = _cache.get_stock_pool("FUND")
        if not funds:
            with _cache._conn() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute("SELECT * FROM fund_info")
                funds = [dict(r) for r in cur.fetchall()]
    return funds


def _refresh_fund_pool() -> None:
    """Fetch ETF pool via EastMoney and cache."""
    ak = _try_akshare()
    if ak is None:
        return
    try:
        df = _fetch_fund_pool_df(ak)
        if df is not None and not df.empty:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fund_rows = []
            for _, r in df.iterrows():
                fund_rows.append(
                    {
                        "code": str(r.get("code", "")),
                        "name": str(r.get("name", "")),
                        "fund_type": "ETF",
                        "nav": safe_float(r.get("nav", 0)),
                        "acc_nav": 0.0,
                        "scale": safe_float(r.get("total_market_cap", 0)),
                        "track_index": "",
                        "updated_at": now,
                    }
                )
            _cache.upsert_fund_info(fund_rows)
    except Exception:
        pass


def get_fund_nav(code: str, days: int = 365) -> List[Dict[str, Any]]:
    """Get fund NAV history. Uses Sina daily for ETFs."""
    cached = _cache.get_fund_nav(code, days)
    if cached:
        return cached
    try:
        ak = _try_akshare()
        if ak:
            with _akshare_lock:
                df = ak.stock_zh_a_daily(symbol=_sina_code(code, "A"), adjust="qfq")
            if df is not None and not df.empty:
                df["date"] = df["date"].astype(str)
                cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                cutoff_clean = cutoff.replace("-", "")
                dates_clean = df["date"].str.replace("-", "")
                df = df[dates_clean >= cutoff_clean]
                rows = []
                for _, r in df.iterrows():
                    rows.append(
                        {
                            "code": code,
                            "date": str(r.get("date", "")),
                            "nav": safe_float(r.get("close", 0)),
                            "acc_nav": 0.0,
                        }
                    )
                if rows:
                    _cache.upsert_fund_nav(rows)
                    return _cache.get_fund_nav(code, days)
    except Exception:
        pass
    return []


# -- Market index -----------------------------------------------------------


def get_market_index(
    index_code: str = "000001", days: int = 250
) -> List[Dict[str, Any]]:
    """Get market index K-line. Graceful degradation."""
    cached = _cache.get_market_index(index_code, days)
    if cached:
        return cached
    try:
        rows = _fetch_market_index(index_code, days)
        if rows:
            _cache.upsert_market_index(rows)
            return _cache.get_market_index(index_code, days)
    except Exception:
        pass
    return []


@_api_call("market_index")
def _fetch_market_index(index_code: str, days: int) -> List[Dict[str, Any]]:
    """Fetch market index via Sina."""
    ak = _try_akshare()
    if ak is None:
        return []
    try:
        df = ak.stock_zh_index_daily(symbol=f"sh{index_code}")
        if df is None or df.empty:
            return []

        df["date"] = df["date"].astype(str)
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        cutoff_clean = cutoff.replace("-", "")
        dates_clean = df["date"].str.replace("-", "")
        df = df[dates_clean >= cutoff_clean]

        rows = []
        for _, r in df.iterrows():
            rows.append(
                {
                    "index_code": index_code,
                    "date": str(r.get("date", "")),
                    "open": safe_float(r.get("open", 0)),
                    "high": safe_float(r.get("high", 0)),
                    "low": safe_float(r.get("low", 0)),
                    "close": safe_float(r.get("close", 0)),
                    "volume": safe_float(r.get("volume", 0)),
                    "amount": 0.0,
                }
            )
        return rows
    except Exception:
        return []


# -- Utility ----------------------------------------------------------------


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _add_days(date_str: str, days: int) -> str:
    try:
        clean = date_str.replace("-", "")
        dt = datetime.strptime(clean, "%Y%m%d")
        return _date_str(dt + timedelta(days=days))
    except (ValueError, TypeError):
        return _date_str(datetime.now() + timedelta(days=days))
