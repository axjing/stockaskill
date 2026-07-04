"""Market scanner: find top stocks across markets."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional

from cache import get_cache
from config import get as cfg_get
from data_engine import (
    ensure_stock_pool_candidates_ready,
    get_fundamentals,
    get_kline,
    get_stock_pool,
)
from data_readiness import ensure_market_scan_ready
from factors.composite import CompositeAnalyzer
from utils import is_new, is_st

_SCAN_HISTORY_DAYS = 365
_MIN_HISTORY_ROWS = 240
_NEW_LISTING_DAYS = 60
_METADATA_COMPLETE_THRESHOLD = 0.75
_METADATA_PARTIAL_THRESHOLD = 0.50


class MarketScanner:
    """Scan and rank stocks by composite score."""

    def __init__(self) -> None:
        self.cache = get_cache()

    def scan_top(
        self,
        market: str = "A",
        top_n: int = 20,
        sector: Optional[str] = None,
        min_mcap: float = 0,
        max_mcap: float = float("inf"),
        max_candidates: int = 0,
    ) -> List[Dict[str, Any]]:
        """Scan market and return top N stocks by composite score.

        Args:
            market: Market identifier (A/HK/US/FUND).
            top_n: Number of results.
            sector: Optional sector filter.
            min_mcap: Minimum market cap filter.
            max_mcap: Maximum market cap filter.
            max_candidates: Max stocks to evaluate (0=auto, default 200).

        Returns:
            List of dicts with code, name, score, and factor details.
        """
        pool = get_stock_pool(market)
        if not pool:
            return []

        limit = max_candidates or cfg_get("scan_max_candidates", 200)
        metadata_limit = cfg_get(
            "data_readiness.scan_pool_metadata_limit",
            limit,
        )
        pre_candidates = []
        for stock in pool:
            code = stock.get("code", "")
            name = stock.get("name", "")

            # Filter ST/delisted
            if is_st(code, name):
                continue
            if not bool(stock.get("is_active", 1)):
                continue

            # Sector filter
            if sector and stock.get("sector") != sector:
                continue

            if code.startswith("bj"):
                continue

            pre_candidates.append(stock)

        if not pre_candidates:
            return []

        metadata_candidates = pre_candidates[: max(metadata_limit, limit)]
        metadata_status = ensure_stock_pool_candidates_ready(
            market,
            [str(stock.get("code", "")) for stock in metadata_candidates],
        )
        self._print_pool_metadata_status(metadata_status)

        refreshed_pool = {
            str(stock.get("code", "")): stock for stock in get_stock_pool(market)
        }
        enriched_candidates = [
            refreshed_pool.get(str(stock.get("code", "")), stock)
            for stock in metadata_candidates
        ]

        filtered = []
        skipped_new = 0
        unknown_list_date = 0
        for stock in enriched_candidates:
            list_date = str(stock.get("list_date", "")).strip()
            if list_date:
                if is_new(list_date, threshold_days=60):
                    skipped_new += 1
                    continue
            else:
                unknown_list_date += 1

            mcap = float(stock.get("total_market_cap", 0) or 0)
            if mcap > 0 and (mcap < min_mcap or mcap > max_mcap):
                continue

            filtered.append(stock)

        if skipped_new:
            print(
                f"  Excluded {skipped_new} newly listed candidates using cached"
                " listing dates.",
                flush=True,
            )
        if unknown_list_date:
            print(
                f"  Listing date still unavailable for {unknown_list_date}"
                " candidates; they remain eligible for scan.",
                flush=True,
            )

        if not filtered:
            return []

        metadata_quality = self._metadata_quality_counts(filtered)
        self._print_metadata_quality_summary(metadata_quality, label="candidate")

        candidates_with_mcap = [
            stock
            for stock in filtered
            if float(stock.get("total_market_cap", 0) or 0) > 0
        ]
        if candidates_with_mcap:
            filtered.sort(
                key=lambda s: float(s.get("total_market_cap", 0) or 0),
                reverse=True,
            )
            if len(candidates_with_mcap) < len(filtered):
                print(
                    "  Market-cap data missing for part of the candidate set;"
                    " ranked those names last.",
                    flush=True,
                )
        else:
            print(
                "  Candidate market-cap data not cached yet; preserving pool"
                " order for scan.",
                flush=True,
            )

        candidates = filtered[:limit]

        n = len(candidates)
        if n == 0:
            print(
                "  No candidates to score (stock pool may be empty or all filtered"
                " out). "
                "Use 'python stockaskill/scripts/run.py fetch pool' to refresh"
                " data.",
                flush=True,
            )
            return []

        sync_status = ensure_market_scan_ready(market, candidates)
        self._print_readiness_summary(sync_status)
        print(f"Scoring {n} candidates...", flush=True)

        # Score each stock (parallel, cached-only for speed)
        results: List[Dict[str, Any]] = []

        def _score_one(stock: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            code = stock["code"]
            try:
                analyzer = CompositeAnalyzer(code, market)
                factor_result = analyzer.analyze(cached_only=True)
                score = factor_result.get("total_score", 0)
                return {
                    "code": code,
                    "name": stock.get("name", ""),
                    "market": market,
                    "total_score": score,
                    "adjusted_score": score - self._metadata_penalty(stock, market),
                    "sector": stock.get("sector", ""),
                    "industry": stock.get("industry", ""),
                    "market_cap": stock.get("total_market_cap", 0),
                    "metadata_source": stock.get("metadata_source", ""),
                    "metadata_status": stock.get("metadata_status", ""),
                    "metadata_completeness": float(
                        stock.get("metadata_completeness", 0) or 0
                    ),
                    "metadata_penalty": self._metadata_penalty(stock, market),
                    "confidence": self._candidate_confidence(stock, score),
                    "provenance": self._candidate_provenance(stock, market),
                    "factors": factor_result.get("factors", {}),
                    "f_score": factor_result.get("f_score", 0),
                }
            except Exception:
                return None

        done = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(_score_one, stock): stock for stock in candidates
            }
            for f in as_completed(futures):
                done += 1
                if done % 25 == 0 or done == n:
                    print(f"  Scan progress: {done}/{n}", flush=True)

                result = f.result()
                if result is not None:
                    results.append(result)

        if not results:
            print(
                "  All candidates scored 0 (no cached data yet). "
                "Run 'python stockaskill/scripts/run.py diagnose' on individual"
                " stocks"
                " to build cache, "
                "or use 'python stockaskill/scripts/run.py alpha A --top 20'"
                " for full scoring.",
                flush=True,
            )
        else:
            print(f"  Scored {len(results)} stocks successfully.", flush=True)

        # Sort by score descending
        results.sort(
            key=lambda x: (
                x.get("adjusted_score", x.get("total_score", 0)),
                x.get("metadata_completeness", 0),
                x.get("total_score", 0),
            ),
            reverse=True,
        )
        return results[:top_n]

    def get_snapshot_status(self, market: str) -> Dict[str, Any]:
        """Return cache status for the latest full-market scan snapshot."""
        latest_trade_date = self.cache.get_latest_market_scan_trade_date(market)
        status = "fresh"
        if latest_trade_date is None:
            status = "missing"
        elif self.cache.market_scan_snapshot_needs_refresh(market):
            status = "stale"
        return {
            "market": market,
            "latest_trade_date": latest_trade_date,
            "needs_refresh": status != "fresh",
            "status": status,
        }

    def scan_snapshot(
        self,
        market: str = "A",
        top_n: int = 20,
        include_incomplete: bool = False,
        trade_date: str = "",
    ) -> Dict[str, Any]:
        """Read top results from the latest cached market snapshot."""
        summary = self.cache.get_market_scan_snapshot_summary(market, trade_date)
        if summary is None:
            return {"results": [], "summary": None}

        snapshot_rows = self.cache.get_market_scan_snapshot(
            market,
            trade_date=summary["trade_date"],
            include_ineligible=include_incomplete,
            limit=top_n,
        )
        pool_by_code = {
            str(stock.get("code", "")): stock for stock in get_stock_pool(market)
        }

        results: List[Dict[str, Any]] = []
        for row in snapshot_rows:
            stock = pool_by_code.get(str(row.get("code", "")), {})
            factors = {
                "value": float(row.get("value_score", 0) or 0),
                "quality": float(row.get("quality_score", 0) or 0),
                "growth": float(row.get("growth_score", 0) or 0),
                "momentum": float(row.get("momentum_score", 0) or 0),
                "low_vol": float(row.get("low_vol_score", 0) or 0),
                "size": float(row.get("size_score", 0) or 0),
            }
            results.append(
                {
                    "code": row["code"],
                    "name": stock.get("name", row["code"]),
                    "market": market,
                    "total_score": float(row.get("composite_score", 0) or 0),
                    "adjusted_score": float(row.get("composite_score", 0) or 0),
                    "sector": stock.get("sector", ""),
                    "industry": stock.get("industry", ""),
                    "market_cap": stock.get("total_market_cap", 0),
                    "metadata_source": stock.get("metadata_source", ""),
                    "metadata_status": stock.get("metadata_status", ""),
                    "metadata_completeness": float(
                        stock.get("metadata_completeness", 0) or 0
                    ),
                    "metadata_penalty": 0.0,
                    "confidence": self._candidate_confidence(
                        stock,
                        float(row.get("composite_score", 0) or 0),
                    ),
                    "provenance": self._candidate_provenance(stock, market),
                    "factors": factors,
                    "f_score": int(row.get("f_score", 0) or 0),
                    "eligible": bool(row.get("eligible")),
                    "ineligible_reason": row.get("ineligible_reason", ""),
                    "trade_date": row.get("trade_date", summary["trade_date"]),
                    "rank_score": float(row.get("rank_score", 0) or 0),
                }
            )
        return {"results": results, "summary": summary}

    def refresh_snapshot(
        self,
        market: str = "A",
        include_incomplete: bool = False,
    ) -> Dict[str, Any]:
        """Refresh and score the full market into a local snapshot."""
        pool = get_stock_pool(market)
        if not pool:
            return {
                "market": market,
                "trade_date": datetime.now().strftime("%Y-%m-%d"),
                "total_count": 0,
                "eligible_count": 0,
                "filtered_count": 0,
                "data_complete_count": 0,
                "data_complete_ratio": 0.0,
                "cache_reused_count": 0,
                "backfilled_count": 0,
                "excluded_count": 0,
                "history_cache_hits": 0,
                "history_fetched_count": 0,
                "history_missing_count": 0,
                "fundamentals_cache_hits": 0,
                "fundamentals_fetched_count": 0,
                "fundamentals_missing_count": 0,
                "metadata_status": {
                    "requested": 0,
                    "already_ready": 0,
                    "profile_backfilled": 0,
                    "cached_history_backfilled": 0,
                    "remote_history_backfilled": 0,
                    "still_missing_list_date": 0,
                    "missing_market_cap": 0,
                    "metadata_complete": 0,
                    "metadata_partial": 0,
                    "inactive_count": 0,
                },
                "metadata_quality": {"complete": 0, "partial": 0, "low": 0},
            }

        metadata_status = ensure_stock_pool_candidates_ready(
            market,
            [str(stock.get("code", "")) for stock in pool],
        )
        self._print_pool_metadata_status(metadata_status)
        refreshed_pool = {
            str(stock.get("code", "")): stock for stock in get_stock_pool(market)
        }
        metadata_quality = self._metadata_quality_counts(list(refreshed_pool.values()))
        self._print_metadata_quality_summary(metadata_quality, label="universe")
        trade_date = datetime.now().strftime("%Y-%m-%d")

        def _evaluate(stock: Dict[str, Any]) -> Dict[str, Any]:
            code = str(stock.get("code", ""))
            name = str(stock.get("name", ""))
            row = refreshed_pool.get(code, stock)
            list_date = str(row.get("list_date", "")).strip()
            is_st_flag = is_st(code, name)
            is_bj_flag = market == "A" and code.lower().startswith("bj")
            has_list_date = bool(list_date)
            is_new_listing = has_list_date and is_new(
                list_date,
                threshold_days=_NEW_LISTING_DAYS,
            )

            cached_kline = get_kline(
                code,
                market,
                days=_SCAN_HISTORY_DAYS,
                cached_only=True,
            )
            cached_fundamentals = get_fundamentals(code, market, cached_only=True) or {}
            kline = cached_kline
            fundamentals = dict(cached_fundamentals)
            remote_fundamentals: Dict[str, Any] = {}

            if len(kline) < _MIN_HISTORY_ROWS:
                kline = get_kline(code, market, days=_SCAN_HISTORY_DAYS) or []
            has_history = len(kline) >= _MIN_HISTORY_ROWS

            market_cap = float(row.get("total_market_cap", 0) or 0)
            if not fundamentals:
                remote_fundamentals = get_fundamentals(code, market) or {}
                fundamentals = dict(remote_fundamentals)
            if market_cap > 0 and float(fundamentals.get("market_cap", 0) or 0) <= 0:
                fundamentals = dict(fundamentals)
                fundamentals["market_cap"] = market_cap
            has_fundamentals = bool(fundamentals)
            cached_history_ready = len(cached_kline) >= _MIN_HISTORY_ROWS
            cached_fundamentals_ready = bool(cached_fundamentals) or market_cap > 0
            history_fetched = not cached_history_ready and has_history
            fundamentals_fetched = not bool(cached_fundamentals) and bool(
                remote_fundamentals
            )

            factor_result = None
            if has_history and has_fundamentals and not is_st_flag and not is_bj_flag:
                analyzer = CompositeAnalyzer(code, market)
                factor_result = analyzer.analyze_from_data(
                    fundamentals,
                    kline,
                    as_of_date=trade_date,
                    persist=True,
                )

            reasons: List[str] = []
            if is_st_flag:
                reasons.append("st")
            if is_bj_flag:
                reasons.append("bj")
            if not has_list_date:
                reasons.append("missing_list_date")
            if is_new_listing:
                reasons.append("new_listing")
            if not has_history:
                reasons.append("missing_history")
            if not has_fundamentals:
                reasons.append("missing_fundamentals")

            return {
                "market": market,
                "trade_date": trade_date,
                "code": code,
                "eligible": 1 if not reasons else 0,
                "composite_score": (
                    float(factor_result.get("total_score", 0) or 0)
                    if factor_result
                    else 0.0
                ),
                "f_score": (
                    int(factor_result.get("f_score", 0) or 0) if factor_result else 0
                ),
                "value_score": (
                    float(factor_result.get("factors", {}).get("value", 0) or 0)
                    if factor_result
                    else 0.0
                ),
                "quality_score": (
                    float(factor_result.get("factors", {}).get("quality", 0) or 0)
                    if factor_result
                    else 0.0
                ),
                "growth_score": (
                    float(factor_result.get("factors", {}).get("growth", 0) or 0)
                    if factor_result
                    else 0.0
                ),
                "momentum_score": (
                    float(factor_result.get("factors", {}).get("momentum", 0) or 0)
                    if factor_result
                    else 0.0
                ),
                "low_vol_score": (
                    float(factor_result.get("factors", {}).get("low_vol", 0) or 0)
                    if factor_result
                    else 0.0
                ),
                "size_score": (
                    float(factor_result.get("factors", {}).get("size", 0) or 0)
                    if factor_result
                    else 0.0
                ),
                "has_list_date": 1 if has_list_date else 0,
                "has_fundamentals": 1 if has_fundamentals else 0,
                "has_history": 1 if has_history else 0,
                "is_st": 1 if is_st_flag else 0,
                "is_bj": 1 if is_bj_flag else 0,
                "is_new_listing": 1 if is_new_listing else 0,
                "rank_score": 0.0,
                "ineligible_reason": ",".join(reasons),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "_cached_history": cached_history_ready,
                "_cached_fundamentals": cached_fundamentals_ready,
                "_history_fetched": history_fetched,
                "_fundamentals_fetched": fundamentals_fetched,
                "_reused": (
                    cached_history_ready
                    and cached_fundamentals_ready
                    and has_list_date
                    and not is_st_flag
                    and not is_bj_flag
                    and not is_new_listing
                ),
                "_backfilled": (
                    (history_fetched or fundamentals_fetched)
                    and has_history
                    and has_fundamentals
                ),
            }

        rows: List[Dict[str, Any]] = []
        pool_rows = list(refreshed_pool.values())
        total = len(pool_rows)
        worker_count = int(cfg_get("data_readiness.scan_refresh_workers", 8) or 8)
        history_cache_hits = 0
        history_fetched_count = 0
        history_missing_count = 0
        fundamentals_cache_hits = 0
        fundamentals_fetched_count = 0
        fundamentals_missing_count = 0
        cache_reused_count = 0
        backfilled_count = 0
        with ThreadPoolExecutor(max_workers=max(worker_count, 1)) as executor:
            futures = {executor.submit(_evaluate, stock): stock for stock in pool_rows}
            processed = 0
            for future in as_completed(futures):
                processed += 1
                if processed % 100 == 0 or processed == total:
                    print(
                        f"  Snapshot refresh progress: {processed}/{total}",
                        flush=True,
                    )
                row = future.result()
                history_cache_hits += 1 if row.pop("_cached_history") else 0
                fundamentals_cache_hits += 1 if row.pop("_cached_fundamentals") else 0
                history_fetched_count += 1 if row.pop("_history_fetched") else 0
                fundamentals_fetched_count += (
                    1 if row.pop("_fundamentals_fetched") else 0
                )
                cache_reused_count += 1 if row.pop("_reused") else 0
                backfilled_count += 1 if row.pop("_backfilled") else 0
                history_missing_count += 1 if not row["has_history"] else 0
                fundamentals_missing_count += 1 if not row["has_fundamentals"] else 0
                rows.append(row)

        eligible_rows = sorted(
            [row for row in rows if row["eligible"]],
            key=lambda item: item["composite_score"],
            reverse=True,
        )
        for index, row in enumerate(eligible_rows, start=1):
            row["rank_score"] = float(index)

        ineligible_rows = sorted(
            [row for row in rows if not row["eligible"]],
            key=lambda item: (item["ineligible_reason"], item["code"]),
        )
        for index, row in enumerate(ineligible_rows, start=1):
            row["rank_score"] = float(1_000_000 + index)

        self.cache.upsert_market_scan_snapshot(rows)
        summary = self.cache.get_market_scan_snapshot_summary(market, trade_date)
        if summary is None:
            return {
                "market": market,
                "trade_date": trade_date,
                "total_count": 0,
                "eligible_count": 0,
                "filtered_count": 0,
            }
        summary.update(
            {
                "cache_reused_count": cache_reused_count,
                "backfilled_count": backfilled_count,
                "excluded_count": summary["filtered_count"],
                "history_cache_hits": history_cache_hits,
                "history_fetched_count": history_fetched_count,
                "history_missing_count": history_missing_count,
                "fundamentals_cache_hits": fundamentals_cache_hits,
                "fundamentals_fetched_count": fundamentals_fetched_count,
                "fundamentals_missing_count": fundamentals_missing_count,
                "metadata_status": metadata_status,
                "metadata_quality": metadata_quality,
                "display_count": (
                    summary["total_count"]
                    if include_incomplete
                    else summary["eligible_count"]
                ),
            }
        )
        return summary

    @staticmethod
    def _print_pool_metadata_status(status: Dict[str, int]) -> None:
        """Print a concise summary of candidate metadata readiness."""
        requested = status.get("requested", 0)
        if requested == 0:
            return
        metadata_complete = int(status.get("metadata_complete", 0) or 0)
        metadata_partial = int(status.get("metadata_partial", 0) or 0)
        inactive_count = int(status.get("inactive_count", 0) or 0)
        fetched = (
            status.get("profile_backfilled", 0)
            + status.get("cached_history_backfilled", 0)
            + status.get("remote_history_backfilled", 0)
        )
        if fetched == 0 and status.get("still_missing_list_date", 0) == 0:
            print(
                "  Candidate metadata ready:"
                f" {status.get('already_ready', requested)}/{requested}"
                " listing dates already cached."
                f" complete={metadata_complete},"
                f" partial={metadata_partial},"
                f" inactive={inactive_count}.",
                flush=True,
            )
            return
        print(
            "  Candidate metadata backfill:"
            f" profile={status.get('profile_backfilled', 0)},"
            f" local_history={status.get('cached_history_backfilled', 0)},"
            f" remote_history={status.get('remote_history_backfilled', 0)},"
            f" still_missing={status.get('still_missing_list_date', 0)},"
            f" complete={metadata_complete},"
            f" partial={metadata_partial},"
            f" inactive={inactive_count}.",
            flush=True,
        )

    @staticmethod
    def _candidate_confidence(stock: Dict[str, Any], score: float) -> Dict[str, Any]:
        """Return a bounded confidence summary for a scan candidate."""
        completeness = float(stock.get("metadata_completeness", 0) or 0)
        bounded_score = 0.35
        if completeness >= 0.75:
            bounded_score += 0.25
        elif completeness >= 0.5:
            bounded_score += 0.15
        if float(score or 0) >= 70:
            bounded_score += 0.25
        elif float(score or 0) >= 55:
            bounded_score += 0.15
        if bool(stock.get("is_active", 1)):
            bounded_score += 0.1
        level = (
            "high"
            if bounded_score >= 0.8
            else ("medium" if bounded_score >= 0.55 else "low")
        )
        return {
            "score": round(max(0.0, min(1.0, bounded_score)), 3),
            "level": level,
            "notes": [
                "扫描结果依赖本地缓存和元数据质量",
                "候选分数只适合作为研究优先级，不是直接交易指令",
            ],
        }

    @staticmethod
    def _candidate_provenance(stock: Dict[str, Any], market: str) -> Dict[str, Any]:
        """Return a standardized provenance block for a scan candidate."""
        return {
            "scope": "scan_candidate",
            "market": market,
            "code": str(stock.get("code", "")).strip(),
            "freshness": "local_cached",
            "covered_through": "",
            "source": str(stock.get("metadata_source", "")).strip() or "unknown",
            "source_status": str(stock.get("metadata_status", "")).strip() or "unknown",
            "metadata_completeness": round(
                float(stock.get("metadata_completeness", 0) or 0),
                3,
            ),
            "inputs": ["stock_pool_metadata", "cached_factor_scores"],
        }

    @staticmethod
    def _print_readiness_summary(status: Dict[str, Any]) -> None:
        """Print a concise sync/readiness summary before scan scoring."""
        requested = int(status.get("requested", 0) or 0)
        if requested <= 0:
            return
        print(
            "  Candidate readiness:"
            f" ready={status.get('ready', 0)}/{requested},"
            f" history_ready={status.get('history_ready', 0)}/{requested},"
            f" fundamentals_ready={status.get('fundamentals_ready', 0)}/{requested},"
            f" cache_hits={status.get('cache_hits', 0)}",
            flush=True,
        )
        missing_codes = status.get("missing_codes", [])
        if missing_codes:
            preview = ", ".join(str(code) for code in missing_codes[:10])
            print(f"  Candidate missing data: {preview}", flush=True)

    @staticmethod
    def _metadata_quality_counts(stocks: List[Dict[str, Any]]) -> Dict[str, int]:
        """Bucket metadata completeness into complete, partial, and low groups."""
        complete = 0
        partial = 0
        low = 0
        for stock in stocks:
            completeness = float(stock.get("metadata_completeness", 0) or 0)
            if completeness >= _METADATA_COMPLETE_THRESHOLD:
                complete += 1
            elif completeness >= _METADATA_PARTIAL_THRESHOLD:
                partial += 1
            else:
                low += 1
        return {"complete": complete, "partial": partial, "low": low}

    @staticmethod
    def _print_metadata_quality_summary(
        metadata_quality: Dict[str, int],
        label: str,
    ) -> None:
        """Print a concise metadata quality summary for a candidate set."""
        total = sum(
            int(metadata_quality.get(key, 0) or 0)
            for key in ("complete", "partial", "low")
        )
        if total <= 0:
            return
        print(
            f"  {label.capitalize()} metadata quality:"
            f" complete={metadata_quality.get('complete', 0)},"
            f" partial={metadata_quality.get('partial', 0)},"
            f" low={metadata_quality.get('low', 0)}",
            flush=True,
        )

    @staticmethod
    def _metadata_penalty(stock: Dict[str, Any], market: str) -> float:
        """Return a small rank-only penalty for low-quality HK/US metadata."""
        if market not in {"HK", "US"}:
            return 0.0
        completeness = float(stock.get("metadata_completeness", 0) or 0)
        if completeness >= _METADATA_COMPLETE_THRESHOLD:
            return 0.0
        if completeness >= _METADATA_PARTIAL_THRESHOLD:
            return 2.0
        return 5.0

    def scan_by_sector(
        self, market: str = "A", top_n: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Scan by sector, return top N per sector.

        Args:
            market: Market identifier.
            top_n: Results per sector.

        Returns:
            Dict mapping sector name to top stocks list.
        """
        pool = get_stock_pool(market)
        if not pool:
            return {}

        # Group by sector
        sectors: Dict[str, List[Dict[str, Any]]] = {}
        for stock in pool:
            sector = stock.get("sector", "Unknown")
            sectors.setdefault(sector, []).append(stock)

        result = {}
        for sector, stocks in sectors.items():
            top = self.scan_top(market, top_n, sector=sector)
            if top:
                result[sector] = top

        return result

    def scan_funds(
        self,
        fund_type: str = "ETF",
        top_n: int = 20,
    ) -> List[Dict[str, Any]]:
        """Scan the ETF-oriented FUND cache.

        Args:
            fund_type: ETF-only at present. Non-ETF values return no results.
            top_n: Number of results.

        Returns:
            List of fund dicts with code, name, nav, scale.
        """
        from data_engine import get_etf_pool

        requested_type = str(fund_type or "ETF").strip().upper()
        if requested_type != "ETF":
            return []

        funds = get_etf_pool()
        if not funds:
            return []

        filtered = [
            f for f in funds if str(f.get("fund_type", "")).strip().upper() == "ETF"
        ]

        # Sort by scale descending
        filtered.sort(key=lambda x: float(x.get("scale", 0) or 0), reverse=True)

        return filtered[:top_n]
