"""Base factor class and normalization utilities."""
from __future__ import annotations

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
        """Normalize scores to [0, 1] using percentile rank."""
        if not scores:
            return scores
        vals = list(scores.values())
        vals_arr = np.array(vals, dtype=float)
        # Handle NaN
        valid = ~np.isnan(vals_arr)
        if not valid.any():
            return scores
        # Percentile rank
        ranks = np.zeros_like(vals_arr)
        sorted_vals = np.sort(vals_arr[valid])
        for i, v in enumerate(sorted_vals):
            pct = np.sum(vals_arr[valid] < v) / max(len(sorted_vals) - 1, 1)
            # Find all indices with this value
            mask = vals_arr == v
            ranks[mask] = pct
        # Clip to [0, 1]
        ranks = np.clip(ranks, 0, 1)
        result = {}
        codes = list(scores.keys())
        for i, code in enumerate(codes):
            result[code] = float(ranks[i])
        return result

    def _safe(self, val: Any, default: float = 0.0) -> float:
        """Safely convert to float."""
        try:
            v = float(val)
            if v != v:  # NaN check
                return default
            return v
        except (TypeError, ValueError):
            return default
