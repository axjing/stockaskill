"""Data structures for the stock selection system."""

from dataclasses import asdict, dataclass, field
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


@dataclass
class WorkflowStep:
    """A single CLI step recommended by the workflow router."""

    title: str
    command: str
    purpose: str


@dataclass
class WorkflowRecommendation:
    """Structured recommendation for a user workflow."""

    intent: str
    market: str
    summary: str
    rationale: List[str] = field(default_factory=list)
    steps: List[WorkflowStep] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass
class WorkflowManifestStep:
    """A manifest-defined workflow step."""

    title: str
    command: str
    purpose: str
    artifact: str = ""
    when: str = ""


@dataclass
class WorkflowManifest:
    """A reusable workflow manifest loaded from disk."""

    name: str
    summary: str
    description: str = ""
    defaults: Dict[str, Any] = field(default_factory=dict)
    required_params: List[str] = field(default_factory=list)
    steps: List[WorkflowManifestStep] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass
class WorkflowRunPlan:
    """A resolved workflow plan after manifest parameter substitution."""

    name: str
    summary: str
    description: str
    market: str
    manifest_path: str
    context: Dict[str, Any] = field(default_factory=dict)
    missing_params: List[str] = field(default_factory=list)
    steps: List[WorkflowManifestStep] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass
class ThesisPostmortem:
    """Postmortem outcome attached to an investment thesis."""

    outcome: str
    reviewed_at: str
    notes: str = ""
    thesis_status: str = "closed"


@dataclass
class ThesisRecord:
    """Local-first thesis memory record."""

    thesis_id: str
    code: str
    market: str
    created_at: str
    source: str
    thesis_status: str
    signal: str
    score: float
    confidence_level: str
    confidence_score: float
    summary: str
    bull_case: List[str] = field(default_factory=list)
    bear_case: List[str] = field(default_factory=list)
    invalidation_conditions: List[str] = field(default_factory=list)
    notes: str = ""
    postmortem: ThesisPostmortem | None = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    diagnosis_report: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass
class ThemeCandidate:
    """Candidate company inside a theme layer."""

    code: str
    name: str
    layer: str
    layer_rank: int
    score: float
    market: str
    sector: str = ""
    industry: str = ""
    evidence: List[str] = field(default_factory=list)
    disconfirming_signals: List[str] = field(default_factory=list)


@dataclass
class ThemeLayerFinding:
    """Ranked supply-chain layer in a theme research report."""

    layer: str
    scarce_layer: str
    rank: int
    score: float
    why_here: str
    evidence: List[str] = field(default_factory=list)
    disconfirming_signals: List[str] = field(default_factory=list)
    candidates: List[ThemeCandidate] = field(default_factory=list)


@dataclass
class ThemeResearchReport:
    """Structured theme-research output."""

    theme: str
    resolved_theme: str
    market: str
    summary: str
    key_question: str
    next_checks: List[str] = field(default_factory=list)
    lower_priority_areas: List[str] = field(default_factory=list)
    layers: List[ThemeLayerFinding] = field(default_factory=list)
    confidence: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)
