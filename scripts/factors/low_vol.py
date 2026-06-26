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
            return 0.5  # Not enough data

        closes = [row.get("close", 0) for row in kline[:250]]
        closes = [c for c in closes if c > 0]
        if len(closes) < 240:
            return 0.5

        # Daily returns
        returns = np.diff(np.array(closes)) / np.array(closes[1:])
        returns = returns[~np.isnan(returns)]
        returns = returns[~np.isinf(returns)]

        if len(returns) < 10:
            return 0.5

        vol = np.std(returns)

        # Typical A-share daily vol range: 1% - 5%
        # Lower vol = higher score
        vol_score = max(0, min(1, 1 - (vol - 0.01) / 0.04))

        # Max daily drop penalty
        max_drop = abs(np.min(returns)) if len(returns) > 0 else 0
        drop_penalty = max(0, min(1, 1 - (max_drop - 0.03) / 0.07))

        return min(1, max(0, vol_score * 0.7 + drop_penalty * 0.3))
