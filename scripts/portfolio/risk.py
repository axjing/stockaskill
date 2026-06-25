"""Risk metrics: drawdown, VaR, CVaR, Sharpe, Sortino."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np


class RiskMetrics:
    """Calculate portfolio risk metrics from return series."""

    def __init__(self, returns: List[float], risk_free: float = 0.03) -> None:
        self.returns = np.array(returns, dtype=float)
        self.risk_free = risk_free
        self.daily_rf = risk_free / 252

    def max_drawdown(self) -> float:
        """Maximum drawdown from cumulative returns."""
        if len(self.returns) < 2:
            return 0.0
        cumulative = np.cumprod(1 + self.returns)
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / peak
        return float(np.min(drawdown))

    def var(self, confidence: float = 0.95) -> float:
        """Value at Risk at given confidence level."""
        if len(self.returns) < 2:
            return 0.0
        return float(np.percentile(self.returns, (1 - confidence) * 100))

    def cvar(self, confidence: float = 0.95) -> float:
        """Conditional VaR (Expected Shortfall)."""
        if len(self.returns) < 2:
            return 0.0
        threshold = np.percentile(self.returns, (1 - confidence) * 100)
        tail = self.returns[self.returns <= threshold]
        if len(tail) == 0:
            return float(threshold)
        return float(np.mean(tail))

    def sharpe_ratio(self) -> float:
        """Annualized Sharpe ratio."""
        if len(self.returns) < 2:
            return 0.0
        excess = self.returns - self.daily_rf
        mean_excess = np.mean(excess)
        std = np.std(excess, ddof=1)
        if std < 1e-10:
            return 0.0
        return float(mean_excess / std * np.sqrt(252))

    def sortino_ratio(self) -> float:
        """Annualized Sortino ratio (downside deviation)."""
        if len(self.returns) < 2:
            return 0.0
        excess = self.returns - self.daily_rf
        mean_excess = np.mean(excess)
        downside = self.returns[self.returns < 0]
        if len(downside) == 0:
            return 0.0
        down_std = np.std(downside, ddof=1)
        if down_std < 1e-10:
            return 0.0
        return float(mean_excess / down_std * np.sqrt(252))

    def volatility(self) -> float:
        """Annualized volatility."""
        if len(self.returns) < 2:
            return 0.0
        return float(np.std(self.returns, ddof=1) * np.sqrt(252))

    def summary(self) -> Dict[str, float]:
        """All risk metrics as a dict."""
        return {
            "max_drawdown": round(self.max_drawdown(), 4),
            "var_95": round(self.var(0.95), 4),
            "cvar_95": round(self.cvar(0.95), 4),
            "var_99": round(self.var(0.99), 4),
            "cvar_99": round(self.cvar(0.99), 4),
            "sharpe": round(self.sharpe_ratio(), 4),
            "sortino": round(self.sortino_ratio(), 4),
            "volatility": round(self.volatility(), 4),
        }
