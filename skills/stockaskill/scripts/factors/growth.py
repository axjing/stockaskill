"""Growth factor: revenue and profit growth rates."""

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
        rev_min, rev_max = self._range("revenue", market)
        prof_min, prof_max = self._range("profit", market)
        accel_min, accel_max = self._range("accel", market)

        # Revenue growth (40%)
        rev_span = rev_max - rev_min
        rev_score = (
            max(0, min(1, (rev_growth - rev_min) / rev_span)) if rev_span > 0 else 0.5
        )
        scores.append(rev_score * 0.40)

        # Profit growth (40%)
        prof_span = prof_max - prof_min
        profit_score = (
            max(0, min(1, (profit_growth - prof_min) / prof_span))
            if prof_span > 0
            else 0.5
        )
        scores.append(profit_score * 0.40)

        # Growth acceleration from K-line trend (20%)
        accel = self._growth_acceleration(kline, accel_min, accel_max)
        scores.append(accel * 0.20)

        return min(1, max(0, sum(scores)))

    @staticmethod
    def _growth_acceleration(
        kline: List[Dict[str, Any]],
        accel_min: float = -0.3,
        accel_max: float = 0.3,
    ) -> float:
        """Proxy growth acceleration from price trend."""
        if len(kline) < 60:
            return 0.5
        closes = [row.get("close", 0) for row in kline[:120]]
        closes = [c for c in closes if c > 0]
        if len(closes) < 60:
            return 0.5
        ret_6m = (closes[0] - closes[60]) / max(closes[60], 1e-9)
        ret_3m = (closes[0] - closes[30]) / max(closes[30], 1e-9)
        accel = ret_3m - ret_6m
        accel_span = accel_max - accel_min
        if accel_span > 0:
            return max(0, min(1, (accel - accel_min) / accel_span))
        return 0.5
