"""Unified CLI entry point for the stockaskill stock selection system.

Provides commands for stock analysis, diagnosis, market scanning, portfolio
building, backtesting, and data synchronization. All commands follow a
local-first pattern: sync missing data, then read from cache.

Usage:
    python stockaskill/scripts/run.py diagnose 600519 --market A
    python stockaskill/scripts/run.py scan A --top 20
    python stockaskill/scripts/run.py sync symbol 600519 --market A --days 365
"""

# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "akshare>=1.10.0",
#     "pandas>=2.0.0",
#     "numpy>=1.24.0",
#     "scipy>=1.10.0",
# ]
# ///

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

_DEFAULT_BADGE = "--"
_MIN_PYTHON = (3, 10)


def _require_supported_python() -> None:
    """Exit early with a clear message on unsupported Python versions."""
    if sys.version_info >= _MIN_PYTHON:
        return
    required = ".".join(str(part) for part in _MIN_PYTHON)
    current = ".".join(str(part) for part in sys.version_info[:3])
    print(
        f"stockaskill requires Python >= {required}; current interpreter is {current}.",
        file=sys.stderr,
    )
    print(
        "Use a Python 3.10+ environment or run via 'uv run"
        " python stockaskill/scripts/run.py ...'.",
        file=sys.stderr,
    )
    raise SystemExit(1)


_require_supported_python()

# Import all command handlers from the commands package.
# The commands package re-exports all cmd_* functions for backward compatibility.
from cli import build_parser  # noqa: E402
from commands import (  # noqa: E402
    cmd_alpha,
    cmd_analyze,
    cmd_backtest,
    cmd_backtest_enhanced,
    cmd_cache,
    cmd_deep_diagnose,
    cmd_diagnose,
    cmd_fetch,
    cmd_market_regime,
    cmd_portfolio,
    cmd_portfolio_enhanced,
    cmd_refresh_scan,
    cmd_risk_alert,
    cmd_route,
    cmd_scan,
    cmd_scheduler,
    cmd_scorecard,
    cmd_status,
    cmd_sync,
    cmd_theme_scan,
    cmd_thesis,
    cmd_track,
    cmd_workflow,
)


def main() -> None:
    """Run the CLI argument parser and dispatch to the appropriate handler."""
    parser = build_parser(
        cmd_route=cmd_route,
        cmd_workflow=cmd_workflow,
        cmd_scorecard=cmd_scorecard,
        cmd_thesis=cmd_thesis,
        cmd_theme_scan=cmd_theme_scan,
        cmd_analyze=cmd_analyze,
        cmd_diagnose=cmd_diagnose,
        cmd_deep_diagnose=cmd_deep_diagnose,
        cmd_scan=cmd_scan,
        cmd_refresh_scan=cmd_refresh_scan,
        cmd_portfolio=cmd_portfolio,
        cmd_market_regime=cmd_market_regime,
        cmd_risk_alert=cmd_risk_alert,
        cmd_fetch=cmd_fetch,
        cmd_sync=cmd_sync,
        cmd_status=cmd_status,
        cmd_alpha=cmd_alpha,
        cmd_backtest=cmd_backtest,
        cmd_backtest_enhanced=cmd_backtest_enhanced,
        cmd_portfolio_enhanced=cmd_portfolio_enhanced,
        cmd_scheduler=cmd_scheduler,
        cmd_cache=cmd_cache,
        cmd_track=cmd_track,
    )
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
