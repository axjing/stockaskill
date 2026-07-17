"""Core data engine: helpers module.

Single source for shared utilities used across kline, fundamentals, pool, and sync.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from cache import get_cache
from utils import safe_float

_cache = get_cache()
logger = logging.getLogger(__name__)


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
    if any(marker in status_text for marker in ("delist", "delisted", "退市", "摘牌")):
        return "delisted"
    if any(
        marker in status_text for marker in ("suspend", "suspended", "halt", "停牌")
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


def get_vwap(code: str, market: str = "A", date: str = "") -> float:
    """Get VWAP for a stock on a given date.

    VWAP = amount / volume. Uses cached data.
    """
    cached = _cache.get_daily_price(code, market=market)
    if date:
        cached = [r for r in cached if r.get("date", "") == date]
    if not cached:
        return 0.0
    row = cached[0]
    return _cache.compute_vwap(
        float(row.get("amount", 0) or 0),
        float(row.get("volume", 0) or 0),
    )


def check_data_completeness(market: str = "A") -> List[Dict[str, int]]:
    """Check data completeness against the trade calendar.

    Returns a list of dicts with code, actual_days, expected_days, missing_days
    for stocks that have fewer rows than the trade calendar.
    """
    return _cache.check_data_completeness(market)


def _estimate_amount(amount: float, volume: float, close: float, market: str) -> float:
    """Estimate amount (成交额) when missing, using volume × close.

    For A-shares the data source already provides amount correctly.
    For US/HK stocks, AKShare and yfinance don't provide amount.
    Estimate: amount = volume × close (ignoring lot_size which varies by market).
    """
    if amount > 0 and volume > 0 and close > 0:
        return amount
    if volume > 0 and close > 0:
        return round(volume * close, 2)
    return amount


def _detect_quality_flags(
    rows: List[Dict[str, Any]], market: str
) -> List[Dict[str, Any]]:
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
                gaps.append(f"{next_str}..{cur_str} ({day_diff}d gap)")
        except Exception:
            continue
    return gaps


def _backfill_missing_factors(result: Dict[str, Any], code: str, market: str) -> None:
    """Backfill missing factor values from related data sources."""
    # Backfill pe_static from pe_ttm (close approximation for A-shares)
    if not result.get("pe_static") and result.get("pe_ttm"):
        result["pe_static"] = result["pe_ttm"]

    # Backfill market_cap from stock_pool
    if not result.get("market_cap"):
        val = _cache.get_market_cap_from_pool(code, market)
        if val:
            result["market_cap"] = val

    # Backfill roa from roe and debt_ratio if available
    # ROA = ROE * (1 - debt_ratio) is a rough approximation
    if not result.get("roa") and result.get("roe") and result.get("debt_ratio"):
        roe = float(result.get("roe", 0) or 0)
        debt = float(result.get("debt_ratio", 0) or 0)
        if roe and debt:
            result["roa"] = round(roe * (1 - debt), 4)


def _backfill_valuation_from_price(
    result: Dict[str, Any], code: str, market: str
) -> None:
    """Compute PE / PB from cached close price and fundamental EPS / BVPS.
    Also backfill market_cap from stock_pool when upstream doesn't provide it.
    """
    eps = result.get("eps", 0.0) or 0.0
    bvps = result.get("bvps", 0.0) or 0.0
    price = _cache.get_latest_close(code, market)
    if price and eps > 0 and not result.get("pe_ttm"):
        result["pe_ttm"] = round(price / eps, 2)
    if price and bvps > 0 and not result.get("pb"):
        result["pb"] = round(price / bvps, 2)

    # Backfill market_cap from stock_pool when upstream doesn't provide it
    if not result.get("market_cap"):
        val = _cache.get_market_cap_from_pool(code, market)
        if val:
            result["market_cap"] = val


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
