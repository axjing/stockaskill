"""Low volatility factor: 12-month daily volatility."""

from typing import Any, Dict, List

import numpy as np

from factors.base import Factor


class LowVolFactor(Factor):
    """Low volatility preference.

    Lower 12-month daily return volatility produces higher scores.
    Maximum single-day drop penalty applied.
    """

    @property
    def name(self) -> str:
        return "low_vol"

    def compute(
        self,
        fundamentals: Dict[str, Any],
        kline: List[Dict[str, Any]],
        market: str = "A",
    ) -> float:
        if len(kline) < 240:
            return 0.5

        closes = [row.get("close", 0) for row in kline[:250]]
        closes = [c for c in closes if c > 0]
        if len(closes) < 240:
            return 0.5

        returns = np.diff(np.array(closes)) / np.array(closes[:-1])
        returns = returns[~np.isnan(returns)]
        returns = returns[~np.isinf(returns)]

        if len(returns) < 10:
            return 0.5

        vol = np.std(returns)

        vol_min, vol_max = self._range("vol", market)
        drop_min, drop_max = self._range("max_drop", market)
        vol_range = vol_max - vol_min
        drop_range = drop_max - drop_min

        # Lower vol = higher score
        vol_score = (
            max(0, min(1, 1 - (vol - vol_min) / vol_range)) if vol_range > 0 else 0.5
        )

        # Max daily drop penalty
        max_drop = abs(np.min(returns)) if len(returns) > 0 else 0
        drop_penalty = (
            max(0, min(1, 1 - (max_drop - drop_min) / drop_range))
            if drop_range > 0
            else 0.5
        )

        return min(1, max(0, vol_score * 0.7 + drop_penalty * 0.3))
