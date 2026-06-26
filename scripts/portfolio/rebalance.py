"""Portfolio rebalancing strategies."""

from datetime import datetime
from typing import Any, Dict, List

from models import Portfolio


class Rebalancer:
    """Portfolio rebalancing engine."""

    def __init__(
        self,
        method: str = "calendar",
        threshold: float = 0.05,
        calendar: str = "monthly",
    ) -> None:
        self.method = method  # 'calendar', 'threshold', 'hybrid'
        self.threshold = threshold  # 5% deviation
        self.calendar = calendar  # 'weekly', 'monthly', 'quarterly'

    def should_rebalance(
        self,
        portfolio: Portfolio,
        last_rebalance: str = "",
    ) -> bool:
        """Check if portfolio needs rebalancing.

        Args:
            portfolio: Current portfolio state.
            last_rebalance: Date of last rebalance (YYYY-MM-DD).

        Returns:
            True if rebalancing is needed.
        """
        if self.method == "calendar":
            return self._calendar_check(last_rebalance)
        if self.method == "threshold":
            return self._threshold_check(portfolio)
        if self.method == "hybrid":
            return (
                self._calendar_check(last_rebalance)
                or self._threshold_check(portfolio)
            )
        return False

    def _calendar_check(self, last_rebalance: str) -> bool:
        if not last_rebalance:
            return True
        try:
            last = datetime.strptime(last_rebalance, "%Y-%m-%d")
            now = datetime.now()
            diff = (now - last).days

            if self.calendar == "weekly":
                return diff >= 7
            if self.calendar == "monthly":
                return diff >= 30
            if self.calendar == "quarterly":
                return diff >= 90
        except (ValueError, TypeError):
            return True
        return False

    def _threshold_check(self, portfolio: Portfolio) -> bool:
        if not portfolio.positions:
            return False
        target_weight = 1.0 / len(portfolio.positions)
        for pos in portfolio.positions:
            deviation = abs(pos.weight - target_weight)
            if deviation > self.threshold:
                return True
        return False

    def rebalance(
        self,
        portfolio: Portfolio,
        new_weights: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """Generate rebalancing trades.

        Args:
            portfolio: Current portfolio.
            new_weights: Target weights by stock code.

        Returns:
            List of trade instructions.
        """
        trades = []
        total_value = sum(
            p.shares * p.current_price for p in portfolio.positions
        )

        for pos in portfolio.positions:
            target = new_weights.get(pos.code, 0)
            target_value = total_value * target
            current_value = pos.shares * pos.current_price
            diff = target_value - current_value

            if abs(diff) > current_value * 0.01:  # >1% threshold
                action = "BUY" if diff > 0 else "SELL"
                shares = int(abs(diff) / max(pos.current_price, 1e-9) / 100) * 100
                if shares > 0:
                    trades.append({
                        "code": pos.code,
                        "action": action,
                        "shares": shares,
                        "reason": f"{action} {abs(diff):.0f} ({target * 100:.1f}%)",
                    })

        return trades
