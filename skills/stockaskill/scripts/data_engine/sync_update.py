"""Dynamic incremental synchronization engine for market data.

Enforces four core data principles:
1. Local-first: Check cache before API; skip fetch when local data is fresh.
2. Incremental by default: Detect missing date gaps with padding overlap.
3. Full history preserved: Upsert via ON CONFLICT DO UPDATE; never truncate.
4. Validate before cache: Strict rejection of malformed or future OHLC rows.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Sequence

from cache import CacheManager, get_cache
from utils import normalize_code_for_market

from data_engine.config import _cold_start_date
from data_engine.helpers import _date_str, _latest_trading_day

logger = logging.getLogger(__name__)


def validate_ohlc_record(row: Dict[str, Any]) -> bool:
    """Validate a single OHLC price record before cache ingestion.

    Args:
        row: K-line row containing open, high, low, close, and date.

    Returns:
        True if the row satisfies all basic OHLC integrity constraints.
    """
    return CacheManager._validate_kline_row(row)


def get_symbol_watermark(code: str, market: str = "A") -> Optional[str]:
    """Retrieve the latest cached trading date for a symbol.

    Args:
        code: Ticker symbol.
        market: Target market identifier (A, HK, US, FUND).

    Returns:
        Latest cached date string in YYYY-MM-DD format, or None.
    """
    canonical_code = normalize_code_for_market(code, market)
    cache = get_cache()
    return cache.get_latest_date(canonical_code, market=market)


def get_market_watermark(market: str = "A") -> Optional[str]:
    """Retrieve the latest cached trading date across an entire market.

    Args:
        market: Target market identifier (A, HK, US, FUND).

    Returns:
        Latest cached date string in YYYY-MM-DD format, or None.
    """
    cache = get_cache()
    return cache.get_latest_daily_price_date(market=market)


def get_scope_watermark(codes: Sequence[str], market: str = "A") -> Optional[str]:
    """Retrieve the latest cached trading date across a collection of symbols."""
    dates = []
    for code in codes:
        d = get_symbol_watermark(code, market)
        if d:
            dates.append(d)
    return max(dates) if dates else None


def compute_incremental_fetch_window(
    latest_cached_date: Optional[str],
    market: str = "A",
    padding_days: int = 3,
) -> tuple[Optional[str], str]:
    """Calculate the incremental date fetch window [start_date, end_date].

    Args:
        latest_cached_date: Latest date already stored locally, or None.
        market: Market identifier.
        padding_days: Overlap days to account for corrections or holidays.

    Returns:
        Tuple of (start_date_str, end_date_str). If start_date is None,
        local data is already fully up to date.
    """
    target_today = _latest_trading_day(market) or _date_str(datetime.now())

    if not latest_cached_date:
        cold_start = _cold_start_date(market)
        if len(cold_start) == 8 and cold_start.isdigit():
            cold_start = f"{cold_start[:4]}-{cold_start[4:6]}-{cold_start[6:8]}"
        return cold_start, target_today

    if latest_cached_date >= target_today:
        return None, target_today

    try:
        latest_dt = datetime.strptime(latest_cached_date, "%Y-%m-%d")
        start_dt = max(
            datetime.strptime("1990-01-01", "%Y-%m-%d"),
            latest_dt - timedelta(days=padding_days),
        )
        start_date = _date_str(start_dt)
    except ValueError:
        start_date = latest_cached_date

    return start_date, target_today


def update_symbol_incremental(
    code: str,
    market: str = "A",
    padding_days: int = 3,
    trigger_snapshot: bool = False,
) -> Dict[str, Any]:
    """Incrementally update K-line data for a single symbol.

    Args:
        code: Ticker symbol.
        market: Market code (A, HK, US, FUND).
        padding_days: Overlap days for incremental fetch.
        trigger_snapshot: Whether to recalculate daily factor snapshot.

    Returns:
        Dict containing execution summary and row statistics.
    """
    canonical_code = normalize_code_for_market(code, market)
    cache = get_cache()
    latest_date = get_symbol_watermark(canonical_code, market)
    start_date, target_today = compute_incremental_fetch_window(
        latest_date, market, padding_days
    )

    if start_date is None:
        try:
            from data_engine.helpers import _upsert_symbol_sync_state

            _upsert_symbol_sync_state(
                canonical_code,
                market,
                "history",
                status="ok" if latest_date else "partial",
                covered_date=latest_date or "",
            )
        except Exception as exc:
            logger.debug("Failed to record sync state: %s", exc)
        return {
            "code": canonical_code,
            "market": market,
            "status": "up_to_date",
            "latest_date": latest_date,
            "fetched_rows": 0,
            "validated_rows": 0,
            "rejected_rows": 0,
            "message": "Local cache is already up to date.",
        }

    from data_engine.kline import _fetch_kline

    raw_rows = _fetch_kline(canonical_code, market, start_date, target_today)
    if not raw_rows:
        return {
            "code": canonical_code,
            "market": market,
            "status": "no_new_data",
            "latest_date": latest_date,
            "fetched_rows": 0,
            "validated_rows": 0,
            "rejected_rows": 0,
            "message": (
                f"No remote records returned for range {start_date} to {target_today}."
            ),
        }

    valid_rows = [r for r in raw_rows if validate_ohlc_record(r)]
    rejected_count = len(raw_rows) - len(valid_rows)

    if valid_rows:
        for r in valid_rows:
            r.setdefault("market", market)
            r.setdefault("code", canonical_code)
        cache.upsert_daily_price(valid_rows)

    new_latest = get_symbol_watermark(canonical_code, market)
    try:
        from data_engine.helpers import _upsert_symbol_sync_state

        _upsert_symbol_sync_state(
            canonical_code,
            market,
            "history",
            status="ok" if new_latest else "partial",
            covered_date=new_latest or "",
        )
    except Exception as exc:
        logger.debug("Failed to record sync state: %s", exc)

    if trigger_snapshot and valid_rows and market != "FUND":
        try:
            from data_engine.daily_snapshot import build_factor_daily_snapshot

            build_factor_daily_snapshot(market=market, codes=[canonical_code], limit=1)
        except Exception as exc:
            logger.warning("Snapshot refresh failed after update: %s", exc)

    return {
        "code": canonical_code,
        "market": market,
        "status": "updated",
        "previous_latest_date": latest_date,
        "latest_date": new_latest,
        "fetch_range": [start_date, target_today],
        "fetched_rows": len(raw_rows),
        "validated_rows": len(valid_rows),
        "rejected_rows": rejected_count,
        "message": (
            f"Successfully updated {len(valid_rows)} records "
            f"(rejected: {rejected_count})."
        ),
    }


def update_symbols_batch(
    codes: Sequence[str],
    market: str = "A",
    padding_days: int = 3,
    limit: int = 0,
    trigger_snapshot: bool = True,
    scope_type: str = "",
    scope_key: str = "",
) -> Dict[str, Any]:
    """Incrementally update a batch of symbols with checkpointing.

    Args:
        codes: List of ticker symbols.
        market: Market code.
        padding_days: Overlap days.
        limit: Max symbols to update (0 = all).
        trigger_snapshot: Rebuild factor snapshot upon completion.

    Returns:
        Summary dict of batch update results.
    """
    target_codes = list(codes[:limit] if limit > 0 else codes)
    total = len(target_codes)
    updated_count = 0
    up_to_date_count = 0
    failed_count = 0
    total_valid_rows = 0
    total_rejected_rows = 0

    for idx, code in enumerate(target_codes, start=1):
        try:
            res = update_symbol_incremental(
                code,
                market=market,
                padding_days=padding_days,
                trigger_snapshot=False,
            )
            if res.get("status") == "updated":
                updated_count += 1
                total_valid_rows += res.get("validated_rows", 0)
                total_rejected_rows += res.get("rejected_rows", 0)
            elif res.get("status") == "up_to_date":
                up_to_date_count += 1
        except Exception as exc:
            logger.error("Failed incremental update for %s: %s", code, exc)
            failed_count += 1

    if trigger_snapshot and updated_count > 0 and market != "FUND":
        try:
            from data_engine.daily_snapshot import build_factor_daily_snapshot

            build_factor_daily_snapshot(market=market, codes=target_codes)
        except Exception as exc:
            logger.warning("Batch snapshot rebuild failed: %s", exc)

    if scope_type:
        try:
            from data_engine.helpers import _upsert_scope_sync_state

            covered_date = get_scope_watermark(target_codes, market) or ""
            _upsert_scope_sync_state(
                scope_type,
                scope_key or market,
                market,
                "summary",
                status="ok" if failed_count == 0 else "partial",
                covered_date=covered_date,
            )
        except Exception as exc:
            logger.debug("Failed to record scope sync state: %s", exc)

    return {
        "market": market,
        "total_symbols": total,
        "updated_symbols": updated_count,
        "already_up_to_date": up_to_date_count,
        "failed_symbols": failed_count,
        "total_ingested_rows": total_valid_rows,
        "total_rejected_rows": total_rejected_rows,
    }
