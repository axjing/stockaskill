"""Unified CLI entry point for the stock selection system."""

# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "akshare>=1.10.0",
#     "pandas>=2.0.0",
#     "numpy>=1.24.0",
#     "scipy>=1.10.0",
# ]
# ///

import argparse
import json
import sys
from pathlib import Path

# Force UTF-8 output for CJK support on Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_scripts_root = str(Path(__file__).resolve().parent)
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

_SCORE_BADGES = [(70, "##"), (40, "==")]
_DEFAULT_BADGE = "--"


def _badge(score: float) -> str:
    """Return a compact badge for a numeric score."""
    for threshold, b in _SCORE_BADGES:
        if score >= threshold:
            return b
    return _DEFAULT_BADGE

from cache import get_cache  # noqa: E402
from config import get as cfg_get  # noqa: E402
from data_engine import (  # noqa: E402
    get_fund_pool,
    get_fundamentals,
    get_kline,
    get_stock_pool,
)
from data_readiness import (  # noqa: E402
    ensure_fund_screen_ready,
    ensure_market_scan_ready,
    ensure_symbol_analysis_ready,
)
from report_generator import (  # noqa: E402
    format_backtest_summary,
    format_diagnosis_summary,
    format_portfolio_summary,
    save_markdown,
    save_report,
)


def _save_report(
    name: str, fmt: str, output_dir: str,
    data: dict | None = None, md: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Save report in requested formats."""
    if fmt == "none":
        return
    if fmt in ("json", "both") and data is not None:
        save_report(data, name, output_dir=output_dir, metadata=metadata)
    if fmt in ("md", "both") and md is not None:
        save_markdown(md, name, output_dir=output_dir)


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


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze a single stock: K-line + valuation + fundamentals."""
    code = args.code
    market = getattr(args, "market", "A") or "A"
    output_dir = getattr(args, "output_dir", "reports")
    fmt = getattr(args, "format", "both")
    print(f"Analyzing {code} (market={market})...")

    ensure_symbol_analysis_ready(code, market)
    kline = get_kline(code, market, days=365)
    print(f"  K-line data: {len(kline)} days cached")

    fund = get_fundamentals(code, market)
    report_data = {"code": code, "market": market}
    if fund:
        print(f"  PE(TTM): {fund.get('pe_ttm', 'N/A')}")
        print(f"  PB:      {fund.get('pb', 'N/A')}")
        print(f"  ROE:     {fund.get('roe', 'N/A')}")
        print(f"  DivYld:  {fund.get('dividend_yield', 'N/A')}%")
        print(f"  MktCap:  {fund.get('market_cap', 0):,.0f}")
        report_data["fundamentals"] = {
            k: fund.get(k)
            for k in (
                "pe_ttm",
                "pb",
                "roe",
                "dividend_yield",
                "market_cap",
            )
        }
    else:
        print("  Fundamentals: not available (using cached/computed)")

    try:
        from factors.composite import CompositeAnalyzer
        analyzer = CompositeAnalyzer(code, market)
        result = analyzer.analyze()
        score = result.get("total_score", 0)
        print(f"  Composite Score: {score:.1f}/100 {_badge(score)}")
        for factor_name, factor_score in result.get("factors", {}).items():
            print(f"    {_badge(factor_score)} {factor_name}: {factor_score:.1f}")
        report_data["factor_analysis"] = result
    except Exception as exc:
        print(f"  Factor analysis: {exc}", file=sys.stderr)

    try:
        from strategies.aggregator import StrategyAggregator
        agg = StrategyAggregator(code, market)
        signals = agg.analyze_all()
        final = signals.get("final_signal", "HOLD")
        final_score = signals.get("final_score", 0)
        sig_badge = {"BUY": "##", "SELL": "!!"}.get(final, "--")
        print(f"  Strategy Signal: {sig_badge} {final} (score={final_score:.1f})")
        report_data["strategy"] = signals
    except Exception as exc:
        print(f"  Strategy analysis: {exc}", file=sys.stderr)

    _save_report(f"analyze_{code}_{market}", fmt, output_dir, data=report_data,
                  metadata={"command": "analyze"})


def cmd_diagnose(args: argparse.Namespace) -> None:
    """Deep diagnosis: strategy + sentiment + risk."""
    code = args.code
    market = getattr(args, "market", "A") or "A"
    output_dir = getattr(args, "output_dir", "reports")
    fmt = getattr(args, "format", "both")
    print(f"Diagnosing {code} (market={market})...")

    try:
        from advisor.diagnosis import StockDiagnosis

        diag = StockDiagnosis(code, market)
        report = diag.full_report()
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))

        md = format_diagnosis_summary(report)
        _save_report(f"diagnose_{code}_{market}", fmt, output_dir,
                      data=report, md=md, metadata={"command": "diagnose"})
    except Exception as exc:
        print(f"Diagnosis failed: {exc}", file=sys.stderr)


def cmd_scan(args: argparse.Namespace) -> None:
    """Scan market for top stocks."""
    market = args.market
    top_n = args.top or 20
    output_dir = getattr(args, "output_dir", "reports")
    fmt = getattr(args, "format", "both")

    if market == "FUND":
        print("Scanning funds...")
        funds = get_fund_pool()
        if not funds:
            print(
                "  No funds found. Run 'python stockaskill/scripts/run.py fetch"
                " pool' first.",
                file=sys.stderr,
            )
            return
        ensure_fund_screen_ready(funds[:top_n], limit=top_n)
        print(f"Found {len(funds)} funds")
        for f in funds[:top_n]:
            print(f"  {f.get('code', '?')} {f.get('name', '?')}")
        _save_report(
            "scan_FUND",
            fmt,
            output_dir,
            data={"market": "FUND", "count": len(funds), "results": funds[:top_n]},
        )
        return

    print(f"Scanning {market} market for top {top_n}...", flush=True)
    try:
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        mode = getattr(args, "mode", "snapshot")
        refreshed = False
        summary = None
        if mode == "realtime":
            print(
                "  Realtime mode is approximate and only evaluates a candidate"
                " subset.",
                flush=True,
            )
            results = scanner.scan_top(
                market,
                top_n,
                max_candidates=getattr(args, "candidates", 0),
            )
        else:
            status = scanner.get_snapshot_status(market)
            if status["status"] != "fresh" and not getattr(args, "refresh", False):
                reason = "缺失" if status["status"] == "missing" else "过期"
                print(f"  本地全市场快照{reason}。", flush=True)
                print(
                    "  推荐执行:"
                    f" python stockaskill/scripts/run.py refresh-scan {market}",
                    flush=True,
                )
                print("  或追加 --refresh 自动先构建快照。", flush=True)
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
            if getattr(args, "refresh", False) or status["status"] != "fresh":
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
            print(f"  {badge} {i:3d}. {r['code']} {name}: {score:.1f} (F={f_score})")

        _save_report(
            f"scan_{market}",
            fmt,
            output_dir,
            data={
                "market": market,
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


def cmd_refresh_scan(args: argparse.Namespace) -> None:
    """Build a full-market local scan snapshot and print the top results."""
    market = args.market
    top_n = args.top or 20
    output_dir = getattr(args, "output_dir", "reports")
    fmt = getattr(args, "format", "both")
    print(f"Refreshing full-market snapshot for {market}...", flush=True)
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
            print(f"  {badge} {i:3d}. {r['code']} {name}: {score:.1f} (F={f_score})")
        _save_report(
            f"refresh_scan_{market}",
            fmt,
            output_dir,
            data={
                "market": market,
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


def cmd_portfolio(args: argparse.Namespace) -> None:
    """Build an investment portfolio."""
    codes = [c.strip() for c in args.codes.split(",")]
    capital = args.capital or 1000000
    market = getattr(args, "market", "A") or "A"
    output_dir = getattr(args, "output_dir", "reports")
    fmt = getattr(args, "format", "both")

    print(f"Building portfolio with {len(codes)} stocks, capital={capital:,.0f}")
    try:
        from portfolio.builder import PortfolioBuilder

        builder = PortfolioBuilder("My Portfolio", capital=capital)
        for c in codes:
            builder.add_from_strategy(c, market)
        portfolio = builder.build()
        print(portfolio.summary())

        positions_data = []
        for p in portfolio.positions:
            positions_data.append({
                "code": p.code, "name": p.name, "weight": p.weight,
                "shares": p.shares, "cost": p.cost,
            })
        port_data = {
            "name": portfolio.name,
            "capital": capital,
            "market": market,
            "positions": positions_data,
            "metrics": portfolio.metrics,
        }
        md = format_portfolio_summary(
            portfolio.name,
            capital,
            positions_data,
            portfolio.metrics,
        )
        _save_report(
            f"portfolio_{market}",
            fmt,
            output_dir,
            data=port_data,
            md=md,
            metadata={"command": "portfolio", "market": market},
        )
    except Exception as exc:
        print(f"Portfolio build failed: {exc}", file=sys.stderr)


def cmd_fetch(args: argparse.Namespace) -> None:
    """Manually refresh data."""
    fetch_type = args.type
    code = getattr(args, "code", "")
    market = getattr(args, "market", "A") or "A"

    if fetch_type == "pool":
        print("Refreshing stock pool...")
        for mkt in ["A", "HK", "US", "FUND"]:
            from data_engine import get_fund_pool, get_stock_pool

            if mkt == "FUND":
                get_fund_pool(force_refresh=True)
            else:
                get_stock_pool(mkt, force_refresh=True)
            print(f"  {mkt}: done")
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


def cmd_alpha(args: argparse.Namespace) -> None:
    """Alpha momentum scan: rank stocks by optimized multi-factor strategy."""
    market = args.market
    top_n = args.top or 10
    output_dir = getattr(args, "output_dir", "reports")
    fmt = getattr(args, "format", "both")

    print(f"Alpha Momentum scan on {market}, top {top_n}...")
    try:
        pool = get_stock_pool(market)
        max_candidates = getattr(args, "candidates", 0)
        if not max_candidates:
            max_candidates = cfg_get("scan_max_candidates", 200)
        candidates = pool[:max_candidates]
        candidate_rows = [
            {"code": stock["code"], "market": market} for stock in candidates
        ]
        ensure_market_scan_ready(market, candidate_rows)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from strategies.alpha_momentum import AlphaMomentumStrategy

        results = []
        strat = AlphaMomentumStrategy()

        def score_one(stock):
            code = stock["code"]
            try:
                r = strat.analyze(code, market)
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

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(score_one, s): s for s in candidates}
            for f in as_completed(futures):
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
            ranked.append({
                "code": code, "name": name, "score": score,
                "signal": signal, "f_score": fsc, "factors": factors,
            })
        _save_report(
            f"alpha_{market}",
            fmt,
            output_dir,
            data={
                "market": market,
                "top_n": top_n,
                "results": ranked,
                "buys": buys,
            },
            metadata={"command": "alpha", "market": market, "top_n": top_n},
        )
    except Exception as exc:
        print(f"Alpha scan failed: {exc}", file=sys.stderr)


def cmd_backtest(args: argparse.Namespace) -> None:
    """Run Alpha Momentum backtest (2018-2026)."""
    output_dir = getattr(args, "output_dir", "reports")
    fmt = getattr(args, "format", "both")
    print("Running Alpha Momentum backtest...")
    try:
        from portfolio.backtest_engine import AlphaMomentumBacktest

        engine = AlphaMomentumBacktest(
            capital=cfg_get("backtest_capital", 1_000_000),
            low_vol_min=cfg_get("low_vol_min", 0.4),
        )
        result = engine.run()

        pool_size = result.get("pool_size", 0)
        years = result.get("years", 0)
        print(f"  Pool: {pool_size} stocks, {years} years")
        period_start = result.get("period_start", "?")
        period_end = result.get("period_end", "?")
        print(f"  Period: {period_start} ~ {period_end}")
        cagr_val = result.get("cagr", 0)
        total_ret = result.get("total_return", 0)
        sharpe_val = result.get("sharpe", 0)
        mdd_val = result.get("max_drawdown", 0)
        monthly_avg = result.get("monthly_avg", 0)
        print(f"  CAGR: {cagr_val * 100:.2f}%")
        print(f"  Total Return: {total_ret * 100:.2f}%")
        print(f"  Sharpe: {sharpe_val:.2f}")
        print(f"  Max Drawdown: {mdd_val * 100:.2f}%")
        print(f"  Monthly Avg: {monthly_avg:.2f}%")

        if cagr_val > 0.12:
            print(
                f"  Result: ## PASS (CAGR {cagr_val * 100:.2f}% > 12% target)"
            )
        else:
            print(
                f"  Result: !! FAIL (CAGR {cagr_val * 100:.2f}% < 12% target)"
            )

        md = format_backtest_summary(result)
        _save_report(
            "backtest",
            fmt,
            output_dir,
            data=result,
            md=md,
            metadata={
                "command": "backtest",
                "engine": "AlphaMomentumBacktest",
            },
        )
    except Exception as exc:
        print(f"Backtest failed: {exc}")
        import traceback

        traceback.print_exc()


def cmd_backtest_enhanced(args: argparse.Namespace) -> None:
    """Run Enhanced Core-Satellite backtest (2018-2026)."""
    output_dir = getattr(args, "output_dir", "reports")
    fmt = getattr(args, "format", "both")
    print("Running Enhanced Core-Satellite backtest...")
    try:
        import importlib

        bt = importlib.import_module("backtest_enhanced")
        result = bt.run_backtest()
        print(
            f"\n  Result: CAGR={result.get('cagr', 0)*100:.2f}%, "
            f"Sharpe={result.get('sharpe', 0):.2f}, "
            f"MaxDD={result.get('max_drawdown', 0)*100:.2f}%"
        )

        md = format_backtest_summary(result)
        _save_report(
            "backtest_enhanced",
            fmt,
            output_dir,
            data=result,
            md=md,
            metadata={
                "command": "backtest-enhanced",
                "engine": "CoreSatellite",
            },
        )
    except Exception as exc:
        print(f"Enhanced backtest failed: {exc}")
        import traceback

        traceback.print_exc()


def cmd_portfolio_enhanced(args: argparse.Namespace) -> None:
    """Build ETF(3) + Alpha Momentum Top3 = 6 positions portfolio."""
    capital = args.capital or 1000000
    output_dir = getattr(args, "output_dir", "reports")
    fmt = getattr(args, "format", "both")
    print(f"Building Enhanced Core-Satellite portfolio, capital={capital:,.0f}")
    try:
        from data_engine import get_stock_pool
        from portfolio.builder import PortfolioBuilder
        from strategies.momentum_enhanced import MomentumEnhancedStrategy

        strat = MomentumEnhancedStrategy()
        pool = get_stock_pool("A")
        candidates = pool[:200]
        selected = strat.select_top_stocks(candidates, max_picks=3)

        etfs = MomentumEnhancedStrategy.get_etf_allocation()
        codes = [e["code"] for e in etfs] + selected
        print(f"  ETFs (core): {[e['code'] for e in etfs]}")
        print(f"  Stocks (satellite): {selected}")

        builder = PortfolioBuilder("Core-Satellite", capital=capital)
        for code in codes:
            builder.add_from_strategy(code, "A")
        portfolio = builder.build()
        print(portfolio.summary())

        positions_data = []
        for p in portfolio.positions:
            positions_data.append({
                "code": p.code, "name": p.name, "weight": p.weight,
                "shares": p.shares, "cost": p.cost,
            })
        port_data = {
            "name": "Core-Satellite",
            "capital": capital,
            "etfs": [e["code"] for e in etfs],
            "stocks": selected,
            "positions": positions_data,
            "metrics": portfolio.metrics,
        }
        md = format_portfolio_summary(
            "Core-Satellite",
            capital,
            positions_data,
            portfolio.metrics,
        )
        _save_report(
            "portfolio_enhanced",
            fmt,
            output_dir,
            data=port_data,
            md=md,
            metadata={"command": "portfolio-enhanced"},
        )
    except Exception as exc:
        print(f"Enhanced portfolio build failed: {exc}")


def cmd_scheduler(args: argparse.Namespace) -> None:
    """Run scheduled analysis."""
    watchlist = cfg_get("watchlist", [])
    if not watchlist:
        print("No watchlist configured")
        return

    if args.run_now:
        print(f"Running scheduled analysis for {len(watchlist)} stocks...")
        for code in watchlist:
            print(f"\n--- {code} ---")
            fake_args = argparse.Namespace(code=code, market="A", output_dir="reports")
            cmd_analyze(fake_args)
    else:
        print("Scheduler mode: use --run-now for immediate execution")
        print("In production, integrate with cron/systemd Task Scheduler")
        print(f"Watching: {', '.join(watchlist)}")


def cmd_cache(args: argparse.Namespace) -> None:
    """Cache management: stats, cleanup."""
    action = args.action
    cache = get_cache()

    if action == "stats":
        s = cache.stats()
        print(f"DB size: {s['db_size_mb']:.1f} MB")
        print(f"API calls today: {s['api_calls_today']}")
        print("Table row counts:")
        for tbl, cnt in sorted(s.items()):
            if tbl in ("db_size_mb", "api_calls_today"):
                continue
            print(f"  {tbl}: {cnt}")
    elif action == "cleanup":
        days = getattr(args, "days", 30)
        removed = cache.cleanup(max_age_days=days)
        total = sum(removed.values())
        print(f"Cleaned up {total} old entries:")
        for tbl, cnt in removed.items():
            if cnt:
                print(f"  {tbl}: {cnt} rows removed")
    else:
        print(f"Unknown cache action: {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AKShare Stock Selection System")
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze
    p = sub.add_parser("analyze", help="Analyze a single stock")
    p.add_argument("code", help="Stock code")
    p.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    p.add_argument("--output-dir", default="reports", help="Report output directory")
    p.add_argument("--format", choices=["json", "md", "both", "none"], default="both",
                    help="Report output format")
    p.set_defaults(func=cmd_analyze)

    # diagnose
    p = sub.add_parser("diagnose", help="Deep stock diagnosis")
    p.add_argument("code", help="Stock code")
    p.add_argument("--market", default="A", help="Market (A/HK/US)")
    p.add_argument("--output-dir", default="reports", help="Report output directory")
    p.add_argument("--format", choices=["json", "md", "both", "none"], default="both",
                    help="Report output format")
    p.set_defaults(func=cmd_diagnose)

    # scan
    p = sub.add_parser("scan", help="Scan market for top stocks")
    p.add_argument("market", help="Market (A/HK/US/FUND)")
    p.add_argument("--top", type=int, default=20, help="Number of results")
    p.add_argument(
        "--candidates",
        type=int,
        default=0,
        help="Realtime mode only: max candidates to evaluate (0=auto)",
    )
    p.add_argument(
        "--mode",
        choices=["snapshot", "realtime"],
        default="snapshot",
        help="Snapshot reads the latest full-market cache; realtime is approximate.",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh the full-market snapshot before reading results.",
    )
    p.add_argument(
        "--include-incomplete",
        action="store_true",
        help="Include ineligible/incomplete rows in snapshot output for debugging.",
    )
    p.add_argument("--output-dir", default="reports", help="Report output directory")
    p.add_argument("--format", choices=["json", "md", "both", "none"], default="both",
                    help="Report output format")
    p.set_defaults(func=cmd_scan)

    # refresh-scan
    p = sub.add_parser(
        "refresh-scan",
        help="Build a full-market local scan snapshot and print the latest ranking",
    )
    p.add_argument("market", help="Market (A/HK/US)")
    p.add_argument("--top", type=int, default=20, help="Number of results")
    p.add_argument(
        "--include-incomplete",
        action="store_true",
        help="Include ineligible/incomplete rows in snapshot output for debugging.",
    )
    p.add_argument("--output-dir", default="reports", help="Report output directory")
    p.add_argument("--format", choices=["json", "md", "both", "none"], default="both",
                    help="Report output format")
    p.set_defaults(func=cmd_refresh_scan)

    # portfolio
    p = sub.add_parser("portfolio", help="Build investment portfolio")
    p.add_argument("--codes", required=True, help="Comma-separated stock codes")
    p.add_argument("--capital", type=float, default=1000000)
    p.add_argument("--market", default="A")
    p.add_argument("--output-dir", default="reports", help="Report output directory")
    p.add_argument("--format", choices=["json", "md", "both", "none"], default="both",
                    help="Report output format")
    p.set_defaults(func=cmd_portfolio)

    # fetch
    p = sub.add_parser("fetch", help="Refresh data")
    p.add_argument("type", choices=["pool", "kline", "fundamentals"])
    p.add_argument(
        "code", nargs="?", default="", help="Stock code (for kline/fundamentals)"
    )
    p.add_argument("--market", default="A")
    p.set_defaults(func=cmd_fetch)

    # alpha
    p = sub.add_parser("alpha", help="Alpha momentum stock scan")
    p.add_argument("market", default="A", nargs="?", help="Market (A/HK/US)")
    p.add_argument("--top", type=int, default=10, help="Number of results")
    p.add_argument(
        "--candidates", type=int, default=0, help="Max candidates to evaluate (0=auto)"
    )
    p.add_argument("--output-dir", default="reports", help="Report output directory")
    p.add_argument("--format", choices=["json", "md", "both", "none"], default="both",
                    help="Report output format")
    p.set_defaults(func=cmd_alpha)

    # backtest
    p = sub.add_parser("backtest", help="Run Alpha Momentum backtest (2018-2026)")
    p.add_argument("--output-dir", default="reports", help="Report output directory")
    p.add_argument("--format", choices=["json", "md", "both", "none"], default="both",
                    help="Report output format")
    p.set_defaults(func=cmd_backtest)

    # backtest-enhanced
    p = sub.add_parser(
        "backtest-enhanced", help="Run Enhanced Core-Satellite backtest (2018-2026)"
    )
    p.add_argument("--output-dir", default="reports", help="Report output directory")
    p.add_argument("--format", choices=["json", "md", "both", "none"], default="both",
                    help="Report output format")
    p.set_defaults(func=cmd_backtest_enhanced)

    # portfolio-enhanced
    p = sub.add_parser(
        "portfolio-enhanced", help="ETF(3)+Alpha Momentum Top3 = 6 positions"
    )
    p.add_argument("--capital", type=float, default=1000000)
    p.add_argument("--output-dir", default="reports", help="Report output directory")
    p.add_argument("--format", choices=["json", "md", "both", "none"], default="both",
                    help="Report output format")
    p.set_defaults(func=cmd_portfolio_enhanced)

    # scheduler
    p = sub.add_parser("scheduler", help="Run scheduled analysis")
    p.add_argument("--run-now", action="store_true")
    p.set_defaults(func=cmd_scheduler)

    # cache
    p = sub.add_parser("cache", help="Cache management")
    cache_sub = p.add_subparsers(dest="action", required=True)
    p_stats = cache_sub.add_parser("stats", help="Show cache statistics")
    p_stats.set_defaults(func=cmd_cache)
    p_clean = cache_sub.add_parser("cleanup", help="Clean old cache entries")
    p_clean.add_argument("--days", type=int, default=30, help="Max age in days")
    p_clean.set_defaults(func=cmd_cache)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
