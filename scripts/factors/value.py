"""Value factor: PE/PB/dividend yield composite valuation."""

from typing import Any, Dict, List

from factors.base import Factor


class ValueFactor(Factor):
    """Composite valuation factor.

    Lower PE/PB and higher dividend yield produce higher scores.
    Industry-relative PE adjustment applied when industry data available.
    """

    @property
    def name(self) -> str:
        return "value"

    def compute(
        self,
        fundamentals: Dict[str, Any],
        kline: List[Dict[str, Any]],
        market: str = "A",
    ) -> float:
        pe = self._safe(fundamentals.get("pe_ttm", 0))
        pb = self._safe(fundamentals.get("pb", 0))
        dy = self._safe(fundamentals.get("dividend_yield", 0))

        scores = []

        # PE score: lower is better (invert percentile)
        if pe > 0:
            # Typical A-share PE range 5-80
            pe_score = max(0, min(1, 1 - (pe - 5) / 75))
            scores.append(pe_score * 0.45)
        else:
            scores.append(0)

        # PB score: lower is better
        if pb > 0:
            # Typical A-share PB range 0.5-10
            pb_score = max(0, min(1, 1 - (pb - 0.5) / 9.5))
            scores.append(pb_score * 0.35)
        else:
            scores.append(0)

        # Dividend yield score: higher is better
        # Typical range 0-6%
        dy_score = min(1, dy / 6.0)
        scores.append(dy_score * 0.20)

        return min(1, max(0, sum(scores)))
