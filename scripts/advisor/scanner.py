"""Market scanner: find top stocks across markets."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional

from data_engine import get_stock_pool, get_kline, get_fundamentals
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
        max_candidates: int = 0,
    ) -> List[Dict[str, Any]]:
        """Scan market and return top N stocks by composite score.

        Args:
            market: Market identifier (A/HK/US/FUND).
            top_n: Number of results.
            sector: Optional sector filter.
            min_mcap: Minimum market cap filter.
            max_mcap: Maximum market cap filter.
            max_candidates: Max stocks to evaluate (0=auto, default 200).

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

        # Sort by market cap descending, take top candidates
        filtered.sort(key=lambda s: float(s.get("total_market_cap", 0) or 0), reverse=True)
        limit = max_candidates or cfg_get("scan_max_candidates", 200)
        candidates = [s for s in filtered if not s.get("code", "").startswith("bj")][:limit]
        if not candidates:
            candidates = filtered[:limit]

        n = len(candidates)
        if n == 0:
            print("  No candidates to score (stock pool may be empty or all filtered out). "
                  "Use 'python scripts/run.py fetch pool' to refresh data.", flush=True)
            return []

        print(f"  Scoring {n} candidates (cached data only, no API calls during scan)...", flush=True)

        # Score each stock (parallel, cached-only for speed)
        results: List[Dict[str, Any]] = []

        def _score_one(stock: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            code = stock["code"]
            try:
                analyzer = CompositeAnalyzer(code, market)
                factor_result = analyzer.analyze(cached_only=True)
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
                }
            except Exception:
                return None

        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_score_one, stock): stock for stock in candidates}
            for f in as_completed(futures):
                done += 1
                if done % 25 == 0 or done == n:
                    print(f"  Scan progress: {done}/{n}", flush=True)

                result = f.result()
                if result is not None:
                    results.append(result)

        if not results:
            print("  All candidates scored 0 (no cached data yet). "
                  "Run 'python scripts/run.py diagnose' on individual stocks to build cache, "
                  "or use 'python scripts/run.py alpha A --top 20' for full scoring.", flush=True)
        else:
            print(f"  Scored {len(results)} stocks successfully.", flush=True)

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
