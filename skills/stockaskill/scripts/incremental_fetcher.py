"""Abstract base class for incremental cache-fetch patterns.

Eliminates duplicated "check cache → compute fetch range → fetch → upsert → fallback"
logic across get_kline, get_fund_nav, get_market_index, and get_fundamentals.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config import get as cfg_get
from utils import normalize_code_for_market

logger = logging.getLogger(__name__)


def _cold_start_date(market: str) -> str:
    """Return market-specific cold start baseline date."""
    defaults = {"A": "20000101", "HK": "19950101", "US": "19900101"}
    return cfg_get("full_history_start_date", defaults.get(market, "20000101"))


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _safe_parse_date(s: str) -> Optional[datetime]:
    s = str(s).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _latest_date(rows: List[Dict[str, Any]], field: str = "date") -> str:
    """Latest date string from cached rows (newest-first order assumed)."""
    if rows:
        return str(rows[0].get(field, "") or "").strip()
    return ""


def _earliest_date(rows: List[Dict[str, Any]], field: str = "date") -> str:
    """Earliest date string from cached rows."""
    values = sorted(
        str(r.get(field, "")).strip() for r in rows if str(r.get(field, "")).strip()
    )
    return values[0] if values else ""


class IncrementalCacheFetcher(ABC):
    """Base class that encodes the incremental cache-fetch lifecycle.

    Subclass and override the abstract methods to wire in cache reads,
    cache writes, and the upstream fetch function.

    Lifecycle:
        1. read_cached() → get existing rows from cache
        2. is_cache_fresh(cached) → decide whether to skip API call
        3. compute_fetch_range(cached, days, full_history) → (start, end)
        4. fetch(start, end) → upstream fetch; return new rows or []
        5. write_cached(new_rows) → upsert into cache
        6. read_cached() again → return updated rows
        7. On fetch failure → fall back to original cached rows
    """

    @abstractmethod
    def read_cached(self) -> List[Dict[str, Any]]:
        """Read all cached rows for this data scope."""
        ...

    @abstractmethod
    def write_cached(self, rows: List[Dict[str, Any]]) -> None:
        """Upsert new rows into cache."""
        ...

    @abstractmethod
    def fetch(self, start: str, end: str) -> List[Dict[str, Any]]:
        """Fetch new data from upstream for [start, end]. Return empty on failure."""
        ...

    def is_cache_fresh(
        self, cached: List[Dict[str, Any]], days: int, force_refresh: bool
    ) -> bool:
        """Return True if cache is sufficient and can skip the API call.

        Default: cached rows >= days AND latest date == today.
        Override for TTL-based checks (e.g. fundamentals staleness).
        """
        if not cached or force_refresh:
            return False
        if len(cached) < days:
            return False
        latest = _latest_date(cached)
        return latest == _date_str(datetime.now())

    def compute_fetch_range(
        self,
        cached: List[Dict[str, Any]],
        days: int,
        full_history: bool,
    ) -> tuple:
        """Return (start_date_str, end_date_str) for the upstream fetch.

        Default implementation handles the common incremental pattern:
        - full_history: pull from cold start or fill gaps
        - incremental: from latest cached date (+ padding) to today
        - cold start: from N days ago to today
        """
        today_str = _date_str(datetime.now())
        padding = cfg_get("kline_incremental_padding_days", 3)

        if full_history:
            return self._full_history_range(cached, padding, today_str)

        if cached:
            latest = _latest_date(cached)
            if latest:
                latest_dt = _safe_parse_date(latest)
                if latest_dt:
                    start = _date_str(latest_dt - timedelta(days=padding))
                else:
                    start = _date_str(datetime.now() - timedelta(days=days + 30))
            else:
                start = _date_str(datetime.now() - timedelta(days=days + 30))
        else:
            start = _date_str(datetime.now() - timedelta(days=days + 30))

        return start, today_str

    def _full_history_range(
        self,
        cached: List[Dict[str, Any]],
        padding: int,
        today_str: str,
    ) -> tuple:
        """Compute fetch range for full_history mode.

        Handles the bidirectional gap-fill: if both early and late data
        are missing, prefer the smaller gap to minimise work.
        """
        target_start = _cold_start_date(self._market())

        if not cached:
            return target_start, today_str

        local_earliest = _earliest_date(cached)
        local_latest = _latest_date(cached)

        # Already fully covered — nothing to fetch
        if (
            local_earliest
            and local_latest
            and local_earliest <= target_start
            and local_latest == today_str
        ):
            return None, None  # signals caller to skip fetch

        needs_early = local_earliest > target_start if local_earliest else True
        needs_latest = local_latest < today_str if local_latest else True

        if needs_early and needs_latest:
            early_dt = _safe_parse_date(local_earliest)
            latest_dt = _safe_parse_date(local_latest)
            if early_dt and latest_dt:
                early_gap = (early_dt - _safe_parse_date(target_start)).days
                latest_gap = (_safe_parse_date(today_str) - latest_dt).days
                if early_gap <= latest_gap:
                    return target_start, _date_str(early_dt + timedelta(days=3))
                else:
                    return _date_str(latest_dt - timedelta(days=padding)), today_str
            # Fall back to early-first if dates can't be parsed
            return target_start, _date_str(
                _safe_parse_date(local_earliest) + timedelta(days=3)
            )
        elif needs_early:
            early_dt = _safe_parse_date(local_earliest)
            if early_dt:
                return target_start, _date_str(early_dt + timedelta(days=3))
            return target_start, today_str
        else:
            # needs_latest only
            latest_dt = _safe_parse_date(local_latest)
            if latest_dt:
                return _date_str(latest_dt - timedelta(days=padding)), today_str
            return _date_str(datetime.now() - timedelta(days=365 + 30)), today_str

    def run(
        self,
        days: int = 365,
        force_refresh: bool = False,
        full_history: bool = False,
        cached_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute the full incremental fetch lifecycle.

        Returns cached rows (sliced to ``days``) after attempting to
        fill any gaps from the upstream source.
        """
        cached = self.read_cached()

        if cached_only:
            return cached[:days] if cached else []

        if self.is_cache_fresh(cached, days, force_refresh):
            return cached[:days]

        start, end = self.compute_fetch_range(cached, days, full_history)

        if start is None and end is None:
            # Full history already covered — skip fetch
            return cached[:days] if days else cached

        new_rows = self.fetch(start, end)
        if new_rows:
            self.write_cached(new_rows)
            cached = self.read_cached()
        elif not cached:
            # Fetch returned zero rows and we have nothing cached either
            cached = self.read_cached()  # double-check after upsert attempt

        return cached[:days] if cached else []

    def _market(self) -> str:
        """Return the market string for cold-start lookup. Override in subclass."""
        return "A"


# ---------------------------------------------------------------------------
# K-line fetcher
# ---------------------------------------------------------------------------

class KlineFetcher(IncrementalCacheFetcher):
    """Incremental fetcher for daily K-line (OHLCV) data."""

    def __init__(self, code: str, market: str = "A") -> None:
        self.code = normalize_code_for_market(code, market)
        self.market = market
        self._detect_quality = None
        self._fetch_fn = None

    def read_cached(self) -> List[Dict[str, Any]]:
        from cache import get_cache
        return get_cache().get_daily_price(self.code, market=self.market)

    def write_cached(self, rows: List[Dict[str, Any]]) -> None:
        from cache import get_cache
        if self._detect_quality:
            rows = self._detect_quality(rows, self.market)
        get_cache().upsert_daily_price(rows)

    def fetch(self, start: str, end: str) -> List[Dict[str, Any]]:
        """Import the existing _fetch_kline from data_engine."""
        from data_engine import _fetch_kline
        return _fetch_kline(self.code, self.market, start, end)

    def _market(self) -> str:
        return self.market


def get_kline_incremental(
    code: str,
    market: str = "A",
    days: int = 365,
    force_refresh: bool = False,
    full_history: bool = False,
    cached_only: bool = False,
    detect_quality=None,
) -> List[Dict[str, Any]]:
    """Get K-line data via the incremental fetcher.

    This is the new entry point; the old get_kline in data_engine.py
    should be replaced by calls to this function.
    """
    fetcher = KlineFetcher(code, market)
    fetcher._detect_quality = detect_quality
    return fetcher.run(days, force_refresh, full_history, cached_only)


# ---------------------------------------------------------------------------
# Fund NAV fetcher
# ---------------------------------------------------------------------------

class FundNavFetcher(IncrementalCacheFetcher):
    """Incremental fetcher for ETF/fund NAV history."""

    def __init__(self, code: str, days: int = 365) -> None:
        self.code = code
        self._days = days

    def read_cached(self) -> List[Dict[str, Any]]:
        from cache import get_cache
        return get_cache().get_fund_nav(self.code, self._days)

    def write_cached(self, rows: List[Dict[str, Any]]) -> None:
        from cache import get_cache
        get_cache().upsert_fund_nav(rows)

    def fetch(self, start: str, end: str) -> List[Dict[str, Any]]:
        """Inline fetch logic for fund NAV (uses AKShare stock_zh_a_daily)."""
        import logging
        logger = logging.getLogger(__name__)
        from data_engine import _try_akshare, _akshare_lock

        ak = _try_akshare()
        if not ak:
            return []

        # Fund NAV uses A-share daily data with forward adjustment
        from data_engine import _sina_code

        try:
            with _akshare_lock:
                df = ak.stock_zh_a_daily(symbol=_sina_code(self.code, "A"), adjust="qfq")
            if df is None or df.empty:
                return []

            df["date"] = df["date"].astype(str)
            clean_start = start.replace("-", "")
            clean_end = end.replace("-", "")
            dates_clean = df["date"].str.replace("-", "")
            df = df[(dates_clean >= clean_start) & (dates_clean <= clean_end)]

            rows = []
            for _, r in df.iterrows():
                rows.append({
                    "code": self.code,
                    "date": str(r.get("date", "")),
                    "nav": float(r.get("close", 0) or 0),
                    "acc_nav": 0.0,
                })
            return rows
        except RuntimeError as exc:
            if "Daily API limit reached" not in str(exc):
                logger.warning("FundNavFetcher fetch failed for %s: %s", self.code, exc)
        except Exception as exc:
            logger.warning("FundNavFetcher fetch failed for %s: %s", self.code, exc)
        return []


def get_fund_nav_incremental(
    code: str,
    days: int = 365,
    cached_only: bool = False,
    force_refresh: bool = False,
    full_history: bool = False,
) -> List[Dict[str, Any]]:
    """Get ETF NAV history via the incremental fetcher."""
    fetcher = FundNavFetcher(code, days)
    return fetcher.run(days, force_refresh, full_history, cached_only)


# ---------------------------------------------------------------------------
# Market index fetcher
# ---------------------------------------------------------------------------

class MarketIndexFetcher(IncrementalCacheFetcher):
    """Incremental fetcher for market index K-line data."""

    def __init__(self, index_code: str, days: int = 250) -> None:
        self.index_code = index_code
        self._days = days

    def read_cached(self) -> List[Dict[str, Any]]:
        from cache import get_cache
        return get_cache().get_market_index(self.index_code, self._days)

    def write_cached(self, rows: List[Dict[str, Any]]) -> None:
        from cache import get_cache
        get_cache().upsert_market_index(rows)

    def fetch(self, start: str, end: str) -> List[Dict[str, Any]]:
        """Import the existing _fetch_market_index from data_engine."""
        from data_engine import _fetch_market_index
        return _fetch_market_index(self.index_code, start, end)


def get_market_index_incremental(
    index_code: str = "000001",
    days: int = 250,
    cached_only: bool = False,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """Get market index K-line via the incremental fetcher."""
    fetcher = MarketIndexFetcher(index_code, days)
    return fetcher.run(days, force_refresh, full_history=False, cached_only=cached_only)
