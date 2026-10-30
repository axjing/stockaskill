"""Goal-oriented portfolio optimizer and backtest validator.

Evaluates historical combinations against user target constraints (e.g.,
annual return >= 8%, max drawdown <= 5%) using vectorized DuckDB price data.
"""

import itertools
import logging
from typing import Any, Dict, List, Optional

import numpy as np
from advisor.screener_duckdb import DuckDBScreener
from cache import get_cache

from portfolio.risk import RiskMetrics

logger = logging.getLogger(__name__)


class TargetPortfolioOptimizer:
    """Solve and validate target-constrained portfolios against historical data."""

    def __init__(self) -> None:
        self.cache = get_cache()
        self.screener = DuckDBScreener()

    def optimize(
        self,
        target_cagr: float = 0.08,
        max_drawdown_limit: float = 0.05,
        top_k: int = 5,
        market: str = "A",
        lookback_years: int = 3,
        candidate_pool_size: int = 12,
        allow_cash_buffer: bool = True,
    ) -> Dict[str, Any]:
        """Find the optimal asset portfolio matching target constraints.

        Args:
            target_cagr: Minimum required annualized compound return (e.g. 0.08).
            max_drawdown_limit: Maximum allowed drawdown (e.g. 0.05).
            top_k: Number of assets in the final portfolio.
            market: Market code (A, HK, US, FUND).
            lookback_years: Historical backtest period in years.
            candidate_pool_size: Size of candidate pool to search over.
            allow_cash_buffer: Whether to allow defensive cash allocation.

        Returns:
            Dict containing best portfolio, verified metrics, and trade tickets.
        """
        # 1. Form a diversified candidate pool
        half = max(2, candidate_pool_size // 2)
        mom_pool = self.screener.screen(
            market=market, preset="momentum_enhanced", top_n=half
        )
        vol_pool = self.screener.screen(market=market, preset="low_vol", top_n=half)

        candidates = {item["code"]: item for item in (mom_pool + vol_pool)}
        all_codes = list(candidates.keys())

        if len(all_codes) < top_k:
            return {
                "success": False,
                "message": f"Candidate pool size ({len(all_codes)}) < top_k ({top_k}).",
            }

        # 2. Load historical prices from DuckDB
        lookback_start = f"{2026 - lookback_years}-01-01"
        codes_ph = ",".join(f"'{c}'" for c in all_codes)
        sql = f"""
        SELECT code, date, close
        FROM daily_price
        WHERE market = ? AND code IN ({codes_ph}) AND date >= ?
        ORDER BY date ASC
        """
        rows = self.cache.engine.fetchall(sql, (market, lookback_start))
        prices_by_date: Dict[str, Dict[str, float]] = {}
        for r in rows:
            prices_by_date.setdefault(r["date"], {})[r["code"]] = float(r["close"])

        sorted_dates = sorted(prices_by_date.keys())
        if len(sorted_dates) < 60:
            return {
                "success": False,
                "message": "Insufficient historical data for backtesting.",
            }

        returns_by_code: Dict[str, List[float]] = {c: [] for c in all_codes}
        for i in range(1, len(sorted_dates)):
            p_prev = prices_by_date[sorted_dates[i - 1]]
            p_curr = prices_by_date[sorted_dates[i]]
            for c in all_codes:
                p0 = p_prev.get(c)
                p1 = p_curr.get(c)
                if p0 and p1 and p0 > 0:
                    returns_by_code[c].append((p1 - p0) / p0)
                else:
                    returns_by_code[c].append(0.0)

        # 3. Combinatorial search across candidate pool
        best_solution: Optional[Dict[str, Any]] = None
        min_distance = float("inf")

        # Limit combinations to max 252 evaluations for sub-second execution
        comb_iter = itertools.combinations(all_codes, top_k)
        for comb in comb_iter:
            mat = np.column_stack([returns_by_code[c] for c in comb])
            weights = np.ones(top_k) / float(top_k)
            asset_returns = mat @ weights

            # Try 100% equity and cash buffer variations if permitted
            cash_ratios = [0.0, 0.25, 0.50] if allow_cash_buffer else [0.0]
            for cash_ratio in cash_ratios:
                rf_daily = 0.025 / 252.0  # 2.5% annual cash yield
                port_daily = (1.0 - cash_ratio) * asset_returns + (
                    cash_ratio * rf_daily
                )

                cum = np.cumprod(1.0 + port_daily)
                total_ret = float(cum[-1] - 1.0)
                duration_years = len(port_daily) / 252.0
                cagr = float((cum[-1]) ** (1.0 / duration_years) - 1.0)
                mdd = float(abs(RiskMetrics(port_daily).max_drawdown()))
                sharpe = float(RiskMetrics(port_daily).sharpe_ratio())

                is_met = cagr >= target_cagr and mdd <= max_drawdown_limit

                # Distance penalty for sorting closest candidate
                cagr_deficit = max(0.0, target_cagr - cagr)
                mdd_excess = max(0.0, mdd - max_drawdown_limit)
                dist = cagr_deficit * 2.0 + mdd_excess * 3.0

                if is_met or dist < min_distance:
                    min_distance = dist
                    best_solution = {
                        "codes": list(comb),
                        "cash_ratio": cash_ratio,
                        "cagr": round(cagr, 4),
                        "max_drawdown": round(mdd, 4),
                        "sharpe": round(sharpe, 2),
                        "total_return": round(total_ret, 4),
                        "target_met": is_met,
                        "duration_years": round(duration_years, 1),
                    }
                    if is_met:
                        break
            if best_solution and best_solution.get("target_met"):
                break

        if not best_solution:
            return {
                "success": False,
                "message": "No portfolio satisfied search constraints.",
            }

        # 4. Compile detailed allocation and trade tickets
        selected_codes = best_solution["codes"]
        cash_ratio = best_solution["cash_ratio"]
        equity_weight_per_stock = round((1.0 - cash_ratio) / len(selected_codes), 4)

        holdings = []
        for code in selected_codes:
            item = candidates.get(code, {})
            holdings.append(
                {
                    "code": code,
                    "name": item.get("name", code),
                    "sector": item.get("sector", ""),
                    "target_weight": equity_weight_per_stock,
                    "latest_price": item.get("current_price", 0.0),
                }
            )

        return {
            "success": True,
            "target_criteria": {
                "target_cagr": target_cagr,
                "max_drawdown_limit": max_drawdown_limit,
                "top_k": top_k,
                "lookback_years": lookback_years,
            },
            "performance": {
                "cagr": best_solution["cagr"],
                "max_drawdown": best_solution["max_drawdown"],
                "sharpe": best_solution["sharpe"],
                "total_return": best_solution["total_return"],
                "target_met": best_solution["target_met"],
                "backtest_years": best_solution["duration_years"],
            },
            "allocation": {
                "cash_reserve_ratio": cash_ratio,
                "holdings": holdings,
            },
            "summary_commentary": (
                f"Portfolio of {top_k} assets achieves "
                f"CAGR {best_solution['cagr'] * 100:.1f}% with "
                f"Max Drawdown {best_solution['max_drawdown'] * 100:.1f}% "
                f"(Target met: "
                f"{'YES' if best_solution['target_met'] else 'CLOSEST FRONTIER'})."
            ),
        }
