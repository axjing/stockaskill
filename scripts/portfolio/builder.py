"""Portfolio builder: construct portfolio from stock list."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from data_engine import get_kline
from models import Portfolio, Position
from portfolio.position import compute_position
from portfolio.allocator import signal_weighted
from portfolio.risk import RiskMetrics


class PortfolioBuilder:
    """Build and manage an investment portfolio."""

    def __init__(self, name: str, capital: float = 1000000) -> None:
        self.name = name
        self.capital = capital
        self._candidates: List[Dict[str, Any]] = []

    def add_from_strategy(
        self, code: str, market: str = "A", weight: Optional[float] = None
    ) -> None:
        """Add a stock from strategy analysis.

        Args:
            code: Stock code.
            market: Market identifier.
            weight: Optional manual weight (auto-computed if None).
        """
        from strategies.aggregator import StrategyAggregator

        agg = StrategyAggregator(code, market)
        result = agg.analyze_all()

        score = result.get("final_score", 50)

        # Get current price from K-line
        kline = get_kline(code, market, days=1)
        current_price = kline[0].get("close", 0) if kline else 0

        pool = self._get_stock_info(code, market)
        name = pool.get("name", code) if pool else code

        self._candidates.append({
            "code": code,
            "name": name,
            "market": market,
            "score": score,
            "current_price": current_price,
            "manual_weight": weight,
        })

    def build(
        self,
        method: str = "signal",
        position_method: str = "kelly",
    ) -> Portfolio:
        """Build the portfolio.

        Args:
            method: Allocation method ('equal', 'signal', 'risk_parity').
            position_method: Position sizing ('kelly', 'fixed').

        Returns:
            Portfolio dataclass.
        """
        if not self._candidates:
            return Portfolio(name=self.name, capital=self.capital)

        # Get scores and compute weights
        scores = [c["score"] for c in self._candidates]

        if method == "signal":
            weights = signal_weighted(scores)
        elif method == "equal":
            from portfolio.allocator import equal_weights
            weights = equal_weights(len(self._candidates))
        else:
            weights = signal_weighted(scores)

        positions: List[Position] = []
        for i, cand in enumerate(self._candidates):
            pos = compute_position(
                code=cand["code"],
                name=cand["name"],
                market=cand["market"],
                capital=self.capital,
                score=cand["score"],
                current_price=cand["current_price"],
                method=position_method,
            )
            if pos.shares > 0:
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
