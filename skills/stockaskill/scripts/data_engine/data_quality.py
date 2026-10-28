"""Data quality check + tiered repair for bounded scopes.

Provides ``run_data_quality_check`` (gap/coverage detection with severity
grading and an audit trail) and ``run_data_quality_repair`` (bounded,
quota-capped, backoff-guarded re-sync of history and fundamentals). Both are
engine-neutral: they read/write through ``get_cache()`` and degrade gracefully
when expected data is missing.

Severity tiers:
- light: minor gap within ``kline_gap_light_days`` / one reporting period.
- heavy: deep gap beyond ``kline_gap_heavy_days`` / two reporting periods, or
  missing history/fundamentals entirely.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from cache import get_cache
from config import get as cfg_get
from utils import normalize_code_for_market

from data_engine import get_fund_nav, get_fundamentals, get_kline
from data_engine.config import _market_supports_fundamentals
from data_engine.pool import get_stock_pool

_ISO = "%Y-%m-%d %H:%M:%S"
_DAY = timedelta(days=1)

logger = logging.getLogger(__name__)


def _dq(key: str, default: Any) -> Any:
    """Read a data-quality config value with a default."""
    block = cfg_get("data_quality", {})
    return block.get(key, default) if isinstance(block, dict) else default


def _now_iso() -> str:
    """Return the current timestamp in the project's canonical format."""
    return datetime.now().strftime(_ISO)


def _as_datetime(value: Any) -> Optional[datetime]:
    """Coerce a stored timestamp (datetime or ISO text) to datetime."""
    if isinstance(value, datetime):
        return value
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", ""))
    except ValueError:
        return None


def _expected_latest_date(cache: Any, market: str) -> str:
    """Return the expected latest trading day for a market.

    Prefers the cached trade calendar, then the market's own latest K-line
    date, then today. FUND NAV uses the NAV backing store implicitly through
    its own get_latest path.
    """
    calendar_date = cache.get_latest_trade_calendar_date(market)
    if calendar_date:
        return str(calendar_date)
    market_date = cache.get_latest_daily_price_date(market)
    if market_date:
        return str(market_date)
    return datetime.now().strftime("%Y-%m-%d")


def _resolve_scope(
    market: str,
    codes: Optional[Sequence[str]],
    limit: int,
) -> List[str]:
    """Resolve the bounded code scope for a check/repair run."""
    if codes is not None:
        selected = [
            normalize_code_for_market(str(code).strip(), market)
            for code in codes
            if str(code).strip()
        ]
    else:
        pool = get_stock_pool(market)
        selected = [
            str(stock.get("code", "")).strip()
            for stock in pool
            if str(stock.get("code", "")).strip()
        ]
    if limit and limit > 0:
        return selected[:limit]
    return selected


def _latest_history_date(cache: Any, code: str, market: str) -> str:
    """Return the latest cached K-line/NAV date for a symbol (or '')."""
    if market == "FUND":
        rows = cache.get_fund_nav(code, 365)
        dates = [
            str(row.get("date", "")).strip()
            for row in rows
            if str(row.get("date", "")).strip()
        ]
        return max(dates) if dates else ""
    return cache.get_latest_date(code, market) or ""


def _history_count(cache: Any, code: str, market: str) -> int:
    """Return the cached K-line row count for a symbol."""
    if market == "FUND":
        return len(cache.get_fund_nav(code, 365))
    return int(cache.get_row_count(code, market) or 0)


def _calendar_gap(latest: str, expected: str) -> int:
    """Return calendar-day gap between two date strings (>= 0)."""
    try:
        latest_dt = datetime.strptime(latest, "%Y-%m-%d")
        expected_dt = datetime.strptime(expected, "%Y-%m-%d")
        return max(0, (expected_dt - latest_dt).days)
    except ValueError:
        return 0


def _check_history(
    cache: Any,
    code: str,
    market: str,
    expected: str,
) -> Dict[str, Any]:
    """Detect history/NAV coverage issues for a single symbol."""
    latest = _latest_history_date(cache, code, market)
    count = _history_count(cache, code, market)
    min_rows = int(_dq("min_history_days", 240))
    light_days = int(_dq("kline_gap_light_days", 5))
    heavy_days = int(_dq("kline_gap_heavy_days", 30))

    issues: List[str] = []
    severity = "ok"
    gap_days = 0
    if not latest:
        issues.append("missing_history")
        severity = _worst(severity, "heavy")
        gap_days = _calendar_gap(datetime.now().strftime("%Y-%m-%d"), expected)
    else:
        gap_days = _calendar_gap(latest, expected)
        if gap_days > heavy_days:
            issues.append("kline_gap")
            severity = _worst(severity, "heavy")
        elif gap_days > light_days:
            issues.append("kline_gap")
            severity = _worst(severity, "light")
        if count < min_rows:
            issues.append("insufficient_history")
            severity = _worst(severity, "heavy" if count == 0 else "light")

    if market == "A":
        rows = cache.get_daily_price(code, market=market)
        max_ret_pct = float(_dq("max_daily_ret_pct", 11.0))
        for i in range(max(0, len(rows) - 60)):
            close = float(rows[i].get("close", 0) or 0)
            prev_close = float(rows[i + 1].get("close", 0) or 0)
            if close > 0 and prev_close > 0:
                daily_ret = abs(close - prev_close) / prev_close
                if daily_ret > max_ret_pct / 100.0:
                    issues.append("implausible_return")
                    severity = _worst(severity, "heavy")
                    break

    return {
        "latest": latest,
        "count": count,
        "min_rows": min_rows,
        "expected": expected,
        "gap_days": gap_days,
        "issues": issues,
        "severity": severity,
    }


def _period_months(market: str) -> int:
    """Reporting-period length in months (3 for A-shares, 12 for HK/US)."""
    return 3 if market == "A" else 12


def _latest_financial_as_of(cache: Any, code: str, market: str) -> str:
    """Return the latest report-period as-of date, or '' when missing."""
    if hasattr(cache, "get_financial_report"):
        report = cache.get_financial_report(code, market)
        if report and report[0].get("report_date"):
            return str(report[0]["report_date"]).strip()
    snapshot = cache.get_latest_factor_snapshot(code, market)
    if snapshot and snapshot.get("date"):
        return str(snapshot.get("date", "")).strip()
    return ""


def _check_fundamentals(
    cache: Any,
    code: str,
    market: str,
) -> Dict[str, Any]:
    """Detect fundamentals staleness for a single symbol."""
    if not _market_supports_fundamentals(market):
        return {"report_date": "", "periods_late": 0, "issues": [], "severity": "ok"}
    light_periods = int(_dq("financial_gap_light_periods", 1))
    heavy_periods = int(_dq("financial_gap_heavy_periods", 2))
    period_months = _period_months(market)

    report_date = _latest_financial_as_of(cache, code, market)
    issues: List[str] = []
    severity = "ok"
    periods_late = 0.0
    if not report_date:
        issues.append("missing_fundamentals")
        severity = _worst(severity, "heavy")
    else:
        try:
            report_dt = datetime.strptime(report_date, "%Y-%m-%d")
            lag_months = max(
                0,
                (datetime.now().year - report_dt.year) * 12
                + (datetime.now().month - report_dt.month),
            )
            periods_late = round(lag_months / period_months, 2)
            if periods_late > heavy_periods:
                issues.append("financial_gap")
                severity = _worst(severity, "heavy")
            elif periods_late > light_periods:
                issues.append("financial_gap")
                severity = _worst(severity, "light")
        except ValueError:
            issues.append("missing_fundamentals")
            severity = _worst(severity, "heavy")

    return {
        "report_date": report_date,
        "periods_late": periods_late,
        "issues": issues,
        "severity": severity,
    }


def _worst(a: str, b: str) -> str:
    """Return the more severe of two severity labels."""
    order = {"ok": 0, "light": 1, "heavy": 2}
    return a if order.get(a, 0) >= order.get(b, 0) else b


def _describe_severity(severity: str) -> str:
    """Return a human label for a severity level."""
    if severity == "heavy":
        return "heavy"
    if severity == "light":
        return "light"
    return "ok"


def _audit(
    cache: Any,
    entry: Dict[str, Any],
) -> None:
    """Append one audit row with an explicit, engine-safe id."""
    entry = dict(entry)
    entry["id"] = int(cache.next_data_quality_log_id())
    entry.setdefault("checked_at", _now_iso())
    entry.setdefault("retry_after", None)
    entry.setdefault("error_message", "")
    entry.setdefault("missing_days", 0)
    if hasattr(cache, "append_data_quality_log"):
        cache.append_data_quality_log([entry])


def _in_backoff(cache: Any, code: str, market: str, data_kind: str) -> bool:
    """Return whether a symbol is currently suspended from repair."""
    row = cache.get_data_quality_backoff(code, market, data_kind)
    if not row:
        return False
    backoff_until = _as_datetime(row.get("backoff_until"))
    if backoff_until is None:
        return False
    return datetime.now() < backoff_until


def run_data_quality_check(
    market: str = "A",
    codes: Optional[Sequence[str]] = None,
    limit: int = 0,
) -> Dict[str, Any]:
    """Run a bounded data-quality check and persist an audit trail.

    Args:
        market: Market identifier (A/HK/US/FUND).
        codes: Explicit bounded code scope. Omit to use the market pool.
        limit: Max codes when *codes* is omitted (0 = whole pool).

    Returns:
        Summary dict with per-severity counts and per-symbol findings.
    """
    cache = get_cache()
    check_run = datetime.now().strftime("%Y%m%d%H%M%S")
    selected = _resolve_scope(market, codes, limit)
    max_codes = int(_dq("check_max_codes", 0))
    scoped = selected[:max_codes] if max_codes else selected
    expected = _expected_latest_date(cache, market)

    symbols: List[Dict[str, Any]] = []
    light_count = 0
    heavy_count = 0
    ok_count = 0

    for code in scoped:
        history = _check_history(cache, code, market, expected)
        fundamentals = _check_fundamentals(cache, code, market)
        severity = _worst(history["severity"], fundamentals["severity"])
        symbol = {
            "code": code,
            "market": market,
            "severity": _describe_severity(severity),
            "issues": history["issues"] + fundamentals["issues"],
            "history": history,
            "fundamentals": fundamentals,
        }
        symbols.append(symbol)

        for kind, detail in (("history", history), ("fundamentals", fundamentals)):
            if detail["severity"] == "ok":
                continue
            _audit(
                cache,
                {
                    "check_run": check_run,
                    "code": code,
                    "market": market,
                    "data_kind": "nav" if market == "FUND" else kind,
                    "severity": detail["severity"],
                    "issue_types": ",".join(detail["issues"]),
                    "start_date": (
                        detail.get("latest", "") or detail.get("report_date", "")
                    ),
                    "end_date": (
                        expected
                        if kind == "history"
                        else datetime.now().strftime("%Y-%m-%d")
                    ),
                    "missing_days": int(detail.get("gap_days", 0)),
                    "action": "check",
                    "repaired": 0,
                    "status": "flagged",
                },
            )

        if severity == "heavy":
            heavy_count += 1
        elif severity == "light":
            light_count += 1
        else:
            ok_count += 1

    return {
        "market": market,
        "check_run": check_run,
        "expected_latest_date": expected,
        "requested": len(selected),
        "checked": len(scoped),
        "ok_count": ok_count,
        "light_count": light_count,
        "heavy_count": heavy_count,
        "symbols": symbols,
    }


def run_data_quality_repair(
    market: str = "A",
    codes: Optional[Sequence[str]] = None,
    limit: int = 0,
    data_kinds: Sequence[str] = ("history", "fundamentals"),
) -> Dict[str, Any]:
    """Repair data-quality issues within a bounded, quota-capped scope.

    Args:
        market: Market identifier (A/HK/US/FUND).
        codes: Explicit bounded code scope. Omit to use the market pool.
        limit: Max codes to repair (defaults to ``repair_batch_codes``).
        data_kinds: Which data kinds to attempt (history/nav, fundamentals).

    Returns:
        Summary dict with repaired/skipped/backoff counts.
    """
    cache = get_cache()
    check_run = datetime.now().strftime("%Y%m%d%H%M%S")
    batch = int(_dq("repair_batch_codes", 10))
    repair_limit = limit or batch
    selected = _resolve_scope(market, codes, repair_limit)
    expected = _expected_latest_date(cache, market)
    backoff_hours = int(_dq("repair_backoff_hours", 24))

    daily_limit = int(cfg_get("daily_api_limit", 500))
    quota_ratio = float(_dq("repair_api_quota_ratio", 0.3))
    allowed_budget = max(1, int(daily_limit * quota_ratio))
    remaining = allowed_budget - int(cache.get_api_usage_today() or 0)

    repaired_count = 0
    failed_count = 0
    skipped_backoff = 0
    skipped_clean = 0
    skipped_quota = 0
    details: List[Dict[str, Any]] = []

    for code in selected:
        if remaining <= 0:
            skipped_quota += 1
            continue

        kinds = [k for k in data_kinds if k in ("history", "fundamentals")] or [
            "history"
        ]
        kind_labels = {
            "history": "nav" if market == "FUND" else "history",
            "fundamentals": "fundamentals",
        }
        suspended = [
            kind
            for kind in kinds
            if _in_backoff(cache, code, market, kind_labels[kind])
        ]
        if suspended:
            skipped_backoff += 1
            details.append(
                {
                    "code": code,
                    "market": market,
                    "status": "backoff",
                    "kinds": suspended,
                }
            )
            continue

        before_severity = "ok"
        issue_map: Dict[str, List[str]] = {}
        before_by_kind: Dict[str, str] = {}
        start_by_kind: Dict[str, str] = {}
        gap_by_kind: Dict[str, int] = {}
        if "history" in kinds:
            history = _check_history(cache, code, market, expected)
            before_severity = _worst(before_severity, history["severity"])
            issue_map["history"] = history["issues"]
            before_by_kind["history"] = history["severity"]
            start_by_kind["history"] = str(history.get("latest", "") or "")
            gap_by_kind["history"] = int(history.get("gap_days", 0) or 0)
        if "fundamentals" in kinds:
            fundamentals = _check_fundamentals(cache, code, market)
            before_severity = _worst(before_severity, fundamentals["severity"])
            issue_map["fundamentals"] = fundamentals["issues"]
            before_by_kind["fundamentals"] = fundamentals["severity"]
            start_by_kind["fundamentals"] = str(
                fundamentals.get("report_date", "") or ""
            )
            gap_by_kind["fundamentals"] = 0

        if before_severity == "ok":
            skipped_clean += 1
            continue

        errors: List[str] = []
        calls = 0
        if "history" in kinds and any(issue_map.get("history", [])):
            repair_days = 365
            gap_days = int(
                _check_history(cache, code, market, expected).get("gap_days", 0)
            )
            if gap_days > repair_days:
                repair_days = gap_days + int(_dq("repair_padding_days", 3))
            try:
                if market == "FUND":
                    get_fund_nav(code, repair_days, force_refresh=True)
                else:
                    get_kline(code, market, days=repair_days, force_refresh=False)
                calls += 1
            except Exception as exc:  # noqa: BLE001 - keep going per symbol
                errors.append(f"history: {exc}")

        if "fundamentals" in kinds and any(issue_map.get("fundamentals", [])):
            if _market_supports_fundamentals(market):
                try:
                    get_fundamentals(code, market, force_refresh=True)
                    calls += 1
                except Exception as exc:  # noqa: BLE001 - keep going per symbol
                    errors.append(f"fundamentals: {exc}")

        remaining = max(0, remaining - calls)

        after_severity = "ok"
        kind_success: Dict[str, bool] = {}
        if "history" in kinds:
            after_history = _check_history(cache, code, market, expected)
            after_severity = _worst(after_severity, after_history["severity"])
            kind_success["history"] = not after_history["issues"]
        if "fundamentals" in kinds:
            after_fundamentals = _check_fundamentals(cache, code, market)
            after_severity = _worst(after_severity, after_fundamentals["severity"])
            kind_success["fundamentals"] = not after_fundamentals["issues"]
        repaired = all(kind_success.get(kind, False) for kind in kinds)
        for kind in kinds:
            label = kind_labels[kind]
            success = kind_success.get(kind, False)
            retry_after: Optional[str] = None
            if success:
                cache.clear_data_quality_backoff(code, market, label)
            else:
                row = cache.get_data_quality_backoff(code, market, label) or {}
                failures = int(row.get("consecutive_failures", 0) or 0) + 1
                retry_after = (
                    datetime.now() + timedelta(hours=backoff_hours)
                ).strftime(_ISO)
                cache.set_data_quality_backoff(
                    code, market, label, retry_after, failures
                )
            _audit(
                cache,
                {
                    "check_run": check_run,
                    "code": code,
                    "market": market,
                    "data_kind": label,
                    "severity": before_by_kind.get(kind, "ok"),
                    "issue_types": ",".join(issue_map.get(kind, [])),
                    "start_date": start_by_kind.get(kind, ""),
                    "end_date": datetime.now().strftime("%Y-%m-%d"),
                    "missing_days": gap_by_kind.get(kind, 0),
                    "action": "repair",
                    "repaired": 1 if success else 0,
                    "status": "ok" if success else "failed",
                    "error_message": "" if success else "; ".join(errors),
                    "retry_after": retry_after,
                },
            )

        if repaired:
            repaired_count += 1
        else:
            failed_count += 1
        details.append(
            {
                "code": code,
                "market": market,
                "status": "repaired" if repaired else "failed",
                "before_severity": before_severity,
                "after_severity": _describe_severity(after_severity),
                "errors": errors,
            }
        )

    return {
        "market": market,
        "check_run": check_run,
        "requested": len(selected),
        "repair_limit": repair_limit,
        "repaired_count": repaired_count,
        "failed_count": failed_count,
        "skipped_backoff": skipped_backoff,
        "skipped_clean": skipped_clean,
        "skipped_quota": skipped_quota,
        "quota_remaining": remaining,
        "details": details,
    }
