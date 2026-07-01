"""Local-first data readiness helpers for analysis, scans, and backtests."""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Sequence

from cache import get_cache
from config import get as cfg_get
from data_engine import (
    get_etf_pool,
    get_market_index,
    get_stock_pool,
    sync_etf_data,
    sync_portfolio_data,
    sync_scan_universe_data,
    sync_symbol_data,
    sync_symbols_data,
    sync_watchlist_data,
)
from utils import normalize_code_for_market

_cache = get_cache()


def ensure_pool_ready(market: str) -> List[Dict[str, Any]]:
    """Ensure a market pool exists locally and return it."""
    if market == "FUND":
        return get_etf_pool()
    return get_stock_pool(market)


def ensure_symbol_analysis_ready(code: str, market: str = "A") -> Dict[str, Any]:
    """Ensure a symbol has enough local data for analysis."""
    return ensure_symbol_ready(
        code,
        market,
        history_days=cfg_get("data_readiness.analysis_history_days", 365),
        need_fundamentals=market != "FUND",
        fundamentals_max_age_days=cfg_get(
            "data_readiness.analysis_fundamentals_max_age_days", 120
        ),
    )


def ensure_symbol_ready(
    code: str,
    market: str = "A",
    history_days: int = 365,
    need_fundamentals: bool = True,
    full_history: bool = False,
    fundamentals_max_age_days: int = 120,
) -> Dict[str, Any]:
    """Ensure local cache is sufficient for a single symbol."""
    canonical_code = normalize_code_for_market(code, market)
    result = sync_symbol_data(
        canonical_code,
        market,
        history_days=history_days,
        need_fundamentals=need_fundamentals,
        full_history=full_history,
        fundamentals_max_age_days=fundamentals_max_age_days,
    )
    result["covered_through"] = result.get("history_covered_through", "")
    return result


def ensure_symbols_ready(
    codes: Sequence[str],
    market: str,
    history_days: int,
    need_fundamentals: bool = True,
    full_history: bool = False,
    fundamentals_max_age_days: int = 120,
    limit: int = 0,
) -> Dict[str, Any]:
    """Ensure local cache is sufficient for a list of symbols."""
    result = sync_symbols_data(
        codes,
        market,
        history_days=history_days,
        need_fundamentals=need_fundamentals,
        full_history=full_history,
        fundamentals_max_age_days=fundamentals_max_age_days,
        limit=limit,
    )
    result["covered_through"] = max(
        [
            str(item.get("history_covered_through", "")).strip()
            for item in result.get("symbols", [])
            if str(item.get("history_covered_through", "")).strip()
        ],
        default="",
    )
    return result


def ensure_market_scan_ready(
    market: str,
    candidates: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Warm local data for scan candidates before cached-only scoring."""
    history_days = cfg_get("data_readiness.scan_history_days", 365)
    prefetch_limit = cfg_get(
        "data_readiness.scan_prefetch_limit",
        cfg_get("scan_max_candidates", 200),
    )
    need_fundamentals = bool(cfg_get("data_readiness.scan_fundamentals", True))
    codes = [str(candidate.get("code", "")) for candidate in candidates if candidate]

    if market == "FUND":
        return ensure_symbols_ready(
            codes,
            market,
            history_days=cfg_get("data_readiness.fund_screen_history_days", 365),
            need_fundamentals=False,
            limit=prefetch_limit,
        )

    return ensure_symbols_ready(
        codes,
        market,
        history_days=history_days,
        need_fundamentals=need_fundamentals,
        limit=prefetch_limit,
    )


def ensure_watchlist_ready(
    market: str = "A",
    history_days: int | None = None,
    need_fundamentals: bool | None = None,
) -> Dict[str, Any]:
    """Warm the configured watchlist within a bounded scope."""
    target_history = history_days or cfg_get(
        "data_readiness.analysis_history_days", 365
    )
    require_fundamentals = (
        market != "FUND"
        if need_fundamentals is None
        else bool(need_fundamentals)
    )
    return sync_watchlist_data(
        market=market,
        history_days=target_history,
        need_fundamentals=require_fundamentals,
        fundamentals_max_age_days=cfg_get(
            "data_readiness.analysis_fundamentals_max_age_days", 120
        ),
    )


def ensure_portfolio_ready(
    codes: Sequence[str],
    market: str = "A",
    history_days: int | None = None,
    need_fundamentals: bool | None = None,
) -> Dict[str, Any]:
    """Warm a portfolio scope within a bounded set of symbols."""
    target_history = history_days or cfg_get(
        "data_readiness.analysis_history_days", 365
    )
    require_fundamentals = (
        market != "FUND"
        if need_fundamentals is None
        else bool(need_fundamentals)
    )
    return sync_portfolio_data(
        codes,
        market=market,
        history_days=target_history,
        need_fundamentals=require_fundamentals,
        fundamentals_max_age_days=cfg_get(
            "data_readiness.analysis_fundamentals_max_age_days", 120
        ),
    )


def ensure_scan_universe_ready(
    market: str = "A",
    limit: int | None = None,
) -> Dict[str, Any]:
    """Warm a bounded scan universe directly from the market pool."""
    return sync_scan_universe_data(
        market=market,
        limit=limit or cfg_get(
            "data_readiness.scan_prefetch_limit",
            cfg_get("scan_max_candidates", 200),
        ),
        history_days=cfg_get("data_readiness.scan_history_days", 365),
        need_fundamentals=bool(cfg_get("data_readiness.scan_fundamentals", True)),
        fundamentals_max_age_days=cfg_get(
            "data_readiness.analysis_fundamentals_max_age_days", 120
        ),
    )


def ensure_etf_ready(
    codes: Sequence[str],
    history_days: int | None = None,
    limit: int = 0,
) -> Dict[str, Any]:
    """Warm a bounded ETF code list using ETF-specific NAV/history semantics."""
    target_days = history_days or cfg_get(
        "data_readiness.fund_screen_history_days", 365
    )
    result = sync_etf_data(
        codes,
        history_days=target_days,
        limit=limit,
    )
    result["covered_through"] = max(
        [
            str(item.get("history_covered_through", "")).strip()
            for item in result.get("symbols", [])
            if str(item.get("history_covered_through", "")).strip()
        ],
        default="",
    )
    return result


def ensure_fund_screen_ready(
    funds: Sequence[Dict[str, Any]],
    history_days: int | None = None,
    limit: int = 0,
) -> Dict[str, Any]:
    """Warm ETF data for the current ETF-oriented fund screening workflow."""
    selected_funds = list(funds[:limit] if limit else funds)
    codes = [str(fund.get("code", "")).strip() for fund in selected_funds if fund]
    return ensure_etf_ready(codes, history_days=history_days, limit=limit)


def ensure_market_index_ready(
    index_code: str = "000300",
    history_days: int | None = None,
) -> Dict[str, Any]:
    """Ensure local market index history exists."""
    target_days = history_days or cfg_get(
        "data_readiness.market_index_history_days", 1500
    )
    before = len(_cache.get_market_index(index_code, target_days))
    if before < target_days:
        get_market_index(index_code, target_days)
    after = len(_cache.get_market_index(index_code, target_days))
    return {
        "index_code": index_code,
        "history_before": before,
        "history_after": after,
        "history_ready": after >= target_days,
    }


def ensure_backtest_ready(
    market: str = "A",
    extra_symbols: Iterable[tuple[str, str]] | None = None,
) -> Dict[str, Any]:
    """Warm a bounded batch of backtest data without forcing a full-market sync."""
    min_history = cfg_get("data_readiness.backtest_history_days", 1500)
    batch_size = cfg_get("data_readiness.backtest_prefetch_batch", 50)
    pool = ensure_pool_ready(market)
    candidates = [
        stock
        for stock in pool
        if str(stock.get("code", ""))
        and not str(stock.get("code", "")).startswith("bj")
    ]
    candidates.sort(
        key=lambda stock: float(stock.get("total_market_cap", 0) or 0),
        reverse=True,
    )
    missing_codes = [
        str(stock["code"])
        for stock in candidates
        if _history_row_count(str(stock["code"])) < min_history
    ]

    result = ensure_symbols_ready(
        missing_codes,
        market,
        history_days=min_history,
        need_fundamentals=market != "FUND",
        full_history=True,
        limit=batch_size,
    )
    if market == "A":
        result["market_index"] = ensure_market_index_ready(
            "000300",
            history_days=cfg_get("data_readiness.market_index_history_days", 1500),
        )

    if extra_symbols:
        extras = []
        for symbol, extra_market in extra_symbols:
            extras.append(
                ensure_symbol_ready(
                    symbol,
                    extra_market,
                    history_days=min_history,
                    need_fundamentals=False,
                    full_history=True,
                )
            )
        result["extra_symbols"] = extras

    result["missing_candidates"] = len(missing_codes)
    return result


def _history_row_count(code: str) -> int:
    """Return the number of locally cached daily-price rows for a symbol."""
    return len(_cache.get_daily_price(code))


def _has_fresh_fundamentals(code: str, max_age_days: int, market: str = "") -> bool:
    """Check whether cached fundamentals exist and are fresh enough."""
    snapshot = _cache.get_latest_factor_snapshot(code, market=market)
    if not snapshot:
        return False
    date_str = str(snapshot.get("date", ""))
    try:
        snapshot_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return False
    return (datetime.now() - snapshot_date).days <= max_age_days
