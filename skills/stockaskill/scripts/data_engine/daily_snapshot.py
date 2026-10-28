"""Precomputed daily factor snapshot builder.

Writes cross-sectional factor values, raw metrics, and percentile ranks for a
bounded scope into ``factor_daily_snapshot`` after each K-line sync. Reads are
strictly cached-only (no upstream API calls), so building a snapshot is cheap
and bounded.

The cross-section is the requested scope: a ``scan-universe`` sync produces a
full-market snapshot, while a symbol/watchlist sync produces a snapshot of that
bounded scope.
"""

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from cache import get_cache
from factors.composite import CompositeAnalyzer
from factors.momentum import MomentumFactor
from utils import _board, is_new, is_st, normalize_code_for_market

from data_engine import get_fundamentals, get_kline, get_stock_pool

_DEFAULT_LOOKBACK_DAYS = 365
_MIN_HISTORY_ROWS = 240
_MIN_TRADING_DAYS_6M = 126
_SKIP_RECENT_DAYS = 21
_VOL_LOOKBACK_BARS = 250
_FACTOR_NAMES = ("value", "quality", "growth", "momentum", "low_vol", "size")

logger = logging.getLogger(__name__)


def _closes(kline: Sequence[Dict[str, Any]]) -> List[float]:
    """Return positive closing prices, newest first."""
    return [
        float(r.get("close", 0) or 0)
        for r in kline
        if float(r.get("close", 0) or 0) > 0
    ]


def _ret_6m(closes: List[float]) -> float:
    """6-month return excluding the recent month (mirrors MomentumFactor)."""
    if len(closes) < _MIN_TRADING_DAYS_6M:
        return 0.0
    if len(closes) > _SKIP_RECENT_DAYS:
        skip_price = closes[_SKIP_RECENT_DAYS]
    else:
        skip_price = closes[0]
    base_price = (
        closes[_MIN_TRADING_DAYS_6M]
        if len(closes) > _MIN_TRADING_DAYS_6M
        else closes[-1]
    )
    if base_price <= 0:
        return 0.0
    return round((skip_price - base_price) / base_price, 6)


def _vol_metrics(closes: List[float]) -> Dict[str, float]:
    """12-month daily volatility and max single-day drawdown."""
    window = closes[:_VOL_LOOKBACK_BARS]
    if len(window) < 2:
        return {"vol_12m": 0.0, "max_drop_12m": 0.0}
    arr = np.array(window, dtype=float)
    returns = np.diff(arr) / arr[:-1]
    returns = returns[~np.isnan(returns)]
    returns = returns[~np.isinf(returns)]
    if len(returns) < 2:
        return {"vol_12m": 0.0, "max_drop_12m": 0.0}
    return {
        "vol_12m": round(float(np.std(returns)), 6),
        "max_drop_12m": round(float(abs(np.min(returns))), 6),
    }


def _pct_ranks(
    values: Dict[str, float],
    higher_is_better: bool = True,
) -> Dict[str, float]:
    """Return cross-sectional percentile ranks (0-1) for a metric vector."""
    from scipy.stats import rankdata

    codes = [code for code, value in values.items() if value is not None]
    if not codes:
        return {}
    arr = np.array([values[code] for code in codes], dtype=float)
    valid = ~np.isnan(arr)
    if valid.any():
        arr[~valid] = float(np.median(arr[valid]))
    else:
        arr[:] = 0.5
    ranks = rankdata(arr, method="average") - 1
    n = len(ranks)
    normalized = ranks / max(n - 1, 1)
    if not higher_is_better:
        normalized = 1.0 - normalized
    return dict(zip(codes, np.clip(normalized, 0, 1).tolist()))


def _first_metric(
    fundamentals: Dict[str, Any],
    names: Sequence[str],
) -> float:
    """Return the first non-zero float metric from a fundamentals dict."""
    for name in names:
        value = fundamentals.get(name)
        if value is None:
            continue
        try:
            val = float(value)
        except (TypeError, ValueError):
            continue
        if val == val and val != 0:
            return val
    return 0.0


def _log_mcap(market_cap: float) -> float:
    """Return natural log of market cap, or 0 when unset."""
    if market_cap and market_cap > 0:
        return round(math.log(market_cap), 6)
    return 0.0


def _resolve_scope(
    market: str,
    codes: Optional[Sequence[str]],
    limit: int,
) -> tuple[List[str], Dict[str, Dict[str, Any]]]:
    """Resolve the bounded code scope and the pool metadata lookup."""
    if codes is not None:
        selected = [
            normalize_code_for_market(str(code).strip(), market)
            for code in codes
            if str(code).strip()
        ]
        return selected, {}
    pool = get_stock_pool(market)
    scope = pool[:limit] if limit else pool
    return (
        [
            str(stock.get("code", "")).strip()
            for stock in scope
            if str(stock.get("code", "")).strip()
        ],
        {str(stock.get("code", "")).strip(): stock for stock in get_stock_pool(market)},
    )


def build_factor_daily_snapshot(
    market: str = "A",
    codes: Optional[Sequence[str]] = None,
    as_of_date: str = "",
    limit: int = 0,
) -> Dict[str, Any]:
    """Build and persist a daily factor snapshot for a bounded scope.

    Args:
        market: Market identifier (A/HK/US).
        codes: Explicit bounded code scope. When omitted, the active stock pool
            for *market* is used (bounded by *limit*).
        as_of_date: Snapshot trade date (YYYY-MM-DD). Defaults to today.
        limit: Max codes to evaluate when *codes* is omitted (0 = whole pool).

    Returns:
        Summary dict with trade_date, requested, written, and per-flag counts.
    """
    cache = get_cache()
    trade_date = as_of_date or datetime.now().strftime("%Y-%m-%d")
    selected, pool_by_code = _resolve_scope(market, codes, limit)

    scored: List[Dict[str, Any]] = []
    raw_metrics: Dict[str, Dict[str, Any]] = {}
    skipped_bj = 0
    skipped_empty = 0

    for code in selected:
        pool_row = pool_by_code.get(code, {})
        name = str(pool_row.get("name", "")).strip()
        if market == "A" and _board(code, "A") == "BJ":
            skipped_bj += 1
            continue

        fundamentals = get_fundamentals(code, market, cached_only=True) or {}
        kline = get_kline(code, market, days=_DEFAULT_LOOKBACK_DAYS, cached_only=True)
        has_fundamentals = bool(fundamentals)
        has_history = len(kline) >= _MIN_HISTORY_ROWS
        if not has_fundamentals and not has_history:
            skipped_empty += 1
            continue

        factor_result = CompositeAnalyzer(code, market).analyze_from_data(
            fundamentals,
            kline,
            as_of_date=trade_date,
        )
        scores = factor_result.get("factors", {})
        market_cap = float(pool_row.get("total_market_cap", 0) or 0)
        if market_cap <= 0:
            market_cap = float(fundamentals.get("market_cap", 0) or 0)
        closes = _closes(kline)
        volume = _vol_metrics(closes)
        raw = {
            "pe_ttm": _first_metric(fundamentals, ("pe_ttm", "pe_static")),
            "pb": _first_metric(fundamentals, ("pb",)),
            "roe": _first_metric(fundamentals, ("roe",)),
            "gross_margin": _first_metric(fundamentals, ("gross_margin",)),
            "profit_growth": _first_metric(fundamentals, ("profit_growth",)),
            "revenue_growth": _first_metric(fundamentals, ("revenue_growth",)),
            "ret_6m": _ret_6m(closes),
            "vol_12m": volume["vol_12m"],
            "max_drop_12m": volume["max_drop_12m"],
            "log_mcap": _log_mcap(market_cap),
            "market_cap": round(market_cap, 2),
            "ma_alignment": (
                round(float(MomentumFactor._ma_alignment(closes)), 4) if closes else 0.0
            ),
        }
        raw_metrics[code] = raw

        list_date = str(pool_row.get("list_date", "")).strip()
        scored.append(
            {
                "trade_date": trade_date,
                "code": code,
                "market": market,
                "name": name,
                "sector": str(pool_row.get("sector", "")).strip(),
                "industry": str(pool_row.get("industry", "")).strip(),
                "is_active": int(bool(pool_row.get("is_active", 1))),
                "list_date": list_date,
                "is_st": int(is_st(code, name)),
                "is_new_listing": int(
                    bool(list_date) and is_new(list_date, threshold_days=60)
                ),
                "has_fundamentals": int(has_fundamentals),
                "has_history": int(has_history),
                "composite_score": round(
                    float(factor_result.get("total_score", 0) or 0), 2
                ),
                "f_score": int(factor_result.get("f_score", 0) or 0),
                **{
                    f"{name}_score": round(float(scores.get(name, 0) or 0), 4)
                    for name in _FACTOR_NAMES
                },
                **raw,
            }
        )

    if not scored:
        return {
            "market": market,
            "trade_date": trade_date,
            "requested": len(selected),
            "written": 0,
            "skipped_bj": skipped_bj,
            "skipped_empty": skipped_empty,
            "coverage_ratio": 0.0,
        }

    percentile_map = {
        "pe_pct": _pct_ranks(
            {code: raw["pe_ttm"] for code, raw in raw_metrics.items()}
        ),
        "pb_pct": _pct_ranks({code: raw["pb"] for code, raw in raw_metrics.items()}),
        "roe_pct": _pct_ranks({code: raw["roe"] for code, raw in raw_metrics.items()}),
        "gross_margin_pct": _pct_ranks(
            {code: raw["gross_margin"] for code, raw in raw_metrics.items()}
        ),
        "growth_pct": _pct_ranks(
            {
                code: (raw["profit_growth"] or raw["revenue_growth"])
                for code, raw in raw_metrics.items()
            }
        ),
        "momentum_pct": _pct_ranks(
            {code: raw["ret_6m"] for code, raw in raw_metrics.items()}
        ),
        "low_vol_pct": _pct_ranks(
            {code: raw["vol_12m"] for code, raw in raw_metrics.items()},
            higher_is_better=False,
        ),
        "size_pct": _pct_ranks(
            {code: raw["log_mcap"] for code, raw in raw_metrics.items()}
        ),
    }
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in scored:
        code = row["code"]
        for pct_key, values in percentile_map.items():
            row[pct_key] = round(float(values.get(code, 0) or 0), 4)
        row["created_at"] = now_str

    if hasattr(cache, "upsert_factor_daily_snapshot"):
        cache.upsert_factor_daily_snapshot(scored)

    return {
        "market": market,
        "trade_date": trade_date,
        "requested": len(selected),
        "written": len(scored),
        "skipped_bj": skipped_bj,
        "skipped_empty": skipped_empty,
        "st_count": sum(1 for row in scored if row.get("is_st")),
        "new_listing_count": sum(1 for row in scored if row.get("is_new_listing")),
        "coverage_ratio": round(len(scored) / max(len(selected), 1), 4),
    }
