"""DuckDB-backed cache manager.

Drop-in replacement for ``scripts/cache.py``'s ``CacheManager``. It exposes
the same public interface so every upper-layer module can keep calling
``get_cache()`` without knowing which engine is active. Selection is driven by
``config.d`` ``db_engine``: ``sqlite`` (default) or ``duckdb``.

Implementation notes:
- All reads go through ``DuckDBEngine.fetchall`` / ``fetchval`` and return
  plain dicts with the same keys as the SQLite path (e.g. ``date`` on k-line
  rows), so consumers that do ``row["date"]`` keep working unchanged.
- All writes use UPSERT via ``DuckDBEngine.upsert`` (``ON CONFLICT DO UPDATE``)
  so ingestion stays idempotent under incremental sync.
- Timestamp-ish columns are stored as VARCHAR (mirroring SQLite's TEXT
  affinity) because callers sometimes pass ``""``; ``cache_meta.last_updated``
  stays numeric (epoch) because TTL logic subtracts it from ``time.time()``.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, cast

from cache import CacheManager
from config import get as cfg_get

from data_engine.duckdb_engine import get_engine

logger = logging.getLogger(__name__)


class DuckDBCacheManager:
    """Thread-safe DuckDB cache with TTL and bulk upsert support."""

    def __init__(self, db_path: Any = None) -> None:
        self.engine = get_engine(db_path)
        self.db_path = self.engine.db_path

    def get_raw_connection(self) -> Any:
        """Return a connection or cursor-like object for direct SQL execution."""
        return self.engine._conn().cursor()

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
        self.engine.upsert(
            "stock_pool",
            normalized_rows,
            id_columns=["market", "code"],
            columns=[
                "market",
                "code",
                "name",
                "sector",
                "industry",
                "list_date",
                "total_market_cap",
                "is_active",
                "metadata_source",
                "metadata_status",
                "metadata_completeness",
                "updated_at",
            ],
        )
        counts_by_market: Dict[str, int] = {}
        for row in normalized_rows:
            market = str(row.get("market", ""))
            counts_by_market[market] = counts_by_market.get(market, 0) + 1
        for market, count in counts_by_market.items():
            self._touch_meta(self._stock_pool_meta_key(market), count)

    def get_stock_pool(
        self, market: str = "A", include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """Get stock pool for a market (v2 table)."""
        if include_inactive:
            return self.engine.fetchall(
                "SELECT * FROM stock_pool WHERE market=?", (market,)
            )
        return self.engine.fetchall(
            "SELECT * FROM stock_pool WHERE market=? AND is_active=1",
            (market,),
        )

    def pool_needs_refresh(self, market: str = "A") -> bool:
        """Check if stock pool TTL has expired."""
        ttl = float(cfg_get("cache_ttl.pool", 86400))
        updated = self._meta_timestamp(self._stock_pool_meta_key(market))
        if updated is None:
            return True
        from time import time

        return (time() - updated) > ttl

    # -- daily price (K-line) ----------------------------------------------

    def upsert_daily_price(self, rows: List[Dict[str, Any]]) -> None:
        """Bulk upsert daily K-line data (v2 table only)."""
        for row in rows:
            row.setdefault("quality_flags", "")
            row.setdefault("adjust_type", "qfq")
        # Two-phase ingest: reject malformed rows before writing to cache
        validated = [r for r in rows if CacheManager._validate_kline_row(r)]
        rejected = len(rows) - len(validated)
        if rejected:
            logger.warning(
                "Rejected %d malformed K-line rows before cache ingestion",
                rejected,
            )
        self.engine.upsert(
            "daily_price",
            validated,
            id_columns=["market", "code", "date"],
            columns=[
                "market",
                "code",
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "quality_flags",
                "adjust_type",
            ],
        )

    def get_daily_price(
        self,
        code: str,
        start_date: str = "",
        end_date: str = "",
        market: str = "A",
    ) -> List[Dict[str, Any]]:
        """Get K-line data for a stock (v2 table), optionally date-filtered."""
        params: List[Any] = [market, code]
        query = "SELECT * FROM daily_price WHERE market=? AND code=?"
        if start_date:
            query += " AND date>=?"
            params.append(start_date)
        if end_date:
            query += " AND date<=?"
            params.append(end_date)
        query += " ORDER BY date DESC"
        return self.engine.fetchall(query, tuple(params))

    def get_date_ranges(self, codes: List[str], market: str = "A") -> Dict[str, tuple]:
        """Get (earliest_date, latest_date) for many codes in one query."""
        if not codes:
            return {}
        placeholders = ",".join(["?" for _ in codes])
        rows = self.engine.fetchall(
            f"SELECT code, MIN(date) AS min_date, MAX(date) AS max_date "
            f"FROM daily_price WHERE market=? AND code IN ({placeholders}) "
            f"GROUP BY code",
            (market, *codes),
        )
        return {
            r["code"]: (r["min_date"], r["max_date"])
            for r in rows
            if r["min_date"] and r["max_date"]
        }

    def get_latest_date(self, code: str, market: str = "A") -> Optional[str]:
        """Get the latest cached date for a stock."""
        return cast(
            Optional[str],
            self.engine.fetchval(
                "SELECT MAX(date) FROM daily_price WHERE market=? AND code=?",
                (market, code),
            ),
        )

    def get_latest_daily_price_date(self, market: str = "A") -> Optional[str]:
        """Get the latest cached date across a market's K-line rows."""
        return cast(
            Optional[str],
            self.engine.fetchval(
                "SELECT MAX(date) FROM daily_price WHERE market=?",
                (market,),
            ),
        )

    def get_latest_trade_calendar_date(self, market: str = "A") -> Optional[str]:
        """Get the latest open trading day from the cached trade calendar."""
        return cast(
            Optional[str],
            self.engine.fetchval(
                "SELECT MAX(date) FROM trade_calendar "
                "WHERE market=? AND is_open=1",
                (market,),
            ),
        )

    def get_earliest_date(self, code: str, market: str = "A") -> Optional[str]:
        """Get the earliest cached date for a stock."""
        return cast(
            Optional[str],
            self.engine.fetchval(
                "SELECT MIN(date) FROM daily_price WHERE market=? AND code=?",
                (market, code),
            ),
        )

    def get_row_count(self, code: str, market: str = "A") -> int:
        """Get cached row count for a stock."""
        val = self.engine.fetchval(
            "SELECT COUNT(*) FROM daily_price WHERE market=? AND code=?",
            (market, code),
            default=0,
        )
        return int(val or 0)

    def get_latest_close(self, code: str, market: str = "A") -> Optional[float]:
        """Get the latest close price for a stock."""
        rows = self.engine.fetchall(
            "SELECT close FROM daily_price "
            "WHERE market=? AND code=? ORDER BY date DESC LIMIT 1",
            (market, code),
        )
        if not rows or not rows[0].get("close"):
            return None
        return float(rows[0]["close"])

    def get_market_cap_from_pool(self, code: str, market: str = "A") -> Optional[float]:
        """Get market_cap from stock_pool for a given code."""
        rows = self.engine.fetchall(
            "SELECT total_market_cap FROM stock_pool "
            "WHERE market=? AND code=? LIMIT 1",
            (market, code),
        )
        if not rows:
            return None
        cap = rows[0].get("total_market_cap")
        return float(cap) if cap and float(cap) > 0 else None

    def get_all_fund_info(self) -> List[Dict[str, Any]]:
        """Return all rows from fund_info table."""
        return self.engine.fetchall("SELECT * FROM fund_info")

    # -- factor snapshot ----------------------------------------------------

    def upsert_factor_snapshot(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert fundamental snapshots (v2 table only)."""
        v2_rows = [dict(row, market=str(row.get("market", ""))) for row in rows]
        self.engine.upsert(
            "factor_snapshot",
            v2_rows,
            id_columns=["market", "code", "date"],
            columns=[
                "market",
                "code",
                "date",
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
            ],
        )

    def get_factor_snapshot_as_of(
        self,
        code: str,
        market: str,
        as_of_date: str,
    ) -> Dict[str, Any] | None:
        """Get the latest factor snapshot for a stock as of a specific date."""
        rows = self.engine.fetchall(
            "SELECT * FROM factor_snapshot "
            "WHERE market=? AND code=? AND date<=? "
            "ORDER BY date DESC LIMIT 1",
            (market, code, as_of_date),
        )
        return rows[0] if rows else None

    def get_latest_factor_snapshot(
        self,
        code: str,
        market: str = "A",
    ) -> Dict[str, Any] | None:
        """Get the most recent fundamental snapshot for a stock (v2 table)."""
        rows = self.engine.fetchall(
            "SELECT * FROM factor_snapshot "
            "WHERE market=? AND code=? ORDER BY date DESC LIMIT 1",
            (market, code),
        )
        return rows[0] if rows else None

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

    # -- report-period financials (new DuckDB table) ------------------------

    def upsert_financial_report(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert report-period financial rows (financial_report table)."""
        if not rows:
            return
        self.engine.upsert(
            "financial_report",
            rows,
            id_columns=["code", "market", "report_date"],
            columns=[
                "market",
                "code",
                "report_date",
                "publish_date",
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
            ],
        )

    def get_financial_report(
        self,
        code: str,
        market: str = "A",
    ) -> List[Dict[str, Any]]:
        """Return report-period financial rows for a code, newest first."""
        return self.engine.fetchall(
            "SELECT * FROM financial_report "
            "WHERE code=? AND market=? ORDER BY report_date DESC",
            (code, market),
        )

    # -- daily factor snapshot (new DuckDB OLAP table) ----------------------

    def upsert_factor_daily_snapshot(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert precomputed daily factor snapshot rows."""
        if not rows:
            return
        self.engine.upsert_named(
            "factor_daily_snapshot", rows, ["trade_date", "code", "market"]
        )

    def get_factor_daily_snapshot(
        self,
        trade_date: str,
        market: str = "A",
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get factor snapshot rows for a trade date, best scored first."""
        query = "SELECT * FROM factor_daily_snapshot WHERE trade_date=? AND market=?"
        params: List[Any] = [trade_date, market]
        query += " ORDER BY composite_score DESC"
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)
        return self.engine.fetchall(query, tuple(params))

    def get_latest_factor_daily_trade_date(self, market: str = "A") -> Optional[str]:
        """Get the latest trade date with a precomputed factor snapshot."""
        return cast(
            Optional[str],
            self.engine.fetchval(
                "SELECT MAX(trade_date) FROM factor_daily_snapshot WHERE market=?",
                (market,),
            ),
        )

    # -- data quality check/repair -----------------------------------------

    def next_data_quality_log_id(self) -> int:
        """Return the next audit log id (explicit ids are cross-engine safe)."""
        return cast(
            int,
            self.engine.fetchval(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM data_quality_log",
                default=1,
            ),
        )

    def append_data_quality_log(self, entries: List[Dict[str, Any]]) -> None:
        """Insert data-quality audit rows (each entry must carry its own id)."""
        if not entries:
            return
        self.engine.upsert(
            "data_quality_log",
            entries,
            id_columns=["id"],
            columns=[
                "id",
                "check_run",
                "code",
                "market",
                "data_kind",
                "checked_at",
                "severity",
                "issue_types",
                "start_date",
                "end_date",
                "missing_days",
                "action",
                "repaired",
                "status",
                "error_message",
                "retry_after",
            ],
        )

    def get_data_quality_log(
        self,
        code: str = "",
        market: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return data-quality audit rows, newest first."""
        query = "SELECT * FROM data_quality_log"
        params: List[Any] = []
        conditions = []
        if code:
            conditions.append("code=?")
            params.append(code)
        if market:
            conditions.append("market=?")
            params.append(market)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return self.engine.fetchall(query, tuple(params))

    def get_data_quality_backoff(
        self,
        code: str,
        market: str,
        data_kind: str = "history",
    ) -> Optional[Dict[str, Any]]:
        """Return the backoff row for a symbol/data kind, if any."""
        rows = self.engine.fetchall(
            "SELECT * FROM data_quality_backoff "
            "WHERE code=? AND market=? AND data_kind=?",
            (code, market, data_kind),
        )
        return rows[0] if rows else None

    def set_data_quality_backoff(
        self,
        code: str,
        market: str,
        data_kind: str,
        backoff_until: str,
        consecutive_failures: int,
    ) -> None:
        """Upsert the backoff row for a symbol/data kind."""
        self.engine.upsert(
            "data_quality_backoff",
            [
                {
                    "code": code,
                    "market": market,
                    "data_kind": data_kind,
                    "backoff_until": backoff_until,
                    "consecutive_failures": consecutive_failures,
                }
            ],
            id_columns=["code", "market", "data_kind"],
            columns=[
                "code",
                "market",
                "data_kind",
                "backoff_until",
                "consecutive_failures",
            ],
        )

    def clear_data_quality_backoff(
        self,
        code: str,
        market: str,
        data_kind: str = "history",
    ) -> None:
        """Remove the backoff row for a symbol/data kind."""
        self.engine.execute(
            "DELETE FROM data_quality_backoff "
            "WHERE code=? AND market=? AND data_kind=?",
            (code, market, data_kind),
        )

    # -- sync state ---------------------------------------------------------

    def upsert_sync_state(self, rows: List[Dict[str, Any]]) -> None:
        """Bulk upsert sync-state rows."""
        if not rows:
            return
        self.engine.upsert(
            "sync_state",
            rows,
            id_columns=["scope_type", "scope_key", "market", "code", "data_kind"],
            columns=[
                "scope_type",
                "scope_key",
                "market",
                "code",
                "data_kind",
                "last_success_at",
                "last_covered_date",
                "last_error",
                "status",
            ],
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
        return self.engine.fetchall(" ".join(query), tuple(params))

    # -- computed factors ---------------------------------------------------

    def upsert_computed_factors(
        self, code: str, date: str, factors: Dict[str, float]
    ) -> None:
        """Store computed factor values."""
        rows = [
            {"code": code, "date": date, "factor_name": name, "factor_value": value}
            for name, value in factors.items()
        ]
        self.engine.upsert(
            "computed_factors",
            rows,
            id_columns=["code", "date", "factor_name"],
            columns=["code", "date", "factor_name", "factor_value"],
        )

    def get_computed_factors(self, code: str, date: str = "") -> Dict[str, float]:
        """Get computed factors for a stock."""
        if date:
            rows = self.engine.fetchall(
                "SELECT factor_name, factor_value FROM computed_factors "
                "WHERE code=? AND date=?",
                (code, date),
            )
        else:
            rows = self.engine.fetchall(
                "SELECT factor_name, factor_value FROM computed_factors "
                "WHERE code=? AND date=("
                "SELECT MAX(date) FROM computed_factors WHERE code=?"
                ")",
                (code, code),
            )
        return {r["factor_name"]: r["factor_value"] for r in rows}

    def get_latest_computed_factors(
        self, code: str
    ) -> Tuple[Optional[str], Dict[str, float]]:
        """Get the latest computed factor set and its date for a stock."""
        latest_date = self.engine.fetchval(
            "SELECT MAX(date) FROM computed_factors WHERE code=?", (code,)
        )
        if not latest_date:
            return None, {}
        rows = self.engine.fetchall(
            "SELECT factor_name, factor_value FROM computed_factors "
            "WHERE code=? AND date=?",
            (code, latest_date),
        )
        return latest_date, {r["factor_name"]: r["factor_value"] for r in rows}

    # -- fund data ----------------------------------------------------------

    def upsert_fund_info(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert fund basic info."""
        self.engine.upsert(
            "fund_info",
            rows,
            id_columns=["code"],
            columns=[
                "code",
                "name",
                "fund_type",
                "nav",
                "acc_nav",
                "scale",
                "track_index",
                "updated_at",
            ],
        )

    def get_fund_info(self, code: str) -> Dict[str, Any] | None:
        """Get fund info by code."""
        rows = self.engine.fetchall("SELECT * FROM fund_info WHERE code=?", (code,))
        return rows[0] if rows else None

    def upsert_fund_nav(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert fund NAV history."""
        self.engine.upsert(
            "fund_nav",
            rows,
            id_columns=["code", "date"],
            columns=["code", "date", "nav", "acc_nav"],
        )

    def get_fund_nav(self, code: str, days: int = 365) -> List[Dict[str, Any]]:
        """Get fund NAV history."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return self.engine.fetchall(
            "SELECT * FROM fund_nav WHERE code=? AND date>=? ORDER BY date DESC",
            (code, cutoff),
        )

    def get_latest_fund_nav_date(self, code: str) -> Optional[str]:
        """Get the latest cached date for a fund NAV."""
        return cast(
            Optional[str],
            self.engine.fetchval(
                "SELECT MAX(date) FROM fund_nav WHERE code=?", (code,)
            ),
        )

    def is_market_data_empty(self, market: str) -> bool:
        """Return True when the cache has no K-line data for the given market."""
        val = self.engine.fetchval(
            "SELECT COUNT(*) FROM daily_price WHERE market=?", (market,), default=0
        )
        return (val or 0) == 0

    # -- market index -------------------------------------------------------

    def upsert_market_index(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert market index daily data."""
        self.engine.upsert(
            "market_index",
            rows,
            id_columns=["index_code", "date"],
            columns=[
                "index_code",
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
            ],
        )

    def get_market_index(
        self, index_code: str, days: int = 250
    ) -> List[Dict[str, Any]]:
        """Get market index K-line data."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return self.engine.fetchall(
            "SELECT * FROM market_index "
            "WHERE index_code=? AND date>=? ORDER BY date DESC",
            (index_code, cutoff),
        )

    def get_latest_market_index_date(self, index_code: str) -> Optional[str]:
        """Get the latest cached date for a market index."""
        return cast(
            Optional[str],
            self.engine.fetchval(
                "SELECT MAX(date) FROM market_index WHERE index_code=?", (index_code,)
            ),
        )

    # -- market scan snapshot ----------------------------------------------

    def upsert_market_scan_snapshot(self, rows: List[Dict[str, Any]]) -> None:
        """Bulk upsert market scan snapshot rows."""
        if not rows:
            return
        self.engine.upsert(
            "market_scan_snapshot",
            rows,
            id_columns=["market", "trade_date", "code"],
            columns=[
                "market",
                "trade_date",
                "code",
                "eligible",
                "composite_score",
                "f_score",
                "value_score",
                "quality_score",
                "growth_score",
                "momentum_score",
                "low_vol_score",
                "size_score",
                "has_list_date",
                "has_fundamentals",
                "has_history",
                "is_st",
                "is_bj",
                "is_new_listing",
                "rank_score",
                "ineligible_reason",
                "created_at",
            ],
        )
        first = rows[0]
        market = str(first.get("market", ""))
        count = sum(1 for row in rows if str(row.get("market", "")) == market)
        self._touch_meta(self._scan_snapshot_meta_key(market), count)

    def get_latest_market_scan_trade_date(self, market: str) -> Optional[str]:
        """Get the latest snapshot trade date for a market."""
        return cast(
            Optional[str],
            self.engine.fetchval(
                "SELECT MAX(trade_date) FROM market_scan_snapshot WHERE market=?",
                (market,),
            ),
        )

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
        query = [
            "SELECT * FROM market_scan_snapshot WHERE market=? AND trade_date=?"
        ]
        params: List[Any] = [market, target_date]
        if not include_ineligible:
            query.append("AND eligible=1")
        query.append(
            "ORDER BY eligible DESC, rank_score ASC NULLS LAST, composite_score DESC"
        )
        if limit > 0:
            query.append("LIMIT ?")
            params.append(limit)
        return self.engine.fetchall(" ".join(query), tuple(params))

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
        ttl = float(cfg_get("cache_ttl.scan_snapshot", 86400))
        updated = self._meta_timestamp(self._scan_snapshot_meta_key(market))
        if updated is None:
            return True
        from time import time

        return (time() - updated) > ttl

    # -- industry mapping ---------------------------------------------------

    def upsert_industry(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert stock-industry mapping."""
        self.engine.upsert(
            "stock_industry",
            rows,
            id_columns=["code"],
            columns=["code", "sector", "industry", "updated_at"],
        )

    def get_industry(self, code: str) -> Tuple[str, str]:
        """Get (sector, industry) for a stock."""
        rows = self.engine.fetchall(
            "SELECT sector, industry FROM stock_industry WHERE code=?", (code,)
        )
        if rows:
            return (rows[0].get("sector") or "", rows[0].get("industry") or "")
        return ("", "")

    # -- KV store (generic cache) -------------------------------------------

    def kv_get(self, key: str) -> Any | None:
        """Get a cached value by key, deleting expired entries."""
        rows = self.engine.fetchall(
            "SELECT value, expires FROM kv_store WHERE key=?", (key,)
        )
        if not rows:
            return None
        value, expires = rows[0].get("value"), rows[0].get("expires")
        from time import time

        if expires and time() > float(expires):
            self.engine.execute("DELETE FROM kv_store WHERE key=?", (key,))
            return None
        return json.loads(cast(str, value))

    def kv_set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set a cached value with TTL."""
        from time import time

        expires = time() + ttl
        self.engine.upsert(
            "kv_store",
            [{"key": key, "value": json.dumps(value), "expires": expires}],
            id_columns=["key"],
            columns=["key", "value", "expires"],
        )

    def kv_get_str(self, key: str) -> str | None:
        """Get a plain string value (no JSON)."""
        rows = self.engine.fetchall(
            "SELECT value, expires FROM kv_store WHERE key=?", (key,)
        )
        if not rows:
            return None
        value, expires = rows[0].get("value"), rows[0].get("expires")
        from time import time

        if expires and time() > float(expires):
            return None
        return value

    def kv_set_str(self, key: str, value: str, ttl: int = 3600) -> None:
        """Set a plain string value with TTL."""
        from time import time

        expires = time() + ttl
        self.engine.upsert(
            "kv_store",
            [{"key": key, "value": value, "expires": expires}],
            id_columns=["key"],
            columns=["key", "value", "expires"],
        )

    # -- API usage tracking -------------------------------------------------

    def record_api_call(self, api_name: str) -> bool:
        """Record an API call. Returns False if daily limit exceeded."""
        today = datetime.now().strftime("%Y-%m-%d")
        limit = cfg_get("daily_api_limit", 500)
        # Atomic check-and-increment: only increment if under limit
        updated = self.engine.fetchall(
            "UPDATE api_usage SET call_count = call_count + 1 "
            "WHERE date=? AND api_name=? AND call_count < ? RETURNING call_count",
            (today, api_name, limit),
        )
        if updated:
            return True
        # Try to insert (first call for this api today)
        self.engine.execute(
            "INSERT INTO api_usage (date, api_name, call_count) "
            "VALUES (?, ?, 1) "
            "ON CONFLICT(date, api_name) DO UPDATE SET call_count=call_count+1 "
            "WHERE call_count < ?",
            (today, api_name, limit),
        )
        count = self.engine.fetchval(
            "SELECT call_count FROM api_usage WHERE date=? AND api_name=?",
            (today, api_name),
        )
        if count is not None and int(count) < limit:
            return True
        # Roll back the increment if it exceeded limit
        self.engine.execute(
            "UPDATE api_usage SET call_count = "
            "CASE WHEN call_count > 0 THEN call_count - 1 ELSE 0 END "
            "WHERE date=? AND api_name=?",
            (today, api_name),
        )
        return False

    def get_api_usage_breakdown(self) -> Dict[str, int]:
        """Return today's API call count per API name."""
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self.engine.fetchall(
            "SELECT api_name, call_count FROM api_usage "
            "WHERE date=? ORDER BY call_count DESC",
            (today,),
        )
        return {r["api_name"]: int(r["call_count"]) for r in rows}

    def get_api_usage_today(self) -> int:
        """Get total API calls today."""
        today = datetime.now().strftime("%Y-%m-%d")
        total = self.engine.fetchval(
            "SELECT SUM(call_count) FROM api_usage WHERE date=?", (today,)
        )
        return int(total or 0)

    # -- data completeness --------------------------------------------------

    def check_data_completeness(
        self,
        market: str = "A",
    ) -> List[Dict[str, int]]:
        """Check data completeness by detecting gaps in daily_price dates.

        Returns a list of dicts with code, actual_days, expected_days,
        missing_days for stocks that have fewer rows than expected.
        """
        rows = self.engine.fetchall(
            """WITH per_code AS (
                SELECT dp.market, dp.code,
                       COUNT(dp.date) AS actual_days,
                       (SELECT COUNT(*)
                        FROM trade_calendar tc
                        WHERE tc.market = dp.market
                          AND tc.date BETWEEN
                              (SELECT MIN(date) FROM daily_price
                               WHERE market = dp.market AND code = dp.code)
                              AND (SELECT MAX(date) FROM daily_price
                                   WHERE market = dp.market AND code = dp.code)
                       ) AS expected_days
                FROM daily_price dp
                WHERE dp.market = ?
                GROUP BY dp.market, dp.code
            )
            SELECT code, actual_days, expected_days,
                   expected_days - actual_days AS missing_days
            FROM per_code
            WHERE actual_days < expected_days
            ORDER BY missing_days DESC""",
            (market,),
        )
        return [
            {
                "code": r["code"],
                "actual_days": int(r["actual_days"]),
                "expected_days": int(r["expected_days"]),
                "missing_days": int(r["missing_days"]),
            }
            for r in rows
        ]

    # -- compute helpers ----------------------------------------------------

    def compute_vwap(self, amount: float, volume: float) -> float:
        """Compute VWAP from cached amount and volume.

        VWAP = amount / volume. Returns 0 if volume is 0.
        """
        if volume > 0 and amount > 0:
            return round(amount / volume, 4)
        return 0.0

    # -- metadata -----------------------------------------------------------

    def _touch_meta(self, table: str, count: int) -> None:
        from time import time

        self.engine.upsert(
            "cache_meta",
            [
                {
                    "table_name": table,
                    "last_updated": time(),
                    "record_count": count,
                    "status": "ok",
                }
            ],
            id_columns=["table_name"],
            columns=["table_name", "last_updated", "record_count", "status"],
        )

    def _meta_timestamp(self, table: str) -> Optional[float]:
        val = self.engine.fetchval(
            "SELECT last_updated FROM cache_meta WHERE table_name=?", (table,)
        )
        return float(val) if val is not None else None

    @staticmethod
    def _stock_pool_meta_key(market: str) -> str:
        """Return the metadata key for a market-specific stock pool."""
        return CacheManager._stock_pool_meta_key(market)

    @staticmethod
    def _scan_snapshot_meta_key(market: str) -> str:
        """Return the metadata key for a market scan snapshot."""
        return CacheManager._scan_snapshot_meta_key(market)

    # -- statistics & cleanup -----------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics: table row counts, size, API usage."""
        stats_dict: Dict[str, Any] = {}
        tables = [
            "stock_pool",
            "daily_price",
            "factor_snapshot",
            "financial_report",
            "factor_daily_snapshot",
            "computed_factors",
            "market_scan_snapshot",
            "fund_info",
            "fund_nav",
            "market_index",
            "api_usage",
        ]
        for table in tables:
            try:
                stats_dict[table] = int(
                    self.engine.fetchval(f"SELECT COUNT(*) FROM {table}", default=0)
                )
            except Exception:  # pragma: no cover - defensive
                stats_dict[table] = -1
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
        removed: Dict[str, int] = {}
        db_size = os.path.getsize(self.db_path) / (1024 * 1024)

        # Do NOT delete daily_price rows — full history must be preserved
        # per AGENTS.md "Data Strategy: Cache-First + Incremental Sync".
        removed["daily_price"] = 0

        if db_size > max_size_mb:
            # Clean up stale factor snapshots only (keep latest per code)
            stale = self.engine.fetchall(
                """SELECT fs.market, fs.code, fs.date
                   FROM factor_snapshot fs
                   WHERE EXISTS (
                       SELECT 1
                       FROM (SELECT market AS m, code AS c,
                                    MAX(date) AS latest_date
                             FROM factor_snapshot
                             GROUP BY market, code) latest
                       WHERE latest.m = fs.market
                         AND latest.c = fs.code
                         AND latest.latest_date > fs.date
                   )"""
            )
            removed["factor_snapshot"] = len(stale)
            self.engine.execute(
                """DELETE FROM factor_snapshot fs
                   WHERE EXISTS (
                       SELECT 1
                       FROM (SELECT market AS m, code AS c,
                                    MAX(date) AS latest_date
                             FROM factor_snapshot
                             GROUP BY market, code) latest
                       WHERE latest.m = fs.market
                         AND latest.c = fs.code
                         AND latest.latest_date > fs.date
                   )"""
            )

        # Clean up expired KV store entries
        from time import time

        before_kv = int(
            self.engine.fetchval("SELECT COUNT(*) FROM kv_store", default=0) or 0
        )
        self.engine.execute("DELETE FROM kv_store WHERE expires < ?", (time(),))
        after_kv = int(
            self.engine.fetchval("SELECT COUNT(*) FROM kv_store", default=0) or 0
        )
        removed["kv_store"] = before_kv - after_kv

        # Reclaim storage after heavy deletes (autocommit per statement).
        self.engine.vacuum()
        return removed
