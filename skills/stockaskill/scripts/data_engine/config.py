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
