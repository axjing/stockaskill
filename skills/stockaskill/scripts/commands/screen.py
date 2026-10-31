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
    to_portfolio = bool(getattr(args, "to_portfolio", False))
    capital = float(getattr(args, "capital", 1000000.0) or 1000000.0)
    track = bool(getattr(args, "track", False))
    is_json = bool(
        getattr(args, "json", False) or getattr(args, "format", "") == "json"
    )

    if not is_json:
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

    if not is_json:
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

    if to_portfolio and results:
        if not is_json:
            print(
                f"\n--- Constructing Execution Portfolio (Capital: {capital:,.0f}) ---",
                flush=True,
            )
        from portfolio.builder import PortfolioBuilder

        builder = PortfolioBuilder("Screened Portfolio", capital=capital)
        for item in results:
            builder.add_candidate(
                code=item["code"],
                name=item.get("name", item["code"]),
                market=market,
                score=float(item.get("score", 60.0)),
                current_price=float(item.get("current_price", 0.0)),
            )
        portfolio = builder.build(position_method="fixed")
        if not is_json:
            print(portfolio.summary())

        tickets = portfolio.trade_ticket()
        for t in tickets:
            if not is_json:
                print(
                    f"    -> BUY {t['code']} {t['name']}: {t['shares']} shares "
                    f"@ {t['price']:.2f} (Amount: {t['amount']:,.0f}, "
                    f"Fee: {t['est_fee']:.1f})"
                )
            if track:
                from tracker import start_tracking

                tr = start_tracking(
                    t["code"],
                    market=market,
                    entry_price=t["price"],
                    notes=f"Auto-tracked from screen preset {preset}",
                )
                t["tracking_id"] = tr.get("tracking_id")

        data["portfolio"] = {
            "name": portfolio.name,
            "capital": portfolio.capital,
            "positions_count": len(portfolio.positions),
        }
        data["trade_tickets"] = tickets
        if track and not is_json:
            print(f"\n  Auto-registered {len(tickets)} positions into active tracking.")

    _save_report(
        f"screen_{preset}_{market}",
        fmt,
        output_dir,
        data=data,
        metadata={"command": "screen"},
    )
