"""Core data engine: sync module."""

import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Sequence

from cache import get_cache
from config import get as cfg_get
from utils import (
    normalize_code_for_market,
    safe_float,
)

from data_engine.config import (
    _api_call,
    _cold_start_date,
    _is_etf_market,
    _market_supports_fundamentals,
    _try_akshare,
)
from data_engine.fundamentals import get_fundamentals
from data_engine.helpers import (
    _aggregate_covered_through,
    _date_str,
    _has_fresh_snapshot,
    _latest_cached_date,
    _upsert_scope_sync_state,
    _upsert_symbol_sync_state,
)
from data_engine.kline import get_kline
from data_engine.pool import _fetch_fund_pool_df, get_stock_pool

_cache = get_cache()
logger = logging.getLogger(__name__)


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
        max(history_days, history_before) if not full_history else history_days
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
        "fundamentals_fetched": (require_fundamentals and not fundamentals_before),
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


def _run_sync_batch(
    codes: Sequence[str],
    sync_fn: Any,
    scope_type: str,
    scope_key: str,
    history_label: str,
    max_workers: int,
    progress_label: str,
    total: int,
) -> tuple:
    """Shared sync orchestration: checkpoint, concurrent exec, progress, sort.

    Args:
        codes: Pending codes to synchronize.
        sync_fn: Function(code) -> result dict.
        scope_type: Checkpoint scope type.
        scope_key: Checkpoint scope key.
        history_label: Human-readable history target.
        max_workers: ThreadPoolExecutor max_workers.
        progress_label: Label for fetched count (e.g. 'K线拉取').
        total: Total codes (including skipped).

    Returns:
        (per_symbol, done_codes, start_time, total_rows,
         cache_hit, hist_fetch, all_earliest, all_latest, skipped)
    """
    start_time = time.time()
    done_codes = _load_checkpoint(scope_type, scope_key)
    pending = [c for c in codes if c not in done_codes]
    skipped = total - len(pending)
    print(
        f"  同步范围: {history_label}"
        f"{' (断点续传: 已跳过 ' + str(skipped) + ' 只' if skipped else ''}",
        flush=True,
    )
    if len(pending) > 10:
        print(f"  并发数: {max_workers}, 剩余 {len(pending)} 只待同步", flush=True)

    results_lock = threading.Lock()
    per_symbol: List[Dict[str, Any]] = []
    hist_fetch = 0
    cache_hit = 0
    total_rows = 0
    all_earliest: List[str] = []
    all_latest: List[str] = []
    processed_count = 0

    def _wrap_accumulate(result: Dict[str, Any]) -> None:
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
            processed_count += 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {
            executor.submit(sync_fn, code): code for code in pending
        }
        completed_this_run = set()
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            try:
                result = future.result()
                if result:
                    _wrap_accumulate(result)
                    completed_this_run.add(code)
            except Exception:
                completed_this_run.add(code)

            batch = max(10, total // 10)
            if processed_count % batch == 0 or processed_count == len(pending):
                pct = (skipped + processed_count) * 100 // total
                date_range = ""
                if all_earliest and all_latest:
                    date_range = f" | 日期范围: {min(all_earliest)} ~ {max(all_latest)}"
                elapsed = time.time() - start_time
                m, s = divmod(int(elapsed), 60)
                time_str = f"{m}分{s}秒" if m else f"{s}秒"
                print(
                    f"  [{skipped + processed_count}/{total}] {pct}% | "
                    f"已用时={time_str} | "
                    f"缓存命中={cache_hit}, {progress_label}={hist_fetch}, "
                    f"累计行数={total_rows:,}{date_range}",
                    flush=True,
                )
                done_codes.update(completed_this_run)
                _save_checkpoint(scope_type, scope_key, done_codes)
                completed_this_run = set()

    if completed_this_run:
        done_codes.update(completed_this_run)
        _save_checkpoint(scope_type, scope_key, done_codes)

    if len(done_codes) >= total:
        _clear_checkpoint(scope_type, scope_key)

    return (
        per_symbol, done_codes, start_time, total_rows,
        cache_hit, hist_fetch, all_earliest, all_latest, skipped,
    )

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

    max_workers = min(cfg_get("sync_max_workers", 1), total)
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
                    date_range = f" | 日期范围: {min(all_earliest)} ~ {max(all_latest)}"
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
        normalize_code_for_market(code, market) for code in codes if str(code).strip()
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

    max_workers = min(cfg_get("sync_max_workers", 1), total)
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
                    date_range = f" | 日期范围: {min(all_earliest)} ~ {max(all_latest)}"
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

    return get_fund_nav_incremental(
        code, days, cached_only, force_refresh, full_history
    )


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
