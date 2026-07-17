"""Core data engine: AKShare (Sina primary) with caching and fallbacks.

Split from monolithic data_engine.py into focused submodules:
- config: data source imports, retry decorator, helper utilities
- pool: stock pool fetch and management
- kline: K-line data fetching
- fundamentals: fundamental data fetching
- sync: bounded sync operations (symbol, watchlist, portfolio, scan-universe)
- helpers: shared validation, estimation, quality flags
"""

# Re-export public API — all imports that previously used
# `from data_engine import get_stock_pool` still work.

# Re-export safe_float from utils (needed by callers)
from utils import safe_float

from data_engine.config import (
    _api_call,
    _api_limit_exhausted,
    _akshare_lock,
    _cold_start_date,
    _is_etf_market,
    _market_supports_fundamentals,
    _report_no_data,
    _sina_code,
    _try_akshare,
    _try_baostock,
    _try_efinance,
    _try_yfinance,
    get_cache,
    is_api_limit_exhausted,
)
from data_engine.helpers import (
    _add_days,
    _has_fresh_snapshot,
    _latest_cached_date,
    _aggregate_covered_through,
    _backfill_missing_factors,
    _backfill_valuation_from_price,
    _date_str,
    _detect_quality_flags,
    _estimate_amount,
    _safe_parse_date,
    check_data_completeness,
    get_vwap,
)
from data_engine.pool import (
    _backfill_pool_metadata_from_bs,
    _enrich_a_pool_from_baostock,
    _fetch_a_stock_pool,
    _fetch_a_stock_pool_baostock,
    _fetch_a_stock_profile_metadata,
    _fetch_fund_pool_df,
    _fetch_hk_stock_pool,
    _fetch_us_stock_pool,
    _infer_list_date_from_history,
    _refresh_stock_pool,
    ensure_stock_pool_candidates_ready,
    get_stock_pool,
)
from data_engine.kline import (
    _fetch_kline,
    _fetch_kline_bs,
    _fetch_kline_ef,
    _fetch_kline_sina,
    _fetch_kline_yfinance,
    _normalize_kline_df,
    _yfinance_symbol,
    get_kline,
)
from data_engine.fundamentals import (
    _fetch_fundamentals,
    _fetch_fundamentals_ak,
    _fetch_fundamentals_hk_analysis,
    _fetch_fundamentals_ths,
    _fetch_fundamentals_us_akshare,
    _fetch_fundamentals_yfinance,
    _map_ths_field,
    _parse_chinese_number,
    get_fundamentals,
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

# For backward compatibility with tests that mock data_engine._cache
from data_engine.config import _cache  # noqa: F401

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
]
