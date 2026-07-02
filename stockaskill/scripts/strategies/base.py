"""Base strategy class and signal enum."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from data_engine import get_fundamentals, get_kline
from models import Signal


class Strategy(ABC):
    """Abstract base class for all quantitative strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name."""

    @property
    def weight(self) -> float:
        """Strategy weight in aggregation."""
        weights = {
            "multi_factor": 0.30,
            "deep_value": 0.25,
            "garp": 0.20,
            "ma_trend": 0.15,
            "contrarian": 0.10,
            "alpha_momentum": 0.15,
        }
        return weights.get(self.name, 0.1)

    @abstractmethod
    def analyze(self, code: str, market: str = "A", cached_only: bool = False) -> Dict[str, Any]:
        """Analyze a stock and return a signal dict.

        Args:
            code: Stock code.
            market: Market identifier.
            cached_only: Skip API calls, use only cached data.

        Returns:
            Dict with signal, score, confidence, detail.
        """

    def _get_data(self, code: str, market: str, cached_only: bool = False) -> tuple:
        """Fetch fundamentals and K-line data."""
        fundamentals = get_fundamentals(code, market, cached_only=cached_only) or {}
        kline = get_kline(code, market, days=365, cached_only=cached_only)
        return fundamentals, kline

    @staticmethod
    def _safe(val: Any, default: float = 0.0) -> float:
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _signal_from_score(score: float) -> Signal:
        if score >= 65:
            return Signal.BUY
        if score <= 35:
            return Signal.SELL
        return Signal.HOLD
