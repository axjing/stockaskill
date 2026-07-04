"""Multi-factor strategy: weighted composite of all factors."""

from typing import Any, Dict

from strategies.base import Strategy


class MultiFactorStrategy(Strategy):
    """Aggregate all factors into a single signal.

    Score thresholds:
    - >= 70: BUY
    - 30-70: HOLD
    - < 30: SELL
    """

    @property
    def name(self) -> str:
        return "multi_factor"

    def analyze(self, code: str, market: str = "A", cached_only: bool = False) -> Dict[str, Any]:
        from factors.composite import CompositeAnalyzer

        analyzer = CompositeAnalyzer(code, market)
        result = analyzer.analyze(cached_only=cached_only)

        score = result.get("total_score", 50)
        signal = self._signal_from_score(score)

        return {
            "strategy_name": self.name,
            "signal": signal.value,
            "score": score,
            "confidence": min(0.9, max(0.3, abs(score - 50) / 50)),
            "detail": {
                "f_score": result.get("f_score", 0),
                "factors": result.get("factors", {}),
            },
        }
