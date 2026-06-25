"""Growth factor: revenue and profit growth rates."""
from __future__ import annotations

from typing import Any, Dict, List

from factors.base import Factor


class GrowthFactor(Factor):
    """Growth assessment based on YoY changes.

    - Revenue growth YoY
    - Net profit growth YoY
    - Growth acceleration (momentum of growth)
    """

    @property
    def name(self) -> str:
        return "growth"

    def compute(
        self,
        fundamentals: Dict[str, Any],
        kline: List[Dict[str, Any]],
        market: str = "A",
    ) -> float:
        rev_growth = self._safe(fundamentals.get("revenue_growth", 0))
        profit_growth = self._safe(fundamentals.get("profit_growth", 0))

        scores = []

        # Revenue growth (40%): typical range -50% to 100%
        rev_score = max(0, min(1, (rev_growth + 0.5) / 1.5))
        scores.append(rev_score * 0.40)

        # Profit growth (40%): typical range -80% to 200%
        profit_score = max(0, min(1, (profit_growth + 0.8) / 2.8))
        scores.append(profit_score * 0.40)

        # Growth acceleration from K-line trend (20%)
        # Use price momentum as proxy if limited fundamentals
        accel = self._growth_acceleration(kline)
        scores.append(accel * 0.20)

        return min(1, max(0, sum(scores)))

    @staticmethod
    def _growth_acceleration(kline: List[Dict[str, Any]]) -> float:
        """Proxy growth acceleration from price trend."""
        if len(kline) < 60:
            return 0.5
        closes = [row.get("close", 0) for row in kline[:120]]
        closes = [c for c in closes if c > 0]
        if len(closes) < 60:
            return 0.5
        # Compare 6-month return vs 3-month return
        ret_6m = (closes[0] - closes[60]) / max(closes[60], 1e-9)
        ret_3m = (closes[0] - closes[30]) / max(closes[30], 1e-9)
        accel = ret_3m - ret_6m  # positive = accelerating
        return max(0, min(1, (accel + 0.3) / 0.6))
