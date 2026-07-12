"""Shared constants, helpers, and imports for CLI command handlers."""

import argparse
import sys
from typing import Optional

from config import load_config

load_config()

_DEFAULT_BADGE = "--"
_MIN_PYTHON = (3, 10)
_SCORE_BADGES = [(65, "##"), (35, "==")]


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


from data_engine import (  # noqa: E402
    get_etf_pool,
    get_stock_pool,
    is_api_limit_exhausted,
)
from market_regime import analyze_market_regime  # noqa: E402
from report_generator import save_markdown, save_report  # noqa: E402


def _print_api_usage() -> None:
    """Print which upstream APIs are currently rate-limited."""
    if is_api_limit_exhausted():
        print(
            "[INFO] One or more upstream APIs are rate-limited today. "
            "Data shown is from cache. Retry after the rate limit window passes.",
            flush=True,
        )


def _badge(score: float) -> str:
    """Return a compact badge for a numeric score."""
    for threshold, b in _SCORE_BADGES:
        if score >= threshold:
            return b
    return _DEFAULT_BADGE


def _cmd_output(args: argparse.Namespace) -> tuple:
    """Extract common output args from any cmd_* handler.

    Returns (output_dir, fmt).
    """
    return (
        getattr(args, "output_dir", "reports"),
        getattr(args, "format", "both"),
    )


def _cmd_error(msg: str, show_traceback: bool = False) -> None:
    """Print error to stderr, optionally with traceback."""
    print(msg, file=sys.stderr)
    if show_traceback:
        import traceback

        traceback.print_exc(file=sys.stderr)


def _save_report(
    name: str,
    fmt: str,
    output_dir: str,
    data: Optional[dict] = None,
    md: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Save report in requested formats."""
    if fmt == "none":
        return
    if fmt in ("json", "both") and data is not None:
        save_report(data, name, output_dir=output_dir, metadata=metadata)
    if fmt in ("md", "both") and md is not None:
        save_markdown(md, name, output_dir=output_dir)


def _print_pool_summary(market: str) -> None:
    """Print a concise summary of a refreshed pool."""
    if market == "FUND":
        pool = get_etf_pool()
    else:
        pool = get_stock_pool(market)
    if not pool:
        print(f"  {market}: 0 entries (no data)")
        return
    total = len(pool)
    labels = sorted(r.get("updated_at", "") for r in pool if r.get("updated_at"))
    updated_at = labels[-1] if labels else "?"
    name = {
        "A": "A 股",
        "HK": "港股",
        "US": "美股",
        "FUND": "ETF",
    }.get(market, market)
    parts = [f"{total} 只"]
    if market != "FUND":
        dates = sorted(
            str(r.get("list_date", "")).strip()
            for r in pool
            if str(r.get("list_date", "")).strip()
        )
        if dates:
            parts.append(f"最早={dates[0]}, 最晚={dates[-1]}")
    print(f"  {name}: {', '.join(parts)} (updated={updated_at})")


def _safe_market_regime(market: str) -> dict:
    """Return a best-effort market regime analysis."""
    try:
        return analyze_market_regime(market)
    except Exception as exc:
        return {
            "market": market,
            "status": "error",
            "score": 50.0,
            "posture": "neutral",
            "posture_label": "中性",
            "risk_budget": 1.0,
            "new_positions_allowed": True,
            "reasons": [f"market_regime_error: {exc}"],
            "breadth": {},
            "technical": {},
        }
