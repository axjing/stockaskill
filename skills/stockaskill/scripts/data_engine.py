"""Core data engine: AKShare (Sina primary) with caching and fallbacks."""

import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from cache import get_cache
from config import get as cfg_get
from utils import (  # noqa: E402
    _suppress_output,
    normalize_code_for_market,
    safe_float,
)

_akshare_lock = threading.RLock()

_cache = get_cache()
logger = logging.getLogger(__name__)

# Track whether any API limit was hit during this session
_api_limit_exhausted = False

# Configure logging if not already configured by the caller
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _is_etf_market(market: str) -> bool:
    """Return True when a market identifier represents the ETF asset path."""
    return str(market).upper() == "FUND"


def _market_supports_fundamentals(market: str) -> bool:
    """Return True when the market should use equity fundamentals sync."""
    return not _is_etf_market(market)


def _cold_start_date(market: str) -> str:
    """Return market-specific cold start baseline date.

    Matches SKILL.md: A: 2000-01-01, HK: 1995-01-01, US: 1990-01-01.
    """
    defaults = {"A": "20000101", "HK": "19950101", "US": "19900101"}
    return cfg_get("full_history_start_date", defaults.get(market, "20000101"))


def _has_fresh_snapshot(
    snapshot: Optional[Dict[str, Any]],
    max_age_days: int,
) -> bool:
    """Return True if a cached fundamentals snapshot is fresh enough."""
    if not snapshot:
        return False
    date_str = str(snapshot.get("date", "")).strip()
    try:
        snapshot_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return False
    return (datetime.now() - snapshot_date).days <= max_age_days


def _latest_cached_date(
    rows: Sequence[Dict[str, Any]],
    field: str = "date",
) -> str:
    """Return the latest date field from cached rows."""
    values = sorted(
        str(row.get(field, "")).strip()
        for row in rows
        if str(row.get(field, "")).strip()
    )
    return values[-1] if values else ""


def _first_present_value(row: pd.Series, candidates: Sequence[str]) -> Any:
    """Return the first non-empty value from the given candidate columns."""
    for candidate in candidates:
        if candidate in row.index:
            value = row.get(candidate)
            if value is None:
                continue
            if isinstance(value, float) and pd.isna(value):
                continue
            if str(value).strip():
                return value
    return ""


def _normalize_pool_text(value: Any) -> str:
    """Return a stripped string value for pool metadata fields."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _infer_active_status(name: str, raw_status: Any = "") -> int:
    """Infer whether a pool row should be treated as active."""
    status_text = _normalize_pool_text(raw_status).lower()
    name_text = _normalize_pool_text(name).lower()
    inactive_markers = (
        "delist",
        "delisted",
        "suspend",
        "suspended",
        "halt",
        "退市",
        "摘牌",
        "停牌",
    )
    combined = f"{name_text} {status_text}".strip()
    return 0 if any(marker in combined for marker in inactive_markers) else 1


def _normalize_metadata_status(raw_status: Any, is_active: int) -> str:
    """Normalize raw upstream status into a compact cache-friendly label."""
    status_text = _normalize_pool_text(raw_status).lower()
    if not status_text:
        return "active" if is_active else "inactive"
    if "active" in status_text or "正常" in status_text:
        return "active"
    if any(
        marker in status_text
        for marker in ("delist", "delisted", "退市", "摘牌")
    ):
        return "delisted"
    if any(
        marker in status_text
        for marker in ("suspend", "suspended", "halt", "停牌")
    ):
        return "suspended"
    return status_text.replace(" ", "_")


def _metadata_completeness_score(
    sector: str,
    industry: str,
    list_date: str,
    total_market_cap: float,
) -> float:
    """Return a simple [0, 1] completeness score for pool metadata."""
    fields_present = 0
    if sector.strip():
        fields_present += 1
    if industry.strip():
        fields_present += 1
    if list_date.strip():
        fields_present += 1
    if total_market_cap > 0:
        fields_present += 1
    return round(fields_present / 4.0, 2)


def _normalize_cross_market_pool_row(
    row: pd.Series,
    source: str,
) -> Dict[str, Any]:
    """Extract a normalized HK/US pool row from heterogeneous upstream fields."""
    name = _normalize_pool_text(
        _first_present_value(
            row,
            ("name", "名称", "中文名称", "股票名称", "Name"),
        )
    )
    raw_status = _first_present_value(row, ("status", "状态", "Status"))
    sector = _normalize_pool_text(
        _first_present_value(
            row,
            ("sector", "地区", "板块", "所属行业", "Sector"),
        )
    )
    industry = _normalize_pool_text(
        _first_present_value(
            row,
            ("industry", "行业", "所属行业", "Industry"),
        )
    )
    list_date = _normalize_pool_text(
        _first_present_value(
            row,
            ("list_date", "上市日期", "IPO日期", "ipo_date", "ListDate"),
        )
    )
    total_market_cap = safe_float(
        _first_present_value(
            row,
            ("total_market_cap", "总市值", "market_cap", "MarketCap"),
        ),
    )
    is_active = _infer_active_status(name, raw_status)
    return {
        "code": _normalize_pool_text(
            _first_present_value(row, ("code", "代码", "symbol", "Symbol"))
        ),
        "name": name,
        "sector": sector,
        "industry": industry,
        "list_date": list_date,
        "total_market_cap": total_market_cap,
        "is_active": is_active,
        "metadata_source": source,
        "metadata_status": _normalize_metadata_status(raw_status, is_active),
        "metadata_completeness": _metadata_completeness_score(
            sector,
            industry,
            list_date,
            total_market_cap,
        ),
    }


def _upsert_symbol_sync_state(
    code: str,
    market: str,
    data_kind: str,
    status: str,
    covered_date: str = "",
    last_error: str = "",
) -> None:
    """Persist sync-state for a single symbol and data kind."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _cache.upsert_sync_state(
        [
            {
                "scope_type": "symbol",
                "scope_key": f"{market}:{code}",
                "market": market,
                "code": code,
                "data_kind": data_kind,
                "last_success_at": timestamp if status == "ok" else "",
                "last_covered_date": covered_date,
                "last_error": last_error,
                "status": status,
            }
        ]
    )


def _upsert_scope_sync_state(
    scope_type: str,
    scope_key: str,
    market: str,
    data_kind: str,
    status: str,
    covered_date: str = "",
    last_error: str = "",
) -> None:
    """Persist sync-state for a bounded scope summary row."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _cache.upsert_sync_state(
        [
            {
                "scope_type": scope_type,
                "scope_key": scope_key,
                "market": market,
                "code": "",
                "data_kind": data_kind,
                "last_success_at": timestamp if status == "ok" else "",
                "last_covered_date": covered_date,
                "last_error": last_error,
                "status": status,
            }
        ]
    )


def _aggregate_covered_through(symbols: Sequence[Dict[str, Any]]) -> str:
    """Return the latest non-empty covered-through date across symbol results."""
    return max(
        [
            str(item.get("history_covered_through", "")).strip()
            for item in symbols
            if str(item.get("history_covered_through", "")).strip()
        ],
        default="",
    )


# -- Output suppression for noisy libraries ---------------------------------
# _suppress_output is imported from utils

# -- Error reporting helpers ------------------------------------------------


def _report_no_data(code: str, market: str, data_kind: str) -> None:
    """Log a user-visible message when no data source succeeded."""
    if market in ("HK", "US"):
        sources = "AKShare -> OpenBB -> yfinance"
    else:
        sources = "AKShare -> baostock -> efinance"
    logger.warning(
        "No %s data for %s (%s). All sources exhausted (%s). "
        "Retry with 'sync %s --market %s' when network is available.",
        data_kind, code, market, sources, code, market,
    )


# -- Retry / rate-limit decorator -------------------------------------------


def _api_call(api_name: str):
    """Decorator: retry with exponential backoff + rate-limit detection.

    Retries up to retry_max times with exponential backoff.
    If all attempts fail with a rate-limit signal, sets _api_limit_exhausted
    and prints a warning before re-raising. Callers should catch the exception
    and fall back to cached data.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            global _api_limit_exhausted
            retry_max = cfg_get("retry_max", 3)
            retry_base = cfg_get("retry_base", 2)
            interval = cfg_get("request_interval", [0.5, 2.0])
            mul = cfg_get("retry_backoff_multiplier", 2)
            cap = cfg_get("retry_max_delay", 30)
            last_exc: Exception | None = None
            for attempt in range(retry_max):
                try:
                    # Check and record API usage against daily limit
                    if not _cache.record_api_call(api_name):
                        raise RuntimeError(
                            f"Daily API limit ({cfg_get('daily_api_limit', 500)}) "
                            f"exceeded for {api_name}"
                        )
                    time.sleep(interval[0])
                    result = func(*args, **kwargs)
                    return result
                except Exception as exc:
                    last_exc = exc
                    err_str = str(exc).lower()
                    # Detect upstream rate-limit signals
                    is_rate_limited = any(
                        token in err_str
                        for token in ("429", "too many", "rate limit", "throttl")
                    )
                    if is_rate_limited and attempt == retry_max - 1:
                        _api_limit_exhausted = True
                        source_name = {
                            "kline": "AKShare/EastMoney",
                            "kline_ef": "efinance",
                            "kline_bs": "Baostock",
                            "kline_openbb": "OpenBB",
                            "kline_yf": "yfinance",
                            "fundamentals": "AKShare/Sina",
                            "fundamentals_openbb": "OpenBB",
                            "fundamentals_yf": "yfinance",
                            "market_index": "AKShare/Sina",
                            "stock_pool_a": "AKShare/EastMoney",
                            "stock_pool_hk": "AKShare/Sina",
                            "stock_pool_us": "AKShare/Sina",
                            "fund_pool": "AKShare/EastMoney",
                        }.get(api_name, api_name)
                        print(
                            f"[WARN] {source_name} rate-limited. "
                            f"Falling back to alternative data source.",
                            flush=True,
                        )
                    if attempt == retry_max - 1:
                        raise
                    delay = min(retry_base**attempt * mul, cap)
                    time.sleep(delay)
            # Should never reach here (last attempt always raises)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


def is_api_limit_exhausted() -> bool:
    """Return True if any API limit was hit during this session."""
    return _api_limit_exhausted


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

        with _suppress_output():
            bs.login()
        return bs
    except Exception:
        return None


_openbb_cache: Optional[Any] = None


def _try_openbb() -> Optional[Any]:
    """Import OpenBB, return obb object or None.

    Cached at module level to avoid repeated extension installation.
    """
    global _openbb_cache
    if _openbb_cache is not None:
        return _openbb_cache
    try:
        from openbb import obb

        _openbb_cache = obb
        return obb
    except Exception:
        # Catch all errors, not just ImportError — OpenBB may fail on
        # network/permission errors during provider initialization.
        return None


def _try_yfinance() -> Optional[Any]:
    """Import yfinance, return module or None."""
    try:
        import yfinance as yf

        return yf
    except ImportError:
        return None


def _openbb_symbol(code: str, market: str) -> Optional[str]:
    """Convert code + market to OpenBB-compatible symbol.

    Returns None if the market is not supported by OpenBB.
    """
    if market == "US":
        return code.upper()
    if market == "HK":
        return f"{code}.HK"
    if market == "A" or _is_etf_market(market):
        return None
    return None


# -- Helpers ----------------------------------------------------------------


def _sina_code(code: str, market: str = "A") -> str:
    """Convert code to Sina format: sh601318, sz002475, sh510300."""
    code = normalize_code_for_market(code, market)
    if market == "A" or _is_etf_market(market):
        if code.startswith("92"):
            return f"bj{code}"
        if code.startswith(("5", "6")):
            return f"sh{code}"
        return f"sz{code}"
    return code


# -- Stock pool -------------------------------------------------------------


def get_stock_pool(
    market: str = "A", force_refresh: bool = False, include_inactive: bool = False
) -> List[Dict[str, Any]]:
    """Get stock pool for a market. Returns cached data, refreshes if needed.

    Args:
        market: Market identifier.
        force_refresh: Force a pool rebuild from upstream API.
        include_inactive: Include delisted/inactive stocks (for backtests).
    """
    if force_refresh or _cache.pool_needs_refresh(market):
        _refresh_stock_pool(market)
    return _cache.get_stock_pool(market, include_inactive=include_inactive)


def ensure_stock_pool_candidates_ready(
    market: str,
    codes: Sequence[str],
) -> Dict[str, int]:
    """Backfill critical pool metadata for candidate codes.

    For A-shares, list-date gaps are filled from company profile data first,
    then from cached/full-history K-line as a fallback. Industry and sector are
    also updated when profile data is available.
    """
    normalized_codes = [
        normalize_code_for_market(code, market) for code in codes if str(code).strip()
    ]
    if not normalized_codes:
        return {
            "requested": len(normalized_codes),
            "already_ready": 0,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 0,
            "missing_market_cap": 0,
            "metadata_complete": 0,
            "metadata_partial": 0,
            "inactive_count": 0,
        }
    if market != "A":
        non_a_pool = {
            row["code"]: dict(row)
            for row in _cache.get_stock_pool(market)
            if row.get("code")
        }
        target_rows = [
            non_a_pool[code] for code in normalized_codes if code in non_a_pool
        ]
        metadata_complete = sum(
            1
            for row in target_rows
            if float(row.get("metadata_completeness", 0) or 0) >= 0.75
        )
        inactive_count = sum(
            1 for row in target_rows if not bool(row.get("is_active", 1))
        )
        return {
            "requested": len(normalized_codes),
            "already_ready": len(target_rows),
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": sum(
                1 for row in target_rows if not str(row.get("list_date", "")).strip()
            ),
            "missing_market_cap": sum(
                1
                for row in target_rows
                if float(row.get("total_market_cap", 0) or 0) <= 0
            ),
            "metadata_complete": metadata_complete,
            "metadata_partial": max(len(target_rows) - metadata_complete, 0),
            "inactive_count": inactive_count,
        }

    pool_map = {
        row["code"]: dict(row)
        for row in _cache.get_stock_pool(market)
        if row.get("code")
    }
    target_rows = [pool_map[code] for code in normalized_codes if code in pool_map]
    if not target_rows:
        return {
            "requested": len(normalized_codes),
            "already_ready": 0,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 0,
            "missing_market_cap": 0,
        }

    updated_rows: List[Dict[str, Any]] = []
    already_ready = 0
    profile_backfilled = 0
    cached_history_backfilled = 0
    remote_history_backfilled = 0

    for row in target_rows:
        row_changed = False
        list_date = str(row.get("list_date", "")).strip()
        if list_date:
            already_ready += 1
        else:
            profile_data = _fetch_a_stock_profile_metadata(row["code"]) or {}
            profile_list_date = str(profile_data.get("list_date", "")).strip()
            if profile_list_date:
                row["list_date"] = profile_list_date
                row_changed = True
                profile_backfilled += 1

            if not str(row.get("industry", "")).strip():
                profile_industry = str(profile_data.get("industry", "")).strip()
                if profile_industry:
                    row["industry"] = profile_industry
                    row_changed = True

            if not str(row.get("sector", "")).strip():
                profile_sector = str(profile_data.get("sector", "")).strip()
                if profile_sector:
                    row["sector"] = profile_sector
                    row_changed = True

            if not str(row.get("list_date", "")).strip():
                inferred_date, used_remote = _infer_list_date_from_history(
                    row["code"],
                    market,
                )
                if inferred_date:
                    row["list_date"] = inferred_date
                    row_changed = True
                    if used_remote:
                        remote_history_backfilled += 1
                    else:
                        cached_history_backfilled += 1

        if row_changed:
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updated_rows.append(row)

    if updated_rows:
        _cache.upsert_stock_pool(updated_rows)

    refreshed_map = {
        row["code"]: row for row in _cache.get_stock_pool(market) if row.get("code")
    }
    still_missing_list_date = sum(
        1
        for code in normalized_codes
        if not str(refreshed_map.get(code, {}).get("list_date", "")).strip()
    )
    missing_market_cap = sum(
        1
        for code in normalized_codes
        if float(refreshed_map.get(code, {}).get("total_market_cap", 0) or 0) <= 0
    )
    return {
        "requested": len(normalized_codes),
        "already_ready": already_ready,
        "profile_backfilled": profile_backfilled,
        "cached_history_backfilled": cached_history_backfilled,
        "remote_history_backfilled": remote_history_backfilled,
        "still_missing_list_date": still_missing_list_date,
        "missing_market_cap": missing_market_cap,
        "metadata_complete": sum(
            1
            for code in normalized_codes
            if float(
                refreshed_map.get(code, {}).get("metadata_completeness", 0) or 0
            )
            >= 0.75
        ),
        "metadata_partial": sum(
            1
            for code in normalized_codes
            if float(
                refreshed_map.get(code, {}).get("metadata_completeness", 0) or 0
            )
            < 0.75
        ),
        "inactive_count": sum(
            1
            for code in normalized_codes
            if not bool(refreshed_map.get(code, {}).get("is_active", 1))
        ),
    }


def _refresh_stock_pool(market: str) -> None:
    """Fetch full stock pool from API and cache it."""
    ak = _try_akshare()
    if ak is None:
        print(
            "[WARN] akshare not installed, cannot refresh stock pool. "
            "Run: pip install akshare"
        )
        return
    print(f"[pool] Fetching {market} pool from upstream...")
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if market == "A":
            df = _fetch_a_stock_pool(ak)
            if df is not None and not df.empty:
                has_limited = (
                    df["industry"].eq("").all()
                    or df["list_date"].eq("").all()
                )
                if has_limited:
                    df = _backfill_pool_metadata_from_bs(df)
                n = len(df)
                warn_min = cfg_get("pool_size_warn_min", 4000)
                warn_max = cfg_get("pool_size_warn_max", 6000)
                if n < warn_min:
                    print(
                        f"[WARN] A-share pool has only {n} stocks"
                        f" (expected {warn_min}-{warn_max}). Data may be incomplete."
                    )
                elif n > warn_max:
                    print(
                        f"[WARN] A-share pool has {n} stocks"
                        f" (expected 5000-6000). May include non-stocks."
                    )
                print(f"  A-share pool: {n} stocks cached")
            else:
                print("  A-share pool: empty response, cache preserved")
        elif market == "HK":
            df = _fetch_hk_stock_pool(ak)
            if df is not None and not df.empty:
                print(f"  HK pool: {len(df)} stocks cached")
            else:
                print("  HK pool: empty response, cache preserved")
        elif market == "US":
            df = _fetch_us_stock_pool(ak)
            if df is not None and not df.empty:
                print(f"  US pool: {len(df)} stocks cached")
            else:
                print("  US pool: empty response, cache preserved")
        elif _is_etf_market(market):
            df = _fetch_fund_pool_df(ak)
            if df is not None and not df.empty:
                pool_rows = []
                for _, r in df.iterrows():
                    pool_rows.append(
                        {
                            "code": normalize_code_for_market(
                                str(r.get("code", "")),
                                "FUND",
                            ),
                            "name": str(r.get("name", "")),
                            "market": "FUND",
                            "sector": "",
                            "industry": str(r.get("fund_type", "ETF")),
                            "list_date": "",
                            "total_market_cap": safe_float(
                                r.get("total_market_cap", 0)
                            ),
                            "is_active": 1,
                            "metadata_source": "akshare_fund_etf_spot_em",
                            "metadata_status": "active",
                            "metadata_completeness": 0.25,
                            "updated_at": now,
                        }
                    )
                _cache.upsert_stock_pool(pool_rows)
                print(f"  FUND pool: {len(pool_rows)} ETFs cached")
            else:
                print("  FUND pool: empty response, cache preserved")
            return
        else:
            return
        if df is not None and not df.empty:
            rows = []
            for _, r in df.iterrows():
                raw_code = str(r.get("code", ""))
                rows.append(
                    {
                        "code": normalize_code_for_market(raw_code, market),
                        "name": str(r.get("name", "")),
                        "market": market,
                        "sector": str(r.get("sector", "")),
                        "industry": str(r.get("industry", "")),
                        "list_date": str(r.get("list_date", "")),
                        "total_market_cap": safe_float(r.get("total_market_cap", 0)),
                        "is_active": int(r.get("is_active", 1) or 0),
                        "metadata_source": str(r.get("metadata_source", "")),
                        "metadata_status": str(r.get("metadata_status", "")),
                        "metadata_completeness": safe_float(
                            r.get("metadata_completeness", 0)
                        ),
                        "updated_at": now,
                    }
                )
            _cache.upsert_stock_pool(rows)
        else:
            # API returned empty data (rate-limited or temporary outage).
            # Preserve existing cached pool and bump the refresh timestamp
            # so callers don't hammer the API on every invocation.
            _cache._touch_meta(_cache._stock_pool_meta_key(market), 0)
    except Exception as exc:
        print(f"[WARN] Failed to refresh stock pool for {market}: {exc}")
        # Same fallback on exception: bump TTL so we don't retry immediately.
        _cache._touch_meta(_cache._stock_pool_meta_key(market), 0)



@_api_call("stock_pool_a")
def _fetch_a_stock_pool(ak) -> Optional[pd.DataFrame]:
    """Fetch A-share pool: EastMoney -> Sina -> Baostock."""
    # Attempt 1: EastMoney with full fields
    try:
        with _akshare_lock:
            df = ak.stock_zh_a_spot_em()
        col_map = {
            "代码": "code",
            "名称": "name",
            "总市值": "total_market_cap",
            "行业": "industry",
            "地区": "sector",
            "市盈率动态": "pe_ttm",
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
        print("EM pool failed, fallback to Sina.")

    # Attempt 2: Sina (code+name only)
    try:
        with _akshare_lock:
            df = ak.stock_info_a_code_name()
        df["industry"] = ""
        df["sector"] = ""
        df["list_date"] = ""
        df["total_market_cap"] = 0.0
        print(f"Fetch A-share pool via Sina ({len(df)} stocks)")
        return df
    except Exception:
        print("Sina pool failed, fallback to Baostock.")

    # Attempt 3: Baostock (code+name+ipoDate)
    return _fetch_a_stock_pool_baostock()


def _fetch_a_stock_pool_baostock() -> Optional[pd.DataFrame]:
    """Fetch A-share pool from Baostock as last resort."""
    bs = _try_baostock()
    if bs is None:
        print("Baostock not available for pool fetch.")
        return None
    try:
        rs = bs.query_stock_basic()
        rows = []
        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()
            if row[4] == "1" and row[5] == "1":
                code = row[0]
                if code.startswith("sh."):
                    code = code[3:]
                elif code.startswith("sz."):
                    code = code[3:]
                elif code.startswith("bj."):
                    code = code[3:]
                rows.append({
                    "code": code,
                    "name": row[1],
                    "industry": "",
                    "sector": "",
                    "list_date": str(row[2]).strip(),
                    "total_market_cap": 0.0,
                })
        if rows:
            print(f"Fetch A-share pool via Baostock ({len(rows)} stocks)")
            return pd.DataFrame(rows)
        return None
    except Exception as exc:
        print(f"Baostock pool fetch failed: {exc}")
        return None
    finally:
        try:
            with _suppress_output():
                bs.logout()
        except Exception:
            pass


def _backfill_pool_metadata_from_bs(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich pool DataFrame with industry/list_date from Baostock."""
    bs = _try_baostock()
    if bs is None or df is None or df.empty:
        return df
    try:
        rs = bs.query_stock_basic()
        meta_map: Dict[str, Dict[str, str]] = {}
        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()
            code = row[0]
            if code.startswith("sh."):
                code = code[3:]
            elif code.startswith("sz."):
                code = code[3:]
            elif code.startswith("bj."):
                code = code[3:]
            meta_map[code] = {
                "industry": "",
                "list_date": str(row[2]).strip(),
            }

        has_changes = False
        for idx, row in df.iterrows():
            code = str(row.get("code", ""))
            if code in meta_map:
                meta = meta_map[code]
                if not str(row.get("list_date", "")).strip() and meta["list_date"]:
                    df.at[idx, "list_date"] = meta["list_date"]
                    has_changes = True
                if not str(row.get("industry", "")).strip() and meta["industry"]:
                    df.at[idx, "industry"] = meta["industry"]
                    has_changes = True

        if has_changes:
            print("Pool metadata backfilled from Baostock.")
        return df
    except Exception as exc:
        print(f"Baostock pool metadata backfill failed: {exc}")
        return df
    finally:
        try:
            with _suppress_output():
                bs.logout()
        except Exception:
            pass


def _fetch_a_stock_profile_metadata(code: str) -> Dict[str, str]:
    """Fetch basic company profile data for one A-share code."""
    ak = _try_akshare()
    if ak is None:
        return {}
    try:
        with _akshare_lock:
            df = ak.stock_profile_cninfo(symbol=code)
    except Exception:
        return {}
    if df is None or df.empty:
        return {}

    first_row = df.iloc[0]
    return {
        "list_date": str(first_row.get("上市日期", "")).strip(),
        "industry": str(first_row.get("所属行业", "")).strip(),
        "sector": str(first_row.get("所属市场", "")).strip(),
    }


def _infer_list_date_from_history(code: str, market: str) -> tuple[str, bool]:
    """Infer list date from cached/full-history K-line data."""
    cached_rows = _cache.get_daily_price(code, market=market)
    if cached_rows:
        dates = sorted(
            str(row.get("date", "")).strip() for row in cached_rows if row.get("date")
        )
        if dates:
            return dates[0], False

    get_kline(
        code,
        market,
        days=365,
        full_history=True,
        force_refresh=False,
    )
    cached_rows = _cache.get_daily_price(code, market=market)
    dates = sorted(
        str(row.get("date", "")).strip() for row in cached_rows if row.get("date")
    )
    if dates:
        return dates[0], True
    return "", True


@_api_call("stock_pool_hk")
def _fetch_hk_stock_pool(ak) -> Optional[pd.DataFrame]:
    """Fetch HK pool via Sina and extract minimal metadata when available."""
    with _suppress_output(capture_exceptions=True):
        with _akshare_lock:
            df = ak.stock_hk_spot()
    if df is None or df.empty:
        return df
    rows = [
        _normalize_cross_market_pool_row(df.iloc[idx], "akshare_stock_hk_spot")
        for idx in range(len(df))
    ]
    return pd.DataFrame(rows)


@_api_call("stock_pool_us")
def _fetch_us_stock_pool(ak) -> Optional[pd.DataFrame]:
    """Fetch US pool via Sina and extract minimal metadata when available."""
    with _suppress_output(capture_exceptions=True):
        with _akshare_lock:
            df = ak.stock_us_spot()
    if df is None or df.empty:
        return df
    rows = [
        _normalize_cross_market_pool_row(df.iloc[idx], "akshare_stock_us_spot")
        for idx in range(len(df))
    ]
    return pd.DataFrame(rows)


@_api_call("fund_pool")
def _fetch_fund_pool_df(ak) -> Optional[pd.DataFrame]:
    """Fetch ETF/fund pool via EastMoney."""
    with _akshare_lock:
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
                "amount": safe_float(r.get("amount", 0)),
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
        with _suppress_output(capture_exceptions=True):
            with _akshare_lock:
                df = ak.stock_us_daily(symbol=code.upper(), adjust="qfq")
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
        for _, r in df.iterrows():
            rows.append(
                {
                    "code": code,
                    "date": str(r.get("date", "")),
                    "open": safe_float(r.get("Open", 0)),
                    "high": safe_float(r.get("High", 0)),
                    "low": safe_float(r.get("Low", 0)),
                    "close": safe_float(r.get("Close", 0)),
                    "volume": safe_float(r.get("Volume", 0)),
                    "amount": 0.0,
                    "market": market,
                }
            )
        return rows
    except Exception:
        return []


# -- OpenBB fundamentals ----------------------------------------------------


@_api_call("fundamentals_openbb")
def _fetch_fundamentals_openbb(
    code: str,
    market: str,
    obb,
) -> Optional[Dict[str, Any]]:
    """Fetch fundamentals from OpenBB (HK/US markets)."""
    symbol = _openbb_symbol(code, market)
    if symbol is None:
        return None
    try:
        df = obb.equity.valuation.metrics(
            symbol=symbol,
            provider="yfinance",
        ).to_df()
        if df is None or df.empty:
            return None
        row = df.iloc[0]
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "code": code,
            "date": today,
            "market_cap": safe_float(row.get("marketCap", row.get("market_cap", 0))),
            "pe_ttm": safe_float(row.get("trailingPE", row.get("pe_ratio", 0))),
            "pe_static": safe_float(row.get("trailingPE", row.get("pe_ratio", 0))),
            "pb": safe_float(row.get("priceToBook", row.get("price_to_book", 0))),
            "ps_ttm": safe_float(row.get("priceToSalesTrailing12Months", 0)),
            "pcf_ttm": safe_float(row.get("priceToCashflow", 0)),
            "dividend_yield": safe_float(row.get("dividendYield", 0)) * 100
                if safe_float(row.get("dividendYield", 0)) <= 1
                else safe_float(row.get("dividendYield", 0)),
            "roe": safe_float(row.get("returnOnEquity", 0)),
            "roa": safe_float(row.get("returnOnAssets", 0)),
            "gross_margin": safe_float(row.get("grossMargins", 0)),
            "net_margin": safe_float(row.get("profitMargins", 0)),
            "revenue_growth": safe_float(row.get("revenueGrowth", 0)),
            "profit_growth": safe_float(row.get("earningsGrowth", 0)),
            "debt_ratio": safe_float(row.get("debtToEquity", 0)),
            "current_ratio": safe_float(row.get("currentRatio", 0)),
            "eps": safe_float(row.get("trailingEps", 0)),
            "bvps": 0.0,
        }
    except Exception:
        return None


@_api_call("fundamentals_yf")
def _fetch_fundamentals_yfinance(
    code: str,
    market: str,
    yf,
) -> Optional[Dict[str, Any]]:
    """Fetch fundamentals from yfinance (HK/US markets)."""
    symbol = _yfinance_symbol(code, market)
    if market not in ("HK", "US"):
        return None
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info:
            return None
        today = datetime.now().strftime("%Y-%m-%d")
        # Normalize yfinance scales to match AKShare expectations:
        # - dividendYield: 0-1 fraction (not percentage)
        # - roe/roa: decimal (0.15 = 15%)
        # - debtToEquity: raw ratio (1.5 = 1.5, not percentage)
        # - growth/margins: decimal
        _div_yield = safe_float(info.get("dividendYield", 0))
        if _div_yield > 1:
            _div_yield /= 100.0
        _debt = safe_float(info.get("debtToEquity", 0))
        if _debt > 10:
            _debt /= 100.0
        return {
            "code": code,
            "date": today,
            "market_cap": safe_float(info.get("marketCap", 0)),
            "pe_ttm": safe_float(info.get("trailingPE", 0)),
            "pe_static": safe_float(info.get("forwardPE", info.get("trailingPE", 0))),
            "pb": safe_float(info.get("priceToBook", 0)),
            "ps_ttm": safe_float(info.get("priceToSalesTrailing12Months", 0)),
            "pcf_ttm": safe_float(info.get("priceToCashflow", 0)),
            "dividend_yield": _div_yield,
            "roe": safe_float(info.get("returnOnEquity", 0)) / 100.0
                if safe_float(info.get("returnOnEquity", 0)) > 1
                else safe_float(info.get("returnOnEquity", 0)),
            "roa": safe_float(info.get("returnOnAssets", 0)) / 100.0
                if safe_float(info.get("returnOnAssets", 0)) > 1
                else safe_float(info.get("returnOnAssets", 0)),
            "gross_margin": safe_float(info.get("grossMargins", 0)),
            "net_margin": safe_float(info.get("profitMargins", 0)),
            "revenue_growth": safe_float(info.get("revenueGrowth", 0)),
            "profit_growth": safe_float(info.get("earningsGrowth", 0)),
            "debt_ratio": _debt,
            "current_ratio": safe_float(info.get("currentRatio", 0)),
            "eps": safe_float(info.get("trailingEps", 0)),
            "bvps": safe_float(info.get("bookValue", 0)),
        }
    except Exception:
        return None



def get_fundamentals(
    code: str,
    market: str = "A",
    force_refresh: bool = False,
    cached_only: bool = False,
    max_age_days: int = 120,
) -> Optional[Dict[str, Any]]:
    """Get latest fundamental snapshot. Graceful degradation."""
    code = normalize_code_for_market(code, market)
    cached = _cache.get_latest_factor_snapshot(code, market=market)
    if cached_only:
        return cached
    if cached and not force_refresh:
        # Add TTL check: if cached data is stale, refresh it.
        date_str = str(cached.get("date", "")).strip()
        if date_str:
            try:
                snapshot_date = datetime.strptime(date_str, "%Y-%m-%d")
                if (datetime.now() - snapshot_date).days <= max_age_days:
                    return cached
            except ValueError:
                pass
    try:
        snapshot = _fetch_fundamentals(code, market)
        if snapshot:
            snapshot["market"] = market
            _cache.upsert_factor_snapshot([snapshot])
            return snapshot
    except RuntimeError as exc:
        msg = str(exc)
        if "Daily API limit reached" in msg:
            logger.debug("get_fundamentals API limit for %s, using cache", code)
        else:
            logger.warning("get_fundamentals fetch failed for %s: %s", code, exc)
    except Exception as exc:
        logger.warning("get_fundamentals fetch failed for %s: %s", code, exc)
    return cached


def _backfill_valuation_from_price(result: Dict[str, Any], code: str, market: str) -> None:
    """Compute PE / PB from cached close price and fundamental EPS / BVPS."""
    eps = result.get("eps", 0.0) or 0.0
    bvps = result.get("bvps", 0.0) or 0.0
    price = None
    with _cache._conn() as conn:
        cur = conn.execute(
            "SELECT close FROM daily_price "
            "WHERE market=? AND code=? ORDER BY date DESC LIMIT 1",
            (market, code),
        )
        row = cur.fetchone()
        if row:
            price = row[0]
    if price and eps > 0 and not result.get("pe_ttm"):
        result["pe_ttm"] = round(price / eps, 2)
    if price and bvps > 0 and not result.get("pb"):
        result["pb"] = round(price / bvps, 2)


def _fetch_fundamentals(code: str, market: str) -> Optional[Dict[str, Any]]:
    """Fetch fundamentals from available source (THS -> Sina -> OpenBB -> yfinance).

    For A-shares: THS provides detailed financials (ROE, margins, growth).
    PE/PB are computed from cached price + EPS/BVPS when available.
    For US/HK: yfinance is the primary source (AKShare US financials unreliable).
    """
    # US/HK: yfinance first (AKShare US/HK financial endpoints are unreliable)
    if market in ("HK", "US"):
        yf = _try_yfinance()
        if yf is not None:
            result = _fetch_fundamentals_yfinance(code, market, yf)
            if result:
                return result
        obb = _try_openbb()
        if obb is not None:
            result = _fetch_fundamentals_openbb(code, market, obb)
            if result:
                return result
        # Fallback: try AKShare (HK only, US already known to be unreliable)
        if market == "HK":
            ak = _try_akshare()
            if ak is not None:
                result = _fetch_fundamentals_hk_analysis(code, ak)
                if result:
                    return result

    # A-shares: THS -> Sina path
    ak = _try_akshare()
    result: Optional[Dict[str, Any]] = None
    if ak is not None:
        ths_result = _fetch_fundamentals_ths(code, ak)
        sina_result = _fetch_fundamentals_ak(code, market, ak)
        if ths_result is not None:
            result = ths_result
            if sina_result is not None:
                for vk in ("market_cap", "pe_ttm", "pe_static", "pb",
                           "ps_ttm", "pcf_ttm", "dividend_yield"):
                    if sina_result.get(vk) and not result.get(vk):
                        result[vk] = sina_result[vk]
        else:
            result = sina_result
    if result:
        _backfill_valuation_from_price(result, code, market)
        return result
    _report_no_data(code, market, "fundamentals")
    return None


def _fetch_fundamentals_ths(code: str, ak) -> Optional[Dict[str, Any]]:
    """Fetch A-share fundamentals via THS financial abstract (primary source).

    Provides richer data than the Sina fallback, including recent-period
    revenue, profit, margins, ROE, leverage, and liquidity ratios.
    """
    try:
        with _akshare_lock:
            df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
    except Exception:
        return None
    if df is None or df.empty:
        return None

    latest = df.iloc[-1]
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
    _map_ths_field(latest, "基本每股收益", result, "eps")
    _map_ths_field(latest, "每股净资产", result, "bvps")
    _map_ths_field(latest, "净资产收益率", result, "roe")
    _map_ths_field(latest, "销售毛利率", result, "gross_margin")
    _map_ths_field(latest, "销售净利率", result, "net_margin")
    _map_ths_field(latest, "资产负债率", result, "debt_ratio")
    _map_ths_field(latest, "营业总收入同比增长率", result, "revenue_growth")
    _map_ths_field(latest, "净利润同比增长率", result, "profit_growth")
    _map_ths_field(latest, "流动比率", result, "current_ratio")
    return result


def _parse_chinese_number(text: Any) -> float:
    """Convert a Chinese-formatted number string to float.

    Handles formats like:
      "8827.11万" -> 88271100.0
      "29.57亿"   -> 2957000000.0
      "31.00%"    -> 0.31
      "0.1040"    -> 0.104
      "--"        -> 0.0
    """
    if text is None:
        return 0.0
    if isinstance(text, (int, float)):
        return float(text) if not (isinstance(text, float) and text != text) else 0.0
    s = str(text).strip().replace(",", "").replace(" ", "")
    if not s or s in ("--", "-", ""):
        return 0.0
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100.0
        except (ValueError, TypeError):
            return 0.0
    multiplier = 1.0
    if s.endswith("亿"):
        multiplier = 1e8
        s = s[:-1]
    elif s.endswith("万"):
        multiplier = 1e4
        s = s[:-1]
    elif s.endswith("元"):
        s = s[:-1]
    try:
        return float(s) * multiplier
    except (ValueError, TypeError):
        return 0.0


def _map_ths_field(row, col_name: str, target: dict, key: str) -> None:
    """Extract a field from a THS financial abstract row into a target dict.

    ``_parse_chinese_number`` already handles percentage (``%``) and
            Chinese-unit (``万``/``亿``) suffixes.
    """
    if col_name not in row.index:
        return
    target[key] = _parse_chinese_number(row[col_name])


@_api_call("fundamentals_hk")
def _fetch_fundamentals_hk_analysis(
    code: str, ak
) -> Optional[Dict[str, Any]]:
    """Fetch HK fundamentals via stock_financial_hk_analysis_indicator_em.

    The older stock_financial_hk_report_em endpoint currently returns an HTML
    error page for most HK stocks; this function uses the working alternative.
    """
    try:
        with _akshare_lock:
            df = ak.stock_financial_hk_analysis_indicator_em(symbol=code)
        if df is None or df.empty:
            return None
        row = df.iloc[0]
        # Use REPORT_DATE if available, else today
        date_str = str(row.get("REPORT_DATE", ""))[:10]
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        return {
            "code": code,
            "date": date_str,
            "market": "HK",
            "market_cap": 0.0,  # backfilled from price later
            "pe_ttm": 0.0,
            "pe_static": 0.0,
            "pb": 0.0,
            "ps_ttm": 0.0,
            "pcf_ttm": 0.0,
            "dividend_yield": 0.0,
            "roe": safe_float(row.get("ROE_AVG", 0)) / 100.0,
            "roa": safe_float(row.get("ROA", 0)) / 100.0,
            "gross_margin": safe_float(row.get("GROSS_PROFIT_RATIO", 0)) / 100.0,
            "net_margin": safe_float(row.get("NET_PROFIT_RATIO", 0)) / 100.0,
            "revenue_growth": safe_float(row.get("OPERATE_INCOME_YOY", 0)) / 100.0,
            "profit_growth": safe_float(row.get("HOLDER_PROFIT_YOY", 0)) / 100.0,
            "debt_ratio": safe_float(row.get("DEBT_ASSET_RATIO", 0)) / 100.0,
            "current_ratio": safe_float(row.get("CURRENT_RATIO", 0)),
            "eps": safe_float(row.get("EPS_TTM", 0)),
            "bvps": safe_float(row.get("BPS", 0)),
        }
    except Exception:
        return None


@_api_call("fundamentals")
def _fetch_fundamentals_ak(code: str, market: str, ak) -> Optional[Dict[str, Any]]:
    """Fetch fundamentals via Sina financial abstract.

    Extracts ALL quarterly periods from the API response (not just the latest),
    enabling point-in-time historical backtesting.
    """
    try:
        with _akshare_lock:
            if market == "A":
                df = ak.stock_financial_report_sina(symbol=code, name="主要指标")
            elif market == "HK":
                result = _fetch_fundamentals_hk_analysis(code, ak)
                if result:
                    return result
                # Fallback: try the old endpoint (may work for some stocks)
                df = ak.stock_financial_hk_report_em(symbol=code)
            elif market == "US":
                df = ak.stock_financial_us_report_em(symbol=code)
            else:
                return None
        if df is None or df.empty or len(df.columns) < 3:
            return None

        # Discover date columns (columns that look like dates)
        date_cols = []
        for col_idx in range(2, len(df.columns)):
            col_name = str(df.columns[col_idx])
            if len(col_name.replace("-", "")) >= 6:
                date_cols.append(col_name)

        if not date_cols:
            date_cols = [df.columns[2]]

        def _parse_one_period(df, col_name: str) -> Dict[str, Any]:
            """Build one fundamental snapshot from a single period column."""
            snap: Dict[str, Any] = {
                "code": code,
                "date": col_name,
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
            for i in range(len(df)):
                name = str(df.iloc[i, 1])
                val = df.iloc[i][col_name]
                if val is None or (isinstance(val, float) and (val != val)):
                    continue
                v = safe_float(val)
                if name == "基本每股收益":
                    snap["eps"] = v
                elif name == "每股净资产":
                    snap["bvps"] = v
                elif name == "净资产收益率(ROE)":
                    snap["roe"] = v / 100.0
                elif name == "毛利率":
                    snap["gross_margin"] = v / 100.0
                elif name == "销售净利率":
                    snap["net_margin"] = v / 100.0
                elif name == "资产负债率":
                    snap["debt_ratio"] = v / 100.0
                elif name == "营业收入增长率":
                    snap["revenue_growth"] = v / 100.0
                elif name == "归属母公司净利润增长率":
                    snap["profit_growth"] = v / 100.0
                elif name == "流动比率":
                    snap["current_ratio"] = v
            return snap

        # HK/US: return only latest (API structure differs)
        if market != "A":
            result = _parse_one_period(df, date_cols[0])
            result["market"] = market
            return result

        # A-shares: extract ALL periods for point-in-time history
        snapshots = []
        for dc in date_cols:
            snap = _parse_one_period(df, dc)
            snap["market"] = market
            snapshots.append(snap)

        if snapshots:
            _cache.upsert_factor_snapshot(snapshots)
            # Return the latest for API compatibility
            return snapshots[0]
        return None
    except Exception:
        return None


def sync_symbol_data(
    code: str,
    market: str = "A",
    history_days: int = 365,
    need_fundamentals: bool | None = None,
    full_history: bool = False,
    fundamentals_max_age_days: int = 120,
) -> Dict[str, Any]:
    """Synchronize local cache for a single symbol within a bounded scope."""
    canonical_code = normalize_code_for_market(code, market)
    require_fundamentals = (
        _market_supports_fundamentals(market)
        if need_fundamentals is None
        else bool(need_fundamentals)
    )

    history_before_rows = _cache.get_daily_price(canonical_code, market=market)
    history_before = len(history_before_rows)

    # Determine if we need to fetch history: either we don't have enough,
    # or full_history is requested.  Also track if the API was actually
    # called (for the "fetched" counter below).
    needs_history_fetch = history_before < history_days or full_history

    # For full_history mode, check if the API can be skipped because
    # local data is already complete.
    _skip_history_api = False
    if full_history and history_before_rows:
        _dates = sorted(
            str(r.get("date", "")).strip()
            for r in history_before_rows
            if str(r.get("date", "")).strip()
        )
        if _dates:
            target_start = _cold_start_date(market)
            local_earliest = _dates[0]
            local_latest = _dates[-1]
            today_str = _date_str(datetime.now())
            if local_earliest <= target_start and local_latest == today_str:
                _skip_history_api = True

    history_target = (
        max(history_days, history_before)
        if not full_history
        else history_days
    )
    history_rows = history_before_rows
    history_error = ""
    history_api_called = False

    if needs_history_fetch and not _skip_history_api:
        try:
            history_rows = get_kline(
                canonical_code,
                market,
                days=history_target,
                force_refresh=full_history,
                full_history=full_history,
            )
            history_api_called = True
        except Exception as exc:
            history_error = str(exc)
        # 增量拉取后从缓存读完整数据，避免 get_kline 返回截断行数
        # 导致 history_after 计数不准。
        history_rows = _cache.get_daily_price(canonical_code, market=market)
    elif needs_history_fetch and _skip_history_api:
        # Local data is already fully covered, treat as cache hit.
        history_api_called = False
    history_after = len(history_rows)
    history_ready = history_after >= history_days
    history_covered_date = _latest_cached_date(history_rows)
    _upsert_symbol_sync_state(
        canonical_code,
        market,
        "history",
        status="ok" if history_ready else "partial",
        covered_date=history_covered_date,
        last_error=history_error,
    )

    fundamentals_before_snapshot = _cache.get_latest_factor_snapshot(
        canonical_code,
        market=market,
    )
    fundamentals_before = _has_fresh_snapshot(
        fundamentals_before_snapshot,
        fundamentals_max_age_days,
    )
    fundamentals_after_snapshot = fundamentals_before_snapshot
    fundamentals_error = ""

    if require_fundamentals and not fundamentals_before:
        try:
            fundamentals_after_snapshot = get_fundamentals(
                canonical_code,
                market,
                force_refresh=False,
            )
        except Exception as exc:
            fundamentals_error = str(exc)
            fundamentals_after_snapshot = _cache.get_latest_factor_snapshot(
                canonical_code,
                market=market,
            )
    fundamentals_after = _has_fresh_snapshot(
        fundamentals_after_snapshot,
        fundamentals_max_age_days,
    )
    fundamentals_covered_date = str(
        (fundamentals_after_snapshot or {}).get("date", "")
    ).strip()
    if require_fundamentals:
        _upsert_symbol_sync_state(
            canonical_code,
            market,
            "fundamentals",
            status="ok" if fundamentals_after else "partial",
            covered_date=fundamentals_covered_date,
            last_error=fundamentals_error,
        )

    return {
        "scope_type": "symbol",
        "scope_key": f"{market}:{canonical_code}",
        "code": canonical_code,
        "market": market,
        "requested": 1,
        "history_before": history_before,
        "history_after": history_after,
        "history_target": history_days,
        "history_ready": history_ready,
        # Cache hit = API was not called (either had enough data or already fully covered)
        "history_cache_hit": not history_api_called and history_after > 0,
        # Fetched = API was called (regardless of whether new rows were added)
        "history_fetched": history_api_called,
        "history_covered_through": history_covered_date,
        "fundamentals_required": require_fundamentals,
        "fundamentals_before": fundamentals_before,
        "fundamentals_after": fundamentals_after,
        "fundamentals_cache_hit": fundamentals_before,
        # Fetched = we attempted the API call (even if it failed/returned None)
        "fundamentals_fetched": (
            require_fundamentals and not fundamentals_before
        ),
        "fundamentals_covered_through": fundamentals_covered_date,
        "ready": history_ready and (fundamentals_after or not require_fundamentals),
        "errors": [err for err in (history_error, fundamentals_error) if err],
    }


def _sync_single_symbol_safe(
    code: str,
    market: str,
    history_days: int,
    need_fundamentals: bool | None,
    full_history: bool,
    fundamentals_max_age_days: int,
) -> Dict[str, Any]:
    """Thread-safe wrapper around sync_symbol_data.

    Each thread gets its own DB connection path (SQLite in WAL mode allows
    concurrent reads, serialised writes). The RLock in _akshare_lock
    prevents concurrent AKShare calls.
    """
    try:
        return sync_symbol_data(
            code,
            market,
            history_days=history_days,
            need_fundamentals=need_fundamentals,
            full_history=full_history,
            fundamentals_max_age_days=fundamentals_max_age_days,
        )
    except Exception as exc:
        canonical = normalize_code_for_market(code, market)
        return {
            "scope_type": "symbol",
            "scope_key": f"{market}:{canonical}",
            "code": canonical,
            "market": market,
            "requested": 1,
            "history_before": 0,
            "history_after": 0,
            "history_target": history_days,
            "history_ready": False,
            "history_cache_hit": False,
            "history_fetched": False,
            "history_covered_through": "",
            "fundamentals_required": False,
            "fundamentals_before": False,
            "fundamentals_after": False,
            "fundamentals_cache_hit": False,
            "fundamentals_fetched": False,
            "fundamentals_covered_through": "",
            "ready": False,
            "errors": [str(exc)],
        }


_CHECKPOINT_KEY_PREFIX = "sync_checkpoint:"


def _save_checkpoint(scope_type: str, scope_key: str, done_codes: set) -> None:
    """Persist checkpoint to kv_store."""
    key = f"{_CHECKPOINT_KEY_PREFIX}{scope_type}:{scope_key}"
    value = ",".join(sorted(done_codes))
    try:
        _cache.kv_set_str(key, value, ttl=86400 * 7)  # 7 天过期
    except Exception:
        pass


def _load_checkpoint(scope_type: str, scope_key: str) -> set:
    """Load checkpoint from kv_store."""
    key = f"{_CHECKPOINT_KEY_PREFIX}{scope_type}:{scope_key}"
    try:
        value = _cache.kv_get_str(key)
        if value:
            return {c.strip() for c in value.split(",") if c.strip()}
    except Exception:
        pass
    return set()


def _clear_checkpoint(scope_type: str, scope_key: str) -> None:
    """Remove checkpoint after successful completion."""
    key = f"{_CHECKPOINT_KEY_PREFIX}{scope_type}:{scope_key}"
    try:
        with _cache._conn() as conn:
            conn.execute("DELETE FROM kv_store WHERE key=?", (key,))
    except Exception:
        pass


def sync_symbols_data(
    codes: Sequence[str],
    market: str,
    history_days: int,
    need_fundamentals: bool | None = None,
    full_history: bool = False,
    fundamentals_max_age_days: int = 120,
    limit: int = 0,
) -> Dict[str, Any]:
    """Synchronize a bounded list of symbols with concurrent fetch + checkpoint.

    Uses ThreadPoolExecutor for parallel API calls (bounded by API rate limits).
    Persists progress via kv_store checkpoint so interrupted runs can resume.
    """
    selected_codes = list(codes[:limit] if limit else codes)
    total = len(selected_codes)
    history_label = "全量历史" if full_history else f"{history_days}天"
    scope_type = "symbol_batch"
    scope_key = f"{market}:{history_days}:{'full' if full_history else 'partial'}"
    start_time = time.time()

    # Load checkpoint: skip already-synced codes
    done_codes = _load_checkpoint(scope_type, scope_key)
    pending = [c for c in selected_codes if c not in done_codes]
    skipped = total - len(pending)

    print(
        f"  同步范围: {market} 市场, 共 {total} 只, 目标={history_label}"
        f"{' (断点续传: 已跳过 ' + str(skipped) + ' 只' if skipped else ''})",
        flush=True,
    )

    max_workers = min(cfg_get("sync_max_workers", 8), total)
    if total > 100:
        print(f"  并发数: {max_workers}, 剩余 {len(pending)} 只待同步", flush=True)

    # Batch-read date ranges for all symbols upfront to avoid N+1 queries.
    # Each symbol would otherwise trigger a separate get_daily_price() SELECT.
    cached_date_ranges = _cache.get_date_ranges(selected_codes, market=market)

    # Thread-safe accumulators for progress tracking
    results_lock = threading.Lock()
    per_symbol: List[Dict[str, Any]] = []

    hist_fetch = 0
    fund_fetch = 0
    cache_hit = 0
    all_earliest: List[str] = []
    all_latest: List[str] = []
    total_rows = 0
    processed_count = 0

    def _accumulate(result: Dict[str, Any]) -> None:
        """Thread-safe accumulation of per-symbol result."""
        nonlocal hist_fetch, fund_fetch, cache_hit, total_rows, processed_count
        with results_lock:
            per_symbol.append(result)

            if result.get("history_fetched"):
                hist_fetch += 1
            if result.get("fundamentals_fetched"):
                fund_fetch += 1
            if result.get("history_cache_hit") and (
                result.get("fundamentals_cache_hit")
                or not result.get("fundamentals_required")
            ):
                cache_hit += 1

            covered = str(result.get("history_covered_through", "")).strip()
            if covered:
                all_latest.append(covered)

            hist_after = result.get("history_after", 0) or 0
            total_rows += hist_after

            code = result.get("code", "")
            rng = cached_date_ranges.get(code)
            if rng:
                all_earliest.append(rng[0])

            processed_count += 1

    # Execute with ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {
            executor.submit(
                _sync_single_symbol_safe,
                code,
                market,
                history_days=history_days,
                need_fundamentals=need_fundamentals,
                full_history=full_history,
                fundamentals_max_age_days=fundamentals_max_age_days,
            ): code
            for code in pending
        }

        completed_this_run = set()
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            try:
                result = future.result()
                if result:
                    _accumulate(result)
                    completed_this_run.add(code)
            except Exception:
                completed_this_run.add(code)

            # Periodic checkpoint + progress print
            if processed_count % 50 == 0 or processed_count == len(pending):
                pct = (skipped + processed_count) * 100 // total
                date_range = ""
                if all_earliest and all_latest:
                    date_range = (
                        f" | 日期范围: {min(all_earliest)} ~ {max(all_latest)}"
                    )
                elapsed = time.time() - start_time
                m, s = divmod(int(elapsed), 60)
                time_str = f"{m}分{s}秒" if m else f"{s}秒"
                print(
                    f"  [{skipped + processed_count}/{total}] {pct}% | "
                    f"已用时={time_str} | "
                    f"缓存命中={cache_hit}, K线拉取={hist_fetch}, "
                    f"基本面拉取={fund_fetch}, "
                    f"累计行数={total_rows:,}{date_range}",
                    flush=True,
                )
                # Save checkpoint every 50 items
                done_codes.update(completed_this_run)
                _save_checkpoint(scope_type, scope_key, done_codes)
                completed_this_run = set()

    # Final checkpoint
    if completed_this_run:
        done_codes.update(completed_this_run)
        _save_checkpoint(scope_type, scope_key, done_codes)

    # Sort per_symbol to match original code order for consistent output
    code_order = {c: i for i, c in enumerate(selected_codes)}
    per_symbol.sort(key=lambda r: code_order.get(r.get("code", ""), 999999))

    # If all codes are ready, clear checkpoint
    if len(done_codes) >= total:
        _clear_checkpoint(scope_type, scope_key)

    elapsed = time.time() - start_time

    return {
        "scope_type": scope_type,
        "market": market,
        "requested": len(selected_codes),
        "history_ready": sum(1 for item in per_symbol if item["history_ready"]),
        "fundamentals_ready": sum(
            1
            for item in per_symbol
            if item.get("fundamentals_required") and item.get("fundamentals_after")
        ),
        "ready": sum(1 for item in per_symbol if item["ready"]),
        "cache_hits": cache_hit,
        "history_fetched_count": hist_fetch,
        "fundamentals_fetched_count": fund_fetch,
        "total_history_rows": total_rows,
        "earliest_date": min(all_earliest) if all_earliest else "",
        "latest_date": max(all_latest) if all_latest else "",
        "missing_codes": [
            item["code"] for item in per_symbol if not item.get("ready", False)
        ],
        "elapsed_seconds": round(elapsed, 1),
        "symbols": per_symbol,
    }


def sync_watchlist_data(
    market: str = "A",
    history_days: int = 365,
    need_fundamentals: bool = True,
    full_history: bool = False,
    fundamentals_max_age_days: int = 120,
) -> Dict[str, Any]:
    """Synchronize the configured watchlist for a market."""
    watchlist = [
        normalize_code_for_market(code, market)
        for code in cfg_get("watchlist", [])
        if str(code).strip()
    ]
    result = sync_symbols_data(
        watchlist,
        market,
        history_days=history_days,
        need_fundamentals=need_fundamentals,
        full_history=full_history,
        fundamentals_max_age_days=fundamentals_max_age_days,
    )
    result["scope_type"] = "watchlist"
    result["scope_key"] = market
    result["covered_through"] = _aggregate_covered_through(result["symbols"])
    _upsert_scope_sync_state(
        "watchlist",
        market,
        market,
        "summary",
        status="ok" if result["ready"] == result["requested"] else "partial",
        covered_date=result["covered_through"],
    )
    return result


def sync_portfolio_data(
    codes: Sequence[str],
    market: str = "A",
    history_days: int = 365,
    need_fundamentals: bool = True,
    full_history: bool = False,
    fundamentals_max_age_days: int = 120,
) -> Dict[str, Any]:
    """Synchronize a user-provided portfolio code list."""
    normalized_codes = [
        normalize_code_for_market(code, market)
        for code in codes
        if str(code).strip()
    ]
    scope_key = ",".join(normalized_codes)
    result = sync_symbols_data(
        normalized_codes,
        market,
        history_days=history_days,
        need_fundamentals=need_fundamentals,
        full_history=full_history,
        fundamentals_max_age_days=fundamentals_max_age_days,
    )
    result["scope_type"] = "portfolio"
    result["scope_key"] = scope_key
    result["covered_through"] = _aggregate_covered_through(result["symbols"])
    _upsert_scope_sync_state(
        "portfolio",
        scope_key,
        market,
        "summary",
        status="ok" if result["ready"] == result["requested"] else "partial",
        covered_date=result["covered_through"],
    )
    return result


def sync_scan_universe_data(
    market: str = "A",
    limit: int = 200,
    history_days: int = 365,
    need_fundamentals: bool = True,
    full_history: bool = False,
    fundamentals_max_age_days: int = 120,
) -> Dict[str, Any]:
    """Synchronize a bounded candidate universe for scanning."""
    if _is_etf_market(market):
        pool = get_fund_pool()
    else:
        pool = get_stock_pool(market)
    candidate_codes = [
        str(item.get("code", "")).strip()
        for item in pool[:limit]
        if str(item.get("code", "")).strip()
    ]
    result = sync_symbols_data(
        candidate_codes,
        market,
        history_days=history_days,
        need_fundamentals=(
            need_fundamentals if _market_supports_fundamentals(market) else False
        ),
        full_history=full_history,
        fundamentals_max_age_days=fundamentals_max_age_days,
        limit=limit,
    )
    result["scope_type"] = "scan-universe"
    result["scope_key"] = f"{market}:{limit}"
    result["covered_through"] = _aggregate_covered_through(result["symbols"])
    _upsert_scope_sync_state(
        "scan-universe",
        result["scope_key"],
        market,
        "summary",
        status="ok" if result["ready"] == result["requested"] else "partial",
        covered_date=result["covered_through"],
    )
    return result


def _sync_single_etf_safe(
    code: str,
    history_days: int,
    full_history: bool,
) -> Dict[str, Any]:
    """Thread-safe wrapper for syncing a single ETF's NAV data."""
    nav_before_rows = _cache.get_fund_nav(code, history_days)
    nav_before = len(nav_before_rows)
    nav_rows = nav_before_rows
    nav_error = ""
    try:
        nav_rows = get_fund_nav(
            code,
            history_days,
            full_history=full_history,
        )
    except Exception as exc:
        nav_error = str(exc)
        nav_rows = _cache.get_fund_nav(code, history_days)
    nav_after = len(nav_rows)
    nav_ready = nav_after >= history_days
    covered_through = _latest_cached_date(nav_rows)
    _upsert_symbol_sync_state(
        code,
        "FUND",
        "nav",
        status="ok" if nav_ready else "partial",
        covered_date=covered_through,
        last_error=nav_error,
    )
    return {
        "scope_type": "symbol",
        "scope_key": f"FUND:{code}",
        "code": code,
        "market": "FUND",
        "history_before": nav_before,
        "history_after": nav_after,
        "history_target": history_days,
        "history_ready": nav_ready,
        "history_cache_hit": nav_before >= history_days,
        "history_fetched": nav_after > nav_before,
        "history_covered_through": covered_through,
        "fundamentals_required": False,
        "fundamentals_before": False,
        "fundamentals_after": False,
        "fundamentals_cache_hit": False,
        "fundamentals_fetched": False,
        "fundamentals_covered_through": "",
        "ready": nav_ready,
        "errors": [nav_error] if nav_error else [],
    }


def sync_etf_data(
    codes: Sequence[str],
    history_days: int = 365,
    limit: int = 0,
    full_history: bool = False,
) -> Dict[str, Any]:
    """Synchronize bounded ETF NAV/history data with concurrent fetch + checkpoint."""
    normalized_codes = [
        normalize_code_for_market(code, "FUND")
        for code in (codes[:limit] if limit else codes)
        if str(code).strip()
    ]
    total = len(normalized_codes)
    history_label = "全量历史" if full_history else f"{history_days}天"
    scope_type = "etf"
    scope_key = f"FUND:{history_days}:{'full' if full_history else 'partial'}"

    # Load checkpoint
    done_codes = _load_checkpoint(scope_type, scope_key)
    pending = [c for c in normalized_codes if c not in done_codes]
    skipped = total - len(pending)

    print(
        f"  同步范围: ETF 共 {total} 只, 目标={history_label}"
        f"{' (断点续传: 已跳过 ' + str(skipped) + ' 只' if skipped else ''})",
        flush=True,
    )

    max_workers = min(cfg_get("sync_max_workers", 8), total)
    if total > 10:
        print(f"  并发数: {max_workers}, 剩余 {len(pending)} 只待同步", flush=True)

    results_lock = threading.Lock()
    per_symbol: List[Dict[str, Any]] = []
    hist_fetch = 0
    cache_hit = 0
    total_rows = 0
    all_earliest: List[str] = []
    all_latest: List[str] = []
    processed_count = 0

    def _accumulate(result: Dict[str, Any]) -> None:
        nonlocal hist_fetch, cache_hit, total_rows, processed_count
        with results_lock:
            per_symbol.append(result)
            if result.get("history_fetched"):
                hist_fetch += 1
            if result.get("history_cache_hit"):
                cache_hit += 1
            total_rows += result.get("history_after", 0) or 0

            covered = str(result.get("history_covered_through", "")).strip()
            if covered:
                all_latest.append(covered)

            code = result.get("code", "")
            cached = _cache.get_fund_nav(code, history_days)
            if cached:
                values = sorted(
                    str(r.get("date", "")).strip()
                    for r in cached
                    if str(r.get("date", "")).strip()
                )
                if values:
                    all_earliest.append(values[0])

            processed_count += 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {
            executor.submit(
                _sync_single_etf_safe,
                code,
                history_days=history_days,
                full_history=full_history,
            ): code
            for code in pending
        }

        completed_this_run = set()
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            try:
                result = future.result()
                if result:
                    _accumulate(result)
                    completed_this_run.add(code)
            except Exception:
                completed_this_run.add(code)

            # Periodic checkpoint + progress
            batch = max(10, total // 10)
            if processed_count % batch == 0 or processed_count == len(pending):
                pct = (skipped + processed_count) * 100 // total
                date_range = ""
                if all_earliest and all_latest:
                    date_range = (
                        f" | 日期范围: {min(all_earliest)} ~ {max(all_latest)}"
                    )
                print(
                    f"  [{skipped + processed_count}/{total}] {pct}% | "
                    f"缓存命中={cache_hit}, NAV拉取={hist_fetch}, "
                    f"累计行数={total_rows:,}{date_range}",
                    flush=True,
                )
                done_codes.update(completed_this_run)
                _save_checkpoint(scope_type, scope_key, done_codes)
                completed_this_run = set()

    # Final checkpoint
    if completed_this_run:
        done_codes.update(completed_this_run)
        _save_checkpoint(scope_type, scope_key, done_codes)

    # Sort to match original order
    code_order = {c: i for i, c in enumerate(normalized_codes)}
    per_symbol.sort(key=lambda r: code_order.get(r.get("code", ""), 999999))

    if len(done_codes) >= total:
        _clear_checkpoint(scope_type, scope_key)

    result = {
        "scope_type": scope_type,
        "scope_key": ",".join(normalized_codes),
        "market": "FUND",
        "requested": len(normalized_codes),
        "history_ready": sum(1 for item in per_symbol if item["history_ready"]),
        "fundamentals_ready": 0,
        "ready": sum(1 for item in per_symbol if item["ready"]),
        "cache_hits": cache_hit,
        "history_fetched_count": hist_fetch,
        "fundamentals_fetched_count": 0,
        "total_history_rows": total_rows,
        "earliest_date": min(all_earliest) if all_earliest else "",
        "latest_date": max(all_latest) if all_latest else "",
        "missing_codes": [
            item["code"] for item in per_symbol if not item.get("ready", False)
        ],
        "covered_through": _aggregate_covered_through(per_symbol),
        "symbols": per_symbol,
    }
    _upsert_scope_sync_state(
        "etf",
        result["scope_key"],
        "FUND",
        "summary",
        status="ok" if result["ready"] == result["requested"] else "partial",
        covered_date=result["covered_through"],
    )
    return result


# -- Fund data --------------------------------------------------------------


def get_fund_pool(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Get the ETF-oriented FUND pool.

    The current FUND path is ETF-first. Broad mutual-fund coverage is not
    guaranteed by this cache or source path.
    """
    if force_refresh or _cache.pool_needs_refresh("FUND"):
        _refresh_fund_pool()
    funds = _cache.get_stock_pool("FUND")
    if not funds:
        with _cache._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM fund_info")
            funds = [dict(r) for r in cur.fetchall()]
    return funds


def get_etf_pool(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Return the current ETF pool using the ETF-oriented FUND backing store."""
    return get_fund_pool(force_refresh=force_refresh)


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


def get_fund_nav(
    code: str,
    days: int = 365,
    cached_only: bool = False,
    force_refresh: bool = False,
    full_history: bool = False,
) -> List[Dict[str, Any]]:
    """Get ETF-style NAV/history with incremental cache update.

    Delegates to IncrementalCacheFetcher to eliminate duplicated
    cache-first + incremental-fetch logic.
    """
    from incremental_fetcher import get_fund_nav_incremental
    return get_fund_nav_incremental(code, days, cached_only, force_refresh, full_history)


def get_etf_nav(code: str, days: int = 365) -> List[Dict[str, Any]]:
    """Return ETF NAV/history via the current ETF-oriented FUND path."""
    return get_fund_nav(code, days)


# -- Market index -----------------------------------------------------------


def get_market_index(
    index_code: str = "000001",
    days: int = 250,
    cached_only: bool = False,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """Get market index K-line with incremental cache update.

    Delegates to IncrementalCacheFetcher to eliminate duplicated
    cache-first + incremental-fetch logic.
    """
    from incremental_fetcher import get_market_index_incremental
    return get_market_index_incremental(index_code, days, cached_only, force_refresh)


@_api_call("market_index")
def _fetch_market_index(index_code: str, start: str, end: str) -> List[Dict[str, Any]]:
    """Fetch market index via Sina with date-range filtering.

    Supports both Shanghai (6xxxxx, 00xxxx starting with 000) and
    Shenzhen (39xxxx, 399xxx) indices.
    """
    ak = _try_akshare()
    if ak is None:
        return []
    # Auto-detect exchange prefix for Shenzhen vs Shanghai indices
    if index_code.startswith(("39", "15")):
        prefix = "sz"
    else:
        prefix = "sh"
    try:
        df = ak.stock_zh_index_daily(symbol=f"{prefix}{index_code}")
        if df is None or df.empty:
            return []

        df["date"] = df["date"].astype(str)
        clean_start = start.replace("-", "")
        clean_end = end.replace("-", "")
        dates_clean = df["date"].str.replace("-", "")
        df = df[(dates_clean >= clean_start) & (dates_clean <= clean_end)]

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


def _safe_parse_date(value: str, fallback: Optional[datetime] = None) -> datetime:
    """Parse a date string that may be 'YYYY-MM-DD' or 'YYYYMMDD'.

    Returns *fallback* (default: now - 365 days) on any parse error so that
    malformed cached dates do not crash the entire data engine.
    """
    if fallback is None:
        fallback = datetime.now() - timedelta(days=365)
    if not value:
        return fallback
    try:
        return datetime.strptime(value.replace("-", ""), "%Y%m%d")
    except (ValueError, TypeError):
        return fallback


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _add_days(date_str: str, days: int) -> str:
    try:
        clean = date_str.replace("-", "")
        dt = datetime.strptime(clean, "%Y%m%d")
        return _date_str(dt + timedelta(days=days))
    except (ValueError, TypeError):
        return _date_str(datetime.now() + timedelta(days=days))
