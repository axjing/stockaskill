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
    quality = build_symbol_quality_summary(canonical_code, market, result)
    result["confidence"] = quality["confidence"]
    result["provenance"] = quality["provenance"]
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
    quality = build_scope_quality_summary(result, market, scope="symbols")
    result["confidence"] = quality["confidence"]
    result["provenance"] = quality["provenance"]
    return result


def ensure_market_scan_ready(
    market: str,
    candidates: Sequence[Dict[str, Any]],
    limit: int = 0,
) -> Dict[str, Any]:
    """Warm local data for scan candidates before cached-only scoring.

    Args:
        market: Market identifier.
        candidates: List of candidate dicts with 'code' and 'market' keys.
        limit: Override the global prefetch limit. When 0, uses the default
            (scan_max_candidates, 0=full market). When >0, caps sync to min(
            len(candidates), limit), so passing the actual candidate count
            avoids wasting API calls on unused slots.
    """
    history_days = cfg_get("data_readiness.scan_history_days", 365)
    default_limit = cfg_get("scan_max_candidates", 0)
    prefetch_limit = limit if limit else cfg_get(
        "data_readiness.scan_prefetch_limit",
        default_limit,
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
        market != "FUND" if need_fundamentals is None else bool(need_fundamentals)
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
        market != "FUND" if need_fundamentals is None else bool(need_fundamentals)
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
        limit=limit
        or cfg_get(
            "data_readiness.scan_prefetch_limit",
            cfg_get("scan_max_candidates", 0),
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
    quality = build_scope_quality_summary(result, "FUND", scope="etf")
    result["confidence"] = quality["confidence"]
    result["provenance"] = quality["provenance"]
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
    result = {
        "index_code": index_code,
        "history_before": before,
        "history_after": after,
        "history_ready": after >= target_days,
    }
    score = 0.9 if result["history_ready"] else 0.45
    result["confidence"] = _build_confidence_block(
        score=score,
        notes=[
            "市场基准历史满足姿态分析要求"
            if result["history_ready"]
            else "市场基准历史不足，姿态分析会退化"
        ],
    )
    result["provenance"] = {
        "scope": "market_index",
        "market": "A",
        "freshness": "fresh" if result["history_ready"] else "partial",
        "covered_through": "",
        "inputs": ["market_index_history"],
        "source": index_code,
        "source_status": "cached",
        "metadata_completeness": 1.0,
    }
    return result


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
        if _history_row_count(str(stock["code"]), market) < min_history
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


def _history_row_count(code: str, market: str = "A") -> int:
    """Return the number of locally cached daily-price rows for a symbol."""
    return len(_cache.get_daily_price(code, market=market))


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


def build_symbol_quality_summary(
    code: str,
    market: str,
    readiness: Dict[str, Any],
) -> Dict[str, Any]:
    """Return confidence/provenance for a symbol-level readiness result."""
    pool_row = _pool_row(code, market)
    completeness = float(pool_row.get("metadata_completeness", 0) or 0)
    history_ready = bool(readiness.get("history_ready"))
    fundamentals_ready = bool(
        readiness.get("fundamentals_after")
        or readiness.get("fundamentals_ready")
        or not readiness.get("fundamentals_required", True)
    )
    freshness = _freshness_label(
        str(
            readiness.get("covered_through", "")
            or readiness.get("history_covered_through", "")
        ).strip()
    )
    components = [
        (history_ready, 0.40),
        (fundamentals_ready, 0.25),
        (completeness >= 0.75, 0.20),
        (freshness == "fresh", 0.15),
    ]
    score = sum(weight for ok, weight in components if ok)
    notes = []
    if history_ready:
        notes.append("历史价格覆盖满足主路径分析要求")
    else:
        notes.append("历史价格覆盖不足")
    if readiness.get("fundamentals_required", True):
        notes.append("基本面数据可用" if fundamentals_ready else "基本面数据不足")
    if completeness >= 0.75:
        notes.append("元数据完整度较高")
    elif completeness >= 0.5:
        notes.append("元数据可用但不完整")
    else:
        notes.append("元数据完整度偏低")
    if readiness.get("errors"):
        notes.append("同步过程中出现过错误，需要复核")
        score = max(0.0, score - 0.15)
    provenance = _build_provenance_block(
        scope="symbol",
        market=market,
        covered_through=str(
            readiness.get("covered_through", "")
            or readiness.get("history_covered_through", "")
        ).strip(),
        source=str(pool_row.get("metadata_source", "")).strip() or "unknown",
        source_status=str(pool_row.get("metadata_status", "")).strip() or "unknown",
        metadata_completeness=completeness,
        inputs=_readiness_inputs(readiness),
        code=code,
    )
    return {
        "confidence": _build_confidence_block(
            score=max(0.0, min(1.0, score)), notes=notes
        ),
        "provenance": provenance,
    }


def build_scope_quality_summary(
    readiness: Dict[str, Any],
    market: str,
    scope: str,
) -> Dict[str, Any]:
    """Return confidence/provenance for a bounded multi-symbol scope."""
    requested = int(readiness.get("requested", 0) or 0)
    ready = int(readiness.get("ready", 0) or 0)
    completeness_ratio = ready / max(requested, 1)
    freshness = _freshness_label(str(readiness.get("covered_through", "")).strip())
    score = completeness_ratio * 0.65
    if freshness == "fresh":
        score += 0.20
    if int(readiness.get("cache_hits", 0) or 0) > 0:
        score += 0.10
    if not readiness.get("missing_codes"):
        score += 0.05
    notes = [
        f"作用域覆盖率 {ready}/{requested}" if requested else "作用域请求为空",
        "覆盖日期较新" if freshness == "fresh" else "覆盖日期一般或未知",
    ]
    if readiness.get("missing_codes"):
        notes.append("仍有缺失代码，需要继续补齐")
    provenance = _build_provenance_block(
        scope=scope,
        market=market,
        covered_through=str(readiness.get("covered_through", "")).strip(),
        source="bounded_sync",
        source_status="cached_or_prefetched",
        metadata_completeness=completeness_ratio,
        inputs=["history", "fundamentals"] if market != "FUND" else ["history"],
    )
    return {
        "confidence": _build_confidence_block(
            score=max(0.0, min(1.0, score)), notes=notes
        ),
        "provenance": provenance,
    }


def _build_confidence_block(score: float, notes: Sequence[str]) -> Dict[str, Any]:
    """Return a standardized confidence block."""
    bounded = max(0.0, min(1.0, float(score or 0)))
    if bounded >= 0.8:
        level = "high"
    elif bounded >= 0.55:
        level = "medium"
    else:
        level = "low"
    return {
        "score": round(bounded, 3),
        "level": level,
        "notes": [str(item) for item in notes if str(item).strip()],
    }


def _build_provenance_block(
    scope: str,
    market: str,
    covered_through: str,
    source: str,
    source_status: str,
    metadata_completeness: float,
    inputs: Sequence[str],
    code: str = "",
) -> Dict[str, Any]:
    """Return a standardized provenance block."""
    return {
        "scope": scope,
        "market": market,
        "code": code,
        "freshness": _freshness_label(covered_through),
        "covered_through": covered_through,
        "source": source,
        "source_status": source_status,
        "metadata_completeness": round(max(0.0, min(1.0, metadata_completeness)), 3),
        "inputs": list(inputs),
    }


def _readiness_inputs(readiness: Dict[str, Any]) -> List[str]:
    """Infer the main inputs used for a readiness result."""
    inputs = ["history"]
    if bool(readiness.get("fundamentals_after") or readiness.get("fundamentals_ready")):
        inputs.append("fundamentals")
    return inputs


def _pool_row(code: str, market: str) -> Dict[str, Any]:
    """Return the matching cached pool row for a symbol."""
    pool = get_etf_pool() if market == "FUND" else get_stock_pool(market)
    canonical = normalize_code_for_market(code, market)
    for row in pool:
        row_code = normalize_code_for_market(str(row.get("code", "")).strip(), market)
        if row_code == canonical:
            return row
    return {}


def _freshness_label(covered_through: str) -> str:
    """Return a bounded freshness label from a covered-through date."""
    if not covered_through:
        return "unknown"
    try:
        covered = datetime.strptime(covered_through, "%Y-%m-%d")
    except ValueError:
        return "unknown"
    age = (datetime.now() - covered).days
    if age <= 7:
        return "fresh"
    if age <= 30:
        return "recent"
    return "stale"
