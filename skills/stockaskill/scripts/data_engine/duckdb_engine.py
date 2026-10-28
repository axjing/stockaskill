"""DuckDB storage engine for the stockaskill quant cache.

High-performance column-store replacement for the SQLite cache. It is only
used when ``config.db_engine == "duckdb"``; the SQLite path remains the
default and is fully preserved for dual-engine comparison.

The engine is a process-wide singleton. Each thread owns one connection to
the single DuckDB file so concurrent sync workers never share a connection
(a DuckDB connection is not safe for concurrent use by multiple threads).

All writes use UPSERT semantics (``ON CONFLICT DO UPDATE``) so ingestion is
idempotent: re-fetching the same range simply overwrites the cached values.
"""

import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import duckdb

logger = logging.getLogger(__name__)

_NULL_TIME = "1970-01-01 00:00:00"

# Table name -> ordered columns used by the schema. Kept close to the SQLite
# schema so the DuckDB cache manager is a drop-in replacement for CacheManager.
_SCHEMA: Dict[str, str] = {
    "stock_pool": """
        CREATE TABLE IF NOT EXISTS stock_pool (
            market VARCHAR NOT NULL, code VARCHAR NOT NULL, name VARCHAR DEFAULT '',
            sector VARCHAR DEFAULT '', industry VARCHAR DEFAULT '',
            list_date VARCHAR DEFAULT '', total_market_cap DOUBLE DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            metadata_source VARCHAR DEFAULT '', metadata_status VARCHAR DEFAULT '',
            metadata_completeness DOUBLE DEFAULT 0, updated_at VARCHAR DEFAULT '',
            PRIMARY KEY (market, code)
        )
    """,
    "daily_price": """
        CREATE TABLE IF NOT EXISTS daily_price (
            market VARCHAR NOT NULL, code VARCHAR NOT NULL,
            date VARCHAR NOT NULL, open DOUBLE DEFAULT 0,
            high DOUBLE DEFAULT 0, low DOUBLE DEFAULT 0,
            close DOUBLE DEFAULT 0, volume DOUBLE DEFAULT 0,
            amount DOUBLE DEFAULT 0, quality_flags VARCHAR DEFAULT '',
            adjust_type VARCHAR DEFAULT 'qfq',
            PRIMARY KEY (market, code, date)
        )
    """,
    # Fundamental snapshot as-of date (mirrors SQLite factor_snapshot).
    "factor_snapshot": """
        CREATE TABLE IF NOT EXISTS factor_snapshot (
            market VARCHAR NOT NULL, code VARCHAR NOT NULL, date VARCHAR NOT NULL,
            market_cap DOUBLE DEFAULT 0, pe_ttm DOUBLE DEFAULT 0,
            pe_static DOUBLE DEFAULT 0, pb DOUBLE DEFAULT 0, ps_ttm DOUBLE DEFAULT 0,
            pcf_ttm DOUBLE DEFAULT 0, dividend_yield DOUBLE DEFAULT 0,
            roe DOUBLE DEFAULT 0, roa DOUBLE DEFAULT 0,
            gross_margin DOUBLE DEFAULT 0, net_margin DOUBLE DEFAULT 0,
            revenue_growth DOUBLE DEFAULT 0, profit_growth DOUBLE DEFAULT 0,
            debt_ratio DOUBLE DEFAULT 0, current_ratio DOUBLE DEFAULT 0,
            eps DOUBLE DEFAULT 0, bvps DOUBLE DEFAULT 0,
            PRIMARY KEY (market, code, date)
        )
    """,
    # Report-period financials with report_date (报告期) and publish_date (披露).
    "financial_report": """
        CREATE TABLE IF NOT EXISTS financial_report (
            market VARCHAR NOT NULL, code VARCHAR NOT NULL,
            report_date VARCHAR NOT NULL, publish_date VARCHAR DEFAULT '',
            market_cap DOUBLE DEFAULT 0, pe_ttm DOUBLE DEFAULT 0,
            pe_static DOUBLE DEFAULT 0, pb DOUBLE DEFAULT 0, ps_ttm DOUBLE DEFAULT 0,
            pcf_ttm DOUBLE DEFAULT 0, dividend_yield DOUBLE DEFAULT 0,
            roe DOUBLE DEFAULT 0, roa DOUBLE DEFAULT 0,
            gross_margin DOUBLE DEFAULT 0, net_margin DOUBLE DEFAULT 0,
            revenue_growth DOUBLE DEFAULT 0, profit_growth DOUBLE DEFAULT 0,
            debt_ratio DOUBLE DEFAULT 0, current_ratio DOUBLE DEFAULT 0,
            eps DOUBLE DEFAULT 0, bvps DOUBLE DEFAULT 0,
            PRIMARY KEY (code, market, report_date)
        )
    """,
    # Precomputed daily factor snapshot (core OLAP table).
    "factor_daily_snapshot": """
        CREATE TABLE IF NOT EXISTS factor_daily_snapshot (
            trade_date VARCHAR NOT NULL, code VARCHAR NOT NULL, market VARCHAR NOT NULL,
            industry VARCHAR DEFAULT '', sector VARCHAR DEFAULT '',
            name VARCHAR DEFAULT '', is_active INTEGER DEFAULT 1,
            list_date VARCHAR DEFAULT '',
            pe_ttm DOUBLE DEFAULT 0, pb DOUBLE DEFAULT 0,
            roe DOUBLE DEFAULT 0, gross_margin DOUBLE DEFAULT 0,
            profit_growth DOUBLE DEFAULT 0, revenue_growth DOUBLE DEFAULT 0,
            ret_6m DOUBLE DEFAULT 0, ma_alignment DOUBLE DEFAULT 0,
            vol_12m DOUBLE DEFAULT 0, max_drop_12m DOUBLE DEFAULT 0,
            log_mcap DOUBLE DEFAULT 0, market_cap DOUBLE DEFAULT 0,
            pe_pct DOUBLE DEFAULT 0, pb_pct DOUBLE DEFAULT 0,
            roe_pct DOUBLE DEFAULT 0, gross_margin_pct DOUBLE DEFAULT 0,
            growth_pct DOUBLE DEFAULT 0, momentum_pct DOUBLE DEFAULT 0,
            low_vol_pct DOUBLE DEFAULT 0, size_pct DOUBLE DEFAULT 0,
            value_score DOUBLE DEFAULT 0, quality_score DOUBLE DEFAULT 0,
            growth_score DOUBLE DEFAULT 0, momentum_score DOUBLE DEFAULT 0,
            low_vol_score DOUBLE DEFAULT 0, size_score DOUBLE DEFAULT 0,
            composite_score DOUBLE DEFAULT 0, f_score INTEGER DEFAULT 0,
            has_fundamentals INTEGER DEFAULT 0, has_history INTEGER DEFAULT 0,
            is_st INTEGER DEFAULT 0, is_new_listing INTEGER DEFAULT 0,
            created_at VARCHAR DEFAULT '',
            PRIMARY KEY (trade_date, code, market)
        )
    """,
    "computed_factors": """
        CREATE TABLE IF NOT EXISTS computed_factors (
            code VARCHAR NOT NULL, date VARCHAR NOT NULL,
            factor_name VARCHAR NOT NULL, factor_value DOUBLE DEFAULT 0,
            PRIMARY KEY (code, date, factor_name)
        )
    """,
    "cache_meta": """
        CREATE TABLE IF NOT EXISTS cache_meta (
            table_name VARCHAR PRIMARY KEY, last_updated DOUBLE DEFAULT 0,
            record_count BIGINT DEFAULT 0, status VARCHAR DEFAULT 'ok'
        )
    """,
    "api_usage": """
        CREATE TABLE IF NOT EXISTS api_usage (
            date VARCHAR NOT NULL, api_name VARCHAR NOT NULL,
            call_count BIGINT DEFAULT 1,
            PRIMARY KEY (date, api_name)
        )
    """,
    "fund_info": """
        CREATE TABLE IF NOT EXISTS fund_info (
            code VARCHAR PRIMARY KEY, name VARCHAR DEFAULT '',
            fund_type VARCHAR DEFAULT '', nav DOUBLE DEFAULT 0,
            acc_nav DOUBLE DEFAULT 0, scale DOUBLE DEFAULT 0,
            track_index VARCHAR DEFAULT '', updated_at VARCHAR DEFAULT ''
        )
    """,
    "fund_nav": """
        CREATE TABLE IF NOT EXISTS fund_nav (
            code VARCHAR NOT NULL, date VARCHAR NOT NULL,
            nav DOUBLE DEFAULT 0, acc_nav DOUBLE DEFAULT 0,
            PRIMARY KEY (code, date)
        )
    """,
    "stock_industry": """
        CREATE TABLE IF NOT EXISTS stock_industry (
            code VARCHAR PRIMARY KEY, sector VARCHAR DEFAULT '',
            industry VARCHAR DEFAULT '', updated_at VARCHAR DEFAULT ''
        )
    """,
    "market_index": """
        CREATE TABLE IF NOT EXISTS market_index (
            index_code VARCHAR NOT NULL, date VARCHAR NOT NULL,
            open DOUBLE DEFAULT 0, high DOUBLE DEFAULT 0,
            low DOUBLE DEFAULT 0, close DOUBLE DEFAULT 0,
            volume DOUBLE DEFAULT 0, amount DOUBLE DEFAULT 0,
            PRIMARY KEY (index_code, date)
        )
    """,
    "trade_calendar": """
        CREATE TABLE IF NOT EXISTS trade_calendar (
            market VARCHAR NOT NULL, date VARCHAR NOT NULL,
            is_open INTEGER DEFAULT 1,
            PRIMARY KEY (market, date)
        )
    """,
    "kv_store": """
        CREATE TABLE IF NOT EXISTS kv_store (
            key VARCHAR PRIMARY KEY, value VARCHAR DEFAULT '', expires DOUBLE DEFAULT 0
        )
    """,
    "factor_weights": """
        CREATE TABLE IF NOT EXISTS factor_weights (
            date VARCHAR NOT NULL, factor_name VARCHAR NOT NULL,
            weight DOUBLE DEFAULT 0,
            PRIMARY KEY (date, factor_name)
        )
    """,
    "market_scan_snapshot": """
        CREATE TABLE IF NOT EXISTS market_scan_snapshot (
            market VARCHAR NOT NULL, trade_date VARCHAR NOT NULL,
            code VARCHAR NOT NULL, eligible INTEGER DEFAULT 0,
            composite_score DOUBLE DEFAULT 0, f_score INTEGER DEFAULT 0,
            value_score DOUBLE DEFAULT 0, quality_score DOUBLE DEFAULT 0,
            growth_score DOUBLE DEFAULT 0, momentum_score DOUBLE DEFAULT 0,
            low_vol_score DOUBLE DEFAULT 0, size_score DOUBLE DEFAULT 0,
            has_list_date INTEGER DEFAULT 0, has_fundamentals INTEGER DEFAULT 0,
            has_history INTEGER DEFAULT 0, is_st INTEGER DEFAULT 0,
            is_bj INTEGER DEFAULT 0, is_new_listing INTEGER DEFAULT 0,
            rank_score DOUBLE DEFAULT 0, ineligible_reason VARCHAR DEFAULT '',
            created_at VARCHAR DEFAULT '',
            PRIMARY KEY (market, trade_date, code)
        )
    """,
    "sync_state": """
        CREATE TABLE IF NOT EXISTS sync_state (
            scope_type VARCHAR NOT NULL, scope_key VARCHAR NOT NULL,
            market VARCHAR NOT NULL, code VARCHAR NOT NULL,
            data_kind VARCHAR NOT NULL, last_success_at VARCHAR DEFAULT '',
            last_covered_date VARCHAR DEFAULT '', last_error VARCHAR DEFAULT '',
            status VARCHAR DEFAULT '',
            PRIMARY KEY (scope_type, scope_key, market, code, data_kind)
        )
    """,
    # Data quality check & repair audit log.
    "data_quality_log": """
        CREATE TABLE IF NOT EXISTS data_quality_log (
            id INTEGER PRIMARY KEY,
            check_run VARCHAR DEFAULT '', code VARCHAR NOT NULL,
            market VARCHAR NOT NULL, data_kind VARCHAR NOT NULL,
            checked_at TIMESTAMP, severity VARCHAR DEFAULT 'light',
            issue_types VARCHAR DEFAULT '', start_date VARCHAR DEFAULT '',
            end_date VARCHAR DEFAULT '', missing_days INTEGER DEFAULT 0,
            action VARCHAR DEFAULT '', repaired INTEGER DEFAULT 0,
            status VARCHAR DEFAULT 'ok', error_message VARCHAR DEFAULT '',
            retry_after TIMESTAMP
        )
    """,
    "data_quality_backoff": """
        CREATE TABLE IF NOT EXISTS data_quality_backoff (
            code VARCHAR NOT NULL, market VARCHAR NOT NULL,
            data_kind VARCHAR NOT NULL, backoff_until TIMESTAMP,
            consecutive_failures INTEGER DEFAULT 0,
            PRIMARY KEY (code, market, data_kind)
        )
    """,
}

_INDEXES: Dict[str, str] = {
    "daily_price_market_date": """
        CREATE INDEX IF NOT EXISTS idx_daily_price_market_date
        ON daily_price(market, date)
    """,
    "daily_price_date": """
        CREATE INDEX IF NOT EXISTS idx_daily_price_date
        ON daily_price(date)
    """,
    "factor_snapshot_lookup": """
        CREATE INDEX IF NOT EXISTS idx_factor_snapshot_lookup
        ON factor_snapshot(market, code, date)
    """,
    "factor_daily_lookup": """
        CREATE INDEX IF NOT EXISTS idx_factor_daily_lookup
        ON factor_daily_snapshot(trade_date, market)
    """,
    "factor_daily_code": """
        CREATE INDEX IF NOT EXISTS idx_factor_daily_code
        ON factor_daily_snapshot(code, trade_date)
    """,
    "market_scan_lookup": """
        CREATE INDEX IF NOT EXISTS idx_market_scan_snapshot_lookup
        ON market_scan_snapshot(market, trade_date, eligible, rank_score)
    """,
}


class DuckDBEngine:
    """Thread-safe singleton wrapper around a single DuckDB database file.

    Attributes:
        db_path: Absolute path to the DuckDB database file.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = str(Path(db_path))
        parent = Path(self.db_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self.init_schema()

    # -- connection lifecycle -------------------------------------------------

    def _conn(self):
        """Return this thread's connection, creating it on first use."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = duckdb.connect(self.db_path)
            conn.execute("PRAGMA threads=4")
            self._local.conn = conn
        return conn

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        """Execute a single statement (no result set)."""
        with self._write_lock:
            self._conn().execute(sql, list(params))

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        """Execute a query and return rows as list of dicts."""
        cur = self._conn().execute(sql, list(params))
        columns = [desc[0] for desc in cur.description] if cur.description else []
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def fetchval(
        self, sql: str, params: Sequence[Any] = (), default: Any = None
    ) -> Any:
        """Execute a scalar query and return the first value or *default*."""
        rows = self.fetchall(sql, params)
        if not rows:
            return default
        return next(iter(rows[0].values()), default)

    def fetch_df(self, sql: str, params: Sequence[Any] = ()):
        """Execute a query and return a pandas DataFrame (empty if zero rows)."""
        return self._conn().execute(sql, list(params)).fetch_df()

    # -- schema ---------------------------------------------------------------

    def init_schema(self) -> None:
        """Create all tables and indexes on startup when they do not exist."""
        with self._write_lock:
            conn = self._conn()
            for ddl in _SCHEMA.values():
                conn.execute(ddl)
            for ddl in _INDEXES.values():
                conn.execute(ddl)

    def drop_all(self, keep_schema: bool = False) -> None:
        """Drop every managed table. Used by migrate for a clean rebuild."""
        with self._write_lock:
            conn = self._conn()
            for table in reversed(list(_SCHEMA)):
                conn.execute(f"DROP TABLE IF EXISTS {table}")
        if keep_schema:
            self.init_schema()

    # -- UPSERT writer --------------------------------------------------------

    def upsert(
        self,
        table: str,
        rows: Sequence[Dict[str, Any]],
        id_columns: Sequence[str],
        columns: Optional[Sequence[str]] = None,
    ) -> None:
        """Idempotently write rows into *table*.

        Args:
            table: Target table name.
            rows: Sequence of row dicts.
            id_columns: PK column names used as the conflict target.
            columns: Explicit ordered column list. Defaults to the union of
                row keys in first-seen order.
        """
        if not rows:
            return
        if columns is None:
            columns = list(rows[0].keys())
        cols = list(columns)
        update_cols = [c for c in cols if c not in id_columns]
        placeholders = ", ".join(["?"] * len(cols))
        col_sql = ", ".join(cols)
        conflict_sql = ", ".join(id_columns)
        if update_cols:
            set_sql = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
            sql = (
                f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {set_sql}"
            )
        else:
            sql = (
                f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_sql}) DO NOTHING"
            )
        with self._write_lock:
            conn = self._conn()
            for row in rows:
                values = [row.get(c) for c in cols]
                conn.execute(sql, values)

    def upsert_named(
        self,
        table: str,
        rows: Sequence[Dict[str, Any]],
        id_columns: Sequence[str],
    ) -> None:
        """Upsert rows whose schemas may vary; missing columns use defaults."""
        if not rows:
            return
        columns: List[str] = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
        self.upsert(table, rows, id_columns, columns)

    def executemany(self, sql: str, params_list: Sequence[Sequence[Any]]) -> None:
        """Execute *sql* against a list of parameter rows (bulk ingestion)."""
        if not params_list:
            return
        with self._write_lock:
            self._conn().executemany(sql, [list(p) for p in params_list])

    # -- bookkeeping ----------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return row counts and file size for all managed tables."""
        counts: Dict[str, Any] = {}
        for table in _SCHEMA:
            try:
                counts[table] = int(
                    self.fetchval(f"SELECT COUNT(*) FROM {table}", default=0)
                )
            except Exception:  # pragma: no cover - defensive
                counts[table] = -1
        try:
            counts["db_size_mb"] = round(
                os.path.getsize(self.db_path) / (1024 * 1024), 2
            )
        except OSError:
            counts["db_size_mb"] = 0.0
        return counts

    def vacuum(self) -> None:
        """Reclaim storage after heavy deletes."""
        with self._write_lock:
            try:
                self._conn().execute("CHECKPOINT")
            except Exception:  # pragma: no cover - defensive
                pass


_engines: Dict[str, "DuckDBEngine"] = {}
_engine_lock = threading.Lock()


def get_engine(db_path: Optional[Path | str] = None) -> DuckDBEngine:
    """Return a process-wide singleton DuckDB engine for *db_path*.

    Engines are cached per absolute database path so concurrent callers share
    one instance per file. When *db_path* is omitted the configured
    ``duckdb_path`` (relative to the scripts root) is used.

    Args:
        db_path: Optional override for the database file path.
    """
    scripts_root = Path(__file__).resolve().parents[1]
    if db_path is None:
        from config import get as cfg_get

        db_path = scripts_root / cfg_get("duckdb_path", ".cache/quant_cache.duckdb")
    abs_path = str(Path(db_path).resolve())
    with _engine_lock:
        engine = _engines.get(abs_path)
        if engine is None:
            engine = DuckDBEngine(abs_path)
            _engines[abs_path] = engine
        return engine


def now_str() -> str:
    """Return the current timestamp in the project's canonical format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
