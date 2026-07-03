"""Stock diagnosis: comprehensive analysis report."""

from typing import Any, Dict, List

import numpy as np
from config import get as cfg_get
from data_engine import get_fundamentals, get_kline
from data_readiness import build_symbol_quality_summary, ensure_symbol_analysis_ready
from factors.composite import CompositeAnalyzer
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
        readiness = ensure_symbol_analysis_ready(self.code, self.market)
        # All subsequent data reads should be cached-only: ensure_symbol_analysis_ready
        # has already synced any missing data.
        fundamentals = get_fundamentals(self.code, self.market, cached_only=True) or {}
        kline = get_kline(self.code, self.market, days=365, cached_only=True)

        # Strategy analysis — cached_only: data was already synced above
        strategy_result = self._strategy_analysis(cached_only=True)

        # Factor analysis
        factor_result = self._factor_analysis(cached_only=True)

        # Sentiment
        sentiment_result = self._sentiment_analysis()

        # Technical analysis
        technical_result = self._technical_analysis(kline)

        # Fundamental health
        fundamental_result = self._fundamental_health(fundamentals)

        # Risk assessment
        risk_result = self._risk_assessment(fundamentals, kline)

        # Confidence / data-quality summary
        confidence_result = self._confidence_assessment(
            strategy_result,
            technical_result,
            fundamental_result,
            sentiment_result,
            kline,
        )
        quality = build_symbol_quality_summary(self.code, self.market, readiness)
        confidence_result = self._merge_confidence(
            confidence_result,
            quality.get("confidence", {}),
        )

        # Combine into final decision
        final_decision = self._final_decision(
            strategy_result,
            sentiment_result,
            factor_result,
            risk_result,
            technical_result,
            fundamental_result,
            confidence_result,
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
            "confidence": confidence_result,
            "provenance": quality.get("provenance", {}),
        }

    def _strategy_analysis(self, cached_only: bool = True) -> Dict[str, Any]:
        """Run strategy aggregator."""
        try:
            agg = StrategyAggregator(self.code, self.market)
            return agg.analyze_all(cached_only=cached_only)
        except Exception as exc:
            return {"error": str(exc), "final_signal": "HOLD", "final_score": 50}

    def _factor_analysis(self, cached_only: bool = True) -> Dict[str, Any]:
        """Run composite factor analysis."""
        try:
            analyzer = CompositeAnalyzer(self.code, self.market)
            return analyzer.analyze(cached_only=cached_only)
        except Exception as exc:
            return {"error": str(exc), "total_score": 50}

    def _sentiment_analysis(self) -> Dict[str, Any]:
        """Get sentiment adjustment."""
        try:
            agg = SentimentAggregator(self.code, self.market)
            return agg.get_sentiment_report()
        except Exception as exc:
            return {"error": str(exc), "adjustment_factor": 1.0}

    def _technical_analysis(self, kline: List[Dict[str, Any]]) -> Dict[str, Any]:
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

    def _fundamental_health(self, fundamentals: Dict[str, Any]) -> Dict[str, Any]:
        """Assess fundamental health."""
        if not fundamentals:
            return {"status": "no_data"}

        pe = fundamentals.get("pe_ttm", 0) or 0
        pb = fundamentals.get("pb", 0) or 0
        roe = fundamentals.get("roe", 0) or 0
        debt = fundamentals.get("debt_ratio", 0) or 0
        dy = fundamentals.get("dividend_yield", 0) or 0

        health_checks = {
            "valuation": "reasonable"
            if 0 < pe < 30
            else ("expensive" if pe > 0 else "unknown"),
            "profitability": "good" if roe > 0.15 else "negative",
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
                closes_asc = list(reversed(closes[:60]))
                returns = np.diff(np.array(closes_asc)) / np.array(closes_asc[:-1])
                vol = np.std(returns)
                if vol > 0.03:
                    risks.append("high_volatility")

        return {
            "risk_count": len(risks),
            "risks": risks,
            "risk_level": "high"
            if len(risks) >= 2
            else ("medium" if len(risks) == 1 else "low"),
        }

    def _final_decision(
        self,
        strategy: Dict[str, Any],
        sentiment: Dict[str, Any],
        factors: Dict[str, Any],
        risk: Dict[str, Any] | None = None,
        technical: Dict[str, Any] | None = None,
        fundamentals: Dict[str, Any] | None = None,
        confidence: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Generate final BUY/SELL/HOLD decision."""
        base_score = strategy.get("final_score", 50)
        adj_factor = sentiment.get("adjustment_factor", 1.0)

        adjusted_score = base_score * adj_factor

        # Risk adjustment
        risk_data = risk or {}
        risk_count = risk_data.get("risk_count", 0)
        if risk_count >= 2:
            adjusted_score *= 0.85

        adjusted_score = max(0, min(100, adjusted_score))

        buy_threshold = cfg_get("signal_thresholds.buy", 65)
        sell_threshold = cfg_get("signal_thresholds.sell", 35)
        if adjusted_score >= buy_threshold:
            signal = "BUY"
        elif adjusted_score <= sell_threshold:
            signal = "SELL"
        else:
            signal = "HOLD"

        # Stop-loss / take-profit references (use pre-computed technical if available)
        tech = technical or self._technical_analysis(
            get_kline(self.code, self.market, days=365, cached_only=True)
        )
        fund = fundamentals or {}
        confidence_data = confidence or {}
        current_price = tech.get("current_price", 0)
        support = tech.get("support_20d", current_price * 0.9)
        bull_case = self._build_bull_case(strategy, factors, tech, fund, sentiment)
        bear_case = self._build_bear_case(strategy, risk_data, tech, fund, sentiment)
        invalidation = self._build_invalidation_conditions(
            signal,
            tech,
            fund,
            risk_data,
        )

        return {
            "signal": signal,
            "adjusted_score": round(adjusted_score, 1),
            "base_score": round(base_score, 1),
            "adjustment_factor": round(adj_factor, 3),
            "confidence_level": confidence_data.get("level", "medium"),
            "confidence_score": confidence_data.get("score", 0.5),
            "bull_case": bull_case,
            "bear_case": bear_case,
            "invalidation_conditions": invalidation,
            "stop_loss": round(support * 0.95, 2) if current_price > 0 else 0,
            "take_profit": round(current_price * 1.20, 2) if current_price > 0 else 0,
        }

    def _confidence_assessment(
        self,
        strategy: Dict[str, Any],
        technical: Dict[str, Any],
        fundamentals: Dict[str, Any],
        sentiment: Dict[str, Any],
        kline: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Estimate confidence from data completeness and agreement strength."""
        checks = {
            "strategy_available": "error" not in strategy,
            "technical_ready": technical.get("status") != "insufficient_data",
            "fundamentals_ready": fundamentals.get("status") != "no_data",
            "sentiment_ready": "error" not in sentiment,
            "history_depth_ok": len(kline) >= 120,
        }
        check_score = sum(1 for ok in checks.values() if ok) / max(len(checks), 1)
        strategy_confidence = float(strategy.get("confidence", 0.5) or 0.5)
        score = max(0.0, min(1.0, check_score * 0.65 + strategy_confidence * 0.35))

        if score >= 0.8:
            level = "high"
        elif score >= 0.55:
            level = "medium"
        else:
            level = "low"

        notes = []
        if not checks["fundamentals_ready"]:
            notes.append("基本面数据不足")
        if not checks["technical_ready"]:
            notes.append("技术面样本不足")
        if not checks["sentiment_ready"]:
            notes.append("情绪数据回退到默认值")
        if checks["history_depth_ok"]:
            notes.append("历史数据覆盖满足分析要求")
        if strategy_confidence >= 0.75:
            notes.append("策略聚合一致性较高")
        elif strategy_confidence <= 0.45:
            notes.append("策略聚合一致性一般")

        return {
            "score": round(score, 3),
            "level": level,
            "checks": checks,
            "notes": notes or ["数据完整度中性"],
        }

    @staticmethod
    def _merge_confidence(
        analytical: Dict[str, Any],
        data_quality: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge analytical confidence with data-quality confidence."""
        analytical_score = float(analytical.get("score", 0.5) or 0.5)
        quality_score = float(data_quality.get("score", 0.5) or 0.5)
        merged_score = max(0.0, min(1.0, analytical_score * 0.7 + quality_score * 0.3))
        if merged_score >= 0.8:
            level = "high"
        elif merged_score >= 0.55:
            level = "medium"
        else:
            level = "low"
        notes = list(analytical.get("notes", []) or [])
        notes.extend(
            item for item in (data_quality.get("notes", []) or []) if item not in notes
        )
        merged = dict(analytical)
        merged["score"] = round(merged_score, 3)
        merged["level"] = level
        merged["notes"] = notes[:6]
        merged["data_quality"] = data_quality
        return merged

    @staticmethod
    def _build_bull_case(
        strategy: Dict[str, Any],
        factors: Dict[str, Any],
        technical: Dict[str, Any],
        fundamentals: Dict[str, Any],
        sentiment: Dict[str, Any],
    ) -> List[str]:
        """Build explicit bullish reasons."""
        reasons: List[str] = []
        top_factors = sorted(
            [
                (name, float(score))
                for name, score in (factors.get("factors", {}) or {}).items()
                if isinstance(score, (int, float))
            ],
            key=lambda item: item[1],
            reverse=True,
        )
        if top_factors:
            formatted = ", ".join(
                f"{name}({score:.1f})" for name, score in top_factors[:3]
            )
            reasons.append(f"高分因子集中在 {formatted}")

        if technical.get("trend") == "bullish":
            reasons.append("短中期均线结构偏多")

        if fundamentals.get("checks", {}).get("profitability") == "good":
            reasons.append("盈利能力处于较好区间")

        if float(sentiment.get("adjustment_factor", 1.0) or 1.0) > 1.03:
            reasons.append("情绪面对总评分形成正向放大")

        if float(strategy.get("confidence", 0.5) or 0.5) >= 0.75:
            reasons.append("多策略信号一致性较高")

        return reasons or ["当前多头证据不强，更多来自中性打分而非强趋势共振"]

    @staticmethod
    def _build_bear_case(
        strategy: Dict[str, Any],
        risk: Dict[str, Any],
        technical: Dict[str, Any],
        fundamentals: Dict[str, Any],
        sentiment: Dict[str, Any],
    ) -> List[str]:
        """Build explicit bearish reasons / main risks."""
        reasons: List[str] = []
        for risk_name in risk.get("risks", [])[:3]:
            reasons.append(f"风险项已触发：{risk_name}")

        if technical.get("trend") == "bearish":
            reasons.append("均线结构暂未形成顺趋势确认")

        if fundamentals.get("checks", {}).get("valuation") == "expensive":
            reasons.append("估值保护不足")

        if float(sentiment.get("adjustment_factor", 1.0) or 1.0) < 0.97:
            reasons.append("情绪面对总评分形成负向压制")

        if float(strategy.get("confidence", 0.5) or 0.5) <= 0.45:
            reasons.append("多策略之间分歧较大")

        return reasons or ["当前主要风险来自后续数据确认不足，而不是单一强负面信号"]

    @staticmethod
    def _build_invalidation_conditions(
        signal: str,
        technical: Dict[str, Any],
        fundamentals: Dict[str, Any],
        risk: Dict[str, Any],
    ) -> List[str]:
        """Build explicit invalidation / what-must-change conditions."""
        conditions: List[str] = []
        support = float(technical.get("support_20d", 0) or 0)
        if support > 0:
            conditions.append(f"跌破 20 日支撑位 {support:.2f} 后未能快速收回")

        if signal == "BUY":
            conditions.append("下一次基本面更新中盈利质量明显走弱")
            conditions.append("风险项继续增加并抬升到 high risk")
        elif signal == "SELL":
            conditions.append("价格重新站回中期均线且趋势修复")
            conditions.append("核心风险项消退，风险等级回落")
        else:
            conditions.append("趋势与基本面中至少一项出现明确改善")
            conditions.append("风险与估值约束至少解除一项")

        if fundamentals.get("checks", {}).get("leverage") == "high":
            conditions.append("杠杆压力未缓解前，不应上调判断")

        if (
            risk.get("risk_level") == "high"
            and "风险项继续增加并抬升到 high risk" not in conditions
        ):
            conditions.append("高风险状态持续存在")

        return conditions

    @staticmethod
    def _compute_rsi(closes: List[float], period: int = 14) -> float:
        """Calculate RSI."""
        if len(closes) < period + 1:
            return 50.0
        changes = np.diff(closes[: period + 1][::-1])
        gains = np.maximum(changes, 0)
        losses = np.maximum(-changes, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
