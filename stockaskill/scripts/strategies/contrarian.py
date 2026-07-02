"""Contrarian strategy: oversold + undervalued + volume stabilization."""

from typing import Any, Dict, List, Tuple

import numpy as np

from strategies.base import Strategy

_OVERSOLD_BRACKETS: List[Tuple[float, int, str]] = [
    (0.25, 35, "deep_oversold"),
    (0.15, 25, "oversold"),
    (0.08, 10, ""),
]

_CHEAP_PE_BRACKETS: List[Tuple[float, int, str]] = [
    (12, 20, "cheap_pe"),
    (20, 10, ""),
]


class ContrarianStrategy(Strategy):
    """Contrarian / mean-reversion strategy.

    Criteria:
    - Price down > 15% from 60-day high
    - Low valuation (PE/PB below median)
    - Volume stabilization after sell-off
    - High safety margin
    """

    @property
    def name(self) -> str:
        return "contrarian"

    def analyze(self, code: str, market: str = "A", cached_only: bool = False) -> Dict[str, Any]:
        fund, kline = self._get_data(code, market, cached_only=cached_only)

        if len(kline) < 60:
            return {
                "strategy_name": self.name,
                "signal": "HOLD",
                "score": 50,
                "confidence": 0.2,
                "detail": {"reason": "insufficient_data"},
            }

        closes = [row.get("close", 0) for row in kline[:120]]
        current = closes[0] if closes else 0
        closes = [c for c in closes if c > 0]
        volumes = [row.get("volume", 0) for row in kline[:120]]
        high_60 = max(closes[:60]) if len(closes) >= 60 else current
        drawdown = (high_60 - current) / max(high_60, 1e-9)

        pe = self._safe(fund.get("pe_ttm", 0))
        pb = self._safe(fund.get("pb", 0))

        score = 0
        checks = []

        # Oversold: down > 15% from 60-day high
        for threshold, pts, label in _OVERSOLD_BRACKETS:
            if drawdown > threshold:
                score += pts
                if label:
                    checks.append(label)
                break

        # Low valuation
        for ceiling, pts, label in _CHEAP_PE_BRACKETS:
            if 0 < pe < ceiling:
                score += pts
                if label:
                    checks.append(label)
                break

        if pb > 0 and pb < 1.2:
            score += 15
            checks.append("cheap_pb")

        # Volume stabilization: recent volume < 60-day avg
        if volumes and len(volumes) >= 30:
            vol_recent = np.mean(volumes[:10])
            vol_60d = np.mean(volumes[:60])
            if vol_recent < vol_60d * 0.7:
                score += 15
                checks.append("volume_drying")
            elif vol_recent > vol_60d * 1.5:
                score += 10
                checks.append("volume_spike_recovery")

        # Safety margin
        if pe > 0 and self._safe(fund.get("dividend_yield", 0)) > 4:
            score += 15
            checks.append("high_yield_safety")

        score = max(0, min(100, score))
        signal = self._signal_from_score(score)

        return {
            "strategy_name": self.name,
            "signal": signal.value,
            "score": score,
            "confidence": min(0.75, max(0.3, score / 100)),
            "detail": {
                "checks": checks,
                "drawdown_60d": round(drawdown * 100, 1),
                "pe": round(pe, 1),
            },
        }
