"""CLI command handlers for portfolio functionality."""

import argparse
import sys

from market_regime import summarize_market_regime
from report_generator import format_portfolio_summary

from commands._common import (
    _cmd_error,
    _cmd_output,
    _safe_market_regime,
    _save_report,
)


def cmd_portfolio(args: argparse.Namespace) -> None:
    """Build an investment portfolio."""
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    capital = args.capital or 1000000
    market = getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)

    print(f"Building portfolio with {len(codes)} stocks, capital={capital:,.0f}")
    regime = _safe_market_regime(market)
    print("  " + summarize_market_regime(regime))
    try:
        from data_engine import sync_portfolio_data
        from portfolio.builder import PortfolioBuilder

        # Phase 1: sync only missing data
        print(f"  Syncing {len(codes)} symbols...")
        sync_result = sync_portfolio_data(codes, market=market, history_days=365)
        print(
            f"  Sync done: {sync_result['ready']}/{sync_result['requested']} ready, "
            f"cache_hits={sync_result['cache_hits']}"
        )

        # Phase 2: all analysis reads cache only
        builder = PortfolioBuilder("My Portfolio", capital=capital)
        for c in codes:
            builder.add_from_strategy(c, market, cached_only=True)
        portfolio = builder.build(
            capital_fraction=float(regime.get("risk_budget", 1.0) or 1.0)
        )
        print(portfolio.summary())

        positions_data = []
        for p in portfolio.positions:
            positions_data.append(
                {
                    "code": p.code,
                    "name": p.name,
                    "weight": p.weight,
                    "shares": p.shares,
                    "cost": p.cost,
                }
            )
        port_data = {
            "name": portfolio.name,
            "capital": capital,
            "market": market,
            "regime": regime,
            "positions": positions_data,
            "metrics": portfolio.metrics,
        }
        md = format_portfolio_summary(
            portfolio.name,
            capital,
            positions_data,
            portfolio.metrics,
            regime=regime,
        )
        _save_report(
            f"portfolio_{market}",
            fmt,
            output_dir,
            data=port_data,
            md=md,
            metadata={"command": "portfolio", "market": market},
        )
    except Exception as exc:
        print(f"Portfolio build failed: {exc}", file=sys.stderr)



def cmd_portfolio_enhanced(args: argparse.Namespace) -> None:
    """Build ETF(3) + Alpha Momentum Top3 = 6 positions portfolio."""
    capital = args.capital or 1000000
    output_dir, fmt = _cmd_output(args)
    print(f"Building Enhanced Core-Satellite portfolio, capital={capital:,.0f}")
    regime = _safe_market_regime("A")
    print("  " + summarize_market_regime(regime))
    try:
        from data_engine import get_stock_pool, sync_portfolio_data
        from portfolio.builder import PortfolioBuilder
        from strategies.momentum_enhanced import MomentumEnhancedStrategy

        strat = MomentumEnhancedStrategy()
        pool = get_stock_pool("A")
        candidates = pool[:200]

        # Phase 1: sync only missing data for candidates + ETFs
        etf_codes = [e["code"] for e in MomentumEnhancedStrategy.get_etf_allocation()]
        codes_to_sync = [c["code"] for c in candidates] + etf_codes
        print(f"  Syncing {len(codes_to_sync)} symbols (pool + ETFs)...")
        sync_result = sync_portfolio_data(codes_to_sync, market="A", history_days=365)
        print(
            f"  Sync done: {sync_result['ready']}/{sync_result['requested']} ready, "
            f"cache_hits={sync_result['cache_hits']}, "
            f"history_fetched={sync_result['history_fetched_count']}, "
            f"fundamentals_fetched={sync_result['fundamentals_fetched_count']}"
        )

        # Phase 2: all analysis reads cache only
        selected = strat.select_top_stocks(candidates, max_picks=3, cached_only=True)

        etfs = MomentumEnhancedStrategy.get_etf_allocation()
        codes = [e["code"] for e in etfs] + selected
        print(f"  ETFs (core): {[e['code'] for e in etfs]}")
        print(f"  Stocks (satellite): {selected}")

        builder = PortfolioBuilder("Core-Satellite", capital=capital)
        for code in codes:
            builder.add_from_strategy(code, "A", cached_only=True)
        portfolio = builder.build(
            capital_fraction=float(regime.get("risk_budget", 1.0) or 1.0)
        )
        print(portfolio.summary())

        positions_data = []
        for p in portfolio.positions:
            positions_data.append(
                {
                    "code": p.code,
                    "name": p.name,
                    "weight": p.weight,
                    "shares": p.shares,
                    "cost": p.cost,
                }
            )
        port_data = {
            "name": "Core-Satellite",
            "capital": capital,
            "regime": regime,
            "etfs": [e["code"] for e in etfs],
            "stocks": selected,
            "positions": positions_data,
            "metrics": portfolio.metrics,
        }
        md = format_portfolio_summary(
            "Core-Satellite",
            capital,
            positions_data,
            portfolio.metrics,
            regime=regime,
        )
        _save_report(
            "portfolio_enhanced",
            fmt,
            output_dir,
            data=port_data,
            md=md,
            metadata={"command": "portfolio-enhanced"},
        )
    except Exception as exc:
        _cmd_error(f"Enhanced portfolio build failed: {exc}")



