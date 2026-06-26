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
        eps = self._safe(fundamentals.get("eps", 0))
        bvps = self._safe(fundamentals.get("bvps", 0))

        scores = []

        # ROE score (40%): typical A-share range -20% to 40%
        roe_norm = max(0, min(1, (roe + 0.2) / 0.6))
        scores.append(roe_norm * 0.40)

        # Gross margin score (25%): range 0-80%
        gm_score = max(0, min(1, gm / 0.8))
        scores.append(gm_score * 0.25)

        # Debt safety (20%): lower is better, range 0-100%
        debt_score = max(0, min(1, 1 - debt))
        scores.append(debt_score * 0.20)

        # FCF proxy: EPS / BVPS (ROE-like) > 0 indicates quality (15%)
        if bvps > 0:
            fcf_proxy = eps / bvps
            fcf_score = max(0, min(1, (fcf_proxy + 0.1) / 0.5))
            scores.append(fcf_score * 0.15)
        else:
            scores.append(0)

        return min(1, max(0, sum(scores)))
