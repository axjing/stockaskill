"""Unified SQLite cache manager for the stock selection system."""

import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import get as cfg_get

_CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"
_DB_PATH = _CACHE_DIR / "quant_cache.db"


def _ensure_cache_dir() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS stock_pool (
        market TEXT, code TEXT, name TEXT,
        sector TEXT, industry TEXT, list_date TEXT,
        total_market_cap REAL, is_active INTEGER DEFAULT 1,
        metadata_source TEXT DEFAULT '', metadata_status TEXT DEFAULT '',
        metadata_completeness REAL DEFAULT 0,
        updated_at TIMESTAMP,
        PRIMARY KEY (market, code)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_stock_pool_market
        ON stock_pool(market)""",
    """CREATE TABLE IF NOT EXISTS daily_price (
        market TEXT, code TEXT, date TEXT, open REAL, high REAL, low REAL,
        close REAL, volume REAL, amount REAL,
        quality_flags TEXT DEFAULT '',
        PRIMARY KEY (market, code, date)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_daily_price_lookup
        ON daily_price(market, code, date)""",
    """CREATE TABLE IF NOT EXISTS factor_snapshot (
        market TEXT, code TEXT, date TEXT, market_cap REAL, pe_ttm REAL,
        pe_static REAL, pb REAL, ps_ttm REAL, pcf_ttm REAL,
        dividend_yield REAL, roe REAL, roa REAL, gross_margin REAL,
        net_margin REAL, revenue_growth REAL, profit_growth REAL,
        debt_ratio REAL, current_ratio REAL, eps REAL, bvps REAL,
        PRIMARY KEY (market, code, date)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_factor_snapshot_lookup
        ON factor_snapshot(market, code, date)""",
    """CREATE TABLE IF NOT EXISTS computed_factors (
        code TEXT, date TEXT, factor_name TEXT, factor_value REAL,
        PRIMARY KEY (code, date, factor_name)
    )""",
    """CREATE TABLE IF NOT EXISTS cache_meta (
        table_name TEXT PRIMARY KEY, last_updated TIMESTAMP,
        record_count INTEGER, status TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS api_usage (
        date TEXT, api_name TEXT, call_count INTEGER DEFAULT 1,
        PRIMARY KEY (date, api_name)
    )""",
    """CREATE TABLE IF NOT EXISTS fund_info (
        code TEXT PRIMARY KEY, name TEXT, fund_type TEXT,
        nav REAL, acc_nav REAL, scale REAL, track_index TEXT,
        updated_at TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS fund_nav (
        code TEXT, date TEXT, nav REAL, acc_nav REAL,
        PRIMARY KEY (code, date)
    )""",
    """CREATE TABLE IF NOT EXISTS stock_industry (
        code TEXT PRIMARY KEY, sector TEXT, industry TEXT,
        updated_at TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS market_index (
        index_code TEXT, date TEXT, open REAL, high REAL,
        low REAL, close REAL, volume REAL, amount REAL,
        PRIMARY KEY (index_code, date)
    )""",
    """CREATE TABLE IF NOT EXISTS trade_calendar (
        market TEXT, date TEXT, is_open INTEGER DEFAULT 1,
        PRIMARY KEY (market, date)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_trade_calendar_market
        ON trade_calendar(market)""",
    """CREATE TABLE IF NOT EXISTS kv_store (
        key TEXT PRIMARY KEY, value TEXT, expires REAL
    )""",
    """CREATE TABLE IF NOT EXISTS factor_weights (
        date TEXT, factor_name TEXT, weight REAL,
        PRIMARY KEY (date, factor_name)
    )""",
    """CREATE TABLE IF NOT EXISTS market_scan_snapshot (
        market TEXT, trade_date TEXT, code TEXT, eligible INTEGER,
        composite_score REAL, f_score INTEGER,
        value_score REAL, quality_score REAL, growth_score REAL,
        momentum_score REAL, low_vol_score REAL, size_score REAL,
        has_list_date INTEGER, has_fundamentals INTEGER, has_history INTEGER,
        is_st INTEGER DEFAULT 0, is_bj INTEGER DEFAULT 0,
        is_new_listing INTEGER DEFAULT 0,
        rank_score REAL, ineligible_reason TEXT, created_at TIMESTAMP,
        PRIMARY KEY (market, trade_date, code)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_market_scan_snapshot_lookup
        ON market_scan_snapshot(market, trade_date, eligible, rank_score)""",
    """CREATE TABLE IF NOT EXISTS sync_state (
        scope_type TEXT, scope_key TEXT, market TEXT, code TEXT, data_kind TEXT,
        last_success_at TIMESTAMP, last_covered_date TEXT,
        last_error TEXT, status TEXT,
        PRIMARY KEY (scope_type, scope_key, market, code, data_kind)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_sync_state_lookup
        ON sync_state(scope_type, scope_key, market, code)""",
]


class CacheManager:
    """Thread-safe SQLite cache with TTL and bulk upsert support."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        _ensure_cache_dir()
        self.db_path = Path(db_path) if db_path else _DB_PATH
        self._init_schema()

    # -- lifecycle ----------------------------------------------------------

    def _init_schema(self) -> None:
        with self._conn() as conn:
            for sql in _SCHEMA:
                conn.execute(sql)
            self._ensure_stock_pool_metadata_columns(conn)
            self._ensure_daily_price_adjust_type_column(conn)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _validate_kline_row(row: dict) -> bool:
        """Validate a K-line row before writing to cache.

        Rejects rows with:
        - Non-positive prices (close, open, high, low)
        - OHLC inconsistencies (high < low, close outside range, etc.)
        - Future dates
        """
        close = row.get("close", 0) or 0
        open_ = row.get("open", 0) or 0
        high = row.get("high", 0) or 0
        low = row.get("low", 0) or 0
        date_str = str(row.get("date", "")).strip()

        if close <= 0 or open_ <= 0 or high <= 0 or low <= 0:
            return False
        if high < low:
            return False
        if close > high or close < low:
            return False
        if open_ > high or open_ < low:
            return False
        if date_str and date_str > datetime.now().strftime("%Y-%m-%d"):
            return False
        return True

    def compute_vwap(self, amount: float, volume: float) -> float:
        """Compute VWAP from cached amount and volume.

        VWAP = amount / volume. Returns 0 if volume is 0.
        """
        if volume > 0 and amount > 0:
            return round(amount / volume, 4)
        return 0.0

    def check_data_completeness(
        self,
        market: str = "A",
    ) -> List[Dict[str, int]]:
        """Check data completeness against the trade calendar.

        Returns a list of dicts with code, actual_days, expected_days, missing_days
        for stocks that have fewer rows than the trade calendar.
        """
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT dp.code,
                       COUNT(dp.date) as actual_days,
                       (SELECT COUNT(*) FROM trade_calendar WHERE market=dp.market) as expected_days,
                       (SELECT COUNT(*) FROM trade_calendar WHERE market=dp.market) - COUNT(dp.date) as missing_days
                FROM daily_price dp
                WHERE dp.market=?
                GROUP BY dp.code
                HAVING actual_days < expected_days
                ORDER BY missing_days DESC
                """,
                (market,),
            )
            return [
                {
                    "code": row[0],
                    "actual_days": row[1],
                    "expected_days": row[2],
                    "missing_days": row[3],
                }
                for row in cur.fetchall()
            ]

    # -- stock pool ---------------------------------------------------------

    def upsert_stock_pool(self, rows: List[Dict[str, Any]]) -> None:
        """Bulk upsert stock pool entries (v2 table only)."""
        normalized_rows = []
        for row in rows:
            normalized = dict(row)
            normalized.setdefault("metadata_source", "")
            normalized.setdefault("metadata_status", "")
            normalized.setdefault("metadata_completeness", 0.0)
            normalized_rows.append(normalized)
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO stock_pool ("
                "market, code, name, sector, industry, list_date, "
                "total_market_cap, is_active, metadata_source, metadata_status, "
                "metadata_completeness, updated_at"
                ") VALUES ("
                ":market, :code, :name, :sector, :industry, :list_date, "
                ":total_market_cap, :is_active, :metadata_source, "
                ":metadata_status, :metadata_completeness, :updated_at"
                ") ON CONFLICT(market, code) DO UPDATE SET "
                "name=excluded.name, sector=excluded.sector, "
                "industry=excluded.industry, list_date=excluded.list_date, "
                "total_market_cap=excluded.total_market_cap, "
                "is_active=excluded.is_active, "
                "metadata_source=excluded.metadata_source, "
                "metadata_status=excluded.metadata_status, "
                "metadata_completeness=excluded.metadata_completeness, "
                "updated_at=excluded.updated_at",
                normalized_rows,
            )
            counts_by_market: Dict[str, int] = {}
            for row in normalized_rows:
                market = str(row.get("market", ""))
                counts_by_market[market] = counts_by_market.get(market, 0) + 1
            for market, count in counts_by_market.items():
                self._touch_meta(self._stock_pool_meta_key(market), count, conn)

    def get_stock_pool(
        self, market: str = "A", include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """Get stock pool for a market (v2 table).

        Args:
            market: Market identifier.
            include_inactive: If True, include delisted/inactive stocks
                to avoid survivorship bias in backtests.
        """
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            if include_inactive:
                cur = conn.execute(
                    "SELECT * FROM stock_pool WHERE market=?",
                    (market,),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM stock_pool WHERE market=? AND is_active=1",
                    (market,),
                )
            return [dict(r) for r in cur.fetchall()]

    def pool_needs_refresh(self, market: str = "A") -> bool:
        """Check if stock pool TTL has expired."""
        ttl = cfg_get("cache_ttl.pool", 86400)
        updated = self._meta_timestamp(self._stock_pool_meta_key(market))
        if updated is None:
            return True
        return (time.time() - updated) > ttl

    # -- daily price (K-line) ----------------------------------------------

    def upsert_daily_price(self, rows: List[Dict[str, Any]]) -> None:
        """Bulk upsert daily K-line data (v2 table only)."""
        for row in rows:
            row.setdefault("quality_flags", "")
            row.setdefault("adjust_type", "qfq")
        # Two-phase ingest: reject malformed rows before writing to cache
        validated = [r for r in rows if self._validate_kline_row(r)]
        rejected = len(rows) - len(validated)
        if rejected:
            import logging

            logging.getLogger(__name__).warning(
                "Rejected %d malformed K-line rows before cache ingestion",
                rejected,
            )
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO daily_price "
                "(market, code, date, open, high, low, close, volume, amount, "
                "quality_flags, adjust_type) "
                "VALUES (:market, :code, :date, :open, :high, :low, :close, "
                ":volume, :amount, :quality_flags, :adjust_type) "
                "ON CONFLICT(market, code, date) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, "
                "close=excluded.close, volume=excluded.volume, "
                "amount=excluded.amount, quality_flags=excluded.quality_flags, "
                "adjust_type=excluded.adjust_type",
                validated,
            )

    def get_daily_price(
        self,
        code: str,
        start_date: str = "",
        end_date: str = "",
        market: str = "A",
    ) -> List[Dict[str, Any]]:
        """Get K-line data for a stock (v2 table), optionally date-filtered."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            params: List[Any] = [market, code]
            query = "SELECT * FROM daily_price WHERE market=? AND code=?"
            if start_date:
                query += " AND date>=?"
                params.append(start_date)
            if end_date:
                query += " AND date<=?"
                params.append(end_date)
            query += " ORDER BY date DESC"
            cur = conn.execute(query, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def get_date_ranges(self, codes: List[str], market: str = "A") -> Dict[str, tuple]:
        """Get (earliest_date, latest_date) for many codes in one query.

        Args:
            codes: List of stock codes.
            market: Market identifier.

        Returns:
            Dict mapping code to (earliest, latest) date strings.
            Codes with no data are omitted.
        """
        if not codes:
            return {}
        placeholders = ",".join(["?" for _ in codes])
        with self._conn() as conn:
            cur = conn.execute(
                f"SELECT code, MIN(date), MAX(date) "
                f"FROM daily_price "
                f"WHERE market=? AND code IN ({placeholders}) "
                f"GROUP BY code",
                (market, *codes),
            )
            return {
                row[0]: (row[1], row[2]) for row in cur.fetchall() if row[1] and row[2]
            }

    def get_latest_date(self, code: str, market: str = "A") -> str | None:
        """Get the latest cached date for a stock (v2 table)."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT MAX(date) FROM daily_price WHERE market=? AND code=?",
                (market, code),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def get_earliest_date(self, code: str, market: str = "A") -> str | None:
        """Get the earliest cached date for a stock (v2 table)."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT MIN(date) FROM daily_price WHERE market=? AND code=?",
                (market, code),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def get_row_count(self, code: str, market: str = "A") -> int:
        """Get cached row count for a stock."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM daily_price WHERE market=? AND code=?",
                (market, code),
            )
            row = cur.fetchone()
            return row[0] if row else 0

    def get_latest_close(self, code: str, market: str = "A") -> float | None:
        """Get the latest close price for a stock."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT close FROM daily_price "
                "WHERE market=? AND code=? ORDER BY date DESC LIMIT 1",
                (market, code),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def get_market_cap_from_pool(self, code: str, market: str = "A") -> float | None:
        """Get market_cap from stock_pool for a given code."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT total_market_cap FROM stock_pool "
                "WHERE market=? AND code=? LIMIT 1",
                (market, code),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] and row[0] > 0 else None

    # -- factor snapshot ----------------------------------------------------

    def upsert_factor_snapshot(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert fundamental snapshots (v2 table only)."""
        v2_rows = []
        for row in rows:
            r = dict(row)
            r.setdefault("market", "")
            v2_rows.append(r)
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO factor_snapshot ("
                "market, code, date, market_cap, pe_ttm, pe_static, pb, ps_ttm, "
                "pcf_ttm, dividend_yield, roe, roa, gross_margin, net_margin, "
                "revenue_growth, profit_growth, debt_ratio, current_ratio, eps, "
                "bvps"
                ") VALUES ("
                ":market, :code, :date, :market_cap, :pe_ttm, :pe_static, :pb, "
                ":ps_ttm, :pcf_ttm, :dividend_yield, :roe, :roa, "
                ":gross_margin, :net_margin, :revenue_growth, :profit_growth, "
                ":debt_ratio, :current_ratio, :eps, :bvps"
                ") ON CONFLICT(market, code, date) DO UPDATE SET "
                "market_cap=excluded.market_cap, pe_ttm=excluded.pe_ttm, "
                "pe_static=excluded.pe_static, pb=excluded.pb, "
                "ps_ttm=excluded.ps_ttm, pcf_ttm=excluded.pcf_ttm, "
                "dividend_yield=excluded.dividend_yield, roe=excluded.roe, "
                "roa=excluded.roa, gross_margin=excluded.gross_margin, "
                "net_margin=excluded.net_margin, "
                "revenue_growth=excluded.revenue_growth, "
                "profit_growth=excluded.profit_growth, "
                "debt_ratio=excluded.debt_ratio, "
                "current_ratio=excluded.current_ratio, "
                "eps=excluded.eps, bvps=excluded.bvps",
                v2_rows,
            )

    def get_factor_snapshot_as_of(
        self,
        code: str,
        market: str,
        as_of_date: str,
    ) -> Dict[str, Any] | None:
        """Get the latest factor snapshot for a stock as of a specific date.

        Used for point-in-time backtesting to avoid look-ahead bias.

        Args:
            code: Stock code.
            market: Market identifier.
            as_of_date: Maximum date (YYYY-MM-DD).

        Returns:
            Factor snapshot dict or None.
        """
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM factor_snapshot "
                "WHERE market=? AND code=? AND date<=? "
                "ORDER BY date DESC LIMIT 1",
                (market, code, as_of_date),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_latest_factor_snapshot(
        self,
        code: str,
        market: str = "A",
    ) -> Dict[str, Any] | None:
        """Get the most recent fundamental snapshot for a stock (v2 table)."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM factor_snapshot "
                "WHERE market=? AND code=? ORDER BY date DESC LIMIT 1",
                (market, code),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def factor_snapshot_needs_refresh(
        self,
        code: str,
        market: str = "A",
        max_age_days: int = 120,
    ) -> bool:
        """Check whether the cached fundamental snapshot is stale."""
        snapshot = self.get_latest_factor_snapshot(code, market=market)
        if not snapshot:
            return True
        date_str = str(snapshot.get("date", "")).strip()
        if not date_str:
            return True
        try:
            snapshot_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return True
        return (datetime.now() - snapshot_date).days > max_age_days

    # -- sync state ---------------------------------------------------------

    def upsert_sync_state(self, rows: List[Dict[str, Any]]) -> None:
        """Bulk upsert sync-state rows."""
        if not rows:
            return
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO sync_state ("
                "scope_type, scope_key, market, code, data_kind, last_success_at, "
                "last_covered_date, last_error, status"
                ") VALUES ("
                ":scope_type, :scope_key, :market, :code, :data_kind, "
                ":last_success_at, :last_covered_date, :last_error, :status"
                ") ON CONFLICT(scope_type, scope_key, market, code, data_kind) "
                "DO UPDATE SET "
                "last_success_at=excluded.last_success_at, "
                "last_covered_date=excluded.last_covered_date, "
                "last_error=excluded.last_error, status=excluded.status",
                rows,
            )

    def get_sync_state(
        self,
        scope_type: str,
        scope_key: str,
        market: str = "",
        code: str = "",
        data_kind: str = "",
    ) -> List[Dict[str, Any]]:
        """Return sync-state rows for a scope, optionally filtered."""
        query = ["SELECT * FROM sync_state WHERE scope_type=? AND scope_key=?"]
        params: List[Any] = [scope_type, scope_key]
        if market:
            query.append("AND market=?")
            params.append(market)
        if code:
            query.append("AND code=?")
            params.append(code)
        if data_kind:
            query.append("AND data_kind=?")
            params.append(data_kind)
        query.append("ORDER BY market, code, data_kind")
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(" ".join(query), tuple(params))
            return [dict(row) for row in cur.fetchall()]

    # -- computed factors ---------------------------------------------------

    def upsert_computed_factors(
        self, code: str, date: str, factors: Dict[str, float]
    ) -> None:
        """Store computed factor values."""
        with self._conn() as conn:
            for name, value in factors.items():
                conn.execute(
                    "INSERT INTO computed_factors "
                    "(code, date, factor_name, factor_value) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(code, date, factor_name) DO UPDATE SET "
                    "factor_value=excluded.factor_value",
                    (code, date, name, value),
                )

    def get_computed_factors(self, code: str, date: str = "") -> Dict[str, float]:
        """Get computed factors for a stock."""
        with self._conn() as conn:
            if date:
                cur = conn.execute(
                    "SELECT factor_name, factor_value FROM computed_factors "
                    "WHERE code=? AND date=?",
                    (code, date),
                )
            else:
                cur = conn.execute(
                    "SELECT factor_name, factor_value FROM computed_factors "
                    "WHERE code=? AND date=("
                    "SELECT MAX(date) FROM computed_factors WHERE code=?"
                    ")",
                    (code, code),
                )
            return {row[0]: row[1] for row in cur.fetchall()}

    def get_latest_computed_factors(
        self, code: str
    ) -> Tuple[str | None, Dict[str, float]]:
        """Get the latest computed factor set and its date for a stock."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT MAX(date) FROM computed_factors WHERE code=?",
                (code,),
            )
            row = cur.fetchone()
            latest_date = row[0] if row and row[0] else None
            if not latest_date:
                return None, {}
            cur = conn.execute(
                "SELECT factor_name, factor_value FROM computed_factors "
                "WHERE code=? AND date=?",
                (code, latest_date),
            )
            return latest_date, {item[0]: item[1] for item in cur.fetchall()}

    # -- fund data ----------------------------------------------------------

    def upsert_fund_info(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert fund basic info."""
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO fund_info "
                "(code, name, fund_type, nav, acc_nav, scale, track_index, "
                "updated_at) "
                "VALUES (:code, :name, :fund_type, :nav, :acc_nav, :scale, "
                ":track_index, :updated_at) "
                "ON CONFLICT(code) DO UPDATE SET "
                "name=excluded.name, fund_type=excluded.fund_type, "
                "nav=excluded.nav, acc_nav=excluded.acc_nav, "
                "scale=excluded.scale, track_index=excluded.track_index, "
                "updated_at=excluded.updated_at",
                rows,
            )

    def get_fund_info(self, code: str) -> Dict[str, Any] | None:
        """Get fund info by code."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM fund_info WHERE code=?",
                (code,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_fund_nav(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert fund NAV history."""
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO fund_nav (code, date, nav, acc_nav) "
                "VALUES (:code, :date, :nav, :acc_nav) "
                "ON CONFLICT(code, date) DO UPDATE SET "
                "nav=excluded.nav, acc_nav=excluded.acc_nav",
                rows,
            )

    def get_fund_nav(self, code: str, days: int = 365) -> List[Dict[str, Any]]:
        """Get fund NAV history."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM fund_nav WHERE code=? AND date>=? ORDER BY date DESC",
                (code, cutoff),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_latest_fund_nav_date(self, code: str) -> str | None:
        """Get the latest cached date for a fund NAV."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT MAX(date) FROM fund_nav WHERE code=?",
                (code,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def is_market_data_empty(self, market: str) -> bool:
        """Return True when the cache has no K-line data for the given market."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM daily_price WHERE market=?",
                (market,),
            )
            return cur.fetchone()[0] == 0

    # -- market index -------------------------------------------------------

    def upsert_market_index(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert market index daily data."""
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO market_index "
                "(index_code, date, open, high, low, close, volume, amount) "
                "VALUES (:index_code, :date, :open, :high, :low, :close, "
                ":volume, :amount) "
                "ON CONFLICT(index_code, date) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, "
                "close=excluded.close, volume=excluded.volume, "
                "amount=excluded.amount",
                rows,
            )

    def get_market_index(
        self, index_code: str, days: int = 250
    ) -> List[Dict[str, Any]]:
        """Get market index K-line data."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM market_index "
                "WHERE index_code=? AND date>=? ORDER BY date DESC",
                (index_code, cutoff),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_latest_market_index_date(self, index_code: str) -> str | None:
        """Get the latest cached date for a market index."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT MAX(date) FROM market_index WHERE index_code=?",
                (index_code,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    # -- market scan snapshot ----------------------------------------------

    def upsert_market_scan_snapshot(self, rows: List[Dict[str, Any]]) -> None:
        """Bulk upsert market scan snapshot rows."""
        if not rows:
            return
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO market_scan_snapshot ("
                "market, trade_date, code, eligible, composite_score, f_score, "
                "value_score, quality_score, growth_score, momentum_score, "
                "low_vol_score, size_score, has_list_date, has_fundamentals, "
                "has_history, is_st, is_bj, is_new_listing, rank_score, "
                "ineligible_reason, created_at"
                ") VALUES ("
                ":market, :trade_date, :code, :eligible, :composite_score, "
                ":f_score, :value_score, :quality_score, :growth_score, "
                ":momentum_score, :low_vol_score, :size_score, :has_list_date, "
                ":has_fundamentals, :has_history, :is_st, :is_bj, "
                ":is_new_listing, :rank_score, :ineligible_reason, :created_at"
                ") ON CONFLICT(market, trade_date, code) DO UPDATE SET "
                "eligible=excluded.eligible, "
                "composite_score=excluded.composite_score, "
                "f_score=excluded.f_score, "
                "value_score=excluded.value_score, "
                "quality_score=excluded.quality_score, "
                "growth_score=excluded.growth_score, "
                "momentum_score=excluded.momentum_score, "
                "low_vol_score=excluded.low_vol_score, "
                "size_score=excluded.size_score, "
                "has_list_date=excluded.has_list_date, "
                "has_fundamentals=excluded.has_fundamentals, "
                "has_history=excluded.has_history, "
                "is_st=excluded.is_st, "
                "is_bj=excluded.is_bj, "
                "is_new_listing=excluded.is_new_listing, "
                "rank_score=excluded.rank_score, "
                "ineligible_reason=excluded.ineligible_reason, "
                "created_at=excluded.created_at",
                rows,
            )
            first = rows[0]
            market = str(first.get("market", ""))
            count = sum(1 for row in rows if str(row.get("market", "")) == market)
            self._touch_meta(self._scan_snapshot_meta_key(market), count, conn)

    def get_latest_market_scan_trade_date(self, market: str) -> str | None:
        """Get the latest snapshot trade date for a market."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT MAX(trade_date) FROM market_scan_snapshot WHERE market=?",
                (market,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def get_market_scan_snapshot(
        self,
        market: str,
        trade_date: str = "",
        include_ineligible: bool = False,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get latest or specified market scan snapshot rows."""
        target_date = trade_date or self.get_latest_market_scan_trade_date(market)
        if not target_date:
            return []
        query = ["SELECT * FROM market_scan_snapshot WHERE market=? AND trade_date=?"]
        params: List[Any] = [market, target_date]
        if not include_ineligible:
            query.append("AND eligible=1")
        query.append("ORDER BY eligible DESC, rank_score ASC, composite_score DESC")
        if limit > 0:
            query.append("LIMIT ?")
            params.append(limit)
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(" ".join(query), tuple(params))
            return [dict(row) for row in cur.fetchall()]

    def get_market_scan_snapshot_summary(
        self,
        market: str,
        trade_date: str = "",
    ) -> Dict[str, Any] | None:
        """Get summary statistics for a market scan snapshot."""
        target_date = trade_date or self.get_latest_market_scan_trade_date(market)
        if not target_date:
            return None
        rows = self.get_market_scan_snapshot(
            market,
            trade_date=target_date,
            include_ineligible=True,
        )
        if not rows:
            return None
        total = len(rows)
        eligible = sum(1 for row in rows if row.get("eligible"))
        complete = sum(
            1
            for row in rows
            if row.get("has_list_date")
            and row.get("has_fundamentals")
            and row.get("has_history")
            and not row.get("is_st")
            and not row.get("is_bj")
            and not row.get("is_new_listing")
        )
        return {
            "market": market,
            "trade_date": target_date,
            "total_count": total,
            "eligible_count": eligible,
            "filtered_count": total - eligible,
            "data_complete_count": complete,
            "data_complete_ratio": (complete / total) if total else 0.0,
            "st_count": sum(1 for row in rows if row.get("is_st")),
            "bj_count": sum(1 for row in rows if row.get("is_bj")),
            "new_listing_count": sum(1 for row in rows if row.get("is_new_listing")),
            "missing_list_date_count": sum(
                1 for row in rows if not row.get("has_list_date")
            ),
            "missing_fundamentals_count": sum(
                1 for row in rows if not row.get("has_fundamentals")
            ),
            "missing_history_count": sum(
                1 for row in rows if not row.get("has_history")
            ),
        }

    def market_scan_snapshot_needs_refresh(self, market: str) -> bool:
        """Check whether the market scan snapshot TTL has expired."""
        ttl = cfg_get("cache_ttl.scan_snapshot", 86400)
        updated = self._meta_timestamp(self._scan_snapshot_meta_key(market))
        if updated is None:
            return True
        return (time.time() - updated) > ttl

    # -- industry mapping ---------------------------------------------------

    def upsert_industry(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert stock-industry mapping."""
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO stock_industry (code, sector, industry, updated_at) "
                "VALUES (:code, :sector, :industry, :updated_at) "
                "ON CONFLICT(code) DO UPDATE SET "
                "sector=excluded.sector, industry=excluded.industry, "
                "updated_at=excluded.updated_at",
                rows,
            )

    def get_industry(self, code: str) -> Tuple[str, str]:
        """Get (sector, industry) for a stock."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT sector, industry FROM stock_industry WHERE code=?",
                (code,),
            )
            row = cur.fetchone()
            if row:
                return (row[0] or "", row[1] or "")
        return ("", "")

    # -- KV store (generic cache) -------------------------------------------

    def kv_get(self, key: str) -> Any | None:
        """Get a cached value by key, deleting expired entries."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT value, expires FROM kv_store WHERE key=?",
                (key,),
            )
            row = cur.fetchone()
            if row:
                if row[1] and time.time() > row[1]:
                    conn.execute("DELETE FROM kv_store WHERE key=?", (key,))
                    return None
                import json

                return json.loads(row[0])
        return None

    def kv_set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set a cached value with TTL."""
        import json

        expires = time.time() + ttl
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO kv_store (key, value, expires) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "value=excluded.value, expires=excluded.expires",
                (key, json.dumps(value), expires),
            )

    def kv_get_str(self, key: str) -> str | None:
        """Get a plain string value (no JSON)."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT value, expires FROM kv_store WHERE key=?",
                (key,),
            )
            row = cur.fetchone()
            if row:
                if row[1] and time.time() > row[1]:
                    return None
                return row[0]
        return None

    def kv_set_str(self, key: str, value: str, ttl: int = 3600) -> None:
        """Set a plain string value with TTL."""
        expires = time.time() + ttl
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO kv_store (key, value, expires) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "value=excluded.value, expires=excluded.expires",
                (key, value, expires),
            )

    # -- API usage tracking -------------------------------------------------

    def record_api_call(self, api_name: str) -> bool:
        """Record an API call. Returns False if daily limit exceeded.

        Uses atomic UPDATE-then-INSERT pattern to avoid race conditions.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        limit = cfg_get("daily_api_limit", 500)
        with self._conn() as conn:
            # Atomic check-and-increment: only increment if under limit
            cur = conn.execute(
                "UPDATE api_usage SET call_count = call_count + 1 "
                "WHERE date=? AND api_name=? AND call_count < ?",
                (today, api_name, limit),
            )
            if cur.rowcount > 0:
                return True
            # Try to insert (first call for this api today)
            conn.execute(
                "INSERT INTO api_usage (date, api_name, call_count) "
                "VALUES (?, ?, 1) "
                "ON CONFLICT(date, api_name) DO UPDATE SET "
                "call_count=call_count+1 "
                "WHERE call_count < ?",
                (today, api_name, limit),
            )
            # Verify the insert/update succeeded
            cur2 = conn.execute(
                "SELECT call_count FROM api_usage WHERE date=? AND api_name=?",
                (today, api_name),
            )
            row = cur2.fetchone()
            if row and row[0] < limit:
                return True
            # Roll back the increment if it exceeded limit
            conn.execute(
                "UPDATE api_usage SET call_count = call_count - 1 "
                "WHERE date=? AND api_name=?",
                (today, api_name),
            )
            return False

    def get_api_usage_breakdown(self) -> Dict[str, int]:
        """Return today's API call count per API name."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT api_name, call_count FROM api_usage "
                "WHERE date=? ORDER BY call_count DESC",
                (today,),
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def get_api_usage_today(self) -> int:
        """Get total API calls today."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT SUM(call_count) FROM api_usage WHERE date=?",
                (today,),
            )
            row = cur.fetchone()
            return row[0] or 0

    # -- metadata -----------------------------------------------------------

    def _touch_meta(
        self, table: str, count: int, conn: sqlite3.Connection | None = None
    ) -> None:
        if conn is None:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO cache_meta "
                    "(table_name, last_updated, record_count, status) "
                    "VALUES (?, ?, ?, 'ok') "
                    "ON CONFLICT(table_name) DO UPDATE SET "
                    "last_updated=excluded.last_updated, "
                    "record_count=excluded.record_count, status='ok'",
                    (table, time.time(), count),
                )
        else:
            conn.execute(
                "INSERT INTO cache_meta "
                "(table_name, last_updated, record_count, status) "
                "VALUES (?, ?, ?, 'ok') "
                "ON CONFLICT(table_name) DO UPDATE SET "
                "last_updated=excluded.last_updated, "
                "record_count=excluded.record_count, status='ok'",
                (table, time.time(), count),
            )

    def _meta_timestamp(self, table: str) -> float | None:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT last_updated FROM cache_meta WHERE table_name=?",
                (table,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    @staticmethod
    def _stock_pool_meta_key(market: str) -> str:
        """Return the metadata key for a market-specific stock pool."""
        return f"stock_pool:{market}"

    @staticmethod
    def _ensure_daily_price_adjust_type_column(conn: sqlite3.Connection) -> None:
        """Ensure adjust_type column exists on daily_price for older cache files."""
        cur = conn.execute("PRAGMA table_info(daily_price)")
        existing = {row[1] for row in cur.fetchall()}
        if "adjust_type" not in existing:
            conn.execute(
                "ALTER TABLE daily_price ADD COLUMN adjust_type TEXT DEFAULT 'qfq'"
            )

    @staticmethod
    def _ensure_stock_pool_metadata_columns(conn: sqlite3.Connection) -> None:
        """Add additive stock-pool metadata columns for older cache files."""
        cur = conn.execute("PRAGMA table_info(stock_pool)")
        existing = {row[1] for row in cur.fetchall()}
        if "metadata_source" not in existing:
            conn.execute(
                "ALTER TABLE stock_pool ADD COLUMN metadata_source TEXT DEFAULT ''"
            )
        if "metadata_status" not in existing:
            conn.execute(
                "ALTER TABLE stock_pool ADD COLUMN metadata_status TEXT DEFAULT ''"
            )
        if "metadata_completeness" not in existing:
            conn.execute(
                "ALTER TABLE stock_pool ADD COLUMN metadata_completeness REAL DEFAULT 0"
            )

    @staticmethod
    def _scan_snapshot_meta_key(market: str) -> str:
        """Return the metadata key for a market scan snapshot."""
        return f"scan_snapshot:{market}"

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics: table row counts, size, API usage."""
        stats_dict: Dict[str, Any] = {}
        tables = [
            "stock_pool",
            "daily_price",
            "factor_snapshot",
            "computed_factors",
            "market_scan_snapshot",
            "fund_info",
            "fund_nav",
            "market_index",
            "api_usage",
        ]
        with self._conn() as conn:
            query = " UNION ALL ".join(
                f"SELECT '{tbl}' AS tbl, COUNT(*) AS cnt FROM {tbl}" for tbl in tables
            )
            try:
                for row in conn.execute(query):
                    stats_dict[row[0]] = row[1]
            except Exception:
                for tbl in tables:
                    stats_dict[tbl] = -1
        db_size = os.path.getsize(self.db_path) / (1024 * 1024)
        stats_dict["db_size_mb"] = round(db_size, 2)
        stats_dict["api_calls_today"] = self.get_api_usage_today()
        return stats_dict

    def cleanup(self, max_age_days: int = 30, max_size_mb: int = 500) -> Dict[str, int]:
        """Clean up old cache entries to prevent unbounded growth.

        Args:
            max_age_days: Remove entries older than this many days.
            max_size_mb: If DB exceeds this size, aggressively clean.

        Returns:
            Dict with counts of removed entries per table.
        """
        removed = {}
        db_size = os.path.getsize(self.db_path) / (1024 * 1024)

        with self._conn() as conn:
            cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime(
                "%Y-%m-%d"
            )
            cur = conn.execute(
                "DELETE FROM daily_price WHERE date < ?",
                (cutoff,),
            )
            removed["daily_price"] = cur.rowcount

            if db_size > max_size_mb:
                cur = conn.execute(
                    "DELETE FROM factor_snapshot WHERE date < ?",
                    (cutoff,),
                )
                removed["factor_snapshot"] = cur.rowcount

            # Clean up expired KV store entries
            cur = conn.execute(
                "DELETE FROM kv_store WHERE expires < ?",
                (time.time(),),
            )
            removed["kv_store"] = cur.rowcount

        # VACUUM must run outside an active transaction.
        with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("VACUUM")

        return removed


# Singleton
_cache: CacheManager | None = None


def get_cache() -> CacheManager:
    global _cache
    if _cache is None:
        _cache = CacheManager()
    return _cache
