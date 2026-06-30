"""Size factor: market cap (negative scoring for large cap)."""

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

        log_mcap = math.log(mcap)
        log_min, log_max = self._range("mcap", market)
        log_range = log_max - log_min
        if log_range <= 0:
            return 0.5
        # Smaller cap -> higher score
        size_score = max(0, min(1, 1 - (log_mcap - log_min) / log_range))
        return size_score
