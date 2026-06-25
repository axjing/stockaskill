"""Moving average trend strategy."""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from models import Signal
from strategies.base import Strategy


class MATrendStrategy(Strategy):
    """Moving average trend following.

    Criteria:
    - MA5/MA10/MA20/MA60 bullish alignment
    - Golden cross / Death cross status
    - Trend strength
    """

    @property
    def name(self) -> str:
        return "ma_trend"

    def analyze(self, code: str, market: str = "A") -> Dict[str, Any]:
        fund, kline = self._get_data(code, market)

        if len(kline) < 60:
            return {
                "strategy_name": self.name,
                "signal": "HOLD",
                "score": 50,
                "confidence": 0.2,
                "detail": {"reason": "insufficient_data"},
            }

        closes = [row.get("close", 0) for row in kline[:120]]
        closes = [c for c in closes if c > 0]

        if len(closes) < 60:
            return {
                "strategy_name": self.name,
                "signal": "HOLD",
                "score": 50,
                "confidence": 0.2,
                "detail": {"reason": "insufficient_data"},
            }

        ma5 = np.mean(closes[:5])
        ma10 = np.mean(closes[:10])
        ma20 = np.mean(closes[:20])
        ma60 = np.mean(closes[:60])

        score = 50  # Neutral start
        checks = []

        # MA alignment
        if ma5 > ma10 > ma20 > ma60:
            score += 30
            checks.append("bullish_alignment")
        elif ma5 > ma10 > ma20:
            score += 15
            checks.append("partial_bullish")
        elif ma5 < ma10 < ma20 < ma60:
            score -= 20
            checks.append("bearish_alignment")

        # Golden/death cross (MA5 vs MA10)
        current_price = closes[0]
        if ma5 > ma10 and closes[0] > ma5:
            score += 10
            checks.append("golden_cross")
        elif ma5 < ma10 and closes[0] < ma5:
            score -= 10
            checks.append("death_cross")

        # Trend strength (MA20 slope)
        if len(closes) >= 40:
            ma20_prev = np.mean(closes[20:40])
            slope = (ma20 - ma20_prev) / max(ma20_prev, 1e-9)
            if slope > 0.02:
                score += 10
                checks.append("uptrend")
            elif slope < -0.02:
                score -= 10
                checks.append("downtrend")

        score = max(0, min(100, score))
        signal = self._signal_from_score(score)

        return {
            "strategy_name": self.name,
            "signal": signal.value,
            "score": score,
            "confidence": min(0.8, max(0.3, abs(score - 50) / 50)),
            "detail": {
                "checks": checks,
                "ma5": round(ma5, 2),
                "ma10": round(ma10, 2),
                "ma20": round(ma20, 2),
                "ma60": round(ma60, 2),
            },
        }
