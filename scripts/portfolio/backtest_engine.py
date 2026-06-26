"""Alpha Momentum backtest engine: 2018-2026 simulation."""

import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from cache import get_cache
from data_engine import get_fundamentals
from factors.growth import GrowthFactor
from factors.low_vol import LowVolFactor
from factors.momentum import MomentumFactor
from factors.quality import QualityFactor
from factors.value import ValueFactor
from utils import is_st


class AlphaMomentumBacktest:
    """Backtest the Alpha Momentum strategy over historical data.

    Strategy: Momentum(30%)+LowVol(28%)+Quality(21%)+Value(14%)+Growth(7%)
    Selection: Top 6 stocks, monthly rebalance.
    Hard filters: low_vol < 0.4 excluded, EPS <= 0 excluded, ST excluded.
    Diversification: max 3 stocks per board (SH/SZ/SME/GEM/STAR).

    Args:
        capital: Initial portfolio capital.
        low_vol_min: Minimum low_vol score threshold.
        top_k: Number of stocks to select per rebalance.
        max_per_board: Maximum stocks per exchange board.
    """

    def __init__(
        self,
        capital: float = 1_000_000,
        low_vol_min: float = 0.4,
        top_k: int = 6,
        max_per_board: int = 3,
    ) -> None:
        self.capital = capital
        self.low_vol_min = low_vol_min
        self.top_k = top_k
        self.max_per_board = max_per_board

        self.mf = MomentumFactor()
        self.lf = LowVolFactor()
        self.qf = QualityFactor()
        self.vf = ValueFactor()
        self.gf = GrowthFactor()

    def run(self) -> Dict[str, Any]:
        """Run the backtest simulation.

        Returns:
            Dict with CAGR, total_return, sharpe, max_drawdown, and monthly_avg.
        """
        cache = get_cache()
        conn = sqlite3.connect(str(cache.db_path))
        cur = conn.execute("""
            SELECT d.code, d.date, d.close, COALESCE(s.name, \'\') as name
            FROM daily_price d
            LEFT JOIN stock_pool s ON d.code = s.code
            WHERE d.code IN (
                SELECT code FROM daily_price GROUP BY code HAVING COUNT(*) >= 1500
            )
            ORDER BY d.code, d.date ASC
        """)

        sd: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        st_codes: set[str] = set()
        for row in cur.fetchall():
            sd[row[0]].append({"date": row[1], "close": float(row[2])})
            if is_st(row[0], row[3]):
                st_codes.add(row[0])
        conn.close()

        codes = sorted(c for c in sd if c not in st_codes)

        fc: Dict[str, Dict[str, Any]] = {}
        for code in codes:
            try:
                f = get_fundamentals(code, "A", force_refresh=False)
                if f and f.get("eps", 0) > 0:
                    fc[code] = f
            except Exception:
                pass
        codes = sorted(fc.keys())

        all_d = sorted(set(d["date"] for code in codes for d in sd[code]))
        all_d = [d for d in all_d if d >= "2018-01-01"]
        md: Dict[str, str] = {}
        for d in all_d:
            md[d[:7]] = d
        rd = sorted(md.values())

        positions: Dict[str, int] = {}
        cash = self.capital
        nav: List[float] = []

        for i, reb_date in enumerate(rd):
            if i == 0:
                continue

            scored: List[tuple[str, float]] = []
            for code in codes:
                kslice = [x for x in sd[code] if x["date"] <= reb_date]
                if len(kslice) < 120:
                    continue
                fund = fc.get(code, {})
                try:
                    s = self.mf.compute(fund, kslice, "A")
                    l = self.lf.compute(kslice, "A")
                    q = self.qf.compute(fund, kslice, "A")
                    v = self.vf.compute(fund, kslice, "A")
                    g = self.gf.compute(fund, kslice, "A")
                    if l < self.low_vol_min:
                        continue
                    score = s * 0.30 + l * 0.28 + q * 0.21 + v * 0.14 + g * 0.07
                    if score > 0:
                        scored.append((code, score))
                except Exception:
                    continue

            scored.sort(key=lambda x: x[1], reverse=True)
            selected = self._select_diversified(scored)

            for code in list(positions.keys()):
                if code not in selected:
                    p = [x["close"] for x in sd[code] if x["date"] <= reb_date]
                    price = p[-1] if p else 0
                    if price > 0:
                        cash += positions[code] * price * (1 - 0.0003 - 0.001)
                        del positions[code]

            if selected:
                alloc = cash / len(selected)
                for code in selected:
                    if code not in positions:
                        p = [x["close"] for x in sd[code] if x["date"] <= reb_date]
                        price = p[-1] if p else 0
                        if price > 0:
                            shares = max(100, int(alloc / price / 100) * 100)
                            cost = shares * price * 1.0003
                            if cost <= cash and shares > 0:
                                positions[code] = shares
                                cash -= cost

            total = cash
            for code, shares in positions.items():
                p = [x["close"] for x in sd[code] if x["date"] <= reb_date]
                price = p[-1] if p else 0
                total += shares * price
            nav.append(total)

        final_date = all_d[-1]
        total = cash
        for code, shares in positions.items():
            p = [x["close"] for x in sd[code] if x["date"] <= final_date]
            price = p[-1] if p else 0
            total += shares * price
        nav.append(total)

        return self._compute_metrics(nav, rd)

    def _board(self, code: str) -> str:
        """Get exchange board for a stock code.

        Args:
            code: 6-digit stock code.

        Returns:
            Board name: SH, STAR, SZ, SME, GEM, or OTHER.
        """
        if code.startswith("60"):
            return "SH"
        if code.startswith("688"):
            return "STAR"
        if code.startswith("000"):
            return "SZ"
        if code.startswith("002"):
            return "SME"
        if code.startswith("300"):
            return "GEM"
        return "OTHER"

    def _select_diversified(
        self, scored: List[tuple[str, float]]
    ) -> List[str]:
        """Select top stocks with board diversification.

        Args:
            scored: List of (code, score) tuples, sorted by score descending.

        Returns:
            List of selected stock codes.
        """
        selected: List[str] = []
        board_count: Dict[str, int] = {}
        for code, score in scored:
            if score <= 0:
                continue
            board = self._board(code)
            if board_count.get(board, 0) >= self.max_per_board:
                continue
            selected.append(code)
            board_count[board] = board_count.get(board, 0) + 1
            if len(selected) >= self.top_k:
                break
        return selected

    def _compute_metrics(
        self, nav: List[float], rd: List[str]
    ) -> Dict[str, Any]:
        """Compute backtest performance metrics.

        Args:
            nav: List of portfolio NAV values.
            rd: List of rebalance dates.

        Returns:
            Dict with CAGR, total_return, sharpe, max_drawdown, monthly_avg.
        """
        na = np.array(nav)
        tr = (na[-1] - na[0]) / na[0]
        start_dt = datetime.strptime(rd[0] if len(rd) > 1 else rd[0], "%Y-%m-%d")
        ed_dt = datetime.strptime(rd[-1], "%Y-%m-%d")
        yr = max((ed_dt - start_dt).days / 365.25, 0.1)
        cagr = (na[-1] / na[0]) ** (1 / yr) - 1

        ra: List[float] = []
        for k in range(1, len(na)):
            if na[k - 1] > 0:
                ra.append((na[k] - na[k - 1]) / na[k - 1])
        ra_arr = np.array(ra)
        sh = 0.0
        if len(ra_arr) > 1 and np.std(ra_arr) > 0:
            sh = float(np.mean(ra_arr) / np.std(ra_arr) * np.sqrt(12))
        cum = np.cumprod(1 + ra_arr) if len(ra_arr) > 0 else np.array([1.0])
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak
        mdd = float(np.min(dd)) if len(dd) > 0 else 0.0

        return {
            "pool_size": len(rd) - 1,
            "period_start": rd[0] if len(rd) > 1 else rd[0],
            "period_end": rd[-1],
            "years": round(yr, 1),
            "cagr": round(cagr, 4),
            "total_return": round(tr, 4),
            "sharpe": round(sh, 2),
            "max_drawdown": round(mdd, 4),
            "monthly_avg": round(float(np.mean(ra_arr)) * 100, 2),
        }
