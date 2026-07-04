"""Momentum factor: 6-month momentum excluding recent reversal."""

from typing import Any, Dict, List

import numpy as np

from factors.base import Factor


class MomentumFactor(Factor):
    """Price momentum factor.

    - 6-month return (excludes last 1 month to avoid reversal)
    - Moving average alignment bonus
    """

    @property
    def name(self) -> str:
        return "momentum"

    def compute(
        self,
        fundamentals: Dict[str, Any],
        kline: List[Dict[str, Any]],
        market: str = "A",
    ) -> float:
        if len(kline) < 120:
            return 0.5

        closes = [row.get("close", 0) for row in kline]
        closes = [c for c in closes if c > 0]
        if len(closes) < 120:
            return 0.5

        m1_ago = closes[20] if len(closes) > 20 else closes[0]
        m6_ago = closes[120] if len(closes) > 120 else closes[-1]
        ret_6m = (m1_ago - m6_ago) / max(m6_ago, 1e-9)

        ret_min, ret_max = self._range("ret_6m", market)
        ret_span = ret_max - ret_min
        mom_score = (
            max(0, min(1, (ret_6m - ret_min) / ret_span)) if ret_span > 0 else 0.5
        )

        ma_bonus = self._ma_alignment(closes)
        return min(1, max(0, mom_score * 0.7 + ma_bonus * 0.3))

    @staticmethod
    def _ma_alignment(closes: List[float]) -> float:
        """Check if moving averages are in bullish alignment."""
        if len(closes) < 60:
            return 0.5
        ma5 = np.mean(closes[:5])
        ma10 = np.mean(closes[:10])
        ma20 = np.mean(closes[:20])
        ma60 = np.mean(closes[:60])
        # Bullish: MA5 > MA10 > MA20 > MA60
        if ma5 > ma10 > ma20 > ma60:
            return 1.0
        if ma5 > ma10 > ma20:
            return 0.7
        if ma5 > ma10:
            return 0.4
        return 0.1
