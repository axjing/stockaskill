"""Unified CLI entry point for the stock selection system."""

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


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze a single stock: K-line + valuation + fundamentals."""
    code = args.code
    market = getattr(args, "market", "A") or "A"
    print(f"Analyzing {code} (market={market})...")

    kline = get_kline(code, market, days=365)
    print(f"  K-line data: {len(kline)} days cached")

    fund = get_fundamentals(code, market)
    if fund:
        print(f"  PE(TTM): {fund.get('pe_ttm', 'N/A')}")
        print(f"  PB:      {fund.get('pb', 'N/A')}")
        print(f"  ROE:     {fund.get('roe', 'N/A')}")
        print(f"  DivYld:  {fund.get('dividend_yield', 'N/A')}%")
        print(f"  MktCap:  {fund.get('market_cap', 0):,.0f}")
    else:
        print("  Fundamentals: not available (using cached/computed)")

    # Run factor analysis
    try:
        from factors.composite import CompositeAnalyzer

        analyzer = CompositeAnalyzer(code, market)
        result = analyzer.analyze()
        score = result.get("total_score", 0)
        print(f"  Composite Score: {score:.1f}/100")
        for factor_name, factor_score in result.get("factors", {}).items():
            print(f"    {factor_name}: {factor_score:.1f}")
    except Exception as exc:
        print(f"  Factor analysis: {exc}")

    # Run strategy analysis
    try:
        from strategies.aggregator import StrategyAggregator

        agg = StrategyAggregator(code, market)
        signals = agg.analyze_all()
        final = signals.get("final_signal", "HOLD")
        final_score = signals.get("final_score", 0)
        print(f"  Strategy Signal: {final} (score={final_score:.1f})")
    except Exception as exc:
        print(f"  Strategy analysis: {exc}")


def cmd_diagnose(args: argparse.Namespace) -> None:
    """Deep diagnosis: strategy + sentiment + risk."""
    code = args.code
    market = getattr(args, "market", "A") or "A"
    print(f"Diagnosing {code} (market={market})...")

    try:
        from advisor.diagnosis import StockDiagnosis

        diag = StockDiagnosis(code, market)
        report = diag.full_report()
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    except Exception as exc:
        print(f"Diagnosis failed: {exc}")


def cmd_scan(args: argparse.Namespace) -> None:
    """Scan market for top stocks."""
    market = args.market
    top_n = args.top or 20

    if market == "FUND":
        print("Scanning funds...")
        funds = get_fund_pool()
        print(f"Found {len(funds)} funds")
        for f in funds[:top_n]:
            print(f"  {f.get('code', '?')} {f.get('name', '?')}")
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
                flush=True,
            )
        for i, r in enumerate(results, 1):
            score = r.get("total_score", 0)
            name = r.get("name", r["code"])
            f_score = r.get("f_score", 0)
            print(f"  {i:3d}. {r['code']} {name}: {score:.1f} (F={f_score})")
    except Exception as exc:
        print(f"Scan failed: {exc}")


def cmd_portfolio(args: argparse.Namespace) -> None:
    """Build an investment portfolio."""
    codes = [c.strip() for c in args.codes.split(",")]
    capital = args.capital or 1000000
    market = getattr(args, "market", "A") or "A"

    print(f"Building portfolio with {len(codes)} stocks, capital={capital:,.0f}")
    try:
        from portfolio.builder import PortfolioBuilder

        builder = PortfolioBuilder("My Portfolio", capital=capital)
        for c in codes:
            builder.add_from_strategy(c, market)
        portfolio = builder.build()
        print(portfolio.summary())
    except Exception as exc:
        print(f"Portfolio build failed: {exc}")


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
        header = f"{'排名':<4} {'代码':<10} {'名称':<10} "
        header += f"{'得分':<6} {'信号':<6} {'F':<4}"
        print(f"\n{header}")
        print("-" * 45)
        for i, (code, name, score, signal, fsc, _) in enumerate(results[:top_n], 1):
            print(f"{i:<4} {code:<10} {name:<10} {score:<6.1f} {signal:<6} {fsc:<4}")

        print("\n推荐买入 (BUY信号):")
        buys = [(c, n, s, f) for c, n, s, sig, f, _ in results[:top_n] if sig == "BUY"]
        for c, n, s, f in buys:
            print(f"  {c} {n} (得分={s:.1f}, F={f})")
        if not buys:
            print("  当前无BUY信号")
    except Exception as exc:
        print(f"Alpha scan failed: {exc}")


def cmd_backtest(args: argparse.Namespace) -> None:
    """Run Alpha Momentum backtest (2018-2026)."""
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

        cagr = result.get("cagr", 0)
        if cagr > 0.12:
            print(f"  Result: PASS (CAGR {cagr * 100:.2f}% > 12% target)")
        else:
            print(f"  Result: FAIL (CAGR {cagr * 100:.2f}% < 12% target)")
    except Exception as exc:
        print(f"Backtest failed: {exc}")
        import traceback

        traceback.print_exc()


def cmd_backtest_enhanced(args: argparse.Namespace) -> None:
    """Run Enhanced Core-Satellite backtest (2018-2026)."""
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
    except Exception as exc:
        print(f"Enhanced backtest failed: {exc}")
        import traceback

        traceback.print_exc()


def cmd_portfolio_enhanced(args: argparse.Namespace) -> None:
    """Build ETF(3) + Alpha Momentum Top3 = 6 positions portfolio."""
    capital = args.capital or 1000000
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
            fake_args = argparse.Namespace(code=code, market="A")
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
    p.set_defaults(func=cmd_analyze)

    # diagnose
    p = sub.add_parser("diagnose", help="Deep stock diagnosis")
    p.add_argument("code", help="Stock code")
    p.add_argument("--market", default="A", help="Market (A/HK/US)")
    p.set_defaults(func=cmd_diagnose)

    # scan
    p = sub.add_parser("scan", help="Scan market for top stocks")
    p.add_argument("market", help="Market (A/HK/US/FUND)")
    p.add_argument("--top", type=int, default=20, help="Number of results")
    p.add_argument(
        "--candidates", type=int, default=0, help="Max candidates to evaluate (0=auto)"
    )
    p.set_defaults(func=cmd_scan)

    # portfolio
    p = sub.add_parser("portfolio", help="Build investment portfolio")
    p.add_argument("--codes", required=True, help="Comma-separated stock codes")
    p.add_argument("--capital", type=float, default=1000000)
    p.add_argument("--market", default="A")
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
    p.set_defaults(func=cmd_alpha)

    # backtest
    p = sub.add_parser("backtest", help="Run Alpha Momentum backtest (2018-2026)")
    p.set_defaults(func=cmd_backtest)

    # backtest-enhanced
    p = sub.add_parser(
        "backtest-enhanced", help="Run Enhanced Core-Satellite backtest (2018-2026)"
    )
    p.set_defaults(func=cmd_backtest_enhanced)

    # portfolio-enhanced
    p = sub.add_parser(
        "portfolio-enhanced", help="ETF(3)+Alpha Momentum Top3 = 6 positions"
    )
    p.add_argument("--capital", type=float, default=1000000)
    p.set_defaults(func=cmd_portfolio_enhanced)

    # scheduler
    p = sub.add_parser("scheduler", help="Run scheduled analysis")
    p.add_argument("--run-now", action="store_true")
    p.set_defaults(func=cmd_scheduler)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
