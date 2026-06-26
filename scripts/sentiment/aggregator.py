"""Sentiment aggregator: combine multiple sources into adjustment factor."""

from typing import Any, Dict, List

from sentiment.sources import (
    get_guba_sentiment,
    get_market_breadth,
    aggregate_market_sentiment,
)


class SentimentAggregator:
    """Aggregate sentiment data and produce an adjustment factor."""

    def __init__(self, code: str, market: str = "A") -> None:
        self.code = code
        self.market = market

    def get_adjustment_factor(self) -> float:
        """Get sentiment adjustment factor.

        Returns:
            Factor in [0.8, 1.15].
            0.8 = extremely bearish, 1.15 = extremely bullish.
        """
        sentiment_score = self._compute_sentiment()

        # Map [0, 1] to [0.8, 1.15]
        factor = 0.8 + sentiment_score * 0.35
        return round(factor, 3)

    def get_sentiment_report(self) -> Dict[str, Any]:
        """Get detailed sentiment report.

        Returns:
            Dict with overall_score, sources, adjustment_factor.
        """
        guba = get_guba_sentiment(self.code)
        market = aggregate_market_sentiment()
        breadth = get_market_breadth()

        # Weighted average
        stock_sentiment = (guba.get("sentiment_score", 0.5) + 1) / 2  # Map [-1,1] to [0,1]
        overall = stock_sentiment * 0.4 + market * 0.6

        return {
            "overall_score": round(overall, 3),
            "stock_sentiment": round(stock_sentiment, 3),
            "market_sentiment": round(market, 3),
            "market_breadth": breadth,
            "adjustment_factor": round(0.8 + overall * 0.35, 3),
            "guba": guba,
        }

    def _compute_sentiment(self) -> float:
        """Compute overall sentiment score [0, 1]."""
        report = self.get_sentiment_report()
        return report["overall_score"]
