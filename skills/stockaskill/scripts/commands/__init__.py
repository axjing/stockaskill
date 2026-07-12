"""CLI command handlers — split from monolithic run.py.

Each submodule implements one or more cmd_* handlers. All are re-exported
here so that cli.py and run.py can import them with
`from commands import cmd_scan, cmd_sync, ...` — zero API change.
"""

from commands.analyze import cmd_analyze, cmd_deep_diagnose, cmd_diagnose
from commands.backtest import cmd_backtest, cmd_backtest_enhanced
from commands.market_regime import cmd_market_regime, cmd_risk_alert
from commands.portfolio import cmd_portfolio, cmd_portfolio_enhanced
from commands.route import cmd_route, cmd_workflow
from commands.scan import cmd_alpha, cmd_refresh_scan, cmd_scan
from commands.scheduler import cmd_cache, cmd_scheduler, cmd_track
from commands.scorecard import cmd_scorecard
from commands.sync import cmd_fetch, cmd_status, cmd_sync
from commands.theme import cmd_theme_scan
from commands.thesis import cmd_thesis

__all__ = [
    # Route/workflow
    "cmd_route",
    "cmd_workflow",
    # Scorecard/thesis
    "cmd_scorecard",
    "cmd_thesis",
    # Theme
    "cmd_theme_scan",
    # Analyze/diagnose
    "cmd_analyze",
    "cmd_diagnose",
    "cmd_deep_diagnose",
    # Scan
    "cmd_scan",
    "cmd_refresh_scan",
    "cmd_alpha",
    # Portfolio
    "cmd_portfolio",
    "cmd_portfolio_enhanced",
    # Sync
    "cmd_fetch",
    "cmd_sync",
    "cmd_status",
    # Backtest
    "cmd_backtest",
    "cmd_backtest_enhanced",
    # Market regime
    "cmd_market_regime",
    "cmd_risk_alert",
    # Scheduler
    "cmd_scheduler",
    "cmd_cache",
    "cmd_track",
]
