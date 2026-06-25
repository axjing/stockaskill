"""Unified CLI entry point for the stock selection system."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

# Force UTF-8 output for CJK support on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
_scripts_root = str(Path(__file__).resolve().parent)
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from config import get as cfg_get
from data_engine import get_kline, get_stock_pool, get_fundamentals, get_fund_pool


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze a single stock: K-line + valuation + fundamentals."""
    code = args.code
    market = getattr(args, "market", "A") or "A"
    print(f"Analyzing {code} (market={market})...")

    pool = get_stock_pool(market)
    info = next((s for s in pool if s["code"] == code), None)
    name = info["name"] if info else code

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
        results = scanner.scan_top(market, top_n, max_candidates=getattr(args, 'candidates', 0))
        if not results:
            print("  No results returned (run 'python scripts/run.py fetch pool' to refresh data).", flush=True)
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
            from data_engine import get_stock_pool, get_fund_pool
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
        max_candidates = getattr(args, "candidates", 0) or cfg_get("scan_max_candidates", 200)
        candidates = pool[:max_candidates]
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from strategies.alpha_momentum import AlphaMomentumStrategy

        results = []
        strat = AlphaMomentumStrategy()

        def score_one(stock):
            code = stock["code"]
            try:
                r = strat.analyze(code, market)
                return (code, stock.get("name", ""), r["score"], r["signal"],
                        r["detail"]["f_score"], r["detail"]["factors"])
            except:
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(score_one, s): s for s in candidates}
            for f in as_completed(futures):
                result = f.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x[2], reverse=True)
        print(f"\n{'排名':<4} {'代码':<10} {'名称':<10} {'得分':<6} {'信号':<6} {'F':<4}")
        print("-" * 45)
        for i, (code, name, score, signal, fsc, _) in enumerate(results[:top_n], 1):
            print(f"{i:<4} {code:<10} {name:<10} {score:<6.1f} {signal:<6} {fsc:<4}")

        print(f"\n推荐买入 (BUY信号):")
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
        import numpy as np
        from datetime import datetime
        from collections import defaultdict
        from cache import get_cache
        from data_engine import get_fundamentals
        from factors.momentum import MomentumFactor
        from factors.low_vol import LowVolFactor
        from factors.quality import QualityFactor
        from factors.value import ValueFactor
        from factors.growth import GrowthFactor
        import sqlite3

        from utils import is_st
        c = get_cache()
        conn = sqlite3.connect(str(c.db_path))
        cur = conn.execute("""
            SELECT d.code, d.date, d.close, COALESCE(s.name, '') as name
            FROM daily_price d
            LEFT JOIN stock_pool s ON d.code = s.code
            WHERE d.code IN (
                SELECT code FROM daily_price GROUP BY code HAVING COUNT(*) >= 1500
            )
            ORDER BY d.code, d.date ASC
        """)
        sd = defaultdict(list)
        st_codes = set()
        for row in cur.fetchall():
            sd[row[0]].append({"date": row[1], "close": float(row[2])})
            if is_st(row[0], row[3]):
                st_codes.add(row[0])
        codes = sorted(sd.keys())
        codes = [c for c in codes if c not in st_codes]
        conn.close()

        fc = {}
        for code in codes:
            try:
                f = get_fundamentals(code, "A", force_refresh=False)
                if f and f.get("eps", 0) > 0:
                    fc[code] = f
            except Exception:
                pass
        codes = sorted(fc.keys())

        all_d = sorted(set(d["date"] for code in codes for d in sd[code]))
        all_d = [d for d in all_d if d >= "2018-01-01"]
        md = {}
        for d in all_d:
            md[d[:7]] = d
        rd = sorted(md.values())

        mf = MomentumFactor()
        lf = LowVolFactor()
        qf = QualityFactor()
        vf = ValueFactor()
        gf = GrowthFactor()

        LOW_VOL_MIN = 0.4

        def _score(code, kslice):
            fund = fc.get(code, {})
            try:
                s = mf.compute(fund, kslice, "A")
                l = lf.compute(kslice, "A")
                q = qf.compute(fund, kslice, "A")
                v = vf.compute(fund, kslice, "A")
                g = gf.compute(fund, kslice, "A")
                # Hard filter: exclude stocks with low_vol below threshold
                if l < LOW_VOL_MIN:
                    return 0
                return s * 0.30 + l * 0.28 + q * 0.21 + v * 0.14 + g * 0.07
            except Exception:
                return 0

        cap = 1000000
        positions = {}
        cash = cap
        nav = []

        def _board(code):
            if code.startswith("60"):
                return "SH"
            if code.startswith("688"):
                return "STAR"
            if code.startswith("000"):
                return "SZ"
            if code.startswith("002"):
                return "SME"
            if code.startswith("300"):
                return "GEM"
            return "OTHER"

        def _select_diversified(scored, top_k=6, max_per_board=3):
            selected = []
            board_count = {}
            for code, score in scored:
                if score <= 0:
                    continue
                board = _board(code)
                if board_count.get(board, 0) >= max_per_board:
                    continue
                selected.append(code)
                board_count[board] = board_count.get(board, 0) + 1
                if len(selected) >= top_k:
                    break
            return selected

        for i, reb_date in enumerate(rd):
            if i == 0:
                continue
            scored = []
            for code in codes:
                kslice = [x for x in sd[code] if x["date"] <= reb_date]
                if len(kslice) < 120:
                    continue
                s = _score(code, kslice)
                if s > 0:
                    scored.append((code, s))
            scored.sort(key=lambda x: x[1], reverse=True)
            selected = _select_diversified(scored, top_k=6, max_per_board=3)

            for code in list(positions.keys()):
                if code not in selected:
                    p = [x["close"] for x in sd[code] if x["date"] <= reb_date]
                    price = p[-1] if p else 0
                    if price > 0:
                        cash += positions[code] * price * (1 - 0.0003 - 0.001)
                        del positions[code]

            if selected:
                alloc = cash / len(selected)
                for code in selected:
                    if code not in positions:
                        p = [x["close"] for x in sd[code] if x["date"] <= reb_date]
                        price = p[-1] if p else 0
                        if price > 0:
                            shares = max(100, int(alloc / price / 100) * 100)
                            cost = shares * price * 1.0003
                            if cost <= cash and shares > 0:
                                positions[code] = shares
                                cash -= cost

            total = cash
            for code, shares in positions.items():
                p = [x["close"] for x in sd[code] if x["date"] <= reb_date]
                price = p[-1] if p else 0
                total += shares * price
            nav.append(total)

        final_date = all_d[-1]
        total = cash
        for code, shares in positions.items():
            p = [x["close"] for x in sd[code] if x["date"] <= final_date]
            price = p[-1] if p else 0
            total += shares * price
        nav.append(total)

        na = np.array(nav)
        tr = (na[-1] - na[0]) / na[0]
        start_dt = datetime.strptime(rd[0] if len(rd) > 1 else rd[0], "%Y-%m-%d")
        ed_dt = datetime.strptime(final_date, "%Y-%m-%d")
        yr = max((ed_dt - start_dt).days / 365.25, 0.1)
        cagr = (na[-1] / na[0]) ** (1 / yr) - 1

        ra = []
        for k in range(1, len(na)):
            if na[k - 1] > 0:
                ra.append((na[k] - na[k - 1]) / na[k - 1])
        ra = np.array(ra)
        sh = 0
        if len(ra) > 1 and np.std(ra) > 0:
            sh = np.mean(ra) / np.std(ra) * np.sqrt(12)
        cum = np.cumprod(1 + ra) if len(ra) > 0 else np.array([1])
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak
        mdd = np.min(dd) if len(dd) > 0 else 0

        print(f"  Pool: {len(codes)} stocks, {len(rd)-1} months")
        print(f"  Period: {rd[0] if len(rd) > 1 else rd[0]} ~ {final_date} ({yr:.1f}y)")
        print(f"  CAGR: {cagr*100:.2f}%")
        print(f"  Total Return: {tr*100:.2f}%")
        print(f"  Sharpe: {sh:.2f}")
        print(f"  Max Drawdown: {mdd*100:.2f}%")
        print(f"  Monthly Avg: {np.mean(ra)*100:.2f}%")

        if cagr > 0.12:
            print(f"  Result: PASS (CAGR {cagr*100:.2f}% > 12% target)")
        else:
            print(f"  Result: FAIL (CAGR {cagr*100:.2f}% < 12% target)")
    except Exception as exc:
        print(f"Backtest failed: {exc}")
        import traceback
        traceback.print_exc()


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
    parser = argparse.ArgumentParser(
        description="AKShare Stock Selection System"
    )
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
    p.add_argument("--candidates", type=int, default=0, help="Max candidates to evaluate (0=auto)")
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
    p.add_argument("code", nargs="?", default="", help="Stock code (for kline/fundamentals)")
    p.add_argument("--market", default="A")
    p.set_defaults(func=cmd_fetch)

    # alpha
    p = sub.add_parser("alpha", help="Alpha momentum stock scan")
    p.add_argument("market", default="A", nargs="?", help="Market (A/HK/US)")
    p.add_argument("--top", type=int, default=10, help="Number of results")
    p.add_argument("--candidates", type=int, default=0, help="Max candidates to evaluate (0=auto)")
    p.set_defaults(func=cmd_alpha)

    # backtest
    p = sub.add_parser("backtest", help="Run Alpha Momentum backtest (2018-2026)")
    p.set_defaults(func=cmd_backtest)

    # scheduler
    p = sub.add_parser("scheduler", help="Run scheduled analysis")
    p.add_argument("--run-now", action="store_true")
    p.set_defaults(func=cmd_scheduler)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
