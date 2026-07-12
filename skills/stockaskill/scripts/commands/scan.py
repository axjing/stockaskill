"""CLI command handlers for scan functionality."""

import argparse
import sys

from cache import get_cache
from config import get as cfg_get
from data_engine import get_etf_pool, get_stock_pool, sync_symbol_data
from data_readiness import ensure_etf_ready
from market_regime import summarize_market_regime

from commands._common import (
    _badge,
    _cmd_output,
    _print_api_usage,
    _safe_market_regime,
    _save_report,
)


def _print_snapshot_summary(summary: dict, refreshed: bool) -> None:
    """Print a concise snapshot status summary for market scans."""
    trade_date = summary.get("trade_date", "?")
    total_count = int(summary.get("total_count", 0) or 0)
    eligible_count = int(summary.get("eligible_count", 0) or 0)
    filtered_count = int(summary.get("filtered_count", 0) or 0)
    complete_ratio = float(summary.get("data_complete_ratio", 0) or 0) * 100
    refresh_label = "yes" if refreshed else "no"
    print(f"  Snapshot date: {trade_date} (refreshed={refresh_label})")
    print(
        "  Snapshot coverage:"
        f" scored={eligible_count}, filtered={filtered_count}, total={total_count}"
    )
    print(f"  Data completeness: {complete_ratio:.1f}%")
    print(
        "  Exclusions:"
        f" missing_list_date={summary.get('missing_list_date_count', 0)},"
        f" missing_fundamentals={summary.get('missing_fundamentals_count', 0)},"
        f" missing_history={summary.get('missing_history_count', 0)},"
        f" st={summary.get('st_count', 0)},"
        f" bj={summary.get('bj_count', 0)},"
        f" new_listing={summary.get('new_listing_count', 0)}"
    )
    metadata_quality = summary.get("metadata_quality", {}) or {}
    if metadata_quality:
        print(
            "  Metadata quality:"
            f" complete={metadata_quality.get('complete', 0)},"
            f" partial={metadata_quality.get('partial', 0)},"
            f" low={metadata_quality.get('low', 0)}"
        )



def _print_refresh_summary(summary: dict) -> None:
    """Print refresh job counters after a full-market snapshot build."""
    print(
        "  Local reuse/backfill:"
        f" reused={summary.get('cache_reused_count', 0)},"
        f" backfilled={summary.get('backfilled_count', 0)},"
        f" excluded={summary.get('excluded_count', 0)}"
    )
    print(
        "  Data fetch counters:"
        f" history_hit={summary.get('history_cache_hits', 0)},"
        f" history_fetched={summary.get('history_fetched_count', 0)},"
        f" history_missing={summary.get('history_missing_count', 0)},"
        f" fundamentals_hit={summary.get('fundamentals_cache_hits', 0)},"
        f" fundamentals_fetched={summary.get('fundamentals_fetched_count', 0)},"
        f" fundamentals_missing={summary.get('fundamentals_missing_count', 0)}"
    )



def cmd_scan(args: argparse.Namespace) -> None:
    """Scan market for top stocks."""
    market = args.market
    top_n = args.top or 20
    output_dir, fmt = _cmd_output(args)

    if market == "FUND":
        print("Scanning ETFs...")
        etfs = get_etf_pool()
        if not etfs:
            print(
                "  No ETFs found. Run 'python stockaskill/scripts/run.py fetch"
                " pool' first.",
                file=sys.stderr,
            )
            return
        ensure_etf_ready(
            [str(item.get("code", "")).strip() for item in etfs[:top_n]],
            limit=top_n,
        )
        print(f"Found {len(etfs)} ETFs")
        for f in etfs[:top_n]:
            print(f"  {f.get('code', '?')} {f.get('name', '?')}")
        _save_report(
            "scan_FUND",
            fmt,
            output_dir,
            data={"market": "FUND", "count": len(etfs), "results": etfs[:top_n]},
        )
        return

    print(f"Scanning {market} market for top {top_n}...", flush=True)

    # Cold start: run bounded warmup before regime analysis needs data
    cache = get_cache()
    if cache.is_market_data_empty(market):
        warmup_n = min(top_n * 3, 30)
        print(
            f"  缓存为空，预热点 {warmup_n} 只股票数据...",
            flush=True,
        )
        pool = get_stock_pool(market)
        codes = [
            str(item.get("code", ""))
            for item in pool[:warmup_n]
            if str(item.get("code", "")).strip()
        ]
        for code in codes:
            try:
                sync_symbol_data(code, market, history_days=365)
            except RuntimeError:
                pass  # API limit hit during warmup, continue with what we have

    try:
        regime = _safe_market_regime(market)
        print("  " + summarize_market_regime(regime), flush=True)

        # Risk alert for cautious/defensive market states
        posture = regime.get("posture", "neutral")
        if posture in ("cautious", "defensive"):
            actions = {
                "cautious": "谨慎，建议减仓至60%以下",
                "defensive": "防御，建议降至25%以下仓位，避免新仓",
            }
            risk_budget = float(regime.get("risk_budget", 1.0) or 1.0)
            allowed = regime.get("new_positions_allowed", True)
            print(
                f"  ⚠️  市场风险预警: {regime.get('posture_label', '中性')}",
                flush=True,
            )
            print(f"  建议: {actions.get(posture, '观望')}", flush=True)
            print(f"  风险预算: {risk_budget:.0%}", flush=True)
            if not allowed:
                print(f"  当前不建议新开仓位", flush=True)
            print(flush=True)

        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        mode = getattr(args, "mode", "auto")
        refreshed = False
        summary = None
        if mode == "realtime":
            print(
                "  Realtime mode is approximate and only evaluates a candidate subset.",
                flush=True,
            )
            results = scanner.scan_top(
                market,
                top_n,
                max_candidates=getattr(args, "candidates", 0),
            )
        else:
            status = scanner.get_snapshot_status(market)
            if mode == "auto" and status["status"] != "fresh":
                reason = "缺失" if status["status"] == "missing" else "过期"
                print(
                    f"  本地全市场快照{reason}，回退到有界 realtime candidate scan。",
                    flush=True,
                )
                print(
                    "  如需构建完整本地快照，可执行:"
                    f" python stockaskill/scripts/run.py refresh-scan {market}",
                    flush=True,
                )
                results = scanner.scan_top(
                    market,
                    top_n,
                    max_candidates=getattr(args, "candidates", 0),
                )
                summary = {
                    **status,
                    "fallback_mode": "realtime",
                    "requested_mode": mode,
                }
            elif (
                mode == "snapshot"
                and status["status"] != "fresh"
                and not getattr(args, "refresh", False)
            ):
                reason = "缺失" if status["status"] == "missing" else "过期"
                print(f"  本地全市场快照{reason}。", flush=True)
                print(
                    "  推荐执行:"
                    f" python stockaskill/scripts/run.py refresh-scan {market}",
                    flush=True,
                )
                print(
                    "  或改用默认 auto / 显式 realtime 做有界候选扫描。",
                    flush=True,
                )
                results = []
                _save_report(
                    f"scan_{market}",
                    fmt,
                    output_dir,
                    data={
                        "market": market,
                        "top_n": top_n,
                        "mode": mode,
                        "results": results,
                        "summary": status,
                        "refreshed": refreshed,
                    },
                    metadata={"command": "scan", "market": market, "top_n": top_n},
                )
                return
            elif getattr(args, "refresh", False) or status["status"] != "fresh":
                print("  Refreshing full-market snapshot first...", flush=True)
                summary = scanner.refresh_snapshot(
                    market,
                    include_incomplete=getattr(args, "include_incomplete", False),
                )
                refreshed = True
                snapshot = scanner.scan_snapshot(
                    market,
                    top_n=top_n,
                    include_incomplete=getattr(args, "include_incomplete", False),
                )
                results = snapshot["results"]
                summary = snapshot["summary"] or summary
                if summary:
                    _print_snapshot_summary(summary, refreshed=refreshed)
                    if refreshed:
                        _print_refresh_summary(summary)
            else:
                snapshot = scanner.scan_snapshot(
                    market,
                    top_n=top_n,
                    include_incomplete=getattr(args, "include_incomplete", False),
                )
                results = snapshot["results"]
                summary = snapshot["summary"] or summary
                if summary:
                    _print_snapshot_summary(summary, refreshed=refreshed)
        if not results:
            print(
                "  No results returned (run 'python stockaskill/scripts/run.py"
                " fetch pool'"
                " to refresh data).",
                file=sys.stderr,
                flush=True,
            )
        for i, r in enumerate(results, 1):
            score = r.get("total_score", 0)
            name = r.get("name", r["code"])
            f_score = r.get("f_score", 0)
            badge = _badge(score)
            metadata_suffix = ""
            if "metadata_completeness" in r:
                metadata_suffix = (
                    f", meta={float(r.get('metadata_completeness', 0) or 0):.2f}"
                )
                penalty = float(r.get("metadata_penalty", 0) or 0)
                if penalty > 0:
                    metadata_suffix += (
                        f", adj={float(r.get('adjusted_score', score) or 0):.1f}"
                    )
            print(
                f"  {badge} {i:3d}. {r['code']} {name}: {score:.1f}"
                f" (F={f_score}{metadata_suffix})"
            )

        _save_report(
            f"scan_{market}",
            fmt,
            output_dir,
            data={
                "market": market,
                "regime": regime,
                "top_n": top_n,
                "mode": mode,
                "results": results,
                "summary": summary,
                "refreshed": refreshed,
            },
            metadata={"command": "scan", "market": market, "top_n": top_n},
        )
    except Exception as exc:
        print(f"Scan failed: {exc}", file=sys.stderr)
    finally:
        _print_api_usage()



def cmd_refresh_scan(args: argparse.Namespace) -> None:
    """Build a full-market local scan snapshot and print the top results."""
    market = args.market
    top_n = args.top or 20
    output_dir, fmt = _cmd_output(args)
    print(f"Refreshing full-market snapshot for {market}...", flush=True)
    regime = _safe_market_regime(market)
    print("  " + summarize_market_regime(regime), flush=True)
    try:
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        summary = scanner.refresh_snapshot(
            market,
            include_incomplete=getattr(args, "include_incomplete", False),
        )
        _print_snapshot_summary(summary, refreshed=True)
        _print_refresh_summary(summary)
        snapshot = scanner.scan_snapshot(
            market,
            top_n=top_n,
            include_incomplete=getattr(args, "include_incomplete", False),
        )
        results = snapshot["results"]
        for i, r in enumerate(results, 1):
            score = r.get("total_score", 0)
            name = r.get("name", r["code"])
            f_score = r.get("f_score", 0)
            badge = _badge(score)
            metadata_suffix = ""
            if "metadata_completeness" in r:
                metadata_suffix = (
                    f", meta={float(r.get('metadata_completeness', 0) or 0):.2f}"
                )
                penalty = float(r.get("metadata_penalty", 0) or 0)
                if penalty > 0:
                    metadata_suffix += (
                        f", adj={float(r.get('adjusted_score', score) or 0):.1f}"
                    )
            print(
                f"  {badge} {i:3d}. {r['code']} {name}: {score:.1f}"
                f" (F={f_score}{metadata_suffix})"
            )
        _save_report(
            f"refresh_scan_{market}",
            fmt,
            output_dir,
            data={
                "market": market,
                "regime": regime,
                "top_n": top_n,
                "mode": "snapshot",
                "results": results,
                "summary": summary,
                "refreshed": True,
            },
            metadata={"command": "refresh-scan", "market": market, "top_n": top_n},
        )
    except Exception as exc:
        print(f"Refresh scan failed: {exc}", file=sys.stderr)



def cmd_alpha(args: argparse.Namespace) -> None:
    """Alpha momentum scan: rank stocks by optimized multi-factor strategy."""
    market = args.market
    top_n = args.top or 10
    output_dir, fmt = _cmd_output(args)

    print(f"Alpha Momentum scan on {market}, top {top_n}...")
    regime = _safe_market_regime(market)
    print("  " + summarize_market_regime(regime))

    # Risk alert for cautious/defensive market states
    posture = regime.get("posture", "neutral")
    if posture in ("cautious", "defensive"):
        actions = {
            "cautious": "谨慎，建议减少候选数量",
            "defensive": "防御，建议暂停扫描，避免追高",
        }
        risk_budget = float(regime.get("risk_budget", 1.0) or 1.0)
        print(
            f"  ⚠️  市场风险预警: {regime.get('posture_label', '中性')}",
            flush=True,
        )
        print(f"  建议: {actions.get(posture, '观望')}", flush=True)
        print(f"  风险预算: {risk_budget:.0%}", flush=True)
        print(flush=True)

    try:
        pool = get_stock_pool(market)
        max_candidates = getattr(args, "candidates", 0) or cfg_get("scan_max_candidates", 0)
        candidates = pool[:max_candidates]

        # Concurrent pre-sync: fetch missing kline + fundamentals in parallel
        from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

        from data_engine import sync_symbol_data

        actual_n = len(candidates)
        print(f"  Pre-syncing {actual_n} candidates (8 workers)...", flush=True)
        sync_done = 0
        sync_errors = 0

        def sync_one(stock):
            try:
                sync_symbol_data(stock["code"], market, history_days=365)
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool_exec:
            sync_futures = {pool_exec.submit(sync_one, s): s for s in candidates}
            for f in as_completed(sync_futures):
                sync_done += 1
                if f.result():
                    sync_errors += 0
                else:
                    sync_errors += 1
                if sync_done % 50 == 0 or sync_done == actual_n:
                    print(f"    Sync progress: {sync_done}/{actual_n}", flush=True)
        if sync_errors:
            print(f"    Sync errors: {sync_errors}/{actual_n} (will skip in scoring)", flush=True)

        from strategies.alpha_momentum import AlphaMomentumStrategy

        results = []
        strat = AlphaMomentumStrategy()

        def score_one(stock):
            code = stock["code"]
            try:
                r = strat.analyze(code, market, cached_only=True)
                return (
                    code,
                    stock.get("name", ""),
                    r["score"],
                    r["signal"],
                    r["detail"]["f_score"],
                    r["detail"]["factors"],
                )
            except Exception:
                return None

        print(f"  Scoring {actual_n} candidates (8 workers)...", flush=True)
        score_done = 0
        with ThreadPoolExecutor(max_workers=8) as exec:
            futures = {exec.submit(score_one, s): s for s in candidates}
            for f in as_completed(futures):
                score_done += 1
                if score_done % 50 == 0 or score_done == actual_n:
                    print(f"    Score progress: {score_done}/{actual_n}", flush=True)
                result = f.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x[2], reverse=True)
        header = f"{'#':<4} {'代码':<10} {'名称':<10} "
        header += f"{'得分':<6} {'信号':<6} {'F':<4}"
        print(f"\n{header}")
        print("-" * 45)
        top_results = results[:top_n]
        for i, (code, name, score, signal, fsc, _) in enumerate(top_results, 1):
            sig_badge = {"BUY": "##", "SELL": "!!"}.get(signal, "--")
            print(f"{i:<4} {code:<10} {name:<10} {score:<6.1f} {sig_badge:<6} {fsc:<4}")

        print("\n## BUY signals:")
        buys = [(c, n, s, f) for c, n, s, sig, f, _ in top_results if sig == "BUY"]
        for c, n, s, f in buys:
            print(f"  ## {c} {n} (score={s:.1f}, F={f})")
        if not buys:
            print("  -- No BUY signals")

        ranked = []
        for code, name, score, signal, fsc, factors in top_results:
            ranked.append(
                {
                    "code": code,
                    "name": name,
                    "score": score,
                    "signal": signal,
                    "f_score": fsc,
                    "factors": factors,
                }
            )
        _save_report(
            f"alpha_{market}",
            fmt,
            output_dir,
            data={
                "market": market,
                "regime": regime,
                "top_n": top_n,
                "results": ranked,
                "buys": buys,
            },
            metadata={"command": "alpha", "market": market, "top_n": top_n},
        )
    except Exception as exc:
        print(f"Alpha scan failed: {exc}", file=sys.stderr)



