"""Market scanner: find top stocks across markets."""
from __future__ import annotations

<<<<<<< HEAD
import logging
=======
from concurrent.futures import ThreadPoolExecutor, as_completed
>>>>>>> 1e809508ea3cc839c82ccac2435f54f6b0e27ed4
from datetime import datetime
from typing import Any, Dict, List, Optional

from cache import get_cache
from data_engine import get_stock_pool, get_kline, get_fundamentals

logger = logging.getLogger(__name__)
from factors.composite import CompositeAnalyzer
from config import get as cfg_get
from utils import is_st, is_new


class MarketScanner:
    """Scan and rank stocks by composite score."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}

    def scan_top(
        self,
        market: str = "A",
        top_n: int = 20,
        sector: Optional[str] = None,
        min_mcap: float = 0,
        max_mcap: float = float("inf"),
<<<<<<< HEAD
        max_analyze: int = 50,
=======
        max_candidates: int = 0,
>>>>>>> 1e809508ea3cc839c82ccac2435f54f6b0e27ed4
    ) -> List[Dict[str, Any]]:
        """Scan market and return top N stocks by composite score.

        To avoid scoring thousands of stocks, the pool is pre-sorted by
        market cap descending and only *max_analyze* candidates are fully
        evaluated.

        Args:
            market: Market identifier (A/HK/US/FUND).
            top_n: Number of results.
            sector: Optional sector filter.
            min_mcap: Minimum market cap filter.
            max_mcap: Maximum market cap filter.
<<<<<<< HEAD
            max_analyze: Max stocks to fully score (default 200).
=======
            max_candidates: Max stocks to evaluate (0=auto, default 200).
>>>>>>> 1e809508ea3cc839c82ccac2435f54f6b0e27ed4

        Returns:
            List of dicts with code, name, score, and factor details.
        """
        pool = get_stock_pool(market)
        if not pool:
            return []

        # Apply filters
        filtered = []
        for stock in pool:
            code = stock.get("code", "")
            name = stock.get("name", "")

            # Filter ST/delisted
            if is_st(code, name):
                continue

            # Filter new stocks
            list_date = stock.get("list_date", "")
            if is_new(list_date, threshold_days=60):
                continue

            # Sector filter
            if sector and stock.get("sector") != sector:
                continue

            # Market cap filter
            mcap = stock.get("total_market_cap", 0) or 0
            if mcap < min_mcap or mcap > max_mcap:
                continue

            filtered.append(stock)

        if not filtered:
            return []

<<<<<<< HEAD
        # Sort: prefer stocks with cached kline, then by code (SH/SZ > BJ)
        _cache_inst = get_cache()
        def _score(stock):
            code = stock.get("code", "")
            has_cache = 1 if code and _cache_inst.get_daily_price(code) else 0
            priority = 0 if code.startswith(("6", "0", "3")) else 1
            return (has_cache, priority, code)
        filtered.sort(key=_score, reverse=True)
        candidates = filtered[:max_analyze]

        # Score each candidate
        results = []
        for stock in candidates:
=======
        # Sort by market cap descending, take top candidates
        filtered.sort(key=lambda s: float(s.get("total_market_cap", 0) or 0), reverse=True)
        limit = max_candidates or cfg_get("scan_max_candidates", 200)
        candidates = [s for s in filtered if not s.get("code", "").startswith("bj")][:limit]
        if not candidates:
            candidates = filtered[:limit]

        # Score each stock (parallel)
        results: List[Dict[str, Any]] = []

        def _score_one(stock: Dict[str, Any]) -> Optional[Dict[str, Any]]:
>>>>>>> 1e809508ea3cc839c82ccac2435f54f6b0e27ed4
            code = stock["code"]
            try:
                analyzer = CompositeAnalyzer(code, market)
                factor_result = analyzer.analyze()
                score = factor_result.get("total_score", 0)
                return {
                    "code": code,
                    "name": stock.get("name", ""),
                    "market": market,
                    "total_score": score,
                    "sector": stock.get("sector", ""),
                    "industry": stock.get("industry", ""),
                    "market_cap": stock.get("total_market_cap", 0),
                    "factors": factor_result.get("factors", {}),
                    "f_score": factor_result.get("f_score", 0),
<<<<<<< HEAD
                })
            except Exception as e:
                logger.warning("scan analyze %s failed: %s", code, e)
                continue
=======
                }
            except Exception:
                return None

        n = len(candidates)
        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_score_one, stock): stock for stock in candidates}
            for f in as_completed(futures):
                done += 1
                if done % 10 == 0 or done == n:
                    print(f"  Scan progress: {done}/{n}")
                result = f.result()
                if result is not None:
                    results.append(result)
>>>>>>> 1e809508ea3cc839c82ccac2435f54f6b0e27ed4

        # Sort by score descending
        results.sort(key=lambda x: x["total_score"], reverse=True)
        return results[:top_n]

    def scan_by_sector(
        self, market: str = "A", top_n: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Scan by sector, return top N per sector.

        Args:
            market: Market identifier.
            top_n: Results per sector.

        Returns:
            Dict mapping sector name to top stocks list.
        """
        pool = get_stock_pool(market)
        if not pool:
            return {}

        # Group by sector
        sectors: Dict[str, List[Dict[str, Any]]] = {}
        for stock in pool:
            sector = stock.get("sector", "Unknown")
            sectors.setdefault(sector, []).append(stock)

        result = {}
        for sector, stocks in sectors.items():
            top = self.scan_top(market, top_n, sector=sector)
            if top:
                result[sector] = top

        return result

    def scan_funds(
        self,
        fund_type: str = "ETF",
        top_n: int = 20,
    ) -> List[Dict[str, Any]]:
        """Scan funds by type.

        Args:
            fund_type: 'ETF', 'LOF', 'Index', 'Active'.
            top_n: Number of results.

        Returns:
            List of fund dicts with code, name, nav, scale.
        """
        from data_engine import get_fund_pool

        funds = get_fund_pool()
        if not funds:
            return []

        # Filter by type
        filtered = [f for f in funds if f.get("fund_type", "") == fund_type]

        # Sort by scale descending
        filtered.sort(
            key=lambda x: float(x.get("scale", 0) or 0), reverse=True
        )

        return filtered[:top_n]
