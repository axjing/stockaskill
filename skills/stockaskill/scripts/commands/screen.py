"""CLI command handler for vectorized stock screening."""

import argparse
from typing import Any, Dict

from advisor.screener_duckdb import DuckDBScreener

from commands._common import _cmd_output, _save_report


def cmd_screen(args: argparse.Namespace) -> None:
    """Run vectorized stock screening on DuckDB."""
    output_dir, fmt = _cmd_output(args)
    market = getattr(args, "market", "A") or "A"
    preset = getattr(args, "preset", "momentum_enhanced")
    top_n = getattr(args, "top", 10) or 10
    min_mcap = getattr(args, "min_mcap", 0.0) or 0.0
    sector = getattr(args, "sector", None)

    print(
        f"Screening {market} market via DuckDB (preset={preset}, top={top_n})...",
        flush=True,
    )
    screener = DuckDBScreener()
    results = screener.screen(
        market=market,
        preset=preset,
        top_n=top_n,
        min_mcap=min_mcap,
        sector=sector,
    )

    print(f"Found {len(results)} ranked candidates:")
    for idx, item in enumerate(results, start=1):
        metrics_parts = [f"{k}={v}" for k, v in item.get("metrics", {}).items()]
        metrics_str = ", ".join(metrics_parts)
        print(
            f"  {idx}. {item['code']} {item.get('name', '')} | "
            f"Score: {item['score']} | {metrics_str}"
        )

    data: Dict[str, Any] = {
        "market": market,
        "preset": preset,
        "top_n": top_n,
        "count": len(results),
        "candidates": results,
    }
    _save_report(
        f"screen_{preset}_{market}",
        fmt,
        output_dir,
        data=data,
        metadata={"command": "screen"},
    )
