"""CLI command handlers for sync functionality."""

import argparse
import time
from datetime import datetime
from typing import Any, Dict, List

from cache import get_cache
from config import get as cfg_get
from data_engine import (
    check_data_completeness,
    get_etf_pool,
    get_fund_pool,
    get_stock_pool,
    sync_etf_data,
    sync_portfolio_data,
    sync_scan_universe_data,
    sync_symbol_data,
    sync_watchlist_data,
)
from utils import normalize_code_for_market

from commands._common import _cmd_output, _print_pool_summary, _save_report


def cmd_fetch(args: argparse.Namespace) -> None:
    """Manually refresh data."""
    fetch_type = args.type
    code = getattr(args, "code", "")
    market = getattr(args, "market", "A") or "A"

    if fetch_type == "pool":
        print("Refreshing stock pool (local-first)...")
        for mkt in ["A", "HK", "US", "FUND"]:
            if mkt == "FUND":
                get_fund_pool(force_refresh=False)
            else:
                get_stock_pool(mkt, force_refresh=False)
            _print_pool_summary(mkt)
    elif fetch_type == "kline":
        print(f"Fetching K-line for {code}...")
        from data_engine import get_kline

        kline = get_kline(code, market, days=730, force_refresh=True)
        print(f"  Cached {len(kline)} days")
    elif fetch_type == "fundamentals":
        print(f"Fetching fundamentals for {code}...")
        from data_engine import get_fundamentals

        fund = get_fundamentals(code, market, force_refresh=True)
        if fund:
            print(f"  PE(TTM): {fund.get('pe_ttm', 'N/A')}")
        else:
            print("  No data")
    else:
        print(f"Unknown fetch type: {fetch_type}")



def cmd_sync(args: argparse.Namespace) -> None:
    """Synchronize bounded local data for a specific scope."""
    sync_type = args.type
    output_dir, fmt = _cmd_output(args)
    market = getattr(args, "market", "A") or "A"
    history_days = getattr(args, "days", 365) or 365
    need_fundamentals = not bool(getattr(args, "skip_fundamentals", False))
    full_history = bool(getattr(args, "full_history", False))
    if sync_type == "symbol":
        code = args.code
        print(
            f"Synchronizing symbol {code} (market={market}, days={history_days}, "
            f"full_history={'yes' if full_history else 'no'})..."
        )
        result = sync_symbol_data(
            code,
            market,
            history_days=history_days,
            need_fundamentals=need_fundamentals,
            full_history=full_history,
        )
        _print_symbol_sync_summary(result)
        report_name = f"sync_symbol_{result['code']}_{market}"
        metadata = {
            "command": "sync",
            "type": sync_type,
            "market": market,
            "code": result["code"],
        }
    elif sync_type == "watchlist":
        if full_history:
            print(
                f"Synchronizing watchlist (market={market}, target=全量历史)..."
            )
        else:
            print(
                f"Synchronizing watchlist (market={market}, days={history_days})..."
            )
        result = sync_watchlist_data(
            market=market,
            history_days=history_days,
            need_fundamentals=need_fundamentals,
            full_history=full_history,
        )
        _print_scope_sync_summary(result, label="watchlist")
        report_name = f"sync_watchlist_{market}"
        metadata = {"command": "sync", "type": sync_type, "market": market}
    elif sync_type == "portfolio":
        codes = [c.strip() for c in getattr(args, "codes", "").split(",") if c.strip()]
        if full_history:
            print(
                f"Synchronizing portfolio ({len(codes)} symbols, market={market}, "
                f"target=全量历史)..."
            )
        else:
            print(
                f"Synchronizing portfolio ({len(codes)} symbols, market={market}, "
                f"days={history_days})..."
            )
        result = sync_portfolio_data(
            codes,
            market=market,
            history_days=history_days,
            need_fundamentals=need_fundamentals,
            full_history=full_history,
        )
        _print_scope_sync_summary(result, label="portfolio")
        report_name = f"sync_portfolio_{market}"
        metadata = {
            "command": "sync",
            "type": sync_type,
            "market": market,
            "codes": codes,
        }
    elif sync_type == "etf":
        codes = [c.strip() for c in getattr(args, "codes", "").split(",") if c.strip()]
        print(
            f"Synchronizing ETFs ({len(codes)} symbols, days={history_days}, "
            f"full_history={'yes' if full_history else 'no'})..."
        )
        result = sync_etf_data(
            codes,
            history_days=history_days,
            full_history=full_history,
        )
        _print_scope_sync_summary(result, label="etf")
        report_name = "sync_etf"
        metadata = {
            "command": "sync",
            "type": sync_type,
            "market": "FUND",
            "codes": codes,
        }
    elif sync_type == "scan-universe":
        limit = getattr(args, "limit", 200) or 200
        if full_history:
            print(
                f"Synchronizing scan universe (market={market}, limit={limit}, "
                f"target=全量历史)..."
            )
        else:
            print(
                f"Synchronizing scan universe (market={market}, limit={limit}, "
                f"days={history_days})..."
            )
        result = sync_scan_universe_data(
            market=market,
            limit=limit,
            history_days=history_days,
            need_fundamentals=need_fundamentals,
            full_history=full_history,
        )
        _print_scope_sync_summary(result, label="scan-universe")
        report_name = f"sync_scan_universe_{market}"
        metadata = {
            "command": "sync",
            "type": sync_type,
            "market": market,
            "limit": limit,
        }
    else:
        print(f"Unknown sync type: {sync_type}")
        return

    _save_report(report_name, fmt, output_dir, data=result, metadata=metadata)



def _print_symbol_sync_summary(result: dict) -> None:
    """Print a concise symbol-sync summary."""
    print(
        "  History:"
        f" before={result.get('history_before', 0)},"
        f" after={result.get('history_after', 0)},"
        f" ready={'yes' if result.get('history_ready') else 'no'},"
        f" covered_through={result.get('history_covered_through', '?') or '?'}"
    )
    if result.get("fundamentals_required"):
        print(
            "  Fundamentals:"
            f" before={'yes' if result.get('fundamentals_before') else 'no'},"
            f" after={'yes' if result.get('fundamentals_after') else 'no'},"
            " covered_through="
            f"{result.get('fundamentals_covered_through', '?') or '?'}"
        )
    if result.get("errors"):
        print("  Errors:")
        for err in result["errors"]:
            print(f"    - {err}")
    print(f"  Ready: {'yes' if result.get('ready') else 'no'}")



def _print_scope_sync_summary(result: dict, label: str) -> None:
    """Print a concise summary for a bounded multi-symbol sync scope."""
    earliest = result.get("earliest_date", "") or ""
    latest = result.get("latest_date", "") or ""
    total_rows = result.get("total_history_rows", 0)
    covered_through = result.get("covered_through", "") or ""
    requested = result.get("requested", 0)
    ready = result.get("ready", 0)
    elapsed = result.get("elapsed_seconds", 0)
    failed = max(0, requested - ready)

    print(
        f"  同步汇总 [{label}]: "
        f"总数={requested}, "
        f"就绪={ready}, "
        f"失败={failed}, "
        f"耗时={_format_elapsed(elapsed)}"
    )
    print(
        f"    缓存命中={result.get('cache_hits', 0)}, "
        f"K线拉取={result.get('history_fetched_count', 0)}, "
        f"基本面拉取={result.get('fundamentals_fetched_count', 0)}"
    )
    if total_rows:
        print(f"    累计K线行数: {total_rows:,}")
    if earliest or latest:
        print(f"    数据日期范围: {earliest or '?'} ~ {latest or '?'}")
    if covered_through:
        print(f"    更新至: {covered_through}")
    if result.get("missing_codes"):
        print(f"    未就绪: {len(result['missing_codes'])} 只")
        print("    未就绪代码: " + ", ".join(result["missing_codes"][:10]))

    # Data completeness report
    market = result.get("market", "")
    if market:
        completeness = check_data_completeness(market)
        if completeness:
            top_incomplete = sorted(
                completeness, key=lambda x: x["missing_days"], reverse=True
            )[:5]
            print(
                f"    数据完整性: {len(completeness)} 只股票缺失交易日"
            )
            for item in top_incomplete:
                print(
                    f"      {item['code']}: "
                    f"{item['actual_days']}/{item['expected_days']} 天 "
                    f"(缺失 {item['missing_days']})"
                )
        else:
            print("    数据完整性: 全部完成")



def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as Xm Ys."""
    m, s = divmod(int(seconds), 60)
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"



def cmd_status(args: argparse.Namespace) -> None:
    """Show bounded sync-state diagnostics."""
    status_type = args.type
    cache = get_cache()
    market = getattr(args, "market", "A") or "A"

    if status_type == "symbol":
        code = normalize_code_for_market(args.code, market)
        rows = cache.get_sync_state(
            "symbol",
            f"{market}:{code}",
            market=market,
            code=code,
        )
        _print_status_summary(rows, label=f"symbol {code}", requested=1)
        _print_market_metadata_summary(_scope_pool_rows([code], market), label="symbol")
    elif status_type == "watchlist":
        rows = cache.get_sync_state("watchlist", market, market=market)
        codes = _normalized_watchlist(market)
        symbol_rows = _collect_symbol_scope_rows(cache, codes, market)
        _print_status_summary(symbol_rows, label="watchlist", requested=len(codes))
        _print_market_metadata_summary(
            _scope_pool_rows(codes, market),
            label="watchlist",
        )
        rows.extend(symbol_rows)
    elif status_type == "portfolio":
        codes = [
            normalize_code_for_market(c.strip(), market)
            for c in getattr(args, "codes", "").split(",")
            if c.strip()
        ]
        rows = cache.get_sync_state(
            "portfolio",
            ",".join(codes),
            market=market,
        )
        symbol_rows = _collect_symbol_scope_rows(cache, codes, market)
        _print_status_summary(symbol_rows, label="portfolio", requested=len(codes))
        _print_market_metadata_summary(
            _scope_pool_rows(codes, market),
            label="portfolio",
        )
        rows.extend(symbol_rows)
    elif status_type == "scan-universe":
        limit = getattr(args, "limit", 200) or 200
        rows = cache.get_sync_state(
            "scan-universe",
            f"{market}:{limit}",
            market=market,
        )
        codes = _scan_universe_codes(market, limit)
        symbol_rows = _collect_symbol_scope_rows(cache, codes, market)
        _print_status_summary(
            symbol_rows,
            label=f"scan-universe {market}:{limit}",
            requested=len(codes),
        )
        _print_market_metadata_summary(
            _scope_pool_rows(codes, market),
            label="scan-universe",
        )
        rows.extend(symbol_rows)
    elif status_type == "etf":
        market = "FUND"
        codes = [
            normalize_code_for_market(c.strip(), market)
            for c in getattr(args, "codes", "").split(",")
            if c.strip()
        ]
        rows = cache.get_sync_state(
            "etf",
            ",".join(codes),
            market=market,
        )
        symbol_rows = _collect_symbol_scope_rows(cache, codes, market)
        _print_status_summary(symbol_rows, label="etf", requested=len(codes))
        _print_market_metadata_summary(_scope_pool_rows(codes, market), label="etf")
        rows.extend(symbol_rows)
    elif status_type == "pool":
        pool = get_stock_pool(market)
        pool_count = len(pool) if pool else 0
        needs_refresh = cache.pool_needs_refresh(market)
        print(f"  Pool: {market}")
        print(f"  Count: {pool_count}")
        print(f"  Needs refresh: {needs_refresh}")
        if pool:
            dates = sorted(
                r.get("updated_at", "")
                for r in pool
                if r.get("updated_at")
            )
            if dates:
                print(f"  Last updated: {dates[-1]}")
                print(f"  Oldest entry: {dates[0]}")
        rows: List[dict] = []
    else:
        print(f"Unknown status type: {status_type}")
        return

    if not rows:
        if status_type != "pool":
            print("No sync state found.")
        return
    print(f"Sync state for {status_type} (market={market}):")
    for row in rows:
        code_label = row.get("code", "") or "-"
        print(
            f"  {row.get('data_kind', '?')}:"
            f" code={code_label},"
            f" status={row.get('status', '?')},"
            f" covered={row.get('last_covered_date', '?') or '?'},"
            f" last_success={row.get('last_success_at', '?') or '?'}"
        )
        if row.get("last_error"):
            print(f"    error={row['last_error']}")



def _normalized_watchlist(market: str) -> list[str]:
    """Return normalized watchlist codes for a market."""
    return [
        normalize_code_for_market(code, market)
        for code in cfg_get("watchlist", [])
        if str(code).strip()
    ]



def _scan_universe_codes(market: str, limit: int) -> List[str]:
    """Return normalized codes for a bounded scan universe."""
    if market == "FUND":
        pool = get_etf_pool()
    else:
        pool = get_stock_pool(market)
    return [
        normalize_code_for_market(str(item.get("code", "")), market)
        for item in pool[:limit]
        if str(item.get("code", "")).strip()
    ]



def _collect_symbol_scope_rows(
    cache: Any,
    codes: List[str],
    market: str,
) -> List[dict]:
    """Collect symbol sync-state rows for a bounded scope."""
    rows: List[dict] = []
    for code in codes:
        rows.extend(
            cache.get_sync_state(
                "symbol",
                f"{market}:{code}",
                market=market,
                code=code,
            )
        )
    return rows



def _scope_pool_rows(
    codes: List[str],
    market: str,
) -> List[dict]:
    """Return cached pool rows for the provided scope codes."""
    if market == "FUND":
        pool = get_etf_pool()
    else:
        pool = get_stock_pool(market)
    pool_by_code = {
        normalize_code_for_market(str(item.get("code", "")), market): item
        for item in pool
        if str(item.get("code", "")).strip()
    }
    return [pool_by_code[code] for code in codes if code in pool_by_code]



def _print_market_metadata_summary(pool_rows: List[dict], label: str) -> None:
    """Print a compact metadata-quality summary for a market scope."""
    if not pool_rows:
        return
    complete = 0
    partial = 0
    low = 0
    inactive = 0
    total_completeness = 0.0
    source_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    for row in pool_rows:
        completeness = float(row.get("metadata_completeness", 0) or 0)
        total_completeness += completeness
        if completeness >= 0.75:
            complete += 1
        elif completeness >= 0.5:
            partial += 1
        else:
            low += 1
        if not bool(row.get("is_active", 1)):
            inactive += 1
        source = str(row.get("metadata_source", "")).strip() or "unknown"
        status = str(row.get("metadata_status", "")).strip() or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1
    top_source = max(source_counts.items(), key=lambda item: item[1])[0]
    top_status = max(status_counts.items(), key=lambda item: item[1])[0]
    avg_completeness = total_completeness / max(len(pool_rows), 1)
    print(
        f"  Metadata {label}:"
        f" complete={complete}, partial={partial}, low={low},"
        f" inactive={inactive}, avg={avg_completeness:.2f},"
        f" top_source={top_source}, top_status={top_status}"
    )



def _status_freshness(row: dict) -> str:
    """Classify a sync-state row as fresh, stale, or missing."""
    ttl_map = {
        "history": int(cfg_get("cache_ttl.daily_kline", 3600) or 3600),
        "fundamentals": int(cfg_get("cache_ttl.financial", 604800) or 604800),
        "nav": int(cfg_get("cache_ttl.fund_nav", 3600) or 3600),
        "summary": int(cfg_get("cache_ttl.daily_kline", 3600) or 3600),
    }
    last_success = str(row.get("last_success_at", "")).strip()
    if not last_success:
        return "missing"
    try:
        timestamp = datetime.strptime(last_success, "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return "unknown"
    ttl = ttl_map.get(str(row.get("data_kind", "")), 3600)
    return "fresh" if (time.time() - timestamp) <= ttl else "stale"



def _print_status_summary(rows: List[dict], label: str, requested: int) -> None:
    """Print aggregate freshness/error summary for a scope."""
    if not rows:
        print(f"  Scope {label}: no symbol sync rows found")
        return
    by_code: Dict[str, List[dict]] = {}
    stale = 0
    fresh = 0
    errors = 0
    for row in rows:
        code = str(row.get("code", "")).strip() or "-"
        by_code.setdefault(code, []).append(row)
        freshness = _status_freshness(row)
        if freshness == "fresh":
            fresh += 1
        elif freshness == "stale":
            stale += 1
        if row.get("last_error"):
            errors += 1
    problem_codes = []
    for code, code_rows in by_code.items():
        if any(
            row.get("status") != "ok"
            or _status_freshness(row) != "fresh"
            or row.get("last_error")
            for row in code_rows
        ):
            problem_codes.append(code)
    print(
        f"  Scope {label}: requested={requested},"
        f" symbol_rows={len(rows)}, fresh={fresh}, stale={stale},"
        f" errors={errors}, symbols_with_issues={len(problem_codes)}"
    )
    if problem_codes:
        print("  Top missing/problem symbols: " + ", ".join(problem_codes[:10]))



