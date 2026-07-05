"""Portfolio builder: construct portfolio from stock list."""

from typing import Any, Dict, List, Optional

import numpy as np
from data_engine import get_kline
from data_readiness import ensure_symbol_analysis_ready
from models import Portfolio, Position

from portfolio.allocator import signal_weighted
from portfolio.position import compute_position
from portfolio.risk import RiskMetrics


class PortfolioBuilder:
    """Build and manage an investment portfolio."""

    def __init__(self, name: str, capital: float = 1000000) -> None:
        self.name = name
        self.capital = capital
        self._candidates: List[Dict[str, Any]] = []

    def add_from_strategy(
        self, code: str, market: str = "A", weight: Optional[float] = None, cached_only: bool = False
    ) -> None:
        """Add a stock from strategy analysis.

        Args:
            code: Stock code.
            market: Market identifier.
            weight: Optional manual weight (auto-computed if None).
            cached_only: Skip API calls, use only cached data.
        """
        ensure_symbol_analysis_ready(code, market)
        from strategies.aggregator import StrategyAggregator

        agg = StrategyAggregator(code, market)
        result = agg.analyze_all(cached_only=cached_only)

        score = result.get("final_score", 50)

        # Get current price from K-line
        kline = get_kline(code, market, days=1, cached_only=cached_only)
        current_price = kline[0].get("close", 0) if kline else 0

        pool = self._get_stock_info(code, market)
        name = pool.get("name", code) if pool else code

        self._candidates.append(
            {
                "code": code,
                "name": name,
                "market": market,
                "score": score,
                "current_price": current_price,
                "manual_weight": weight,
            }
        )

    def build(
        self,
        method: str = "signal",
        position_method: str = "kelly",
        capital_fraction: float = 1.0,
    ) -> Portfolio:
        """Build the portfolio.

        Args:
            method: Allocation method ('equal', 'signal', 'risk_parity').
            position_method: Position sizing ('kelly', 'fixed').
            capital_fraction: Fraction of total capital to deploy.

        Returns:
            Portfolio dataclass.
        """
        if not self._candidates:
            return Portfolio(name=self.name, capital=self.capital)

        capital_fraction = max(0.0, min(1.0, float(capital_fraction)))
        weights = self._resolve_weights(method)

        positions: List[Position] = []
        for i, cand in enumerate(self._candidates):
            w = weights[i] * capital_fraction
            pos = compute_position(
                code=cand["code"],
                name=cand["name"],
                market=cand["market"],
                capital=self.capital * w,
                score=cand["score"],
                current_price=cand["current_price"],
                method=position_method,
                max_weight=1.0,  # weight already applied to capital
            )
            if pos.shares > 0:
                pos.weight = w
                positions.append(pos)

        portfolio = Portfolio(
            name=self.name,
            capital=self.capital,
            positions=positions,
        )

        # Calculate risk metrics if we have enough data
        if len(positions) >= 2:
            try:
                returns = self._simulate_returns(positions)
                if returns:
                    risk = RiskMetrics(returns)
                    portfolio.metrics = risk.summary()
            except Exception:
                pass

        return portfolio

    def _resolve_weights(self, method: str) -> List[float]:
        """Resolve final allocation weights with manual weights taking priority."""
        scores = [float(c["score"]) for c in self._candidates]
        manual_weights = [c.get("manual_weight") for c in self._candidates]

        if not any(weight is not None for weight in manual_weights):
            return self._auto_weights(method, scores)

        specified_indices = [
            i for i, weight in enumerate(manual_weights) if weight is not None
        ]
        unspecified_indices = [
            i for i, weight in enumerate(manual_weights) if weight is None
        ]
        specified_weights = [float(manual_weights[i] or 0.0) for i in specified_indices]
        specified_total = sum(specified_weights)
        if specified_total < 0:
            raise ValueError("Manual weights must be non-negative")
        if specified_total > 1.0:
            raise ValueError("Manual weights must not sum to more than 1.0")

        weights = [0.0] * len(self._candidates)
        for index, manual_weight in zip(specified_indices, specified_weights):
            weights[index] = manual_weight

        if unspecified_indices:
            remaining = 1.0 - specified_total
            auto_scores = [scores[i] for i in unspecified_indices]
            auto_weights = self._auto_weights(method, auto_scores)
            for index, auto_weight in zip(unspecified_indices, auto_weights):
                weights[index] = remaining * auto_weight
            return weights

        if specified_total == 0:
            return self._auto_weights(method, scores)

        return [weight / specified_total for weight in weights]

    @staticmethod
    def _auto_weights(method: str, scores: List[float]) -> List[float]:
        """Compute automatic weights for a score list."""
        if method == "signal":
            weights = signal_weighted(scores)
        elif method == "equal":
            from portfolio.allocator import equal_weights

            weights = equal_weights(len(scores))
        else:
            weights = signal_weighted(scores)

        if not weights:
            return [1.0 / len(scores)] * len(scores)
        return weights

    def _simulate_returns(self, positions: List[Position]) -> List[float]:
        """Simulate portfolio returns from individual stock K-lines."""
        all_returns: Dict[str, List[float]] = {}
        for pos in positions:
            kline = get_kline(pos.code, pos.market, days=60)
            if len(kline) >= 2:
                closes = [r.get("close", 0) for r in reversed(kline)]
                closes = [c for c in closes if c > 0]
                if len(closes) >= 2:
                    returns = np.diff(np.array(closes)) / np.array(closes[:-1])
                    all_returns[pos.code] = returns.tolist()

        if not all_returns:
            return []

        # Equal-weighted portfolio return
        codes = list(all_returns.keys())
        min_len = min(len(all_returns[c]) for c in codes)
        portfolio_returns = []
        for i in range(min_len):
            daily_return = sum(all_returns[c][i] for c in codes) / len(codes)
            portfolio_returns.append(daily_return)

        return portfolio_returns

    @staticmethod
    def _get_stock_info(code: str, market: str) -> Optional[Dict[str, Any]]:
        """Get stock info from cached pool."""
        from data_engine import get_stock_pool

        pool = get_stock_pool(market)
        return next((s for s in pool if s["code"] == code), None)
