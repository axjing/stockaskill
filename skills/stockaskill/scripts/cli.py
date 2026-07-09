"""CLI argument definitions for the stockaskill system.

Extracted from run.py to reduce its size from ~2800 lines to ~2000.
Each top-level command gets a _add_<name>() function for independent readability.
"""

import argparse
from typing import Callable

_FORMAT_CHOICES = ["json", "md", "both", "none"]


def _common_output_args(parser: argparse.ArgumentParser) -> None:
    """Add --output-dir and --format to any sub-parser."""
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Report output directory",
    )
    parser.add_argument(
        "--format",
        choices=_FORMAT_CHOICES,
        default="both",
        help="Report output format",
    )


# -- Individual command parsers -----------------------------------------------


def _add_route(sub: argparse._SubParsersAction, func: Callable) -> None:
    for command_name in ("route", "recommend"):
        p = sub.add_parser(
            command_name,
            help="Recommend a bounded workflow for a user goal",
        )
        p.add_argument(
            "goal",
            nargs="*",
            help="Natural-language goal, e.g. find opportunities or review a symbol",
        )
        p.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
        p.add_argument("--code", default="", help="Single symbol for analysis flows")
        p.add_argument(
            "--codes",
            default="",
            help="Comma-separated symbol codes for portfolio flows",
        )
        p.add_argument("--top", type=int, default=10, help="Top candidate count")
        p.add_argument(
            "--capital",
            type=float,
            default=1000000,
            help="Portfolio capital used in examples",
        )
        _common_output_args(p)
        p.set_defaults(func=func)


def _add_workflow(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("workflow", help="Manifest-based workflow routines")
    workflow_sub = p.add_subparsers(dest="action", required=True)

    p_list = workflow_sub.add_parser(
        "list",
        help="List available workflow manifests",
    )
    _common_output_args(p_list)
    p_list.set_defaults(func=func)

    p_run = workflow_sub.add_parser(
        "run",
        help="Resolve one workflow manifest into a concrete routine",
    )
    p_run.add_argument("name", help="Workflow manifest name")
    p_run.add_argument("--market", default="A", help="Market (A/HK/US)")
    p_run.add_argument("--code", default="", help="Single symbol code")
    p_run.add_argument("--codes", default="", help="Comma-separated symbol codes")
    p_run.add_argument(
        "--theme",
        nargs="*",
        default=[],
        help="Theme name for theme research routines",
    )
    p_run.add_argument("--top", type=int, default=10)
    p_run.add_argument("--capital", type=float, default=1000000)
    _common_output_args(p_run)
    p_run.set_defaults(func=func)


def _add_scorecard(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("scorecard", help="Build scorecards for research artifacts")
    scorecard_sub = p.add_subparsers(dest="action", required=True)

    p_thesis = scorecard_sub.add_parser(
        "thesis",
        help="Build a scorecard for a saved thesis record",
    )
    p_thesis.add_argument("--thesis-id", default="", help="Saved thesis id")
    p_thesis.add_argument("--code", default="", help="Code for latest thesis")
    p_thesis.add_argument("--market", default="A", help="Market (A/HK/US)")
    _common_output_args(p_thesis)
    p_thesis.set_defaults(func=func)

    p_theme = scorecard_sub.add_parser(
        "theme",
        help="Build a scorecard for a theme research report",
    )
    p_theme.add_argument("theme", nargs="+", help="Theme name")
    p_theme.add_argument("--market", default="A", help="Market (A/HK/US)")
    p_theme.add_argument("--top", type=int, default=3)
    p_theme.add_argument("--candidates", type=int, default=0)
    _common_output_args(p_theme)
    p_theme.set_defaults(func=func)

    p_diagnose = scorecard_sub.add_parser(
        "diagnose",
        help="Build a scorecard for a diagnosis report",
    )
    p_diagnose.add_argument("code", help="Stock code")
    p_diagnose.add_argument("--market", default="A", help="Market (A/HK/US)")
    _common_output_args(p_diagnose)
    p_diagnose.set_defaults(func=func)


def _add_thesis(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("thesis", help="Manage local thesis memory")
    thesis_sub = p.add_subparsers(dest="action", required=True)

    p_capture = thesis_sub.add_parser(
        "capture",
        help="Run diagnosis and persist a thesis record",
    )
    p_capture.add_argument("code", help="Stock code")
    p_capture.add_argument("--market", default="A", help="Market (A/HK/US)")
    p_capture.add_argument(
        "--status",
        default="active",
        choices=["active", "watch", "closed"],
        help="Initial thesis status",
    )
    p_capture.add_argument("--notes", default="", help="Optional thesis note")
    _common_output_args(p_capture)
    p_capture.set_defaults(func=func)

    p_list = thesis_sub.add_parser(
        "list",
        help="List saved thesis records",
    )
    p_list.add_argument("--market", default="", help="Filter by market")
    p_list.add_argument("--code", default="", help="Filter by code")
    p_list.add_argument(
        "--status",
        default="",
        choices=["", "active", "watch", "closed"],
        help="Filter by thesis status",
    )
    p_list.add_argument("--limit", type=int, default=10)
    _common_output_args(p_list)
    p_list.set_defaults(func=func)

    p_review = thesis_sub.add_parser(
        "review",
        help="Review a saved thesis record",
    )
    p_review.add_argument("--thesis-id", default="", help="Saved thesis id")
    p_review.add_argument("--code", default="", help="Code for latest thesis")
    p_review.add_argument("--market", default="A", help="Market (A/HK/US)")
    _common_output_args(p_review)
    p_review.set_defaults(func=func)

    p_postmortem = thesis_sub.add_parser(
        "postmortem",
        help="Attach a postmortem to a saved thesis record",
    )
    p_postmortem.add_argument("--thesis-id", default="", help="Saved thesis id")
    p_postmortem.add_argument("--code", default="", help="Code for latest thesis")
    p_postmortem.add_argument("--market", default="A", help="Market (A/HK/US)")
    p_postmortem.add_argument(
        "--outcome",
        required=True,
        choices=["win", "loss", "neutral"],
        help="Outcome classification",
    )
    p_postmortem.add_argument("--notes", default="", help="Review notes")
    p_postmortem.add_argument(
        "--status",
        default="closed",
        choices=["watch", "closed"],
        help="Final thesis status",
    )
    _common_output_args(p_postmortem)
    p_postmortem.set_defaults(func=func)


def _add_theme_scan(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("theme-scan", help="Run local-first theme research")
    p.add_argument("theme", nargs="+", help="Theme name, e.g. AI基础设施 or 机器人")
    p.add_argument("--market", default="A", help="Market (A/HK/US)")
    p.add_argument("--top", type=int, default=3, help="Top layers/candidates to print")
    p.add_argument(
        "--candidates",
        type=int,
        default=0,
        help="Max pool candidates to inspect before theme mapping (0=auto)",
    )
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_analyze(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("analyze", help="Analyze a single stock")
    p.add_argument("code", help="Stock code")
    p.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_diagnose(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("diagnose", help="Deep stock diagnosis")
    p.add_argument("code", help="Stock code")
    p.add_argument("--market", default="A", help="Market (A/HK/US)")
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_deep_diagnose(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("deep-diagnose", help="Long-form stock deep diagnosis")
    p.add_argument("code", help="Stock code")
    p.add_argument("--market", default="A", help="Market (A/HK/US)")
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_scan(sub: argparse._SubParsersAction, func: Callable) -> None:
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
        choices=["auto", "snapshot", "realtime"],
        default="auto",
        help=(
            "Auto prefers a fresh full-market snapshot and falls back to bounded "
            "realtime candidate scoring when needed."
        ),
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
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_refresh_scan(sub: argparse._SubParsersAction, func: Callable) -> None:
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
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_portfolio(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("portfolio", help="Build investment portfolio")
    p.add_argument("--codes", required=True, help="Comma-separated stock codes")
    p.add_argument("--capital", type=float, default=1000000)
    p.add_argument("--market", default="A")
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_market_regime(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("market-regime", help="Analyze current market posture")
    p.add_argument(
        "market",
        nargs="?",
        default="A",
        choices=["A", "HK", "US"],
        help="Market to analyze (positional or --market)",
    )
    p.add_argument(
        "--market",
        dest="market_flag",
        default=None,
        choices=["A", "HK", "US"],
        help="Market to analyze (named alternative)",
    )
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_fetch(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("fetch", help="Refresh data")
    p.add_argument("type", choices=["pool", "kline", "fundamentals"])
    p.add_argument(
        "code", nargs="?", default="", help="Stock code (for kline/fundamentals)"
    )
    p.add_argument("--market", default="A")
    p.set_defaults(func=func)


def _add_sync(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("sync", help="Synchronize bounded local data")
    sync_sub = p.add_subparsers(dest="type", required=True)

    def _sync_common(parser: argparse.ArgumentParser) -> None:
        _common_output_args(parser)

    p_symbol = sync_sub.add_parser("symbol", help="Synchronize one symbol")
    p_symbol.add_argument("code", help="Symbol code")
    p_symbol.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    p_symbol.add_argument("--days", type=int, default=365, help="Target history days")
    p_symbol.add_argument(
        "--skip-fundamentals",
        action="store_true",
        help="Skip fundamentals sync for this symbol.",
    )
    p_symbol.add_argument(
        "--full-history",
        action="store_true",
        help="Attempt to fetch the symbol's full available history.",
    )
    _sync_common(p_symbol)
    p_symbol.set_defaults(func=func)

    p_watchlist = sync_sub.add_parser(
        "watchlist",
        help="Synchronize configured watchlist",
    )
    p_watchlist.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    p_watchlist.add_argument("--days", type=int, default=365, help="Target history days")
    p_watchlist.add_argument(
        "--skip-fundamentals",
        action="store_true",
        help="Skip fundamentals sync for this scope.",
    )
    p_watchlist.add_argument("--full-history", action="store_true")
    _sync_common(p_watchlist)
    p_watchlist.set_defaults(func=func)

    p_portfolio = sync_sub.add_parser(
        "portfolio",
        help="Synchronize a portfolio code list",
    )
    p_portfolio.add_argument("--codes", required=True, help="Comma-separated symbol codes")
    p_portfolio.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    p_portfolio.add_argument("--days", type=int, default=365, help="Target history days")
    p_portfolio.add_argument(
        "--skip-fundamentals",
        action="store_true",
        help="Skip fundamentals sync for this scope.",
    )
    p_portfolio.add_argument("--full-history", action="store_true")
    _sync_common(p_portfolio)
    p_portfolio.set_defaults(func=func)

    p_etf = sync_sub.add_parser(
        "etf",
        help="Synchronize a bounded ETF code list",
    )
    p_etf.add_argument("--codes", required=True, help="Comma-separated ETF codes")
    p_etf.add_argument("--days", type=int, default=365, help="Target history days")
    p_etf.add_argument(
        "--skip-fundamentals",
        action="store_true",
        help="Skip fundamentals sync (ETF only has NAV).",
    )
    p_etf.add_argument("--full-history", action="store_true")
    _sync_common(p_etf)
    p_etf.set_defaults(func=func)

    p_scan = sync_sub.add_parser(
        "scan-universe",
        help="Synchronize a bounded candidate universe for scanning",
    )
    p_scan.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    p_scan.add_argument("--limit", type=int, default=200, help="Max candidate symbols")
    p_scan.add_argument("--days", type=int, default=365, help="Target history days")
    p_scan.add_argument(
        "--skip-fundamentals",
        action="store_true",
        help="Skip fundamentals sync for this scope.",
    )
    p_scan.add_argument("--full-history", action="store_true")
    _sync_common(p_scan)
    p_scan.set_defaults(func=func)


def _add_status(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("status", help="Show data sync status")
    status_sub = p.add_subparsers(dest="status_command", required=True)
    p_data = status_sub.add_parser(
        "data",
        help="Show bounded sync-state diagnostics",
    )
    data_sub = p_data.add_subparsers(dest="type", required=True)

    p_symbol = data_sub.add_parser("symbol", help="Show symbol sync state")
    p_symbol.add_argument("code", help="Symbol code")
    p_symbol.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    p_symbol.set_defaults(func=func)

    p_watchlist = data_sub.add_parser(
        "watchlist",
        help="Show watchlist sync state",
    )
    p_watchlist.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    p_watchlist.set_defaults(func=func)

    p_portfolio = data_sub.add_parser(
        "portfolio",
        help="Show portfolio sync state",
    )
    p_portfolio.add_argument("--codes", required=True, help="Comma-separated symbol codes")
    p_portfolio.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    p_portfolio.set_defaults(func=func)

    p_etf = data_sub.add_parser(
        "etf",
        help="Show ETF sync state",
    )
    p_etf.add_argument("--codes", required=True, help="Comma-separated ETF codes")
    p_etf.set_defaults(func=func)

    p_scan = data_sub.add_parser(
        "scan-universe",
        help="Show scan-universe sync state",
    )
    p_scan.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    p_scan.add_argument("--limit", type=int, default=200, help="Candidate scope size used during sync.")
    p_scan.set_defaults(func=func)

    p_pool = data_sub.add_parser(
        "pool",
        help="Show pool metadata and refresh state",
    )
    p_pool.add_argument("--market", default="A", help="Market (A/HK/US/FUND)")
    p_pool.set_defaults(func=func)


def _add_alpha(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("alpha", help="Alpha momentum stock scan")
    p.add_argument("market", default="A", nargs="?", help="Market (A/HK/US)")
    p.add_argument("--top", type=int, default=10, help="Number of results")
    p.add_argument(
        "--candidates",
        type=int,
        default=0,
        help="Max candidates to evaluate (0=auto)",
    )
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_backtest(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("backtest", help="Run Alpha Momentum backtest (2018-2026)")
    _common_output_args(p)
    p.add_argument(
        "--market",
        default="A",
        choices=["A", "HK", "US"],
        help="Market to backtest",
    )
    p.set_defaults(func=func)


def _add_backtest_enhanced(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser(
        "backtest-enhanced", help="Run Enhanced Core-Satellite backtest (2018-2026)"
    )
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_portfolio_enhanced(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser(
        "portfolio-enhanced", help="ETF(3)+Alpha Momentum Top3 = 6 positions"
    )
    p.add_argument("--capital", type=float, default=1000000)
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_scheduler(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("scheduler", help="Run scheduled analysis")
    p.add_argument("--run-now", action="store_true")
    p.set_defaults(func=func)


def _add_cache(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("cache", help="Cache management")
    cache_sub = p.add_subparsers(dest="action", required=True)
    p_stats = cache_sub.add_parser("stats", help="Show cache statistics")
    p_stats.set_defaults(func=func)
    p_clean = cache_sub.add_parser("cleanup", help="Clean old cache entries")
    p_clean.add_argument("--days", type=int, default=30, help="Max age in days")
    p_clean.set_defaults(func=func)


def _add_risk_alert(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("risk-alert", help="Show market risk alert and suggestions")
    p.add_argument(
        "--market",
        default="A",
        choices=["A", "HK", "US"],
        help="Market to check (default: A)",
    )
    _common_output_args(p)
    p.set_defaults(func=func)


def _add_track(sub: argparse._SubParsersAction, func: Callable) -> None:
    p = sub.add_parser("track", help="Portfolio stop-loss/take-profit tracking")
    track_sub = p.add_subparsers(dest="action", required=True)

    p_start = track_sub.add_parser("start", help="Start tracking a position")
    p_start.add_argument("code", help="Stock code")
    p_start.add_argument("--market", default="A", help="Market (A/HK/US)")
    p_start.add_argument("--price", type=float, required=True, help="Entry price")
    p_start.add_argument("--stop-loss", type=float, default=0.15, help="Stop-loss pct (default 15%%)")
    p_start.add_argument("--take-profit", type=float, default=0.30, help="Take-profit pct (default 30%%)")
    p_start.add_argument("--notes", default="", help="Notes")
    _common_output_args(p_start)
    p_start.set_defaults(func=func)

    p_status = track_sub.add_parser("status", help="List tracked positions")
    p_status.add_argument("--status", default="active", choices=["active", "closed", "all"])
    p_status.add_argument("--market", default="A")
    _common_output_args(p_status)
    p_status.set_defaults(func=func)

    p_check = track_sub.add_parser("check", help="Check for stop-loss/take-profit triggers")
    p_check.add_argument("--market", default="A")
    p_check.add_argument("--days", type=int, default=5, help="Days of kline to check")
    _common_output_args(p_check)
    p_check.set_defaults(func=func)

    p_close = track_sub.add_parser("close", help="Close a tracked position")
    p_close.add_argument("tracking_id", help="Tracking ID")
    p_close.add_argument("--price", type=float, default=0, help="Exit price")
    p_close.add_argument("--notes", default="", help="Exit notes")
    _common_output_args(p_close)
    p_close.set_defaults(func=func)


# -- Entry point ---------------------------------------------------------------


def build_parser(
    cmd_route,
    cmd_workflow,
    cmd_scorecard,
    cmd_thesis,
    cmd_theme_scan,
    cmd_analyze,
    cmd_diagnose,
    cmd_deep_diagnose,
    cmd_scan,
    cmd_refresh_scan,
    cmd_portfolio,
    cmd_market_regime,
    cmd_risk_alert,
    cmd_fetch,
    cmd_sync,
    cmd_status,
    cmd_alpha,
    cmd_backtest,
    cmd_backtest_enhanced,
    cmd_portfolio_enhanced,
    cmd_scheduler,
    cmd_cache,
    cmd_track,
) -> argparse.ArgumentParser:
    """Build and return the root ArgumentParser.

    Handlers are passed in to keep cli.py independent of the business logic
    in run.py — this avoids circular imports.
    """
    parser = argparse.ArgumentParser(description="AKShare Stock Selection System")
    sub = parser.add_subparsers(dest="command", required=True)

    _add_route(sub, cmd_route)
    _add_workflow(sub, cmd_workflow)
    _add_scorecard(sub, cmd_scorecard)
    _add_thesis(sub, cmd_thesis)
    _add_theme_scan(sub, cmd_theme_scan)
    _add_analyze(sub, cmd_analyze)
    _add_diagnose(sub, cmd_diagnose)
    _add_deep_diagnose(sub, cmd_deep_diagnose)
    _add_scan(sub, cmd_scan)
    _add_refresh_scan(sub, cmd_refresh_scan)
    _add_portfolio(sub, cmd_portfolio)
    _add_market_regime(sub, cmd_market_regime)
    _add_fetch(sub, cmd_fetch)
    _add_sync(sub, cmd_sync)
    _add_status(sub, cmd_status)
    _add_alpha(sub, cmd_alpha)
    _add_backtest(sub, cmd_backtest)
    _add_backtest_enhanced(sub, cmd_backtest_enhanced)
    _add_portfolio_enhanced(sub, cmd_portfolio_enhanced)
    _add_scheduler(sub, cmd_scheduler)
    _add_cache(sub, cmd_cache)
    _add_risk_alert(sub, cmd_risk_alert)
    _add_track(sub, cmd_track)

    return parser
