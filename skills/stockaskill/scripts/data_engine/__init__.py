"""Core data engine: AKShare (Sina primary) with caching and fallbacks.

Split from monolithic data_engine.py into focused submodules:
- config: data source imports, retry decorator, helper utilities
- pool: stock pool fetch and management
- kline: K-line data fetching
- fundamentals: fundamental data fetching
- sync: bounded sync operations (symbol, watchlist, portfolio, scan-universe)
- helpers: shared validation, estimation, quality flags
"""

# Re-export public API so all imports that previously used
# from data_engine import get_stock_pool still work.

from utils import safe_float

# For backward compatibility with tests that mock data_engine._cache
from data_engine.config import (
    _akshare_lock,
    _api_call,
    _api_limit_exhausted,
    _cache,  # noqa: F401
    _cold_start_date,
    _is_etf_market,
    _market_supports_fundamentals,
    _report_no_data,
    _try_akshare,
    get_cache,
    is_api_limit_exhausted,
)
from data_engine.fundamentals import (
    _fetch_fundamentals,
    get_fundamentals,
)
from data_engine.helpers import (
    _add_days,
    _detect_quality_flags,
    _latest_cached_date,
    check_data_completeness,
    get_vwap,
)
from data_engine.kline import (
    _fetch_kline,
    get_kline,
)
from data_engine.pool import (
    ensure_stock_pool_candidates_ready,
    get_stock_pool,
)
from data_engine.sync import (
    _fetch_market_index,
    get_etf_nav,
    get_etf_pool,
    get_fund_nav,
    get_fund_pool,
    get_market_index,
    sync_etf_data,
    sync_portfolio_data,
    sync_scan_universe_data,
    sync_symbol_data,
    sync_symbols_data,
    sync_watchlist_data,
)

__all__ = [
    # Public API
    "get_stock_pool",
    "get_etf_pool",
    "get_fund_pool",
    "get_kline",
    "get_fundamentals",
    "get_vwap",
    "get_market_index",
    "get_fund_nav",
    "get_etf_nav",
    "check_data_completeness",
    "is_api_limit_exhausted",
    "sync_symbol_data",
    "sync_watchlist_data",
    "sync_portfolio_data",
    "sync_scan_universe_data",
    "sync_etf_data",
    "ensure_stock_pool_candidates_ready",
    # Internal (exposed for submodules and tests)
    "_api_call",
    "_akshare_lock",
    "_api_limit_exhausted",
    "_cold_start_date",
    "_detect_quality_flags",
    "_fetch_kline",
    "_fetch_fundamentals",
    "_is_etf_market",
    "_latest_cached_date",
    "_market_supports_fundamentals",
    "_report_no_data",
    "safe_float",
    "_add_days",
    "get_cache",
    "_fetch_market_index",
    "sync_symbols_data",
    "_try_akshare",
]
