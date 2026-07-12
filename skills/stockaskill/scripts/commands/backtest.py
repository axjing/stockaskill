"""CLI command handlers for backtest functionality."""

import argparse
import sys

from config import get as cfg_get
from report_generator import format_backtest_summary

from commands._common import _cmd_output, _save_report


def cmd_backtest(args: argparse.Namespace) -> None:
    """Run Alpha Momentum backtest (2018-2026)."""
    output_dir, fmt = _cmd_output(args)
    market = getattr(args, "market", "A") or "A"
    print(f"Running Alpha Momentum backtest ({market})...")
    try:
        from portfolio.backtest_engine import AlphaMomentumBacktest

        engine = AlphaMomentumBacktest(
            capital=cfg_get("backtest_capital", 1_000_000),
            low_vol_min=cfg_get("low_vol_min", 0.4),
            top_k=cfg_get("alpha_momentum.top_k", 6),
            max_per_board=cfg_get("alpha_momentum.max_per_board", 3),
            market=market,
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
            print(f"  Result: ## PASS (CAGR {cagr_val * 100:.2f}% > 12% target)")
        else:
            print(f"  Result: !! FAIL (CAGR {cagr_val * 100:.2f}% < 12% target)")

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
        print(f"Backtest failed: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()



def cmd_backtest_enhanced(args: argparse.Namespace) -> None:
    """Run Enhanced Core-Satellite backtest (2018-2026)."""
    output_dir, fmt = _cmd_output(args)
    print("Running Enhanced Core-Satellite backtest...")
    try:
        import importlib

        bt = importlib.import_module("backtest_enhanced")
        result = bt.run_backtest()
        print(
            f"\n  Result: CAGR={result.get('cagr', 0) * 100:.2f}%, "
            f"Sharpe={result.get('sharpe', 0):.2f}, "
            f"MaxDD={result.get('max_drawdown', 0) * 100:.2f}%"
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
        print(f"Enhanced backtest failed: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()



