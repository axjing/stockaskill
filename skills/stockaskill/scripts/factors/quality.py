"""Quality factor: ROE/gross margin/debt/FCF composite."""

from typing import Any, Dict, List

from factors.base import Factor


class QualityFactor(Factor):
    """Stock quality assessment.

    - ROE (40%): Higher is better
    - Gross margin stability (25%): Consistent high margins
    - Debt safety (20%): Lower debt ratio is better
    - FCF quality (15%): Positive free cash flow
    """

    @property
    def name(self) -> str:
        return "quality"

    def compute(
        self,
        fundamentals: Dict[str, Any],
        kline: List[Dict[str, Any]],
        market: str = "A",
    ) -> float:
        roe = self._safe(fundamentals.get("roe", 0))
        gm = self._safe(fundamentals.get("gross_margin", 0))
        debt = self._safe(fundamentals.get("debt_ratio", 0))
        nm = self._safe(fundamentals.get("net_margin", 0))

        scores = []
        roe_min, roe_max = self._range("roe", market)
        _, gm_max = self._range("gross_margin", market)
        nm_min, nm_max = self._range("net_margin", market)

        # ROE score (40%)
        roe_span = roe_max - roe_min
        roe_norm = max(0, min(1, (roe - roe_min) / roe_span)) if roe_span > 0 else 0.5
        scores.append(roe_norm * 0.40)

        # Gross margin score (25%)
        gm_score = max(0, min(1, gm / gm_max)) if gm_max > 0 else 0
        scores.append(gm_score * 0.25)

        # Debt safety (20%): lower is better, range 0-100%
        debt_score = max(0, min(1, 1 - debt))
        scores.append(debt_score * 0.20)

        # Profit quality (15%): net margin as pricing power indicator
        nm_span = nm_max - nm_min
        nm_score = max(0, min(1, (nm - nm_min) / nm_span)) if nm_span > 0 else 0.5
        scores.append(nm_score * 0.15)

        return min(1, max(0, sum(scores)))
