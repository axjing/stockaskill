"""Composite factor analyzer: aggregates all 7 factors + F-Score."""

from datetime import datetime
from typing import Any, Dict, List

from cache import get_cache
from config import get as cfg_get
from data_engine import get_fundamentals, get_kline
from utils import safe_float

from factors.base import Factor
from factors.growth import GrowthFactor
from factors.low_vol import LowVolFactor
from factors.momentum import MomentumFactor
from factors.quality import QualityFactor
from factors.size import SizeFactor
from factors.value import ValueFactor

_FACTORIES = [
    ValueFactor,
    QualityFactor,
    GrowthFactor,
    MomentumFactor,
    LowVolFactor,
    SizeFactor,
]


class CompositeAnalyzer:
    """Run all factors and produce a composite score."""

    def __init__(self, code: str, market: str = "A") -> None:
        self.code = code
        self.market = market

    def analyze(self, cached_only: bool = False) -> Dict[str, Any]:
        """Analyze all factors for the stock.

        Args:
            cached_only: Skip API calls, use only cached data.

        Returns:
            Dict with total_score, factors (name->score), f_score, details.
        """
        fundamentals = (
            get_fundamentals(self.code, self.market, cached_only=cached_only) or {}
        )
        kline = get_kline(self.code, self.market, days=365, cached_only=cached_only)
        return self.analyze_from_data(fundamentals, kline)

    def analyze_from_data(
        self,
        fundamentals: Dict[str, Any],
        kline: List[Dict[str, Any]],
        as_of_date: str = "",
        persist: bool = False,
    ) -> Dict[str, Any]:
        """Analyze using already-loaded local data.

        Args:
            fundamentals: Fundamental snapshot dict.
            kline: Daily price rows (newest first).
            as_of_date: Snapshot date for persistence/reporting.
            persist: Persist factor values into the computed-factors cache.

        Returns:
            Dict with total_score, factors (name->score), f_score, details.
        """
        result = self._analyze_with_inputs(fundamentals, kline, as_of_date=as_of_date)
        if persist and result["date"]:
            get_cache().upsert_computed_factors(
                self.code,
                result["date"],
                result["factors"],
            )
        return result

    def _analyze_with_inputs(
        self,
        fundamentals: Dict[str, Any],
        kline: List[Dict[str, Any]],
        as_of_date: str = "",
    ) -> Dict[str, Any]:
        """Shared scoring implementation for live and batch workflows."""

        factor_weights = cfg_get("factor_weights", {})
        factor_results: Dict[str, float] = {}
        factor_details: Dict[str, Dict[str, Any]] = {}

        total_score = 0.0
        total_weight = 0.0

        for factory in _FACTORIES:
            factor: Factor = factory()
            fname = factor.name
            weight = factor_weights.get(fname, factor.weight)
            score = factor.compute(fundamentals, kline, self.market)
            factor_results[fname] = score
            factor_details[fname] = {
                "score": round(score, 3),
                "weight": weight,
                "weighted": round(score * weight, 3),
            }
            total_score += score * weight
            total_weight += weight

        # Normalize by total weight
        if total_weight > 0:
            total_score = total_score / total_weight

        # F-Score (Piotroski)
        f_score = self._compute_fscore(fundamentals, kline)

        # Scale to 0-100
        composite_100 = total_score * 100

        return {
            "code": self.code,
            "market": self.market,
            "total_score": round(composite_100, 1),
            "factors": factor_results,
            "factor_details": factor_details,
            "f_score": f_score,
            "date": as_of_date or datetime.now().strftime("%Y-%m-%d"),
        }

    @staticmethod
    def _compute_fscore(
        fundamentals: Dict[str, Any], kline: List[Dict[str, Any]]
    ) -> int:
        """Piotroski F-Score (0-9).

        Criteria:
        1. ROA > 0
        2. Operating cash flow > 0 (proxied by EPS > 0)
        3. ROA increase YoY (proxied by profit_growth > 0)
        4. Accrual: CFO > ROA (proxied by EPS growth)
        5. Leverage decrease (debt_ratio < 0.5)
        6. Liquidity increase (current_ratio > 1)
        7. No dilution (simplified)
        8. Gross margin increase
        9. Asset turnover increase (simplified)
        """
        score = 0
        roa = fundamentals.get("roe", 0) or 0  # Use ROE as ROA proxy
        eps = fundamentals.get("eps", 0) or 0
        profit_g = fundamentals.get("profit_growth", 0) or 0
        debt = fundamentals.get("debt_ratio", 0) or 0
        curr = fundamentals.get("current_ratio", 0) or 0
        gm = safe_float(fundamentals.get("gross_margin", 0))
        net_m = safe_float(fundamentals.get("net_margin", 0))

        # 1. ROA > 0
        if roa > 0:
            score += 1
        # 2. Positive EPS (cash flow proxy)
        if eps > 0:
            score += 1
        # 3. Profit growth > 0
        if profit_g > 0:
            score += 1
        # 4. Accrual: EPS positive and growing
        if eps > 0 and profit_g > 0:
            score += 1
        # 5. Low leverage
        if debt < 0.5:
            score += 1
        # 6. Good liquidity
        if curr > 1:
            score += 1
        # 7. Revenue growth > 0 (proxy for no economic deterioration)
        if safe_float(fundamentals.get("revenue_growth", 0)) > 0:
            score += 1
        # 8. Gross margin > 20% (proxy for margin quality)
        if gm > 0.2:
            score += 1
        # 9. Net margin > 0 (proxy for asset efficiency)
        if net_m > 0:
            score += 1

        return score
