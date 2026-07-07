"""Strategy aggregator: weighted vote across all strategies."""

from typing import Any, Dict, List

from config import signal_from_score, signal_thresholds
from strategies.alpha_momentum import AlphaMomentumStrategy
from strategies.base import Strategy
from strategies.contrarian import ContrarianStrategy
from strategies.deep_value import DeepValueStrategy
from strategies.garp import GARPStrategy
from strategies.ma_trend import MATrendStrategy
from strategies.momentum_enhanced import MomentumEnhancedStrategy
from strategies.multi_factor import MultiFactorStrategy

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

    def analyze_all(self, cached_only: bool = False) -> Dict[str, Any]:
        """Run all strategies and aggregate signals.

        Args:
            cached_only: Skip API calls, use only cached data.

        Returns:
            Dict with final_signal, final_score, confidence, signals list.
        """
        signals: List[Dict[str, Any]] = []
        total_weight = 0.0
        final_score = 0.0

        for factory in _STRATEGIES:
            strategy: Strategy = factory()
            result = strategy.analyze(self.code, self.market, cached_only=cached_only)
            signals.append(result)

            w = strategy.weight
            total_weight += w
            score = result.get("score", 50)
            final_score += score * w

        if total_weight > 0:
            final_score = final_score / total_weight

        # Confidence: average of individual confidences
        confidences = [s.get("confidence", 0.5) for s in signals]
        avg_confidence = sum(confidences) / max(len(confidences), 1)

        # Final signal — delegate to centralized threshold function
        final_signal = signal_from_score(final_score)

        # Adjust confidence based on strategy agreement
        # (SKIP signals are not counted toward consensus)
        buy_count = sum(1 for s in signals if s.get("signal") == "BUY")
        sell_count = sum(1 for s in signals if s.get("signal") == "SELL")
        thresholds = signal_thresholds()
        buy_consensus = thresholds.get("buy_consensus_count", 4)
        if buy_count >= buy_consensus or sell_count >= buy_consensus:
            avg_confidence = min(0.95, avg_confidence + 0.1)

        return {
            "code": self.code,
            "market": self.market,
            "final_signal": final_signal,
            "final_score": round(final_score, 1),
            "confidence": round(avg_confidence, 2),
            "signals": signals,
        }
