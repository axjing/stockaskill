"""Deep value strategy: low PE/PB + high F-Score + high dividend."""

from typing import Any, Dict, List, Tuple

from strategies.base import Strategy

_PE_BRACKETS: List[Tuple[float, int, str]] = [
    (15, 30, "low_pe"),
    (25, 15, "moderate_pe"),
]

_PB_BRACKETS: List[Tuple[float, int, str]] = [
    (1.5, 25, "low_pb"),
    (2.5, 10, ""),
]

_DY_BRACKETS: List[Tuple[float, int, str]] = [
    (3, 20, "high_dividend"),
    (1.5, 10, ""),
]

_FSCORE_BRACKETS: List[Tuple[int, int, str]] = [
    (7, 25, "high_fscore"),
    (5, 15, ""),
]


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

    def analyze(self, code: str, market: str = "A", cached_only: bool = False) -> Dict[str, Any]:
        fund, kline = self._get_data(code, market, cached_only=cached_only)

        pe = self._safe(fund.get("pe_ttm", 0))
        pb = self._safe(fund.get("pb", 0))
        dy = self._safe(fund.get("dividend_yield", 0))

        # F-Score from composite
        from factors.composite import CompositeAnalyzer

        f_score = CompositeAnalyzer(code, market).analyze(cached_only=cached_only).get("f_score", 0)

        score = 0
        checks = []

        # PE check: lower is better
        for ceiling, pts, label in _PE_BRACKETS:
            if 0 < pe < ceiling:
                score += pts
                if label:
                    checks.append(label)
                break

        # PB check
        for ceiling, pts, label in _PB_BRACKETS:
            if 0 < pb < ceiling:
                score += pts
                if label:
                    checks.append(label)
                break

        # Dividend yield
        for threshold, pts, label in _DY_BRACKETS:
            if dy >= threshold:
                score += pts
                if label:
                    checks.append(label)
                break

        # F-Score
        for threshold, pts, label in _FSCORE_BRACKETS:
            if f_score >= threshold:
                score += pts
                if label:
                    checks.append(label)
                break

        # Safety margin estimate (Graham Number: sqrt(22.5 * EPS * BVPS))
        eps_val = self._safe(fund.get("eps", 0))
        bvps_val = self._safe(fund.get("bvps", 0))
        current_price = kline[0].get("close", 0) if kline and len(kline) > 0 else 0
        if eps_val > 0 and bvps_val > 0 and current_price > 0:
            graham_num = (22.5 * eps_val * bvps_val) ** 0.5
            safety = (graham_num - current_price) / current_price
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
