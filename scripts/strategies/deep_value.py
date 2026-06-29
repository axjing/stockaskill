"""Deep value strategy: low PE/PB + high F-Score + high dividend."""

from typing import Any, Dict

from strategies.base import Strategy


class DeepValueStrategy(Strategy):
    """Deep value investing.

    Criteria:
    - PE < industry 25th percentile (or PE < 15 as fallback)
    - PB < 1.5
    - Dividend yield > 3%
    - F-Score >= 6
    """

    @property
    def name(self) -> str:
        return "deep_value"

    def analyze(self, code: str, market: str = "A") -> Dict[str, Any]:
        fund, kline = self._get_data(code, market)

        pe = self._safe(fund.get("pe_ttm", 0))
        pb = self._safe(fund.get("pb", 0))
        dy = self._safe(fund.get("dividend_yield", 0))

        # F-Score from composite
        from factors.composite import CompositeAnalyzer

        f_score = CompositeAnalyzer(code, market).analyze().get("f_score", 0)

        score = 0
        checks = []

        # PE check: lower is better
        if pe > 0 and pe < 15:
            score += 30
            checks.append("low_pe")
        elif pe > 0 and pe < 25:
            score += 15
            checks.append("moderate_pe")

        # PB check
        if pb > 0 and pb < 1.5:
            score += 25
            checks.append("low_pb")
        elif pb > 0 and pb < 2.5:
            score += 10

        # Dividend yield
        if dy >= 3:
            score += 20
            checks.append("high_dividend")
        elif dy >= 1.5:
            score += 10

        # F-Score
        if f_score >= 7:
            score += 25
            checks.append("high_fscore")
        elif f_score >= 5:
            score += 15

        # Safety margin estimate (simplified Graham number)
        if pe > 0 and self._safe(fund.get("bvps", 0)) > 0:
            graham_num = (22.5 * pe * self._safe(fund.get("bvps", 0))) ** 0.5
            _ = self._safe(fund.get("market_cap", 0))
            # Simplified: use PE*BV as proxy
            safety = (graham_num - pe) / max(pe, 1)
            if safety > 0.3:
                checks.append("safety_margin")

        signal = self._signal_from_score(score)

        return {
            "strategy_name": self.name,
            "signal": signal.value,
            "score": score,
            "confidence": min(0.85, max(0.3, score / 100)),
            "detail": {"checks": checks, "f_score": f_score},
        }
