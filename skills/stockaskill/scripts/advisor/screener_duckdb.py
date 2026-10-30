"""Vectorized cross-sectional stock screener powered by DuckDB OLAP engine.

Provides sub-second multi-factor screening across millions of historical
price rows for A, HK, and US equities.
"""

from typing import Any, Dict, List, Optional

from cache import get_cache


class DuckDBScreener:
    """Sub-second cross-sectional screener operating directly on DuckDB."""

    def __init__(self) -> None:
        self.cache = get_cache()
        self.engine = getattr(self.cache, "engine", None)

    def screen(
        self,
        market: str = "A",
        preset: str = "momentum_enhanced",
        top_n: int = 10,
        min_mcap: float = 0,
        sector: Optional[str] = None,
        lookback_days: int = 365,
    ) -> List[Dict[str, Any]]:
        """Screen and rank universe based on quantitative presets.

        Args:
            market: Target market (A, HK, US).
            preset: Strategy preset (momentum_enhanced, low_vol, deep_value,
                balanced).
            top_n: Number of candidate stocks to return.
            min_mcap: Minimum market cap filter in亿元.
            sector: Optional industry sector filter.
            lookback_days: Days of recent history to evaluate.

        Returns:
            List of ranked candidate dicts with score and metrics.
        """
        if self.engine is None:
            from advisor.scanner import MarketScanner

            return MarketScanner().scan_top(
                market=market, top_n=top_n, sector=sector, min_mcap=min_mcap
            )

        if preset in ("low_vol", "low_volatility"):
            return self._screen_low_vol(
                market=market, top_n=top_n, min_mcap=min_mcap, sector=sector
            )
        elif preset in ("deep_value", "value"):
            return self._screen_value(
                market=market, top_n=top_n, min_mcap=min_mcap, sector=sector
            )
        else:
            return self._screen_momentum(
                market=market, top_n=top_n, min_mcap=min_mcap, sector=sector
            )

    def _screen_momentum(
        self,
        market: str,
        top_n: int,
        min_mcap: float,
        sector: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Screen for high-momentum leaders with trend confirmation."""
        sector_filter = "AND sp.sector = ?" if sector else ""
        mcap_filter = "AND sp.total_market_cap >= ?" if min_mcap > 0 else ""

        params: List[Any] = [market]
        if sector:
            params.append(sector)
        if min_mcap > 0:
            params.append(min_mcap)
        params.append(top_n)

        sql = f"""
        WITH windowed AS (
            SELECT
                dp.code,
                dp.market,
                dp.date,
                dp.close,
                LAG(dp.close, 20) OVER (
                    PARTITION BY dp.code ORDER BY dp.date
                ) as close_20d,
                LAG(dp.close, 60) OVER (
                    PARTITION BY dp.code ORDER BY dp.date
                ) as close_60d,
                LAG(dp.close, 120) OVER (
                    PARTITION BY dp.code ORDER BY dp.date
                ) as close_120d,
                ROW_NUMBER() OVER (
                    PARTITION BY dp.code ORDER BY dp.date DESC
                ) as rn
            FROM daily_price dp
            WHERE dp.market = ? AND dp.date >= '2025-01-01'
        ),
        latest_ranks AS (
            SELECT
                w.code,
                w.market,
                w.date as latest_date,
                w.close as current_price,
                w.close_20d,
                w.close_60d,
                w.close_120d,
                (w.close - w.close_20d) / NULLIF(w.close_20d, 0) as ret_20d,
                (w.close - w.close_60d) / NULLIF(w.close_60d, 0) as ret_60d,
                (w.close - w.close_120d) / NULLIF(w.close_120d, 0) as ret_120d
            FROM windowed w
            WHERE w.rn = 1 AND w.close > 0 AND w.close_60d > 0
        )
        SELECT
            lr.code,
            COALESCE(sp.name, lr.code) as name,
            COALESCE(sp.sector, '') as sector,
            COALESCE(sp.industry, '') as industry,
            COALESCE(sp.total_market_cap, 0) as market_cap,
            lr.latest_date,
            lr.current_price,
            lr.ret_20d,
            lr.ret_60d,
            lr.ret_120d,
            (COALESCE(lr.ret_60d, 0) * 0.6 + COALESCE(lr.ret_120d, 0) * 0.4) as score
        FROM latest_ranks lr
        LEFT JOIN stock_pool sp ON lr.code = sp.code AND lr.market = sp.market
        WHERE lr.current_price > 2.0
          AND (sp.is_active IS NULL OR sp.is_active = 1)
          {sector_filter}
          {mcap_filter}
        ORDER BY score DESC
        LIMIT ?
        """
        raw = self.engine.fetchall(sql, tuple(params))
        results = []
        for r in raw:
            results.append(
                {
                    "code": r["code"],
                    "name": r.get("name", r["code"]),
                    "sector": r.get("sector", ""),
                    "industry": r.get("industry", ""),
                    "market": market,
                    "latest_date": r.get("latest_date", ""),
                    "current_price": round(float(r.get("current_price", 0)), 2),
                    "score": round(float(r.get("score", 0)) * 100, 2),
                    "metrics": {
                        "ret_20d": round(float(r.get("ret_20d", 0) or 0) * 100, 2),
                        "ret_60d": round(float(r.get("ret_60d", 0) or 0) * 100, 2),
                        "ret_120d": round(float(r.get("ret_120d", 0) or 0) * 100, 2),
                        "market_cap": round(float(r.get("market_cap", 0) or 0), 2),
                    },
                }
            )
        return results

    def _screen_low_vol(
        self,
        market: str,
        top_n: int,
        min_mcap: float,
        sector: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Screen for low-volatility defensive stocks."""
        sector_filter = "AND sp.sector = ?" if sector else ""
        mcap_filter = "AND sp.total_market_cap >= ?" if min_mcap > 0 else ""

        params: List[Any] = [market]
        if sector:
            params.append(sector)
        if min_mcap > 0:
            params.append(min_mcap)
        params.append(top_n)

        sql = f"""
        WITH recent_prices AS (
            SELECT
                code,
                market,
                date,
                close,
                (close - LAG(close) OVER (PARTITION BY code ORDER BY date))
                    / NULLIF(LAG(close) OVER (PARTITION BY code ORDER BY date), 0)
                    as daily_ret,
                ROW_NUMBER() OVER (
                    PARTITION BY code ORDER BY date DESC
                ) as rn
            FROM daily_price
            WHERE market = ? AND date >= '2025-06-01'
        ),
        vol_calc AS (
            SELECT
                code,
                market,
                MAX(date) as latest_date,
                ARGMAX(close, date) as current_price,
                STDDEV_POP(daily_ret) * SQRT(252) as ann_vol,
                COUNT(daily_ret) as trade_days
            FROM recent_prices
            WHERE rn <= 60
            GROUP BY code, market
            HAVING COUNT(daily_ret) >= 30 AND STDDEV_POP(daily_ret) > 0
        )
        SELECT
            vc.code,
            COALESCE(sp.name, vc.code) as name,
            COALESCE(sp.sector, '') as sector,
            COALESCE(sp.industry, '') as industry,
            COALESCE(sp.total_market_cap, 0) as market_cap,
            vc.latest_date,
            vc.current_price,
            vc.ann_vol,
            (1.0 / NULLIF(vc.ann_vol, 0)) as score
        FROM vol_calc vc
        LEFT JOIN stock_pool sp ON vc.code = sp.code AND vc.market = sp.market
        WHERE vc.current_price > 2.0
          {sector_filter}
          {mcap_filter}
        ORDER BY vc.ann_vol ASC
        LIMIT ?
        """
        raw = self.engine.fetchall(sql, tuple(params))
        results = []
        for r in raw:
            ann_vol = float(r.get("ann_vol", 0) or 0)
            results.append(
                {
                    "code": r["code"],
                    "name": r.get("name", r["code"]),
                    "sector": r.get("sector", ""),
                    "industry": r.get("industry", ""),
                    "market": market,
                    "latest_date": r.get("latest_date", ""),
                    "current_price": round(float(r.get("current_price", 0)), 2),
                    "score": round(max(0, (0.50 - ann_vol)) * 200, 2),
                    "metrics": {
                        "annualized_vol": round(ann_vol * 100, 2),
                        "market_cap": round(float(r.get("market_cap", 0) or 0), 2),
                    },
                }
            )
        return results

    def _screen_value(
        self,
        market: str,
        top_n: int,
        min_mcap: float,
        sector: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Screen for high quality value stocks with reasonable PE/PB."""
        sector_filter = "AND sp.sector = ?" if sector else ""
        mcap_filter = "AND sp.total_market_cap >= ?" if min_mcap > 0 else ""

        params: List[Any] = [market]
        if sector:
            params.append(sector)
        if min_mcap > 0:
            params.append(min_mcap)
        params.append(top_n)

        sql = f"""
        WITH latest_p AS (
            SELECT
                code,
                market,
                date as latest_date,
                close as current_price,
                ROW_NUMBER() OVER (
                    PARTITION BY code ORDER BY date DESC
                ) as rn
            FROM daily_price
            WHERE market = ? AND date >= '2025-01-01'
        ),
        latest_f AS (
            SELECT
                code,
                market,
                pe_ttm,
                pb,
                roe,
                dividend_yield,
                ROW_NUMBER() OVER (
                    PARTITION BY code ORDER BY date DESC
                ) as rn
            FROM factor_snapshot
            WHERE market = ?
        )
        SELECT
            lp.code,
            COALESCE(sp.name, lp.code) as name,
            COALESCE(sp.sector, '') as sector,
            COALESCE(sp.industry, '') as industry,
            COALESCE(sp.total_market_cap, 0) as market_cap,
            lp.latest_date,
            lp.current_price,
            COALESCE(lf.pe_ttm, 0) as pe_ttm,
            COALESCE(lf.pb, 0) as pb,
            COALESCE(lf.roe, 0) as roe,
            COALESCE(lf.dividend_yield, 0) as dividend_yield,
            (COALESCE(lf.roe, 0) * 100.0 - COALESCE(lf.pe_ttm, 30.0)) as score
        FROM latest_p lp
        LEFT JOIN latest_f lf
            ON lp.code = lf.code AND lp.market = lf.market AND lf.rn = 1
        LEFT JOIN stock_pool sp ON lp.code = sp.code AND lp.market = sp.market
        WHERE lp.rn = 1
          AND lp.current_price > 2.0
          AND lf.pe_ttm > 0 AND lf.pe_ttm < 40
          AND lf.pb > 0 AND lf.pb < 5
          {sector_filter}
          {mcap_filter}
        ORDER BY score DESC
        LIMIT ?
        """
        raw = self.engine.fetchall(sql, tuple(params))
        results = []
        for r in raw:
            results.append(
                {
                    "code": r["code"],
                    "name": r.get("name", r["code"]),
                    "sector": r.get("sector", ""),
                    "industry": r.get("industry", ""),
                    "market": market,
                    "latest_date": r.get("latest_date", ""),
                    "current_price": round(float(r.get("current_price", 0)), 2),
                    "score": round(float(r.get("score", 0)), 2),
                    "metrics": {
                        "pe_ttm": round(float(r.get("pe_ttm", 0)), 2),
                        "pb": round(float(r.get("pb", 0)), 2),
                        "roe": round(float(r.get("roe", 0)) * 100, 2),
                        "dividend_yield": round(
                            float(r.get("dividend_yield", 0)) * 100, 2
                        ),
                    },
                }
            )
        return results
