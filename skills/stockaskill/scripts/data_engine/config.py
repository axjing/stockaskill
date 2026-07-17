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


# -- Output suppression for noisy libraries ---------------------------------
# _suppress_output is imported from utils

# -- Error reporting helpers ------------------------------------------------


def _report_no_data(code: str, market: str, data_kind: str) -> None:
    """Log a user-visible message when no data source succeeded."""
    if market in ("HK", "US"):
        sources = "AKShare -> yfinance"
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
                            "kline_yf": "yfinance",
                            "fundamentals": "AKShare/Sina",
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



def _try_yfinance() -> Optional[Any]:
    """Import yfinance, return module or None."""
    try:
        import yfinance as yf

        return yf
    except ImportError:
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
