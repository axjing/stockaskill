"""Alpha Momentum backtest engine: 2018-2026 simulation."""

import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple

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

    Memory: processes data in 2-year windows (~3 years of kline per window)
    instead of loading entire history at once, reducing peak memory by ~3-5x.

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

        codes, st_codes = self._load_eligible_codes(conn)
        codes = sorted(c for c in codes if c not in st_codes)

        fc = self._load_fundamentals(codes)
        codes = sorted(fc.keys())

        all_d = self._load_dates(conn)
        md, rd = self._rebalance_dates(all_d)

        positions: Dict[str, int] = {}
        cash = self.capital
        nav: List[float] = []

        windows = self._build_windows(rd)
        for wstart, wend, wrd in windows:
            if not wrd:
                continue
            wsd = self._load_window_data(conn, wstart, wend)
            positions, cash, nav = self._process_window(
                wrd, wsd, fc, codes, positions, cash, nav
            )
            wsd.clear()

        if all_d[-1] != rd[-1]:
            total = cash
            for code, shares in positions.items():
                cur = conn.execute(
                    "SELECT close FROM daily_price "
                    "WHERE code=? AND date=?",
                    (code, all_d[-1]),
                )
                row = cur.fetchone()
                price = float(row[0]) if row else 0
                total += shares * price
            nav.append(total)

        conn.close()
        return self._compute_metrics(nav, rd)

    # -- Loading helpers -----------------------------------------------------

    def _load_eligible_codes(
        self, conn: sqlite3.Connection
    ) -> Tuple[List[str], set[str]]:
        """Get codes with sufficient data history and identify ST stocks.

        Returns:
            (all_eligible_codes, st_codes_set).
        """
        cur = conn.execute("""
            SELECT code FROM daily_price
            GROUP BY code HAVING COUNT(*) >= 1500
        """)
        all_codes = [row[0] for row in cur.fetchall()]

        st_codes: set[str] = set()
        for code in all_codes:
            cur = conn.execute(
                "SELECT COALESCE(s.name, '') FROM stock_pool s WHERE s.code=?",
                (code,),
            )
            row = cur.fetchone()
            name = row[0] if row else ""
            if is_st(code, name):
                st_codes.add(code)

        return all_codes, st_codes

    def _load_fundamentals(
        self, codes: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Load fundamentals for codes, keeping only EPS-positive stocks."""
        fc: Dict[str, Dict[str, Any]] = {}
        for code in codes:
            try:
                f = get_fundamentals(code, "A", force_refresh=False)
                if f and f.get("eps", 0) > 0:
                    fc[code] = f
            except Exception:
                pass
        return fc

    @staticmethod
    def _load_dates(conn: sqlite3.Connection) -> List[str]:
        """Get all unique trading dates from 2018 onwards."""
        cur = conn.execute(
            "SELECT DISTINCT date FROM daily_price "
            "WHERE date >= '2018-01-01' ORDER BY date"
        )
        return [row[0] for row in cur.fetchall()]

    @staticmethod
    def _rebalance_dates(
        all_d: List[str],
    ) -> Tuple[Dict[str, str], List[str]]:
        """Build month-end rebalance dates from all trading dates."""
        md: Dict[str, str] = {}
        for d in all_d:
            md[d[:7]] = d
        return md, sorted(md.values())

    @staticmethod
    def _build_windows(
        rd: List[str],
    ) -> List[Tuple[str, str, List[str]]]:
        """Build 2-year processing windows with 1-year lookback overlap.

        Each window loads data from (window_start - 1 year) to window_end,
        ensuring all factor computations have sufficient lookback history.

        Args:
            rd: Sorted rebalance date strings.

        Returns:
            List of (lookback_start, window_end, window_rd) tuples.
        """
        year_ranges = [
            ("2017-01-01", "2019-12-31"),
            ("2019-01-01", "2021-12-31"),
            ("2021-01-01", "2023-12-31"),
            ("2023-01-01", "2026-12-31"),
        ]
        windows = []
        for wstart, wend in year_ranges:
            w_rd = [r for r in rd if wstart[:4] <= r[:4] <= wend[:4]]
            if w_rd:
                windows.append((wstart, wend, w_rd))
        return windows

    @staticmethod
    def _load_window_data(
        conn: sqlite3.Connection,
        start: str,
        end: str,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Load kline (code, date, close) for a date range.

        Args:
            conn: SQLite connection.
            start: Inclusive start date (YYYY-MM-DD).
            end: Inclusive end date (YYYY-MM-DD).

        Returns:
            Dict mapping code to list of {date, close} dicts (ascending date).
        """
        cur = conn.execute("""
            SELECT d.code, d.date, d.close
            FROM daily_price d
            WHERE d.date >= ? AND d.date <= ?
            ORDER BY d.code, d.date ASC
        """, (start, end))

        wsd: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in cur.fetchall():
            wsd[row[0]].append({"date": row[1], "close": float(row[2])})
        return wsd

    # -- Window processing ---------------------------------------------------

    def _process_window(
        self,
        wrd: List[str],
        wsd: Dict[str, List[Dict[str, Any]]],
        fc: Dict[str, Dict[str, Any]],
        all_codes: List[str],
        prev_positions: Dict[str, int],
        prev_cash: float,
        prev_nav: List[float],
    ) -> Tuple[Dict[str, int], float, List[float]]:
        """Process all rebalance dates within a single data window.

        Args:
            wrd: Rebalance dates for this window.
            wsd: Window kline data (code -> [{date, close}]).
            fc: Fundamentals dict.
            all_codes: All eligible stock codes.
            prev_positions: Positions carried from previous window.
            prev_cash: Cash carried from previous window.
            prev_nav: NAV history accumulated so far.

        Returns:
            (positions, cash, nav) after processing this window.
        """
        positions = dict(prev_positions)
        cash = prev_cash
        nav = list(prev_nav)
        codes = [c for c in all_codes if c in wsd]

        for i, reb_date in enumerate(wrd):
            if i == 0 and not nav:
                continue

            scored = self._score_codes(codes, wsd, fc, reb_date)
            scored.sort(key=lambda x: x[1], reverse=True)
            selected = self._select_diversified(scored)

            positions, cash = self._sell_others(
                positions, cash, selected, wsd, reb_date
            )
            positions, cash = self._buy_new(
                positions, cash, selected, wsd, reb_date
            )

            total = cash
            for code, shares in positions.items():
                p = [x["close"] for x in wsd[code] if x["date"] <= reb_date]
                price = p[-1] if p else 0
                total += shares * price
            nav.append(total)

        return positions, cash, nav

    # -- Rebalance helpers ---------------------------------------------------

    def _score_codes(
        self,
        codes: List[str],
        wsd: Dict[str, List[Dict[str, Any]]],
        fc: Dict[str, Dict[str, Any]],
        reb_date: str,
    ) -> List[Tuple[str, float]]:
        """Compute composite factor scores for all codes at a rebalance date."""
        scored: List[Tuple[str, float]] = []
        for code in codes:
            kslice = [x for x in wsd[code] if x["date"] <= reb_date]
            if len(kslice) < 120:
                continue
            fund = fc.get(code, {})
            try:
                s = self.mf.compute(fund, kslice, "A")
                lv = self.lf.compute(kslice, "A")
                q = self.qf.compute(fund, kslice, "A")
                v = self.vf.compute(fund, kslice, "A")
                g = self.gf.compute(fund, kslice, "A")
                if lv < self.low_vol_min:
                    continue
                score = s * 0.30 + lv * 0.28 + q * 0.21 + v * 0.14 + g * 0.07
                if score > 0:
                    scored.append((code, score))
            except Exception:
                continue
        return scored

    def _sell_others(
        self,
        positions: Dict[str, int],
        cash: float,
        selected: List[str],
        wsd: Dict[str, List[Dict[str, Any]]],
        reb_date: str,
    ) -> Tuple[Dict[str, int], float]:
        """Sell positions not in the selected set."""
        for code in list(positions.keys()):
            if code not in selected:
                p = [x["close"] for x in wsd.get(code, []) if x["date"] <= reb_date]
                price = p[-1] if p else 0
                if price > 0:
                    cash += positions[code] * price * (1 - 0.0003 - 0.001)
                    del positions[code]
        return positions, cash

    def _buy_new(
        self,
        positions: Dict[str, int],
        cash: float,
        selected: List[str],
        wsd: Dict[str, List[Dict[str, Any]]],
        reb_date: str,
    ) -> Tuple[Dict[str, int], float]:
        """Buy selected stocks not already held, equal-weight allocation."""
        if not selected:
            return positions, cash
        alloc = cash / len(selected)
        for code in selected:
            if code not in positions:
                p = [x["close"] for x in wsd.get(code, []) if x["date"] <= reb_date]
                price = p[-1] if p else 0
                if price > 0:
                    shares = max(100, int(alloc / price / 100) * 100)
                    cost = shares * price * 1.0003
                    if cost <= cash and shares > 0:
                        positions[code] = shares
                        cash -= cost
        return positions, cash

    # -- Diversification -----------------------------------------------------

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

    def _select_diversified(self, scored: List[Tuple[str, float]]) -> List[str]:
        """Select top stocks with board diversification.

        Args:
            scored: List of (code, score) tuples, sorted by score descending.

        Returns:
            List of selected stock codes.
        """
        selected: List[str] = []
        board_count: Dict[str, int] = {}
        for code, s in scored:
            if s <= 0:
                continue
            board = self._board(code)
            if board_count.get(board, 0) >= self.max_per_board:
                continue
            selected.append(code)
            board_count[board] = board_count.get(board, 0) + 1
            if len(selected) >= self.top_k:
                break
        return selected

    # -- Metrics -------------------------------------------------------------

    def _compute_metrics(self, nav: List[float], rd: List[str]) -> Dict[str, Any]:
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
