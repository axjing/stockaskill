"""Data structures for the stock selection system."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Market(str, Enum):
    A = "A"
    HK = "HK"
    US = "US"
    FUND = "FUND"


@dataclass
class StockInfo:
    code: str
    name: str
    market: str
    sector: str = ""
    industry: str = ""
    list_date: str = ""
    total_market_cap: float = 0.0
    is_active: bool = True


@dataclass
class KlineData:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


@dataclass
class FactorSnapshot:
    code: str
    date: str
    market_cap: float = 0.0
    pe_ttm: float = 0.0
    pe_static: float = 0.0
    pb: float = 0.0
    ps_ttm: float = 0.0
    pcf_ttm: float = 0.0
    dividend_yield: float = 0.0
    roe: float = 0.0
    roa: float = 0.0
    gross_margin: float = 0.0
    net_margin: float = 0.0
    revenue_growth: float = 0.0
    profit_growth: float = 0.0
    debt_ratio: float = 0.0
    current_ratio: float = 0.0
    eps: float = 0.0
    bvps: float = 0.0


@dataclass
class FactorResult:
    name: str
    score: float  # 0-1
    weight: float = 0.0
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategySignal:
    strategy_name: str
    signal: Signal
    score: float  # 0-100
    confidence: float = 0.5
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    code: str
    name: str = ""
    market: str = "A"
    weight: float = 0.0
    shares: int = 0
    cost: float = 0.0
    current_price: float = 0.0


@dataclass
class Portfolio:
    name: str
    capital: float = 0.0
    positions: List[Position] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Portfolio: {self.name}",
            f"Capital: {self.capital:,.0f}",
            f"Positions: {len(self.positions)}",
        ]
        total_w = sum(p.weight for p in self.positions)
        lines.append(f"Allocated: {total_w * 100:.1f}%")
        for p in self.positions:
            lines.append(
                f"  {p.code} {p.name}: {p.weight * 100:.1f}% "
                f"({p.shares} shares @ {p.cost:.2f})"
            )
        if self.metrics:
            lines.append("Risk Metrics:")
            for k, v in self.metrics.items():
                lines.append(f"  {k}: {v:.4f}")
        return "\n".join(lines)


@dataclass
class FundInfo:
    code: str
    name: str
    fund_type: str = ""  # ETF-first in the current FUND workflow
    nav: float = 0.0
    acc_nav: float = 0.0
    scale: float = 0.0
    track_index: str = ""
