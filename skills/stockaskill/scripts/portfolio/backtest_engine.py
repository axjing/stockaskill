"""Alpha Momentum backtest engine: 2018-2026 simulation (v2 cache only)."""

import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple

import numpy as np
from cache import get_cache
from config import get as cfg_get
from data_readiness import ensure_backtest_ready
from factors.growth import GrowthFactor
from factors.low_vol import LowVolFactor
from factors.momentum import MomentumFactor
from factors.quality import QualityFactor
from factors.value import ValueFactor
from utils import is_st

from portfolio.risk import RiskMetrics


class AlphaMomentumBacktest:
    """Backtest the Alpha Momentum strategy over historical data.

    Strategy: Momentum(30%)+LowVol(28%)+Quality(21%)+Value(14%)+Growth(7%)
    Selection: Top 6 stocks, monthly rebalance.
    Hard filters: low_vol < 0.4 excluded, EPS <= 0 excluded, ST excluded.
    Diversification: max 3 stocks per board (SH/SZ/SME/GEM/STAR).

    Memory: processes data in 2-year windows (~3 years of kline per window)
    instead of loading entire history at once, reducing peak memory by ~3-5x.

    Uses cache tables (daily_price, stock_pool) exclusively.
    Delegates metrics computation to portfolio.risk.RiskMetrics.

    Args:
        capital: Initial portfolio capital.
        low_vol_min: Minimum low_vol score threshold.
        top_k: Number of stocks to select per rebalance.
        max_per_board: Maximum stocks per exchange board.
        market: Market code ("A", "HK", "US"). Defaults from config.
    """

    def __init__(
        self,
        capital: float | None = None,
        low_vol_min: float | None = None,
        top_k: int | None = None,
        max_per_board: int | None = None,
        market: str | None = None,
    ) -> None:
        self.market = (
            market
            if market is not None
            else cfg_get("alpha_momentum.default_market", "A")
        )
        self.capital = (
            capital if capital is not None else cfg_get("backtest_capital", 1_000_000)
        )
        self.low_vol_min = (
            low_vol_min if low_vol_min is not None else cfg_get("low_vol_min", 0.4)
        )
        self.top_k = top_k if top_k is not None else cfg_get("alpha_momentum.top_k", 6)
        self.max_per_board = (
            max_per_board
            if max_per_board is not None
            else cfg_get("alpha_momentum.max_per_board", 3)
        )

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
        ensure_backtest_ready(self.market)
        cache = get_cache()
        conn = sqlite3.connect(str(cache.db_path))

        codes, st_codes = self._load_eligible_codes(conn)
        codes = sorted(c for c in codes if c not in st_codes)

        all_d = self._load_dates(conn)
        _, rd = self._rebalance_dates(all_d)

        positions: Dict[str, int] = {}
        cash = self.capital
        nav: List[float] = []

        windows = self._build_windows(rd)
        for wstart, wend, wrd in windows:
            if not wrd:
                continue
            wsd = self._load_window_data(conn, wstart, wend)
            positions, cash, nav = self._process_window(
                wrd, wsd, codes, positions, cash, nav, conn
            )
            wsd.clear()

        if all_d[-1] != rd[-1]:
            total = cash
            for code, shares in positions.items():
                cur = conn.execute(
                    "SELECT close FROM daily_price "
                    "WHERE market=? AND code=? AND date=?",
                    (self.market, code, all_d[-1]),
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
        min_bars = cfg_get("alpha_momentum.min_history_bars", 1500)
        cur = conn.execute(
            "SELECT code FROM daily_price "
            "WHERE market=? "
            "GROUP BY code HAVING COUNT(*) >= ?",
            (self.market, min_bars),
        )
        all_codes = [row[0] for row in cur.fetchall()]

        st_codes: set[str] = set()
        for code in all_codes:
            cur = conn.execute(
                "SELECT COALESCE(s.name, '') FROM stock_pool s "
                "WHERE s.market=? AND s.code=?",
                (self.market, code),
            )
            row = cur.fetchone()
            name = row[0] if row else ""
            if is_st(code, name):
                st_codes.add(code)

        return all_codes, st_codes

    def _load_fundamentals_as_of(
        self, codes: List[str], as_of_date: str, conn: sqlite3.Connection
    ) -> Dict[str, Dict[str, Any]]:
        """Load fundamentals for all codes as of a specific date.

        Uses point-in-time factor_snapshot queries to avoid look-ahead bias.
        For each code, returns the latest snapshot with date <= as_of_date.

        Args:
            codes: List of stock codes.
            as_of_date: Maximum date (YYYY-MM-DD).
            conn: SQLite connection.

        Returns:
            Dict mapping code to fundamentals dict (EPS-positive only).
        """
        if not codes:
            return {}
        placeholders = ",".join(["?" for _ in codes])
        cur = conn.execute(
            f"SELECT code, date, market_cap, pe_ttm, pe_static, pb, ps_ttm, "
            f"pcf_ttm, dividend_yield, roe, roa, gross_margin, net_margin, "
            f"revenue_growth, profit_growth, debt_ratio, current_ratio, eps, bvps "
            f"FROM factor_snapshot "
            f"WHERE market=? AND code IN ({placeholders}) AND date<=? "
            f"ORDER BY code, date DESC",
            (self.market, *codes, as_of_date),
        )
        # Pick latest per code (first occurrence due to DESC ordering)
        seen: set[str] = set()
        fc: Dict[str, Dict[str, Any]] = {}
        for row in cur.fetchall():
            code = row[0]
            if code not in seen:
                seen.add(code)
                eps = float(row[17] or 0)
                if eps > 0:
                    fc[code] = {
                        "code": code,
                        "date": row[1],
                        "market_cap": float(row[2] or 0),
                        "pe_ttm": float(row[3] or 0),
                        "pe_static": float(row[4] or 0),
                        "pb": float(row[5] or 0),
                        "ps_ttm": float(row[6] or 0),
                        "pcf_ttm": float(row[7] or 0),
                        "dividend_yield": float(row[8] or 0),
                        "roe": float(row[9] or 0),
                        "roa": float(row[10] or 0),
                        "gross_margin": float(row[11] or 0),
                        "net_margin": float(row[12] or 0),
                        "revenue_growth": float(row[13] or 0),
                        "profit_growth": float(row[14] or 0),
                        "debt_ratio": float(row[15] or 0),
                        "current_ratio": float(row[16] or 0),
                        "eps": eps,
                        "bvps": float(row[18] or 0),
                    }
        return fc

    def _load_dates(self, conn: sqlite3.Connection) -> List[str]:
        """Get all unique trading dates from config start_date onwards."""
        start = cfg_get("alpha_momentum.start_date", "2018-01-01")
        cur = conn.execute(
            "SELECT DISTINCT date FROM daily_price "
            "WHERE market=? AND date >= ? ORDER BY date",
            (self.market, start),
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
        year_ranges = cfg_get(
            "alpha_momentum.window_ranges",
            [
                ("2017-01-01", "2019-12-31"),
                ("2019-01-01", "2021-12-31"),
                ("2021-01-01", "2023-12-31"),
                ("2023-01-01", "2026-12-31"),
            ],
        )
        windows = []
        for wstart, wend in year_ranges:
            w_rd = [r for r in rd if wstart[:4] <= r[:4] <= wend[:4]]
            if w_rd:
                windows.append((wstart, wend, w_rd))
        return windows

    def _load_window_data(
        self,
        conn: sqlite3.Connection,
        start: str,
        end: str,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Load kline (code, date, close) for a date range (v2 table).

        Args:
            conn: SQLite connection.
            start: Inclusive start date (YYYY-MM-DD).
            end: Inclusive end date (YYYY-MM-DD).

        Returns:
            Dict mapping code to list of {date, close} dicts (ascending date).
        """
        cur = conn.execute(
            "SELECT d.code, d.date, d.close "
            "FROM daily_price d "
            "WHERE d.market=? AND d.date >= ? AND d.date <= ? "
            "ORDER BY d.code, d.date ASC",
            (self.market, start, end),
        )

        wsd: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in cur.fetchall():
            wsd[row[0]].append({"date": row[1], "close": float(row[2])})
        return wsd

    # -- Window processing ---------------------------------------------------

    def _process_window(
        self,
        wrd: List[str],
        wsd: Dict[str, List[Dict[str, Any]]],
        all_codes: List[str],
        prev_positions: Dict[str, int],
        prev_cash: float,
        prev_nav: List[float],
        conn: sqlite3.Connection,
    ) -> Tuple[Dict[str, int], float, List[float]]:
        """Process all rebalance dates within a single data window.

        Args:
            wrd: Rebalance dates for this window.
            wsd: Window kline data (code -> [{date, close}]).
            all_codes: All eligible stock codes.
            prev_positions: Positions carried from previous window.
            prev_cash: Cash carried from previous window.
            prev_nav: NAV history accumulated so far.
            conn: SQLite connection for point-in-time fundamental queries.

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

            # Load point-in-time fundamentals at each rebalance date
            fc = self._load_fundamentals_as_of(codes, reb_date, conn)
            active_codes = sorted(fc.keys())

            scored = self._score_codes(active_codes, wsd, fc, reb_date)
            scored.sort(key=lambda x: x[1], reverse=True)
            selected = self._select_diversified(scored)

            positions, cash = self._sell_others(
                positions, cash, selected, wsd, reb_date
            )
            positions, cash = self._buy_new(positions, cash, selected, wsd, reb_date)

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
        min_bars = cfg_get("alpha_momentum.min_kline_bars", 120)
        scored: List[Tuple[str, float]] = []
        for code in codes:
            kslice = [x for x in wsd[code] if x["date"] <= reb_date]
            if len(kslice) < min_bars:
                continue
            fund = fc.get(code, {})
            try:
                s = self.mf.compute(fund, kslice, self.market)
                lv = self.lf.compute(fund, kslice, self.market)
                q = self.qf.compute(fund, kslice, self.market)
                v = self.vf.compute(fund, kslice, self.market)
                g = self.gf.compute(fund, kslice, self.market)
                if lv < self.low_vol_min:
                    continue
                w = cfg_get("alpha_momentum.weights", {})
                score = (
                    s * w.get("momentum", 0.30)
                    + lv * w.get("low_vol", 0.28)
                    + q * w.get("quality", 0.21)
                    + v * w.get("value", 0.14)
                    + g * w.get("growth", 0.07)
                )
                if score > 0:
                    scored.append((code, score))
            except Exception:
                continue
        return scored

    @staticmethod
    def _sell_others(
        positions: Dict[str, int],
        cash: float,
        selected: List[str],
        wsd: Dict[str, List[Dict[str, Any]]],
        reb_date: str,
    ) -> Tuple[Dict[str, int], float]:
        """Sell positions not in the selected set."""
        commission = cfg_get("commission", 0.0003)
        stamp_tax = cfg_get("stamp_tax", 0.001)
        for code in list(positions.keys()):
            if code not in selected:
                p = [x["close"] for x in wsd.get(code, []) if x["date"] <= reb_date]
                price = p[-1] if p else 0
                if price > 0:
                    cash += positions[code] * price * (1 - commission - stamp_tax)
                    del positions[code]
        return positions, cash

    @staticmethod
    def _buy_new(
        positions: Dict[str, int],
        cash: float,
        selected: List[str],
        wsd: Dict[str, List[Dict[str, Any]]],
        reb_date: str,
    ) -> Tuple[Dict[str, int], float]:
        """Buy selected stocks not already held, equal-weight allocation."""
        if not selected:
            return positions, cash
        commission = cfg_get("commission", 0.0003)
        alloc = cash / len(selected)
        for code in selected:
            if code not in positions:
                p = [x["close"] for x in wsd.get(code, []) if x["date"] <= reb_date]
                price = p[-1] if p else 0
                if price > 0:
                    lot = cfg_get("alpha_momentum.lot_size", 100)
                    shares = max(lot, int(alloc / price / lot) * lot)
                    cost = shares * price * (1 + commission)
                    if cost <= cash and shares > 0:
                        positions[code] = shares
                        cash -= cost
        return positions, cash

    # -- Diversification -----------------------------------------------------

    def _select_diversified(self, scored: List[Tuple[str, float]]) -> List[str]:
        """Select top stocks with board diversification."""
        from utils import diversify_by_board

        filtered = [(code, s) for code, s in scored if s > 0]
        diversified = diversify_by_board(
            [{"code": code} for code, _ in filtered],
            max_per_board=self.max_per_board,
        )
        return [item["code"] for item in diversified[: self.top_k]]

    # -- Metrics -------------------------------------------------------------

    def _compute_metrics(self, nav: List[float], rd: List[str]) -> Dict[str, Any]:
        """Compute backtest performance metrics via RiskMetrics.

        Args:
            nav: List of portfolio NAV values at each rebalance date.
            rd: List of rebalance dates.

        Returns:
            Dict with CAGR, total_return, sharpe, max_drawdown, monthly_avg.
        """
        na = np.array(nav)
        total_return = (na[-1] - na[0]) / na[0]
        start_dt = datetime.strptime(rd[0], "%Y-%m-%d")
        end_dt = datetime.strptime(rd[-1], "%Y-%m-%d")
        years = max((end_dt - start_dt).days / 365.25, 0.1)
        cagr = (na[-1] / na[0]) ** (1 / years) - 1

        period_returns: List[float] = []
        for k in range(1, len(na)):
            if na[k - 1] > 0:
                period_returns.append((na[k] - na[k - 1]) / na[k - 1])

        ret_arr = np.array(period_returns)
        sharpe = 0.0
        if len(ret_arr) > 1 and np.std(ret_arr) > 0:
            sharpe = float(np.mean(ret_arr) / np.std(ret_arr) * np.sqrt(12))

        risk = RiskMetrics(period_returns)

        return {
            "pool_size": len(rd) - 1,
            "period_start": rd[0],
            "period_end": rd[-1],
            "years": round(years, 1),
            "cagr": round(cagr, 4),
            "total_return": round(total_return, 4),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(risk.max_drawdown(), 4),
            "monthly_avg": round(float(np.mean(ret_arr)) * 100, 2),
        }
