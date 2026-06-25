"""Stock diagnosis: comprehensive analysis report."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from data_engine import get_kline, get_fundamentals
from factors.composite import CompositeAnalyzer
from models import Signal
from sentiment.aggregator import SentimentAggregator
from strategies.aggregator import StrategyAggregator


class StockDiagnosis:
    """Generate comprehensive stock diagnosis report."""

    def __init__(self, code: str, market: str = "A") -> None:
        self.code = code
        self.market = market

    def full_report(self) -> Dict[str, Any]:
        """Generate full diagnosis report.

        Returns:
            Dict with all analysis sections.
        """
        fundamentals = get_fundamentals(self.code, self.market) or {}
        kline = get_kline(self.code, self.market, days=365)

        # Strategy analysis
        strategy_result = self._strategy_analysis()

        # Factor analysis
        factor_result = self._factor_analysis()

        # Sentiment
        sentiment_result = self._sentiment_analysis()

        # Technical analysis
        technical_result = self._technical_analysis(kline)

        # Fundamental health
        fundamental_result = self._fundamental_health(fundamentals)

        # Risk assessment
        risk_result = self._risk_assessment(fundamentals, kline)

        # Combine into final decision
        final_decision = self._final_decision(
            strategy_result, sentiment_result, factor_result
        )

        return {
            "code": self.code,
            "market": self.market,
            "final_decision": final_decision,
            "adjusted_score": final_decision.get("adjusted_score", 50),
            "strategy": strategy_result,
            "factors": factor_result,
            "sentiment": sentiment_result,
            "technical": technical_result,
            "fundamentals": fundamental_result,
            "risks": risk_result,
        }

    def _strategy_analysis(self) -> Dict[str, Any]:
        """Run strategy aggregator."""
        try:
            agg = StrategyAggregator(self.code, self.market)
            return agg.analyze_all()
        except Exception as exc:
            return {"error": str(exc), "final_signal": "HOLD", "final_score": 50}

    def _factor_analysis(self) -> Dict[str, Any]:
        """Run composite factor analysis."""
        try:
            analyzer = CompositeAnalyzer(self.code, self.market)
            return analyzer.analyze()
        except Exception as exc:
            return {"error": str(exc), "total_score": 50}

    def _sentiment_analysis(self) -> Dict[str, Any]:
        """Get sentiment adjustment."""
        try:
            agg = SentimentAggregator(self.code, self.market)
            return agg.get_sentiment_report()
        except Exception as exc:
            return {"error": str(exc), "adjustment_factor": 1.0}

    def _technical_analysis(
        self, kline: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Technical indicators from K-line data."""
        if not kline or len(kline) < 60:
            return {"status": "insufficient_data"}

        closes = [r.get("close", 0) for r in kline[:120]]
        closes = [c for c in closes if c > 0]

        if len(closes) < 60:
            return {"status": "insufficient_data"}

        current = closes[0]
        ma5 = np.mean(closes[:5])
        ma10 = np.mean(closes[:10])
        ma20 = np.mean(closes[:20])
        ma60 = np.mean(closes[:60])

        # Support/resistance
        low_20 = min(closes[:20])
        high_20 = max(closes[:20])

        # RSI (14-day)
        rsi = self._compute_rsi(closes, 14)

        return {
            "current_price": round(current, 2),
            "ma5": round(ma5, 2),
            "ma10": round(ma10, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "support_20d": round(low_20, 2),
            "resistance_20d": round(high_20, 2),
            "rsi_14": round(rsi, 1),
            "trend": "bullish" if ma5 > ma10 > ma20 else "bearish",
        }

    def _fundamental_health(
        self, fundamentals: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess fundamental health."""
        if not fundamentals:
            return {"status": "no_data"}

        pe = fundamentals.get("pe_ttm", 0) or 0
        pb = fundamentals.get("pb", 0) or 0
        roe = fundamentals.get("roe", 0) or 0
        debt = fundamentals.get("debt_ratio", 0) or 0
        dy = fundamentals.get("dividend_yield", 0) or 0

        health_checks = {
            "valuation": "reasonable" if 0 < pe < 30 else ("expensive" if pe > 0 else "unknown"),
            "profitability": "good" if roe > 0.15 else ("weak" if roe > 0 else "negative"),
            "leverage": "safe" if debt < 0.5 else "high",
            "dividend": "paying" if dy > 0 else "none",
        }

        return {
            "pe_ttm": pe,
            "pb": pb,
            "roe": roe,
            "debt_ratio": debt,
            "dividend_yield": dy,
            "checks": health_checks,
        }

    def _risk_assessment(
        self,
        fundamentals: Dict[str, Any],
        kline: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Assess risks."""
        risks = []

        # High debt
        debt = (fundamentals or {}).get("debt_ratio", 0) or 0
        if debt > 0.7:
            risks.append("high_leverage")

        # Negative profit growth
        profit_g = (fundamentals or {}).get("profit_growth", 0) or 0
        if profit_g < -0.3:
            risks.append("declining_profit")

        # High valuation
        pe = (fundamentals or {}).get("pe_ttm", 0) or 0
        if pe > 50:
            risks.append("high_valuation")

        # High volatility
        if kline and len(kline) >= 60:
            closes = [r.get("close", 0) for r in kline[:120]]
            closes = [c for c in closes if c > 0]
            if len(closes) >= 60:
                returns = np.diff(np.array(closes[:60])) / np.array(closes[1:60])
                vol = np.std(returns)
                if vol > 0.03:
                    risks.append("high_volatility")

        return {
            "risk_count": len(risks),
            "risks": risks,
            "risk_level": "high" if len(risks) >= 2 else (
                "medium" if len(risks) == 1 else "low"
            ),
        }

    def _final_decision(
        self,
        strategy: Dict[str, Any],
        sentiment: Dict[str, Any],
        factors: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate final BUY/SELL/HOLD decision."""
        base_score = strategy.get("final_score", 50)
        adj_factor = sentiment.get("adjustment_factor", 1.0)

        adjusted_score = base_score * adj_factor

        # Risk adjustment
        risk_count = 0
        if "risks" in factors:
            risk_count = len(factors.get("risks", []))
        if risk_count >= 2:
            adjusted_score *= 0.85

        adjusted_score = max(0, min(100, adjusted_score))

        if adjusted_score >= 65:
            signal = "BUY"
        elif adjusted_score <= 35:
            signal = "SELL"
        else:
            signal = "HOLD"

        # Stop-loss / take-profit references
        tech = self._technical_analysis(
            get_kline(self.code, self.market, days=365)
        )
        current_price = tech.get("current_price", 0)
        support = tech.get("support_20d", current_price * 0.9)

        return {
            "signal": signal,
            "adjusted_score": round(adjusted_score, 1),
            "base_score": round(base_score, 1),
            "adjustment_factor": round(adj_factor, 3),
            "stop_loss": round(support * 0.95, 2) if current_price > 0 else 0,
            "take_profit": round(current_price * 1.20, 2) if current_price > 0 else 0,
        }

    @staticmethod
    def _compute_rsi(closes: List[float], period: int = 14) -> float:
        """Calculate RSI."""
        if len(closes) < period + 1:
            return 50.0
        changes = np.diff(closes[:period + 1][::-1])
        gains = np.maximum(changes, 0)
        losses = np.maximum(-changes, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
