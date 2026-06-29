"""Unified SQLite cache manager for the stock selection system."""

import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import get as cfg_get

_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
_DB_PATH = _CACHE_DIR / "quant_cache.db"


def _ensure_cache_dir() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS stock_pool (
        code TEXT PRIMARY KEY, name TEXT, market TEXT,
        sector TEXT, industry TEXT, list_date TEXT,
        total_market_cap REAL, is_active INTEGER DEFAULT 1,
        updated_at TIMESTAMP
    )""",
    """CREATE INDEX IF NOT EXISTS idx_stock_pool_market
        ON stock_pool(market)""",
    """CREATE TABLE IF NOT EXISTS daily_price (
        code TEXT, date TEXT, open REAL, high REAL, low REAL,
        close REAL, volume REAL, amount REAL, market TEXT,
        PRIMARY KEY (code, date)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_daily_price_code
        ON daily_price(code)""",
    """CREATE TABLE IF NOT EXISTS factor_snapshot (
        code TEXT, date TEXT, market_cap REAL, pe_ttm REAL,
        pe_static REAL, pb REAL, ps_ttm REAL, pcf_ttm REAL,
        dividend_yield REAL, roe REAL, roa REAL, gross_margin REAL,
        net_margin REAL, revenue_growth REAL, profit_growth REAL,
        debt_ratio REAL, current_ratio REAL, eps REAL, bvps REAL,
        PRIMARY KEY (code, date)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_factor_snapshot_code
        ON factor_snapshot(code)""",
    """CREATE TABLE IF NOT EXISTS computed_factors (
        code TEXT, date TEXT, factor_name TEXT, factor_value REAL,
        PRIMARY KEY (code, date, factor_name)
    )""",
    """CREATE TABLE IF NOT EXISTS sentiment (
        code TEXT, date TEXT, source TEXT, title TEXT, url TEXT,
        sentiment_score REAL,
        PRIMARY KEY (code, date, source, title)
    )""",
    """CREATE TABLE IF NOT EXISTS cache_meta (
        table_name TEXT PRIMARY KEY, last_updated TIMESTAMP,
        record_count INTEGER, status TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS api_usage (
        date TEXT, api_name TEXT, call_count INTEGER DEFAULT 1,
        PRIMARY KEY (date, api_name)
    )""",
    # New tables for fund and cross-market support
    """CREATE TABLE IF NOT EXISTS fund_info (
        code TEXT PRIMARY KEY, name TEXT, fund_type TEXT,
        nav REAL, acc_nav REAL, scale REAL, track_index TEXT,
        updated_at TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS fund_nav (
        code TEXT, date TEXT, nav REAL, acc_nav REAL,
        PRIMARY KEY (code, date)
    )""",
    """CREATE TABLE IF NOT EXISTS fund_etf_info (
        code TEXT PRIMARY KEY, name TEXT, track_index TEXT,
        scale REAL, updated_at TIMESTAMP
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
    """CREATE TABLE IF NOT EXISTS kv_store (
        key TEXT PRIMARY KEY, value TEXT, expires REAL
    )""",
    """CREATE TABLE IF NOT EXISTS factor_weights (
        date TEXT, factor_name TEXT, weight REAL,
        PRIMARY KEY (date, factor_name)
    )""",
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

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- stock pool ---------------------------------------------------------

    def upsert_stock_pool(self, rows: List[Dict[str, Any]]) -> None:
        """Bulk upsert stock pool entries."""
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO stock_pool (code, name, market, sector, industry, "
                "list_date, total_market_cap, is_active, updated_at) "
                "VALUES (:code, :name, :market, :sector, :industry, "
                ":list_date, :total_market_cap, :is_active, :updated_at) "
                "ON CONFLICT(code) DO UPDATE SET "
                "name=excluded.name, market=excluded.market, "
                "sector=excluded.sector, industry=excluded.industry, "
                "list_date=excluded.list_date, "
                "total_market_cap=excluded.total_market_cap, "
                "is_active=excluded.is_active, updated_at=excluded.updated_at",
                rows,
            )
            self._touch_meta("stock_pool", len(rows), conn)

    def get_stock_pool(self, market: str = "A") -> List[Dict[str, Any]]:
        """Get stock pool for a market."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM stock_pool WHERE market=? AND is_active=1",
                (market,),
            )
            return [dict(r) for r in cur.fetchall()]

    def pool_needs_refresh(self) -> bool:
        """Check if stock pool TTL has expired."""
        ttl = cfg_get("cache_ttl.pool", 86400)
        updated = self._meta_timestamp("stock_pool")
        if updated is None:
            return True
        return (time.time() - updated) > ttl

    # -- daily price (K-line) ----------------------------------------------

    def upsert_daily_price(self, rows: List[Dict[str, Any]]) -> None:
        """Bulk upsert daily K-line data."""
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO daily_price "
                "(code, date, open, high, low, close, volume, amount, market) "
                "VALUES (:code, :date, :open, :high, :low, :close, "
                ":volume, :amount, :market) "
                "ON CONFLICT(code, date) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, "
                "close=excluded.close, volume=excluded.volume, "
                "amount=excluded.amount, market=excluded.market",
                rows,
            )

    def get_daily_price(
        self, code: str, start_date: str = "", end_date: str = ""
    ) -> List[Dict[str, Any]]:
        """Get K-line data for a stock, optionally date-filtered."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            if start_date and end_date:
                cur = conn.execute(
                    "SELECT * FROM daily_price "
                    "WHERE code=? AND date>=? AND date<=? "
                    "ORDER BY date DESC",
                    (code, start_date, end_date),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM daily_price " "WHERE code=? ORDER BY date DESC",
                    (code,),
                )
            return [dict(r) for r in cur.fetchall()]

    def get_latest_date(self, code: str) -> str | None:
        """Get the latest cached date for a stock."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT MAX(date) FROM daily_price WHERE code=?",
                (code,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    # -- factor snapshot ----------------------------------------------------

    def upsert_factor_snapshot(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert fundamental snapshots."""
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO factor_snapshot "
                "(code, date, market_cap, pe_ttm, pe_static, pb, ps_ttm, "
                "pcf_ttm, dividend_yield, roe, roa, gross_margin, net_margin, "
                "revenue_growth, profit_growth, debt_ratio, current_ratio, "
                "eps, bvps) "
                "VALUES (:code, :date, :market_cap, :pe_ttm, :pe_static, :pb, "
                ":ps_ttm, :pcf_ttm, :dividend_yield, :roe, :roa, "
                ":gross_margin, :net_margin, :revenue_growth, :profit_growth, "
                ":debt_ratio, :current_ratio, :eps, :bvps) "
                "ON CONFLICT(code, date) DO UPDATE SET "
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
                rows,
            )

    def get_latest_factor_snapshot(self, code: str) -> Dict[str, Any] | None:
        """Get the most recent fundamental snapshot for a stock."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM factor_snapshot "
                "WHERE code=? ORDER BY date DESC LIMIT 1",
                (code,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

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
                    "WHERE code=? ORDER BY date DESC LIMIT 100",
                    (code,),
                )
            return {row[0]: row[1] for row in cur.fetchall()}

    # -- sentiment ----------------------------------------------------------

    def upsert_sentiment(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert sentiment analysis results."""
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO sentiment "
                "(code, date, source, title, url, sentiment_score) "
                "VALUES (:code, :date, :source, :title, :url, :sentiment_score) "
                "ON CONFLICT(code, date, source, title) DO UPDATE SET "
                "sentiment_score=excluded.sentiment_score",
                rows,
            )

    def get_sentiment(self, code: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent sentiment data for a stock."""
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM sentiment WHERE code=? AND date>=? "
                "ORDER BY date DESC",
                (code, cutoff),
            )
            return [dict(r) for r in cur.fetchall()]

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
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM fund_nav WHERE code=? AND date>=? " "ORDER BY date DESC",
                (code, cutoff),
            )
            return [dict(r) for r in cur.fetchall()]

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
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM market_index "
                "WHERE index_code=? AND date>=? ORDER BY date DESC",
                (index_code, cutoff),
            )
            return [dict(r) for r in cur.fetchall()]

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
        """Get a cached value by key."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT value, expires FROM kv_store WHERE key=?",
                (key,),
            )
            row = cur.fetchone()
            if row:
                if row[1] and time.time() > row[1]:
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
                "SELECT call_count FROM api_usage " "WHERE date=? AND api_name=?",
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

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics: table row counts, size, API usage."""
        stats_dict: Dict[str, Any] = {}
        tables = [
            "stock_pool", "daily_price", "factor_snapshot",
            "computed_factors", "sentiment", "fund_info",
            "fund_nav", "market_index", "api_usage",
        ]
        with self._conn() as conn:
            for tbl in tables:
                try:
                    cur = conn.execute(f"SELECT COUNT(*) FROM {tbl}")
                    stats_dict[tbl] = cur.fetchone()[0]
                except Exception:
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
            # Remove old daily_price entries
            cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime(
                "%Y-%m-%d"
            )
            cur = conn.execute(
                "DELETE FROM daily_price WHERE date < ?",
                (cutoff,),
            )
            removed["daily_price"] = cur.rowcount

            # Remove old sentiment entries
            cur = conn.execute(
                "DELETE FROM sentiment WHERE date < ?",
                (cutoff,),
            )
            removed["sentiment"] = cur.rowcount

            # If DB is still too large, clean more aggressively
            if db_size > max_size_mb:
                cur = conn.execute(
                    "DELETE FROM factor_snapshot WHERE date < ?",
                    (cutoff,),
                )
                removed["factor_snapshot"] = cur.rowcount

            # Vacuum to reclaim space
            conn.execute("VACUUM")

        return removed


# Singleton
_cache: CacheManager | None = None


def get_cache() -> CacheManager:
    global _cache
    if _cache is None:
        _cache = CacheManager()
    return _cache
