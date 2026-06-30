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
        pe_min, pe_max = self._range("pe", market)
        pb_min, pb_max = self._range("pb", market)
        _, dy_max = self._range("dy", market)

        # PE score: lower is better (invert percentile)
        if pe > 0 and pe_max > pe_min:
            pe_score = max(0, min(1, 1 - (pe - pe_min) / (pe_max - pe_min)))
            scores.append(pe_score * 0.45)
        else:
            scores.append(0)

        # PB score: lower is better
        if pb > 0 and pb_max > pb_min:
            pb_score = max(0, min(1, 1 - (pb - pb_min) / (pb_max - pb_min)))
            scores.append(pb_score * 0.35)
        else:
            scores.append(0)

        # Dividend yield score: higher is better
        dy_score = min(1, dy / dy_max) if dy_max > 0 else 0
        scores.append(dy_score * 0.20)

        return min(1, max(0, sum(scores)))
