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

# Force UTF-8 output for CJK support on Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

_scripts_root = str(Path(__file__).resolve().parent)
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from config import get as cfg_get  # noqa: E402
from data_engine import (  # noqa: E402
    get_fund_pool,
    get_fundamentals,
    get_kline,
    get_stock_pool,
)

from report_generator import (  # noqa: E402
    save_report,
    save_json,
    save_markdown,
    format_scan_results,
    format_portfolio_summary,
    format_diagnosis_summary,
    format_backtest_summary,
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


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze a single stock: K-line + valuation + fundamentals."""
    code = args.code
    market = getattr(args, "market", "A") or "A"
    output_dir = getattr(args, "output_dir", "reports")
    fmt = getattr(args, "format", "both")
    print(f"Analyzing {code} (market={market})...")

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
            k: fund.get(k) for k in ("pe_ttm", "pb", "roe", "dividend_yield", "market_cap")
        }
    else:
        print("  Fundamentals: not available (using cached/computed)")

    try:
        from factors.composite import CompositeAnalyzer
        analyzer = CompositeAnalyzer(code, market)
        result = analyzer.analyze()
        score = result.get("total_score", 0)
        badge = "##" if score >= 70 else ("!!" if score >= 40 else "!!")
        print(f"  Composite Score: {score:.1f}/100 {badge}")
        for factor_name, factor_score in result.get("factors", {}).items():
            fb = "##" if factor_score >= 70 else ("==" if factor_score >= 40 else "--")
            print(f"    {fb} {factor_name}: {factor_score:.1f}")
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
            print("  No funds found. Run 'python scripts/run.py fetch pool' first.", file=sys.stderr)
            return
        print(f"Found {len(funds)} funds")
        for f in funds[:top_n]:
            print(f"  {f.get('code', '?')} {f.get('name', '?')}")
        _save_report("scan_FUND", fmt, output_dir,
                      data={"market": "FUND", "count": len(funds), "results": funds[:top_n]})
        return

    print(f"Scanning {market} market for top {top_n}...", flush=True)
    try:
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        results = scanner.scan_top(
            market, top_n, max_candidates=getattr(args, "candidates", 0)
        )
        if not results:
            print(
                "  No results returned (run 'python scripts/run.py fetch pool'"
                " to refresh data).",
                file=sys.stderr,
                flush=True,
            )
        for i, r in enumerate(results, 1):
            score = r.get("total_score", 0)
            name = r.get("name", r["code"])
            f_score = r.get("f_score", 0)
            badge = "##" if score >= 70 else ("==" if score >= 40 else "--")
            print(f"  {badge} {i:3d}. {r['code']} {name}: {score:.1f} (F={f_score})")

        _save_report(f"scan_{market}", fmt, output_dir,
                      data={"market": market, "top_n": top_n, "results": results},
                      metadata={"command": "scan", "market": market, "top_n": top_n})
    except Exception as exc:
        print(f"Scan failed: {exc}", file=sys.stderr)


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
        md = format_portfolio_summary(portfolio.name, capital, positions_data, portfolio.metrics)
        _save_report(f"portfolio_{market}", fmt, output_dir,
                      data=port_data, md=md,
                      metadata={"command": "portfolio", "market": market})
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

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(score_one, s): s for s in candidates}
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
        _save_report(f"alpha_{market}", fmt, output_dir,
                      data={"market": market, "top_n": top_n, "results": ranked, "buys": buys},
                      metadata={"command": "alpha", "market": market, "top_n": top_n})
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

        if cagr > 0.12:
            print(f"  Result: ## PASS (CAGR {cagr * 100:.2f}% > 12% target)")
        else:
            print(f"  Result: !! FAIL (CAGR {cagr * 100:.2f}% < 12% target)")

        md = format_backtest_summary(result, "Alpha Momentum Backtest (2018-2026)")
        _save_report("backtest", fmt, output_dir, data=result, md=md,
                      metadata={"command": "backtest", "engine": "AlphaMomentumBacktest"})
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

        md = format_backtest_summary(result, "Enhanced Core-Satellite Backtest (2018-2026)")
        _save_report("backtest_enhanced", fmt, output_dir, data=result, md=md,
                      metadata={"command": "backtest-enhanced", "engine": "CoreSatellite"})
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
        md = format_portfolio_summary("Core-Satellite", capital, positions_data, portfolio.metrics)
        _save_report("portfolio_enhanced", fmt, output_dir, data=port_data, md=md,
                      metadata={"command": "portfolio-enhanced"})
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
        "--candidates", type=int, default=0, help="Max candidates to evaluate (0=auto)"
    )
    p.add_argument("--output-dir", default="reports", help="Report output directory")
    p.add_argument("--format", choices=["json", "md", "both", "none"], default="both",
                    help="Report output format")
    p.set_defaults(func=cmd_scan)

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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
