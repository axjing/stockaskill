"""One-time data migration: SQLite cache -> DuckDB cache.

Copies every managed table from ``quant_cache.db`` into the DuckDB database so
``db_engine: duckdb`` can be enabled without re-fetching history. Writes are
UPSERT-style so re-running the migration is idempotent.

The report-period ``financial_report`` table is populated from the existing
``factor_snapshot`` rows (``date`` becomes ``report_date`` and
``publish_date``) since pre-DuckDB caches never stored report period data.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from data_engine.duckdb_cache import DuckDBCacheManager
from data_engine.duckdb_engine import DuckDBEngine

logger = logging.getLogger(__name__)

_SQLITE_DB_PATH = Path(__file__).resolve().parents[1] / ".cache" / "quant_cache.db"

# id (conflict target) columns per source table — must match DuckDB PK order.
_TABLE_ID_COLUMNS: Dict[str, Sequence[str]] = {
    "stock_pool": ["market", "code"],
    "daily_price": ["market", "code", "date"],
    "factor_snapshot": ["market", "code", "date"],
    "computed_factors": ["code", "date", "factor_name"],
    "cache_meta": ["table_name"],
    "api_usage": ["date", "api_name"],
    "fund_info": ["code"],
    "fund_nav": ["code", "date"],
    "stock_industry": ["code"],
    "market_index": ["index_code", "date"],
    "trade_calendar": ["market", "date"],
    "kv_store": ["key"],
    "factor_weights": ["date", "factor_name"],
    "market_scan_snapshot": ["market", "trade_date", "code"],
    "sync_state": ["scope_type", "scope_key", "market", "code", "data_kind"],
}

_FINANCIAL_COLUMNS = [
    "market_cap",
    "pe_ttm",
    "pe_static",
    "pb",
    "ps_ttm",
    "pcf_ttm",
    "dividend_yield",
    "roe",
    "roa",
    "gross_margin",
    "net_margin",
    "revenue_growth",
    "profit_growth",
    "debt_ratio",
    "current_ratio",
    "eps",
    "bvps",
]

_CHUNK_SIZE = 5000


def _table_columns(engine: DuckDBEngine, table: str) -> List[str]:
    """Return the ordered column names of a DuckDB table."""
    rows = engine.fetchall(f"DESCRIBE {table}")
    return [r["column_name"] for r in rows]


def _build_upsert_sql(
    table: str, columns: Sequence[str], id_columns: Sequence[str]
) -> str:
    """Build an INSERT ... ON CONFLICT DO UPDATE statement for *columns*."""
    col_sql = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))
    conflict_sql = ", ".join(id_columns)
    update_cols = [c for c in columns if c not in id_columns]
    if update_cols:
        set_sql = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
        return (
            f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {set_sql}"
        )
    return (
        f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_sql}) DO NOTHING"
    )


def _copy_table(
    src: sqlite3.Connection,
    engine: DuckDBEngine,
    table: str,
) -> int:
    """Stream-copy every row of *table* from SQLite into DuckDB.

    Args:
        src: Read-only SQLite connection.
        engine: Destination DuckDB engine.
        table: Source/destination table name.

    Returns:
        Number of rows copied.
    """
    columns = _table_columns(engine, table)
    id_columns = _TABLE_ID_COLUMNS.get(table, [columns[0]])
    sql = _build_upsert_sql(table, columns, id_columns)
    src.row_factory = sqlite3.Row
    cur = src.execute(f"SELECT {', '.join(columns)} FROM {table}")
    total = 0
    while True:
        batch = cur.fetchmany(_CHUNK_SIZE)
        if not batch:
            break
        params = [tuple(r[c] for c in columns) for r in batch]
        engine.executemany(sql, params)
        total += len(batch)
    logger.info("migrated table=%s rows=%d", table, total)
    return total


def _migrate_financial_report(
    src: sqlite3.Connection,
    engine: DuckDBEngine,
) -> int:
    """Populate ``financial_report`` from existing ``factor_snapshot`` rows."""
    columns = ["market", "code", "date"] + _FINANCIAL_COLUMNS
    sql = _build_upsert_sql(
        "financial_report",
        ["market", "code", "report_date", "publish_date"] + _FINANCIAL_COLUMNS,
        ["code", "market", "report_date"],
    )
    src.row_factory = sqlite3.Row
    cur = src.execute(f"SELECT {', '.join(columns)} FROM factor_snapshot")
    total = 0
    while True:
        batch = cur.fetchmany(_CHUNK_SIZE)
        if not batch:
            break
        params = []
        for r in batch:
            row = {
                "market": r["market"],
                "code": r["code"],
                "report_date": r["date"],
                "publish_date": r["date"],
            }
            row.update({k: r[k] for k in _FINANCIAL_COLUMNS})
            params.append(
                tuple(row[c] for c in ["market", "code", "report_date", "publish_date"])
                + tuple(row[k] for k in _FINANCIAL_COLUMNS)
            )
        engine.executemany(sql, params)
        total += len(batch)
    logger.info("migrated table=financial_report rows=%d (from factor_snapshot)", total)
    return total


def migrate_sqlite_to_duckdb(
    sqlite_path: Optional[Path | str] = None,
    duckdb_path: Optional[Path | str] = None,
) -> Dict[str, int]:
    """Copy all cache tables from SQLite into the DuckDB database.

    Args:
        sqlite_path: Source quant_cache.db path (defaults to the project cache).
        duckdb_path: Destination DuckDB file (defaults to configured duckdb_path).

    Returns:
        Dict mapping table name to row count copied.
    """
    src_path = Path(sqlite_path) if sqlite_path else _SQLITE_DB_PATH
    if not src_path.exists():
        raise FileNotFoundError(f"SQLite cache not found: {src_path}")
    manager = DuckDBCacheManager(duckdb_path)
    engine = manager.engine

    # Sanity check: only create a DuckDB cache from a real SQLite cache, never
    # the other way around; refuse if the source exposes no readable tables.
    src = sqlite3.connect(str(src_path), timeout=10.0)
    src.row_factory = sqlite3.Row
    try:
        results: Dict[str, int] = {}
        for table in _TABLE_ID_COLUMNS:
            results[table] = _copy_table(src, engine, table)
        results["financial_report"] = _migrate_financial_report(src, engine)
        engine.vacuum()
        return results
    finally:
        src.close()
