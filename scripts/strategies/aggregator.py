"""Strategy aggregator: weighted vote across all strategies."""

from typing import Any, Dict, List

from strategies.base import Strategy
from strategies.multi_factor import MultiFactorStrategy
from strategies.deep_value import DeepValueStrategy
from strategies.garp import GARPStrategy
from strategies.ma_trend import MATrendStrategy
from strategies.contrarian import ContrarianStrategy
from strategies.alpha_momentum import AlphaMomentumStrategy
from strategies.momentum_enhanced import MomentumEnhancedStrategy

_STRATEGIES = [
    MultiFactorStrategy,
    DeepValueStrategy,
    GARPStrategy,
    MATrendStrategy,
    ContrarianStrategy,
    AlphaMomentumStrategy,
    MomentumEnhancedStrategy,
]


class StrategyAggregator:
    """Aggregate signals from all strategies with weighted voting."""

    def __init__(self, code: str, market: str = "A") -> None:
        self.code = code
        self.market = market

    def analyze_all(self) -> Dict[str, Any]:
        """Run all strategies and aggregate signals.

        Returns:
            Dict with final_signal, final_score, confidence, signals list.
        """
        signals: List[Dict[str, Any]] = []
        weighted_buy = 0.0
        weighted_sell = 0.0
        total_weight = 0.0
        final_score = 0.0

        for factory in _STRATEGIES:
            strategy: Strategy = factory()
            result = strategy.analyze(self.code, self.market)
            signals.append(result)

            w = strategy.weight
            total_weight += w
            score = result.get("score", 50)
            final_score += score * w

            if result.get("signal") == "BUY":
                weighted_buy += w * (score / 100)
            elif result.get("signal") == "SELL":
                weighted_sell += w * (score / 100)

        if total_weight > 0:
            final_score = final_score / total_weight

        # Confidence: average of individual confidences
        confidences = [s.get("confidence", 0.5) for s in signals]
        avg_confidence = sum(confidences) / max(len(confidences), 1)

        # Final signal
        if final_score >= 65:
            final_signal = "BUY"
        elif final_score <= 35:
            final_signal = "SELL"
        else:
            final_signal = "HOLD"

        # Adjust confidence based on strategy agreement
        buy_count = sum(1 for s in signals if s.get("signal") == "BUY")
        sell_count = sum(1 for s in signals if s.get("signal") == "SELL")
        if buy_count >= 4 or sell_count >= 4:
            avg_confidence = min(0.95, avg_confidence + 0.1)

        return {
            "code": self.code,
            "market": self.market,
            "final_signal": final_signal,
            "final_score": round(final_score, 1),
            "confidence": round(avg_confidence, 2),
            "signals": signals,
        }



