"""Size factor: market cap (negative scoring for large cap)."""
from __future__ import annotations

import math
from typing import Any, Dict, List

from factors.base import Factor


class SizeFactor(Factor):
    """Market capitalization factor.

    Smaller market cap gets higher score (A-share small-cap premium).
    Score = 1 - log(mcap) / log(max_mcap)
    """

    @property
    def name(self) -> str:
        return "size"

    def compute(
        self,
        fundamentals: Dict[str, Any],
        kline: List[Dict[str, Any]],
        market: str = "A",
    ) -> float:
        mcap = self._safe(fundamentals.get("market_cap", 0))
        if mcap <= 0:
            return 0.5

        # Typical A-share range: 10B - 3T RMB
        log_mcap = math.log(mcap)
        # Normalize: 10B -> 1, 3T -> 0
        log_min = math.log(1e10)  # 10 billion
        log_max = math.log(3e12)  # 3 trillion
        size_score = max(0, min(1, 1 - (log_mcap - log_min) / (log_max - log_min)))
        return size_score
