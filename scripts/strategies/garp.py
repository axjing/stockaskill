"""GARP strategy: Growth at a Reasonable Price."""

from typing import Any, Dict

from models import Signal
from strategies.base import Strategy


class GARPStrategy(Strategy):
    """Growth at a Reasonable Price.

    Criteria:
    - PEG < 1
    - ROE > 15%
    - Revenue growth > 10%
    - Consecutive positive growth (4 quarters proxy)
    """

    @property
    def name(self) -> str:
        return "garp"

    def analyze(self, code: str, market: str = "A") -> Dict[str, Any]:
        fund, kline = self._get_data(code, market)

        pe = self._safe(fund.get("pe_ttm", 0))
        roe = self._safe(fund.get("roe", 0))
        rev_growth = self._safe(fund.get("revenue_growth", 0))
        profit_growth = self._safe(fund.get("profit_growth", 0))

        # PEG = PE / (profit_growth * 100)
        peg = pe / (profit_growth * 100) if profit_growth > 0 else 99

        score = 0
        checks = []

        # PEG < 1 is ideal
        if peg < 1:
            score += 30
            checks.append("low_peg")
        elif peg < 1.5:
            score += 15

        # ROE > 15%
        if roe > 0.15:
            score += 25
            checks.append("high_roe")
        elif roe > 0.1:
            score += 10

        # Revenue growth > 10%
        if rev_growth > 0.10:
            score += 25
            checks.append("revenue_growth")
        elif rev_growth > 0.05:
            score += 10

        # Growth consistency (profit growth > 0 as proxy)
        if profit_growth > 0:
            score += 20
            checks.append("consistent_growth")

        signal = self._signal_from_score(score)

        return {
            "strategy_name": self.name,
            "signal": signal.value,
            "score": score,
            "confidence": min(0.85, max(0.3, score / 100)),
            "detail": {
                "checks": checks,
                "peg": round(peg, 2),
                "roe": round(roe, 3),
            },
        }
