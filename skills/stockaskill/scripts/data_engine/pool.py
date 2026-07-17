"""Core data engine: pool module."""

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from cache import get_cache
from config import get as cfg_get
from utils import (
    _suppress_output,
    normalize_code_for_market,
    safe_float,
)

from data_engine.config import (
    _akshare_lock,
    _api_call,
    _is_etf_market,
    _try_akshare,
    _try_baostock,
)
from data_engine.kline import get_kline

_cache = get_cache()

logger = logging.getLogger(__name__)


_BAOSTOCK_QUERY_TIMEOUT = 30  # seconds, per query


def _bs_query_with_timeout(bs, method_name: str, *args, **kwargs):
    """Run a Baostock query call in a thread with a timeout.


    Returns the query result on success, raises TimeoutError on timeout,

    or re-raises the original exception on failure.

    """

    def _do_query():

        return getattr(bs, method_name)(*args, **kwargs)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_do_query)

        try:
            return future.result(timeout=_BAOSTOCK_QUERY_TIMEOUT)

        except FuturesTimeout:
            raise TimeoutError(
                f"Baostock {method_name} timed out after {_BAOSTOCK_QUERY_TIMEOUT}s"
            )


def _bs_iter_with_timeout(rs, label: str):
    """Iterate Baostock ResultSet rows with a per-row timeout."""

    while rs.error_code == "0":

        def _next_row():

            if rs.next():
                return rs.get_row_data()

            return None  # end of data

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_next_row)

            try:
                row = future.result(timeout=_BAOSTOCK_QUERY_TIMEOUT)

            except FuturesTimeout:
                raise TimeoutError(
                    f"Baostock {label} row iteration timed out after {_BAOSTOCK_QUERY_TIMEOUT}s"
                )

        if row is None:
            break

        yield row


def get_stock_pool(
    market: str = "A", force_refresh: bool = False, include_inactive: bool = False
) -> List[Dict[str, Any]]:
    """Get stock pool for a market. Returns cached data, refreshes if needed.


    Args:

        market: Market identifier.

        force_refresh: Force a pool rebuild from upstream API.

        include_inactive: Include delisted/inactive stocks (for backtests).

    """

    if force_refresh or _cache.pool_needs_refresh(market):
        _refresh_stock_pool(market)

    return _cache.get_stock_pool(market, include_inactive=include_inactive)


def ensure_stock_pool_candidates_ready(
    market: str,
    codes: Sequence[str],
) -> Dict[str, int]:
    """Backfill critical pool metadata for candidate codes.


    For A-shares, list-date gaps are filled from company profile data first,

    then from cached/full-history K-line as a fallback. Industry and sector are

    also updated when profile data is available.

    """

    normalized_codes = [
        normalize_code_for_market(code, market) for code in codes if str(code).strip()
    ]

    if not normalized_codes:
        return {
            "requested": len(normalized_codes),
            "already_ready": 0,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 0,
            "missing_market_cap": 0,
            "metadata_complete": 0,
            "metadata_partial": 0,
            "inactive_count": 0,
        }

    if market != "A":
        non_a_pool = {
            row["code"]: dict(row)
            for row in _cache.get_stock_pool(market)
            if row.get("code")
        }

        target_rows = [
            non_a_pool[code] for code in normalized_codes if code in non_a_pool
        ]

        metadata_complete = sum(
            1
            for row in target_rows
            if float(row.get("metadata_completeness", 0) or 0) >= 0.75
        )

        inactive_count = sum(
            1 for row in target_rows if not bool(row.get("is_active", 1))
        )

        return {
            "requested": len(normalized_codes),
            "already_ready": len(target_rows),
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": sum(
                1 for row in target_rows if not str(row.get("list_date", "")).strip()
            ),
            "missing_market_cap": sum(
                1
                for row in target_rows
                if float(row.get("total_market_cap", 0) or 0) <= 0
            ),
            "metadata_complete": metadata_complete,
            "metadata_partial": max(len(target_rows) - metadata_complete, 0),
            "inactive_count": inactive_count,
        }

    pool_map = {
        row["code"]: dict(row)
        for row in _cache.get_stock_pool(market)
        if row.get("code")
    }

    target_rows = [pool_map[code] for code in normalized_codes if code in pool_map]

    if not target_rows:
        return {
            "requested": len(normalized_codes),
            "already_ready": 0,
            "profile_backfilled": 0,
            "cached_history_backfilled": 0,
            "remote_history_backfilled": 0,
            "still_missing_list_date": 0,
            "missing_market_cap": 0,
        }

    updated_rows: List[Dict[str, Any]] = []

    already_ready = 0

    profile_backfilled = 0

    cached_history_backfilled = 0

    remote_history_backfilled = 0

    for row in target_rows:
        row_changed = False

        list_date = str(row.get("list_date", "")).strip()

        if list_date:
            already_ready += 1

        else:
            profile_data = _fetch_a_stock_profile_metadata(row["code"]) or {}

            profile_list_date = str(profile_data.get("list_date", "")).strip()

            if profile_list_date:
                row["list_date"] = profile_list_date

                row_changed = True

                profile_backfilled += 1

            if not str(row.get("industry", "")).strip():
                profile_industry = str(profile_data.get("industry", "")).strip()

                if profile_industry:
                    row["industry"] = profile_industry

                    row_changed = True

            if not str(row.get("sector", "")).strip():
                profile_sector = str(profile_data.get("sector", "")).strip()

                if profile_sector:
                    row["sector"] = profile_sector

                    row_changed = True

            if not str(row.get("list_date", "")).strip():
                inferred_date, used_remote = _infer_list_date_from_history(
                    row["code"],
                    market,
                )

                if inferred_date:
                    row["list_date"] = inferred_date

                    row_changed = True

                    if used_remote:
                        remote_history_backfilled += 1

                    else:
                        cached_history_backfilled += 1

        if row_changed:
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            updated_rows.append(row)

    if updated_rows:
        _cache.upsert_stock_pool(updated_rows)

    refreshed_map = {
        row["code"]: row for row in _cache.get_stock_pool(market) if row.get("code")
    }

    still_missing_list_date = sum(
        1
        for code in normalized_codes
        if not str(refreshed_map.get(code, {}).get("list_date", "")).strip()
    )

    missing_market_cap = sum(
        1
        for code in normalized_codes
        if float(refreshed_map.get(code, {}).get("total_market_cap", 0) or 0) <= 0
    )

    return {
        "requested": len(normalized_codes),
        "already_ready": already_ready,
        "profile_backfilled": profile_backfilled,
        "cached_history_backfilled": cached_history_backfilled,
        "remote_history_backfilled": remote_history_backfilled,
        "still_missing_list_date": still_missing_list_date,
        "missing_market_cap": missing_market_cap,
        "metadata_complete": sum(
            1
            for code in normalized_codes
            if float(refreshed_map.get(code, {}).get("metadata_completeness", 0) or 0)
            >= 0.75
        ),
        "metadata_partial": sum(
            1
            for code in normalized_codes
            if float(refreshed_map.get(code, {}).get("metadata_completeness", 0) or 0)
            < 0.75
        ),
        "inactive_count": sum(
            1
            for code in normalized_codes
            if not bool(refreshed_map.get(code, {}).get("is_active", 1))
        ),
    }


def _refresh_stock_pool(market: str) -> None:
    """Fetch full stock pool from API and cache it."""

    ak = _try_akshare()

    if ak is None:
        print(
            "[WARN] akshare not installed, cannot refresh stock pool. "
            "Run: pip install akshare"
        )

        return

    print(f"[pool] Fetching {market} pool from upstream...")

    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if market == "A":
            df = _fetch_a_stock_pool(ak)

            if df is not None and not df.empty:
                has_limited = (
                    df["industry"].eq("").all() or df["list_date"].eq("").all()
                )

                if has_limited:
                    df = _backfill_pool_metadata_from_bs(df)

                n = len(df)

                warn_min = cfg_get("pool_size_warn_min", 4000)

                warn_max = cfg_get("pool_size_warn_max", 6000)

                if n < warn_min:
                    print(
                        f"[WARN] A-share pool has only {n} stocks"
                        f" (expected {warn_min}-{warn_max}). Data may be incomplete."
                    )

                elif n > warn_max:
                    print(
                        f"[WARN] A-share pool has {n} stocks"
                        f" (expected 5000-6000). May include non-stocks."
                    )

                print(f"  A-share pool: {n} stocks cached")

            else:
                print("  A-share pool: empty response, cache preserved")

        elif market == "HK":
            df = _fetch_hk_stock_pool(ak)

            if df is not None and not df.empty:
                print(f"  HK pool: {len(df)} stocks cached")

            else:
                print("  HK pool: empty response, cache preserved")

        elif market == "US":
            df = _fetch_us_stock_pool(ak)

            if df is not None and not df.empty:
                print(f"  US pool: {len(df)} stocks cached")

            else:
                print("  US pool: empty response, cache preserved")

        elif _is_etf_market(market):
            df = _fetch_fund_pool_df(ak)

            if df is not None and not df.empty:
                pool_rows = []

                for _, r in df.iterrows():
                    pool_rows.append(
                        {
                            "code": normalize_code_for_market(
                                str(r.get("code", "")),
                                "FUND",
                            ),
                            "name": str(r.get("name", "")),
                            "market": "FUND",
                            "sector": "",
                            "industry": str(r.get("fund_type", "ETF")),
                            "list_date": "",
                            "total_market_cap": safe_float(
                                r.get("total_market_cap", 0)
                            ),
                            "is_active": 1,
                            "metadata_source": "akshare_fund_etf_spot_em",
                            "metadata_status": "active",
                            "metadata_completeness": 0.25,
                            "updated_at": now,
                        }
                    )

                _cache.upsert_stock_pool(pool_rows)

                print(f"  FUND pool: {len(pool_rows)} ETFs cached")

            else:
                print("  FUND pool: empty response, cache preserved")

            return

        else:
            return

        if df is not None and not df.empty:
            rows = []

            for _, r in df.iterrows():
                raw_code = str(r.get("code", ""))

                rows.append(
                    {
                        "code": normalize_code_for_market(raw_code, market),
                        "name": str(r.get("name", "")),
                        "market": market,
                        "sector": str(r.get("sector", "")),
                        "industry": str(r.get("industry", "")),
                        "list_date": str(r.get("list_date", "")),
                        "total_market_cap": safe_float(r.get("total_market_cap", 0)),
                        "is_active": int(r.get("is_active", 1) or 0),
                        "metadata_source": str(r.get("metadata_source", "")),
                        "metadata_status": str(r.get("metadata_status", "")),
                        "metadata_completeness": safe_float(
                            r.get("metadata_completeness", 0)
                        ),
                        "updated_at": now,
                    }
                )

            _cache.upsert_stock_pool(rows)

        else:
            # API returned empty data (rate-limited or temporary outage).

            # Preserve existing cached pool and bump the refresh timestamp

            # so callers don't hammer the API on every invocation.

            _cache._touch_meta(_cache._stock_pool_meta_key(market), 0)

    except Exception as exc:
        print(f"[WARN] Failed to refresh stock pool for {market}: {exc}")

        # Same fallback on exception: bump TTL so we don't retry immediately.

        _cache._touch_meta(_cache._stock_pool_meta_key(market), 0)


@_api_call("stock_pool_a")
def _fetch_a_stock_pool(ak) -> Optional[pd.DataFrame]:
    """Fetch A-share pool: EastMoney -> Sina -> Baostock."""

    # Attempt 1: EastMoney with full fields

    try:
        with _akshare_lock:
            df = ak.stock_zh_a_spot_em()

        col_map = {
            "代码": "code",
            "名称": "name",
            "总市值": "total_market_cap",
            "行业": "industry",
            "地区": "sector",
            "市盈率动态": "pe_ttm",
        }

        df = df.rename(columns=col_map)

        df["list_date"] = ""

        df["total_market_cap"] = df["total_market_cap"].fillna(0).astype(float)

        if "industry" not in df.columns:
            df["industry"] = ""

        if "sector" not in df.columns:
            df["sector"] = ""

        print(f"Fetch A-share pool via EM ({len(df)} stocks)")

        return df

    except Exception:
        print("EM pool failed, fallback to Sina.")

    # Attempt 2: Sina (code+name only), then enrich with Baostock

    try:
        with _akshare_lock:
            df = ak.stock_info_a_code_name()

        print(f"Sina pool OK ({len(df)} stocks), enriching via Baostock...")

        try:
            df = _enrich_a_pool_from_baostock(df)

        except Exception as enrich_exc:
            print(f"Baostock enrichment failed ({enrich_exc}), using Sina-only data.")

        print(f"Fetch A-share pool via Sina ({len(df)} stocks)")

        return df

    except Exception:
        print("Sina pool failed, fallback to Baostock.")

    # Attempt 3: Baostock (code+name+ipoDate)

    return _fetch_a_stock_pool_baostock()


def _fetch_a_stock_pool_baostock() -> Optional[pd.DataFrame]:
    """Fetch A-share pool from Baostock as last resort."""

    bs = _try_baostock()

    if bs is None:
        print("Baostock not available for pool fetch.")

        return None

    try:
        rs = _bs_query_with_timeout(bs, "query_stock_basic")

        rows = []

        for row in _bs_iter_with_timeout(rs, "query_stock_basic"):
            if row[4] == "1" and row[5] == "1":
                code = row[0]

                if code.startswith(("sh.", "sz.", "bj.")):
                    code = code[3:]

                rows.append(
                    {
                        "code": code,
                        "name": row[1],
                        "industry": "",
                        "sector": "",
                        "list_date": str(row[2]).strip(),
                        "total_market_cap": 0.0,
                    }
                )

        if rows:
            print(f"Fetch A-share pool via Baostock ({len(rows)} stocks)")

            return pd.DataFrame(rows)

        return None

    except TimeoutError as exc:
        print(f"[WARN] Baostock pool query timed out: {exc}")

        return None

    except Exception as exc:
        print(f"Baostock pool fetch failed: {exc}")

        return None

    finally:
        try:
            with _suppress_output():
                bs.logout()

        except Exception:
            pass


def _enrich_a_pool_from_baostock(df: pd.DataFrame) -> pd.DataFrame:
    """Add industry and list_date to a Sina-fetched A-share pool via Baostock.


    Each Baostock query is wrapped with a per-query timeout so the call cannot

    hang indefinitely.  On timeout or failure the original Sina DataFrame is

    returned with empty enrichment fields — partial data is better than no data.

    """

    bs = _try_baostock()

    if bs is None or df is None or df.empty:
        df["industry"] = ""

        df["sector"] = ""

        df["list_date"] = ""

        if "total_market_cap" not in df.columns:
            df["total_market_cap"] = 0.0

        return df

    basic_map: Dict[str, str] = {}

    industry_map: Dict[str, str] = {}

    basic_ok = False

    industry_ok = False

    try:
        # Build mapping from Baostock: code -> {list_date}

        rs = _bs_query_with_timeout(bs, "query_stock_basic")

        for row in _bs_iter_with_timeout(rs, "query_stock_basic"):
            code = row[0]

            if code.startswith(("sh.", "sz.", "bj.")):
                code = code[3:]

            if len(row) > 4 and row[4] == "1":  # stock type
                basic_map[code] = str(row[2]).strip()

        basic_ok = True

    except TimeoutError as exc:
        print(f"[WARN] Baostock query_stock_basic timed out: {exc}")

    except Exception as exc:
        print(f"[WARN] Baostock query_stock_basic failed: {exc}")

    if basic_ok:
        try:
            # Build mapping from Baostock: code -> industry

            rs2 = _bs_query_with_timeout(bs, "query_stock_industry")

            for row_data in _bs_iter_with_timeout(rs2, "query_stock_industry"):
                # Fields: updateDate, code, code_name, industry, industryClassification

                code = row_data[1] if len(row_data) > 1 else ""

                if code.startswith(("sh.", "sz.", "bj.")):
                    code = code[3:]

                ind = str(row_data[3]).strip() if len(row_data) > 3 else ""

                if ind:
                    industry_map[code] = ind

            industry_ok = True

        except TimeoutError as exc:
            print(f"[WARN] Baostock query_stock_industry timed out: {exc}")

        except Exception as exc:
            print(f"[WARN] Baostock query_stock_industry failed: {exc}")

    if not basic_ok and not industry_ok:
        print("[WARN] Both Baostock queries failed, using Sina-only data.")

    else:
        got = []

        if basic_ok:
            got.append("list_date")

        if industry_ok:
            got.append("industry")

        print(f"Baostock enriched: {', '.join(got)}.")

    # Apply whatever we managed to get

    if basic_map:
        df["list_date"] = df["code"].map(basic_map).fillna("").astype(str)

    elif "list_date" not in df.columns:
        df["list_date"] = ""

    if industry_map:
        df["industry"] = df["code"].map(industry_map).fillna("").astype(str)

    elif "industry" not in df.columns:
        df["industry"] = ""

    if "sector" not in df.columns:
        df["sector"] = ""

    if "total_market_cap" not in df.columns:
        df["total_market_cap"] = 0.0

    else:
        df["total_market_cap"] = df["total_market_cap"].fillna(0).astype(float)

    try:
        with _suppress_output():
            bs.logout()

    except Exception:
        pass

    return df


def _backfill_pool_metadata_from_bs(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich pool DataFrame with industry/list_date from Baostock."""

    bs = _try_baostock()

    if bs is None or df is None or df.empty:
        return df

    try:
        rs = bs.query_stock_basic()

        meta_map: Dict[str, Dict[str, str]] = {}

        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()

            code = row[0]

            if code.startswith("sh."):
                code = code[3:]

            elif code.startswith("sz."):
                code = code[3:]

            elif code.startswith("bj."):
                code = code[3:]

            meta_map[code] = {
                "industry": "",
                "list_date": str(row[2]).strip(),
            }

        has_changes = False

        for idx, row in df.iterrows():
            code = str(row.get("code", ""))

            if code in meta_map:
                meta = meta_map[code]

                if not str(row.get("list_date", "")).strip() and meta["list_date"]:
                    df.at[idx, "list_date"] = meta["list_date"]

                    has_changes = True

                if not str(row.get("industry", "")).strip() and meta["industry"]:
                    df.at[idx, "industry"] = meta["industry"]

                    has_changes = True

        if has_changes:
            print("Pool metadata backfilled from Baostock.")

        return df

    except Exception as exc:
        print(f"Baostock pool metadata backfill failed: {exc}")

        return df

    finally:
        try:
            with _suppress_output():
                bs.logout()

        except Exception:
            pass


def _fetch_a_stock_profile_metadata(code: str) -> Dict[str, str]:
    """Fetch basic company profile data for one A-share code."""

    ak = _try_akshare()

    if ak is None:
        return {}

    try:
        with _akshare_lock:
            df = ak.stock_profile_cninfo(symbol=code)

    except Exception:
        return {}

    if df is None or df.empty:
        return {}

    first_row = df.iloc[0]

    return {
        "list_date": str(first_row.get("上市日期", "")).strip(),
        "industry": str(first_row.get("所属行业", "")).strip(),
        "sector": str(first_row.get("所属市场", "")).strip(),
    }


def _infer_list_date_from_history(code: str, market: str) -> tuple[str, bool]:
    """Infer list date from cached/full-history K-line data."""

    cached_rows = _cache.get_daily_price(code, market=market)

    if cached_rows:
        dates = sorted(
            str(row.get("date", "")).strip() for row in cached_rows if row.get("date")
        )

        if dates:
            return dates[0], False

    get_kline(
        code,
        market,
        days=365,
        full_history=True,
        force_refresh=False,
    )

    cached_rows = _cache.get_daily_price(code, market=market)

    dates = sorted(
        str(row.get("date", "")).strip() for row in cached_rows if row.get("date")
    )

    if dates:
        return dates[0], True

    return "", True


def _normalize_cross_market_pool_row(
    row,
    source,
):
    """Normalize a single row from HK/US spot data to pool schema columns.

    Args:
        row: Single DataFrame row from AKShare spot API.
        source: Source identifier string for logging.

    Returns:
        Dict with normalized column names matching the stock_pool schema.
    """
    return {
        "market": "HK" if "_hk_" in source else "US",
        "code": str(row.get("code", row.get("symbol", ""))).strip(),
        "name": str(
            row.get("name", row.get("stock_name", row.get("ticker", "")))
        ).strip(),
        "total_market_cap": safe_float(
            row.get("market_cap", row.get("total_market_cap", 0))
        ),
        "sector": "",
        "industry": "",
        "list_date": "",
        "is_active": 1,
        "metadata_source": source,
        "metadata_status": "minimal",
        "metadata_completeness": 0.3,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@_api_call("stock_pool_hk")
def _fetch_hk_stock_pool(ak) -> Optional[pd.DataFrame]:
    """Fetch HK pool via Sina and extract minimal metadata when available."""

    with _suppress_output(capture_exceptions=True):
        with _akshare_lock:
            df = ak.stock_hk_spot()

    if df is None or df.empty:
        return df

    rows = [
        _normalize_cross_market_pool_row(df.iloc[idx], "akshare_stock_hk_spot")
        for idx in range(len(df))
    ]

    return pd.DataFrame(rows)


@_api_call("stock_pool_us")
def _fetch_us_stock_pool(ak) -> Optional[pd.DataFrame]:
    """Fetch US pool via Sina and extract minimal metadata when available."""

    with _suppress_output(capture_exceptions=True):
        with _akshare_lock:
            df = ak.stock_us_spot()

    if df is None or df.empty:
        return df

    rows = [
        _normalize_cross_market_pool_row(df.iloc[idx], "akshare_stock_us_spot")
        for idx in range(len(df))
    ]

    return pd.DataFrame(rows)


@_api_call("fund_pool")
def _fetch_fund_pool_df(ak) -> Optional[pd.DataFrame]:
    """Fetch ETF/fund pool via EastMoney."""

    with _akshare_lock:
        df = ak.fund_etf_spot_em()

    col_map = {
        "\u4ee3\u7801": "code",
        "\u540d\u79f0": "name",
        "\u6700\u65b0\u4ef7": "nav",
        "\u603b\u5e02\u503c": "total_market_cap",
    }

    df = df.rename(columns=col_map)

    df["fund_type"] = "ETF"

    return df
