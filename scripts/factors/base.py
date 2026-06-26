"""Base factor class and normalization utilities."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import numpy as np

from config import get as cfg_get


class Factor(ABC):
    """Abstract base class for all stock selection factors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Factor name (e.g. 'value', 'quality')."""

    @property
    def weight(self) -> float:
        """Default weight from config."""
        return cfg_get(f"factor_weights.{self.name}", 0.1)

    @abstractmethod
    def compute(
        self,
        fundamentals: Dict[str, Any],
        kline: List[Dict[str, Any]],
        market: str = "A",
    ) -> float:
        """Compute factor score for a single stock.

        Args:
            fundamentals: Fundamental snapshot dict.
            kline: K-line data list (newest first).
            market: Market identifier.

        Returns:
            Score in [0, 1].
        """

    def compute_batch(
        self,
        stocks: List[Dict[str, Any]],
        market: str = "A",
    ) -> Dict[str, float]:
        """Compute factor scores for a batch of stocks.

        Args:
            stocks: List of stock info dicts with fundamentals/kline.
            market: Market identifier.

        Returns:
            Dict mapping stock code to score [0, 1].
        """
        raw_scores: Dict[str, float] = {}
        for stock in stocks:
            code = stock.get("code", "")
            fund = stock.get("fundamentals", {})
            kline = stock.get("kline", [])
            score = self.compute(fund, kline, market)
            raw_scores[code] = score
        return self._normalize(raw_scores)

    @staticmethod
    def _normalize(scores: Dict[str, float]) -> Dict[str, float]:
        """Normalize scores to [0, 1] using percentile rank.

        Uses scipy.stats.rankdata for O(n log n) performance instead
        of the previous O(n^2) nested loop approach.

        Args:
            scores: Dict mapping stock code to raw factor score.

        Returns:
            Dict mapping stock code to normalized score in [0, 1].
        """
        if not scores:
            return scores
        from scipy.stats import rankdata

        vals = np.array(list(scores.values()), dtype=float)
        # Handle NaN: replace with median for ranking
        valid = ~np.isnan(vals)
        if not valid.any():
            return scores
        vals[~valid] = np.median(vals[valid])

        # Use rankdata for O(n log n) percentile ranking
        ranks = rankdata(vals, method="average") - 1
        n = len(ranks)
        normalized = ranks / max(n - 1, 1)
        normalized = np.clip(normalized, 0, 1)

        return dict(zip(scores.keys(), normalized.tolist()))

    def _safe(self, val: Any, default: float = 0.0) -> float:
        """Safely convert to float."""
        try:
            v = float(val)
            if v != v:  # NaN check
                return default
            return v
        except (TypeError, ValueError):
            return default
