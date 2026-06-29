"""Backtesting engine: daily simulation with transaction costs."""

from typing import Any, Dict, List

import numpy as np
from data_engine import get_kline

from portfolio.risk import RiskMetrics


class BacktestEngine:
    """Daily backtesting engine."""

    def __init__(
        self,
        capital: float = 1000000,
        commission: float = 0.0003,  # Default from config
        stamp_tax: float = 0.001,
        slippage: float = 0.001,
    ) -> None:
        self.initial_capital = capital
        self.capital = capital
        self.commission = commission  # Buy commission
        self.stamp_tax = stamp_tax  # Sell stamp tax (A-share)
        self.slippage = slippage
        self.positions: Dict[str, int] = {}  # code -> shares
        self.nav_history: List[float] = [capital]
        self.trade_log: List[Dict[str, Any]] = []

    def run(
        self,
        signals: List[Dict[str, Any]],
        start_date: str = "",
        end_date: str = "",
    ) -> Dict[str, Any]:
        """Run backtest on a list of stock signals.

        Args:
            signals: List of dicts with 'code', 'market', 'signal', 'score'.
            start_date: Backtest start date.
            end_date: Backtest end date.

        Returns:
            Dict with nav_history, returns, risk_metrics, trades.
        """
        # Fetch K-line data for all stocks
        all_kline: Dict[str, List[Dict[str, Any]]] = {}
        for sig in signals:
            kline = get_kline(sig["code"], sig.get("market", "A"), days=250)
            if kline:
                all_kline[sig["code"]] = kline

        if not all_kline:
            return {"error": "No K-line data available"}

        # Align by date
        dates = self._get_common_dates(all_kline)
        if not dates:
            return {"error": "No common dates"}

        # Run daily simulation
        for date in reversed(dates):
            self._step(date, all_kline, signals)

        returns = np.diff(self.nav_history) / self.nav_history[:-1]
        risk = RiskMetrics(returns.tolist())

        return {
            "initial_capital": self.initial_capital,
            "final_capital": self.nav_history[-1],
            "total_return": (self.nav_history[-1] - self.initial_capital)
            / self.initial_capital,
            "nav_history": self.nav_history,
            "risk_metrics": risk.summary(),
            "trades": self.trade_log,
            "num_trades": len(self.trade_log),
        }

    def _get_common_dates(
        self, all_kline: Dict[str, List[Dict[str, Any]]]
    ) -> List[str]:
        """Get common trading dates across all stocks."""
        date_sets = []
        for code, kline in all_kline.items():
            dates = set(r.get("date", "") for r in kline)
            dates.discard("")
            date_sets.append(dates)
        if not date_sets:
            return []
        common = date_sets[0]
        for ds in date_sets[1:]:
            common = common & ds
        return sorted(common, reverse=True)

    def _step(
        self,
        date: str,
        all_kline: Dict[str, List[Dict[str, Any]]],
        signals: List[Dict[str, Any]],
    ) -> None:
        """Execute one day of simulation."""
        # Update positions value
        portfolio_value = self.capital
        for code, shares in self.positions.items():
            if code in all_kline:
                kline = all_kline[code]
                day_data = next((r for r in kline if r.get("date") == date), None)
                if day_data:
                    price = day_data.get("close", 0)
                    portfolio_value += shares * price

        # Rebalance: sell SELL signals, buy BUY signals
        for sig in signals:
            code = sig["code"]
            if code not in all_kline:
                continue
            kline = all_kline[code]
            day_data = next((r for r in kline if r.get("date") == date), None)
            if not day_data:
                continue
            price = day_data.get("close", 0) * (1 + self.slippage)

            if sig.get("signal") == "SELL" and code in self.positions:
                shares = self.positions.pop(code)
                revenue = shares * price * (1 - self.commission - self.stamp_tax)
                self.capital += revenue
                self.trade_log.append(
                    {
                        "date": date,
                        "code": code,
                        "action": "SELL",
                        "shares": shares,
                        "price": price,
                    }
                )
            elif sig.get("signal") == "BUY" and code not in self.positions:
                alloc = portfolio_value * 0.10 / max(len(signals), 1)
                shares = int(alloc / price / 100) * 100
                if shares > 0:
                    cost = shares * price * (1 + self.commission)
                    if cost <= self.capital:
                        self.positions[code] = shares
                        self.capital -= cost
                        self.trade_log.append(
                            {
                                "date": date,
                                "code": code,
                                "action": "BUY",
                                "shares": shares,
                                "price": price,
                            }
                        )

        # Record NAV
        total = self.capital
        for code, shares in self.positions.items():
            if code in all_kline:
                kline = all_kline[code]
                day_data = next((r for r in kline if r.get("date") == date), None)
                if day_data:
                    total += shares * day_data.get("close", 0)
        self.nav_history.append(total)
