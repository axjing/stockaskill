"""GARP strategy: Growth at a Reasonable Price."""

from typing import Any, Dict, List, Tuple

from strategies.base import Strategy

_PEG_BRACKETS: List[Tuple[float, int, str]] = [
    (1, 30, "low_peg"),
    (1.5, 15, ""),
]

_ROE_BRACKETS: List[Tuple[float, int, str]] = [
    (0.15, 25, "high_roe"),
    (0.1, 10, ""),
]

_REVGROWTH_BRACKETS: List[Tuple[float, int, str]] = [
    (0.10, 25, "revenue_growth"),
    (0.05, 10, ""),
]


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

    def analyze(self, code: str, market: str = "A", cached_only: bool = False) -> Dict[str, Any]:
        fund, kline = self._get_data(code, market, cached_only=cached_only)

        pe = self._safe(fund.get("pe_ttm", 0))
        roe = self._safe(fund.get("roe", 0))
        rev_growth = self._safe(fund.get("revenue_growth", 0))
        profit_growth = self._safe(fund.get("profit_growth", 0))

        # PEG = PE / (profit_growth * 100)
        peg = pe / (profit_growth * 100) if profit_growth > 0 else 99

        score = 0
        checks = []

        # PEG < 1 is ideal
        for ceiling, pts, label in _PEG_BRACKETS:
            if peg < ceiling:
                score += pts
                if label:
                    checks.append(label)
                break

        # ROE > 15%
        for threshold, pts, label in _ROE_BRACKETS:
            if roe > threshold:
                score += pts
                if label:
                    checks.append(label)
                break

        # Revenue growth > 10%
        for threshold, pts, label in _REVGROWTH_BRACKETS:
            if rev_growth > threshold:
                score += pts
                if label:
                    checks.append(label)
                break

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
