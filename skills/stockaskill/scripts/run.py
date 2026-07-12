"""Unified CLI entry point for the stockaskill stock selection system.

Provides commands for stock analysis, diagnosis, market scanning, portfolio
building, backtesting, and data synchronization. All commands follow a
local-first pattern: sync missing data, then read from cache.

Usage:
    python stockaskill/scripts/run.py diagnose 600519 --market A
    python stockaskill/scripts/run.py scan A --top 20
    python stockaskill/scripts/run.py sync symbol 600519 --market A --days 365
"""

# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "akshare>=1.10.0",
#     "pandas>=2.0.0",
#     "numpy>=1.24.0",
#     "scipy>=1.10.0",
# ]
# ///

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Force UTF-8 output for CJK support on Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_scripts_root = str(Path(__file__).resolve().parent)
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

_DEFAULT_BADGE = "--"
_MIN_PYTHON = (3, 10)


def _require_supported_python() -> None:
    """Exit early with a clear message on unsupported Python versions."""
    if sys.version_info >= _MIN_PYTHON:
        return
    required = ".".join(str(part) for part in _MIN_PYTHON)
    current = ".".join(str(part) for part in sys.version_info[:3])
    print(
        f"stockaskill requires Python >= {required}; current interpreter is {current}.",
        file=sys.stderr,
    )
    print(
        "Use a Python 3.10+ environment or run via 'uv run"
        " python stockaskill/scripts/run.py ...'.",
        file=sys.stderr,
    )
    raise SystemExit(1)


_require_supported_python()


_SCORE_BADGES = [(65, "##"), (35, "==")]


def _print_api_usage() -> None:
    """Print which upstream APIs are currently rate-limited."""
    if is_api_limit_exhausted():
        print(
            "[INFO] One or more upstream APIs are rate-limited today. "
            "Data shown is from cache. Retry after the rate limit window passes.",
            flush=True,
        )


def _badge(score: float) -> str:
    """Return a compact badge for a numeric score."""
    for threshold, b in _SCORE_BADGES:
        if score >= threshold:
            return b
    return _DEFAULT_BADGE


def _cmd_output(args: argparse.Namespace) -> tuple:
    """Extract common output args from any cmd_* handler.

    Returns (output_dir, fmt).
    """
    return (
        getattr(args, "output_dir", "reports"),
        getattr(args, "format", "both"),
    )


def _cmd_error(msg: str, show_traceback: bool = False) -> None:
    """Print error to stderr, optionally with traceback."""
    print(msg, file=sys.stderr)
    if show_traceback:
        import traceback
        traceback.print_exc(file=sys.stderr)


from cache import get_cache  # noqa: E402
from config import get as cfg_get, signal_from_score, signal_thresholds  # noqa: E402
from data_engine import (  # noqa: E402
    check_data_completeness,
    get_etf_pool,
    get_fund_pool,
    get_fundamentals,
    get_kline,
    get_stock_pool,
    is_api_limit_exhausted,
    sync_etf_data,
    sync_portfolio_data,
    sync_scan_universe_data,
    sync_symbol_data,
    sync_watchlist_data,
)
from data_readiness import (  # noqa: E402
    ensure_etf_ready,
    ensure_market_scan_ready,
    ensure_symbol_analysis_ready,
)
from deep_diagnosis import build_deep_diagnosis  # noqa: E402
from market_regime import analyze_market_regime, summarize_market_regime  # noqa: E402
from report_generator import (  # noqa: E402
    format_backtest_summary,
    format_deep_diagnosis_summary,
    format_diagnosis_summary,
    format_market_regime_summary,
    format_portfolio_summary,
    format_scorecard,
    format_theme_research,
    format_thesis_summary,
    format_workflow_run_summary,
    save_markdown,
    save_report,
)
from scorecards import (  # noqa: E402
    build_diagnosis_scorecard,
    build_theme_scorecard,
    build_thesis_scorecard,
)
from theme_research import build_theme_report  # noqa: E402
from thesis_memory import (  # noqa: E402
    build_thesis_record,
    get_thesis_record,
    list_thesis_records,
    save_thesis_record,
    update_thesis_postmortem,
)
from utils import normalize_code_for_market  # noqa: E402
from workflow_runner import (  # noqa: E402
    build_workflow_run_plan,
    list_workflow_manifests,
)
from workflows import build_workflow_recommendation  # noqa: E402


def _save_report(
    name: str,
    fmt: str,
    output_dir: str,
    data: Optional[dict] = None,
    md: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Save report in requested formats."""
    if fmt == "none":
        return
    if fmt in ("json", "both") and data is not None:
        save_report(data, name, output_dir=output_dir, metadata=metadata)
    if fmt in ("md", "both") and md is not None:
        save_markdown(md, name, output_dir=output_dir)


def _print_snapshot_summary(summary: dict, refreshed: bool) -> None:
    """Print a concise snapshot status summary for market scans."""
    trade_date = summary.get("trade_date", "?")
    total_count = int(summary.get("total_count", 0) or 0)
    eligible_count = int(summary.get("eligible_count", 0) or 0)
    filtered_count = int(summary.get("filtered_count", 0) or 0)
    complete_ratio = float(summary.get("data_complete_ratio", 0) or 0) * 100
    refresh_label = "yes" if refreshed else "no"
    print(f"  Snapshot date: {trade_date} (refreshed={refresh_label})")
    print(
        "  Snapshot coverage:"
        f" scored={eligible_count}, filtered={filtered_count}, total={total_count}"
    )
    print(f"  Data completeness: {complete_ratio:.1f}%")
    print(
        "  Exclusions:"
        f" missing_list_date={summary.get('missing_list_date_count', 0)},"
        f" missing_fundamentals={summary.get('missing_fundamentals_count', 0)},"
        f" missing_history={summary.get('missing_history_count', 0)},"
        f" st={summary.get('st_count', 0)},"
        f" bj={summary.get('bj_count', 0)},"
        f" new_listing={summary.get('new_listing_count', 0)}"
    )
    metadata_quality = summary.get("metadata_quality", {}) or {}
    if metadata_quality:
        print(
            "  Metadata quality:"
            f" complete={metadata_quality.get('complete', 0)},"
            f" partial={metadata_quality.get('partial', 0)},"
            f" low={metadata_quality.get('low', 0)}"
        )


def _print_pool_summary(market: str) -> None:
    """Print a concise summary of a refreshed pool."""
    if market == "FUND":
        pool = get_etf_pool()
    else:
        pool = get_stock_pool(market)
    if not pool:
        print(f"  {market}: 0 entries (no data)")
        return
    total = len(pool)
    labels = sorted(r.get("updated_at", "") for r in pool if r.get("updated_at"))
    updated_at = labels[-1] if labels else "?"
    name = {
        "A": "A 股",
        "HK": "港股",
        "US": "美股",
        "FUND": "ETF",
    }.get(market, market)
    parts = [f"{total} 只"]
    if market != "FUND":
        dates = sorted(
            str(r.get("list_date", "")).strip()
            for r in pool
            if str(r.get("list_date", "")).strip()
        )
        if dates:
            parts.append(f"最早={dates[0]}, 最晚={dates[-1]}")
    print(f"  {name}: {', '.join(parts)} (updated={updated_at})")


def _print_refresh_summary(summary: dict) -> None:
    """Print refresh job counters after a full-market snapshot build."""
    print(
        "  Local reuse/backfill:"
        f" reused={summary.get('cache_reused_count', 0)},"
        f" backfilled={summary.get('backfilled_count', 0)},"
        f" excluded={summary.get('excluded_count', 0)}"
    )
    print(
        "  Data fetch counters:"
        f" history_hit={summary.get('history_cache_hits', 0)},"
        f" history_fetched={summary.get('history_fetched_count', 0)},"
        f" history_missing={summary.get('history_missing_count', 0)},"
        f" fundamentals_hit={summary.get('fundamentals_cache_hits', 0)},"
        f" fundamentals_fetched={summary.get('fundamentals_fetched_count', 0)},"
        f" fundamentals_missing={summary.get('fundamentals_missing_count', 0)}"
    )


def _safe_market_regime(market: str) -> dict:
    """Return a best-effort market regime analysis."""
    try:
        return analyze_market_regime(market)
    except Exception as exc:
        return {
            "market": market,
            "status": "error",
            "score": 50.0,
            "posture": "neutral",
            "posture_label": "中性",
            "risk_budget": 1.0,
            "new_positions_allowed": True,
            "reasons": [f"market_regime_error: {exc}"],
            "breadth": {},
            "technical": {},
        }


def _print_workflow_recommendation(recommendation: dict) -> None:
    """Print a compact workflow recommendation."""
    print(f"Intent: {recommendation.get('intent', '?')}")
    print(f"Market: {recommendation.get('market', '?')}")
    print(f"Summary: {recommendation.get('summary', '')}")
    rationale = recommendation.get("rationale", []) or []
    if rationale:
        print("Rationale:")
        for item in rationale:
            print(f"  - {item}")
    steps = recommendation.get("steps", []) or []
    if steps:
        print("Steps:")
        for idx, step in enumerate(steps, 1):
            print(f"  {idx}. {step.get('title', 'step')}")
            print(f"     {step.get('command', '')}")
            print(f"     purpose: {step.get('purpose', '')}")
    notes = recommendation.get("notes", []) or []
    if notes:
        print("Notes:")
        for item in notes:
            print(f"  - {item}")


def cmd_route(args: argparse.Namespace) -> None:
    """Recommend a bounded workflow for a user goal."""
    goal = " ".join(getattr(args, "goal", []) or []).strip()
    market = getattr(args, "market", "A") or "A"
    code = str(getattr(args, "code", "") or "").strip()
    codes = [
        item.strip()
        for item in str(getattr(args, "codes", "") or "").split(",")
        if item.strip()
    ]
    top_n = int(getattr(args, "top", 10) or 10)
    capital = float(getattr(args, "capital", 1_000_000) or 1_000_000)
    output_dir, fmt = _cmd_output(args)

    try:
        recommendation = build_workflow_recommendation(
            goal=goal,
            market=market,
            code=code,
            codes=codes,
            top_n=top_n,
            capital=capital,
        ).to_dict()
        _print_workflow_recommendation(recommendation)
        _save_report(
            f"route_{market}",
            fmt,
            output_dir,
            data=recommendation,
            metadata={
                "command": "route",
                "market": market,
                "goal": goal,
                "code": code,
                "codes": codes,
            },
        )
    except Exception as exc:
        print(f"Route failed: {exc}", file=sys.stderr)


def cmd_workflow(args: argparse.Namespace) -> None:
    """List or resolve manifest-based workflow routines."""
    action = getattr(args, "action", "")
    output_dir, fmt = _cmd_output(args)

    if action == "list":
        names = list_workflow_manifests()
        print(f"Available workflows ({len(names)}):")
        for idx, name in enumerate(names, 1):
            print(f"  {idx}. {name}")
        _save_report(
            "workflow_list",
            fmt,
            output_dir,
            data={"workflows": names},
            metadata={"command": "workflow-list"},
        )
        return

    if action == "run":
        name = str(getattr(args, "name", "") or "").strip()
        plan = build_workflow_run_plan(
            name=name,
            market=getattr(args, "market", "A") or "A",
            code=str(getattr(args, "code", "") or "").strip(),
            codes=str(getattr(args, "codes", "") or "").strip(),
            theme=" ".join(getattr(args, "theme", []) or []).strip(),
            top=int(getattr(args, "top", 10) or 10),
            capital=float(getattr(args, "capital", 1_000_000) or 1_000_000),
        ).to_dict()
        print(f"Workflow: {plan.get('name', '?')} (market={plan.get('market', '?')})")
        print(plan.get("summary", ""))
        if plan.get("missing_params"):
            print("Missing params: " + ", ".join(plan["missing_params"]))
        for idx, step in enumerate(plan.get("steps", []), 1):
            print(f"  {idx}. {step.get('title', 'step')}")
            print(f"     {step.get('command', '')}")
            print(f"     purpose: {step.get('purpose', '')}")
        for item in plan.get("notes", [])[:4]:
            print(f"  Note: {item}")
        md = format_workflow_run_summary(plan)
        _save_report(
            f"workflow_run_{name}",
            fmt,
            output_dir,
            data=plan,
            md=md,
            metadata={"command": "workflow-run", "workflow": name},
        )
        return

    print(f"Unknown workflow action: {action}")


def cmd_scorecard(args: argparse.Namespace) -> None:
    """Build scorecards for thesis, theme, or diagnosis artifacts."""
    action = getattr(args, "action", "")
    market = getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)

    if action == "thesis":
        thesis_id = str(getattr(args, "thesis_id", "") or "").strip()
        code = normalize_code_for_market(args.code, market) if args.code else ""
        record = get_thesis_record(thesis_id=thesis_id, code=code, market=market)
        if not record:
            print("Thesis record not found.", file=sys.stderr)
            return
        scorecard = record.get("scorecard", {}) or build_thesis_scorecard(record)
        print(
            f"Scorecard thesis {record.get('code', '?')} "
            f"(score={float(scorecard.get('score', 0) or 0):.1f}, "
            f"level={scorecard.get('level', 'medium')})"
        )
        md = format_scorecard(scorecard)
        print(md)
        report_name = (
            f"scorecard_thesis_{record.get('code', 'unknown')}_"
            f"{record.get('market', market)}"
        )
        _save_report(
            report_name,
            fmt,
            output_dir,
            data=scorecard,
            md=md,
            metadata={
                "command": "scorecard-thesis",
                "market": record.get("market", market),
                "code": record.get("code", ""),
                "thesis_id": record.get("thesis_id", ""),
            },
        )
        return

    if action == "theme":
        theme = " ".join(getattr(args, "theme", []) or []).strip()
        report = build_theme_report(
            theme=theme,
            market=market,
            top_n=int(getattr(args, "top", 3) or 3),
            candidate_limit=int(getattr(args, "candidates", 0) or 0),
        ).to_dict()
        scorecard = report.get("scorecard", {}) or build_theme_scorecard(report)
        print(
            f"Scorecard theme {theme} "
            f"(score={float(scorecard.get('score', 0) or 0):.1f}, "
            f"level={scorecard.get('level', 'medium')})"
        )
        md = format_scorecard(scorecard)
        print(md)
        _save_report(
            f"scorecard_theme_{market}",
            fmt,
            output_dir,
            data=scorecard,
            md=md,
            metadata={"command": "scorecard-theme", "market": market, "theme": theme},
        )
        return

    if action == "diagnose":
        from advisor.diagnosis import StockDiagnosis

        code = normalize_code_for_market(args.code, market)
        report = StockDiagnosis(code, market).full_report()
        scorecard = build_diagnosis_scorecard(report)
        print(
            f"Scorecard diagnose {code} "
            f"(score={float(scorecard.get('score', 0) or 0):.1f}, "
            f"level={scorecard.get('level', 'medium')})"
        )
        md = format_scorecard(scorecard)
        print(md)
        _save_report(
            f"scorecard_diagnose_{code}_{market}",
            fmt,
            output_dir,
            data=scorecard,
            md=md,
            metadata={"command": "scorecard-diagnose", "market": market, "code": code},
        )
        return

    print(f"Unknown scorecard action: {action}")


def cmd_thesis(args: argparse.Namespace) -> None:
    """Manage local thesis memory and postmortem records."""
    action = getattr(args, "action", "")
    market = getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)

    if action == "capture":
        code = normalize_code_for_market(args.code, market)
        print(f"Capturing thesis for {code} (market={market})...")
        from advisor.diagnosis import StockDiagnosis

        report = StockDiagnosis(code, market).full_report()
        record = build_thesis_record(
            report,
            source="diagnose",
            thesis_status=getattr(args, "status", "active"),
            notes=str(getattr(args, "notes", "") or "").strip(),
        )
        paths = save_thesis_record(record)
        payload = record.to_dict()
        print(format_thesis_summary(payload))
        print(f"  Thesis JSON: {paths['json_path']}")
        print(f"  Thesis Markdown: {paths['md_path']}")
        _save_report(
            f"thesis_capture_{code}_{market}",
            fmt,
            output_dir,
            data=payload,
            md=format_thesis_summary(payload),
            metadata={"command": "thesis-capture", "market": market, "code": code},
        )
        return

    if action == "list":
        code = normalize_code_for_market(args.code, market) if args.code else ""
        status = str(getattr(args, "status", "") or "").strip()
        limit = int(
            getattr(args, "limit", cfg_get("thesis_memory.default_limit", 10)) or 10
        )
        records = list_thesis_records(
            market=market if getattr(args, "market", "") else "",
            code=code,
            thesis_status=status,
            limit=limit,
        )
        if not records:
            print("No thesis records found.")
            return
        print(f"Thesis records ({len(records)}):")
        for idx, record in enumerate(records, 1):
            print(
                f"  {idx}. {record.get('thesis_id', '?')} "
                f"{record.get('code', '?')} {record.get('market', '?')} "
                f"{record.get('signal', 'HOLD')} "
                f"score={float(record.get('score', 50) or 50):.1f} "
                f"status={record.get('thesis_status', 'active')}"
            )
            print(f"     {record.get('summary', '')}")
        _save_report(
            "thesis_list",
            fmt,
            output_dir,
            data={"records": records},
            metadata={"command": "thesis-list", "market": market},
        )
        return

    if action == "review":
        thesis_id = str(getattr(args, "thesis_id", "") or "").strip()
        code = normalize_code_for_market(args.code, market) if args.code else ""
        record = get_thesis_record(thesis_id=thesis_id, code=code, market=market)
        if not record:
            print("Thesis record not found.", file=sys.stderr)
            return
        md = format_thesis_summary(record)
        print(md)
        report_name = (
            f"thesis_review_{record.get('code', 'unknown')}_"
            f"{record.get('market', market)}"
        )
        _save_report(
            report_name,
            fmt,
            output_dir,
            data=record,
            md=md,
            metadata={
                "command": "thesis-review",
                "market": record.get("market", market),
                "code": record.get("code", ""),
                "thesis_id": record.get("thesis_id", ""),
            },
        )
        return

    if action == "postmortem":
        thesis_id = str(getattr(args, "thesis_id", "") or "").strip()
        code = normalize_code_for_market(args.code, market) if args.code else ""
        try:
            record = update_thesis_postmortem(
                outcome=str(getattr(args, "outcome", "neutral") or "neutral"),
                notes=str(getattr(args, "notes", "") or "").strip(),
                thesis_id=thesis_id,
                code=code,
                market=market,
                thesis_status=str(getattr(args, "status", "closed") or "closed"),
            )
        except ValueError:
            print("Thesis record not found.", file=sys.stderr)
            return
        md = format_thesis_summary(record)
        print(md)
        report_name = (
            f"thesis_postmortem_{record.get('code', 'unknown')}_"
            f"{record.get('market', market)}"
        )
        _save_report(
            report_name,
            fmt,
            output_dir,
            data=record,
            md=md,
            metadata={
                "command": "thesis-postmortem",
                "market": record.get("market", market),
                "code": record.get("code", ""),
                "thesis_id": record.get("thesis_id", ""),
            },
        )
        return

    print(f"Unknown thesis action: {action}")


def cmd_theme_scan(args: argparse.Namespace) -> None:
    """Run local-first theme research and rank layers before companies."""
    theme = " ".join(getattr(args, "theme", []) or []).strip()
    market = getattr(args, "market", "A") or "A"
    top_n = int(getattr(args, "top", 3) or 3)
    candidate_limit = int(getattr(args, "candidates", 0) or 0)
    output_dir, fmt = _cmd_output(args)

    print(f"Theme research: {theme} (market={market})")
    report = build_theme_report(
        theme=theme,
        market=market,
        top_n=top_n,
        candidate_limit=candidate_limit,
    ).to_dict()
    print(report.get("summary", ""))
    print(f"  关键问题: {report.get('key_question', '')}")
    confidence = report.get("confidence", {}) or {}
    provenance = report.get("provenance", {}) or {}
    if confidence:
        print(
            "  Confidence:"
            f" {confidence.get('level', 'medium')}"
            f" ({float(confidence.get('score', 0.5) or 0.5):.2f})"
        )
    if provenance:
        print(
            "  Provenance:"
            f" source={provenance.get('source', 'unknown')},"
            f" status={provenance.get('source_status', 'unknown')},"
            f" freshness={provenance.get('freshness', 'unknown')}"
        )
    for layer in report.get("layers", [])[:top_n]:
        print(
            f"  {layer.get('rank', '?')}. {layer.get('layer', '')} "
            f"| 卡点={layer.get('scarce_layer', '')} "
            f"| score={float(layer.get('score', 0) or 0):.1f}"
        )
        for candidate in layer.get("candidates", [])[:top_n]:
            print(
                f"     - {candidate.get('code', '?')} {candidate.get('name', '')}: "
                f"{float(candidate.get('score', 0) or 0):.1f}"
            )
    md = format_theme_research(report)
    _save_report(
        f"theme_scan_{market}",
        fmt,
        output_dir,
        data=report,
        md=md,
        metadata={"command": "theme-scan", "market": market, "theme": theme},
    )


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze a single stock: K-line + valuation + fundamentals."""
    code = args.code
    market = getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)
    print(f"Analyzing {code} (market={market})...")

    ensure_symbol_analysis_ready(code, market)
    kline = get_kline(code, market, days=365, cached_only=True)
    print(f"  K-line data: {len(kline)} days cached")

    fund = get_fundamentals(code, market, cached_only=True)
    report_data = {"code": code, "market": market}
    if fund:
        print(f"  PE(TTM): {fund.get('pe_ttm', 'N/A')}")
        print(f"  PB:      {fund.get('pb', 'N/A')}")
        print(f"  ROE:     {fund.get('roe', 'N/A')}")
        print(f"  DivYld:  {fund.get('dividend_yield', 'N/A')}%")
        print(f"  MktCap:  {fund.get('market_cap', 0):,.0f}")
        report_data["fundamentals"] = {
            k: fund.get(k)
            for k in (
                "pe_ttm",
                "pb",
                "roe",
                "dividend_yield",
                "market_cap",
            )
        }
    else:
        print("  Fundamentals: not available (using cached/computed)")

    try:
        from factors.composite import CompositeAnalyzer

        analyzer = CompositeAnalyzer(code, market)
        result = analyzer.analyze()
        score = result.get("total_score", 0)
        print(f"  Composite Score: {score:.1f}/100 {_badge(score)}")
        for factor_name, factor_score in result.get("factors", {}).items():
            print(f"    {_badge(factor_score)} {factor_name}: {factor_score:.1f}")
        report_data["factor_analysis"] = result
    except Exception as exc:
        print(f"  Factor analysis: {exc}", file=sys.stderr)

    try:
        from strategies.aggregator import StrategyAggregator

        agg = StrategyAggregator(code, market)
        signals = agg.analyze_all()
        final = signals.get("final_signal", "HOLD")
        final_score = signals.get("final_score", 0)
        sig_badge = {"BUY": "##", "SELL": "!!"}.get(final, "--")
        print(f"  Strategy Signal: {sig_badge} {final} (score={final_score:.1f})")
        report_data["strategy"] = signals
    except Exception as exc:
        print(f"  Strategy analysis: {exc}", file=sys.stderr)

    _save_report(
        f"analyze_{code}_{market}",
        fmt,
        output_dir,
        data=report_data,
        metadata={"command": "analyze"},
    )


def cmd_diagnose(args: argparse.Namespace) -> None:
    """Deep diagnosis: strategy + sentiment + risk."""
    code = args.code
    market = getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)
    print(f"Diagnosing {code} (market={market})...")

    try:
        from advisor.diagnosis import StockDiagnosis

        diag = StockDiagnosis(code, market)
        report = diag.full_report()
        if fmt in ("json", "both"):
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))

        md = format_diagnosis_summary(report)
        _save_report(
            f"diagnose_{code}_{market}",
            fmt,
            output_dir,
            data=report,
            md=md,
            metadata={"command": "diagnose"},
        )
    except Exception as exc:
        print(f"Diagnosis failed: {exc}", file=sys.stderr)


def cmd_deep_diagnose(args: argparse.Namespace) -> None:
    """Run a heavier long-form single-symbol diagnosis."""
    code = args.code
    market = getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)
    print(f"Deep diagnosing {code} (market={market})...")

    try:
        report = build_deep_diagnosis(code, market)
        decision = report.get("final_decision", {}) or {}
        print(report.get("executive_summary", ""))
        print(
            "  Signal / Score:"
            f" {decision.get('signal', 'HOLD')}"
            f" / {float(decision.get('adjusted_score', 50) or 50):.1f}"
        )
        confidence = report.get("confidence", {}) or {}
        if confidence:
            print(
                "  Confidence:"
                f" {confidence.get('level', 'medium')}"
                f" ({float(confidence.get('score', 0.5) or 0.5):.2f})"
            )
        conflicts = report.get("conflict_matrix", []) or []
        for item in conflicts[:3]:
            print(
                f"  Conflict {item.get('topic', '?')}:"
                f" {item.get('status', 'mixed')}"
                f" | {item.get('implication', '')}"
            )
        for item in report.get("next_checks", [])[:3]:
            print(f"  Next check: {item}")

        md = format_deep_diagnosis_summary(report)
        _save_report(
            f"deep_diagnose_{code}_{market}",
            fmt,
            output_dir,
            data=report,
            md=md,
            metadata={"command": "deep-diagnose", "market": market, "code": code},
        )
    except Exception as exc:
        print(f"Deep diagnosis failed: {exc}", file=sys.stderr)


def cmd_scan(args: argparse.Namespace) -> None:
    """Scan market for top stocks."""
    market = args.market
    top_n = args.top or 20
    output_dir, fmt = _cmd_output(args)

    if market == "FUND":
        print("Scanning ETFs...")
        etfs = get_etf_pool()
        if not etfs:
            print(
                "  No ETFs found. Run 'python stockaskill/scripts/run.py fetch"
                " pool' first.",
                file=sys.stderr,
            )
            return
        ensure_etf_ready(
            [str(item.get("code", "")).strip() for item in etfs[:top_n]],
            limit=top_n,
        )
        print(f"Found {len(etfs)} ETFs")
        for f in etfs[:top_n]:
            print(f"  {f.get('code', '?')} {f.get('name', '?')}")
        _save_report(
            "scan_FUND",
            fmt,
            output_dir,
            data={"market": "FUND", "count": len(etfs), "results": etfs[:top_n]},
        )
        return

    print(f"Scanning {market} market for top {top_n}...", flush=True)

    # Cold start: run bounded warmup before regime analysis needs data
    cache = get_cache()
    if cache.is_market_data_empty(market):
        warmup_n = min(top_n * 3, 30)
        print(
            f"  缓存为空，预热点 {warmup_n} 只股票数据...",
            flush=True,
        )
        pool = get_stock_pool(market)
        codes = [
            str(item.get("code", ""))
            for item in pool[:warmup_n]
            if str(item.get("code", "")).strip()
        ]
        for code in codes:
            try:
                sync_symbol_data(code, market, history_days=365)
            except RuntimeError:
                pass  # API limit hit during warmup, continue with what we have

    try:
        regime = _safe_market_regime(market)
        print("  " + summarize_market_regime(regime), flush=True)

        # Risk alert for cautious/defensive market states
        posture = regime.get("posture", "neutral")
        if posture in ("cautious", "defensive"):
            actions = {
                "cautious": "谨慎，建议减仓至60%以下",
                "defensive": "防御，建议降至25%以下仓位，避免新仓",
            }
            risk_budget = float(regime.get("risk_budget", 1.0) or 1.0)
            allowed = regime.get("new_positions_allowed", True)
            print(
                f"  ⚠️  市场风险预警: {regime.get('posture_label', '中性')}",
                flush=True,
            )
            print(f"  建议: {actions.get(posture, '观望')}", flush=True)
            print(f"  风险预算: {risk_budget:.0%}", flush=True)
            if not allowed:
                print(f"  当前不建议新开仓位", flush=True)
            print(flush=True)

        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        mode = getattr(args, "mode", "auto")
        refreshed = False
        summary = None
        if mode == "realtime":
            print(
                "  Realtime mode is approximate and only evaluates a candidate subset.",
                flush=True,
            )
            results = scanner.scan_top(
                market,
                top_n,
                max_candidates=getattr(args, "candidates", 0),
            )
        else:
            status = scanner.get_snapshot_status(market)
            if mode == "auto" and status["status"] != "fresh":
                reason = "缺失" if status["status"] == "missing" else "过期"
                print(
                    f"  本地全市场快照{reason}，回退到有界 realtime candidate scan。",
                    flush=True,
                )
                print(
                    "  如需构建完整本地快照，可执行:"
                    f" python stockaskill/scripts/run.py refresh-scan {market}",
                    flush=True,
                )
                results = scanner.scan_top(
                    market,
                    top_n,
                    max_candidates=getattr(args, "candidates", 0),
                )
                summary = {
                    **status,
                    "fallback_mode": "realtime",
                    "requested_mode": mode,
                }
            elif (
                mode == "snapshot"
                and status["status"] != "fresh"
                and not getattr(args, "refresh", False)
            ):
                reason = "缺失" if status["status"] == "missing" else "过期"
                print(f"  本地全市场快照{reason}。", flush=True)
                print(
                    "  推荐执行:"
                    f" python stockaskill/scripts/run.py refresh-scan {market}",
                    flush=True,
                )
                print(
                    "  或改用默认 auto / 显式 realtime 做有界候选扫描。",
                    flush=True,
                )
                results = []
                _save_report(
                    f"scan_{market}",
                    fmt,
                    output_dir,
                    data={
                        "market": market,
                        "top_n": top_n,
                        "mode": mode,
                        "results": results,
                        "summary": status,
                        "refreshed": refreshed,
                    },
                    metadata={"command": "scan", "market": market, "top_n": top_n},
                )
                return
            elif getattr(args, "refresh", False) or status["status"] != "fresh":
                print("  Refreshing full-market snapshot first...", flush=True)
                summary = scanner.refresh_snapshot(
                    market,
                    include_incomplete=getattr(args, "include_incomplete", False),
                )
                refreshed = True
                snapshot = scanner.scan_snapshot(
                    market,
                    top_n=top_n,
                    include_incomplete=getattr(args, "include_incomplete", False),
                )
                results = snapshot["results"]
                summary = snapshot["summary"] or summary
                if summary:
                    _print_snapshot_summary(summary, refreshed=refreshed)
                    if refreshed:
                        _print_refresh_summary(summary)
            else:
                snapshot = scanner.scan_snapshot(
                    market,
                    top_n=top_n,
                    include_incomplete=getattr(args, "include_incomplete", False),
                )
                results = snapshot["results"]
                summary = snapshot["summary"] or summary
                if summary:
                    _print_snapshot_summary(summary, refreshed=refreshed)
        if not results:
            print(
                "  No results returned (run 'python stockaskill/scripts/run.py"
                " fetch pool'"
                " to refresh data).",
                file=sys.stderr,
                flush=True,
            )
        for i, r in enumerate(results, 1):
            score = r.get("total_score", 0)
            name = r.get("name", r["code"])
            f_score = r.get("f_score", 0)
            badge = _badge(score)
            metadata_suffix = ""
            if "metadata_completeness" in r:
                metadata_suffix = (
                    f", meta={float(r.get('metadata_completeness', 0) or 0):.2f}"
                )
                penalty = float(r.get("metadata_penalty", 0) or 0)
                if penalty > 0:
                    metadata_suffix += (
                        f", adj={float(r.get('adjusted_score', score) or 0):.1f}"
                    )
            print(
                f"  {badge} {i:3d}. {r['code']} {name}: {score:.1f}"
                f" (F={f_score}{metadata_suffix})"
            )

        _save_report(
            f"scan_{market}",
            fmt,
            output_dir,
            data={
                "market": market,
                "regime": regime,
                "top_n": top_n,
                "mode": mode,
                "results": results,
                "summary": summary,
                "refreshed": refreshed,
            },
            metadata={"command": "scan", "market": market, "top_n": top_n},
        )
    except Exception as exc:
        print(f"Scan failed: {exc}", file=sys.stderr)
    finally:
        _print_api_usage()


def cmd_refresh_scan(args: argparse.Namespace) -> None:
    """Build a full-market local scan snapshot and print the top results."""
    market = args.market
    top_n = args.top or 20
    output_dir, fmt = _cmd_output(args)
    print(f"Refreshing full-market snapshot for {market}...", flush=True)
    regime = _safe_market_regime(market)
    print("  " + summarize_market_regime(regime), flush=True)
    try:
        from advisor.scanner import MarketScanner

        scanner = MarketScanner()
        summary = scanner.refresh_snapshot(
            market,
            include_incomplete=getattr(args, "include_incomplete", False),
        )
        _print_snapshot_summary(summary, refreshed=True)
        _print_refresh_summary(summary)
        snapshot = scanner.scan_snapshot(
            market,
            top_n=top_n,
            include_incomplete=getattr(args, "include_incomplete", False),
        )
        results = snapshot["results"]
        for i, r in enumerate(results, 1):
            score = r.get("total_score", 0)
            name = r.get("name", r["code"])
            f_score = r.get("f_score", 0)
            badge = _badge(score)
            metadata_suffix = ""
            if "metadata_completeness" in r:
                metadata_suffix = (
                    f", meta={float(r.get('metadata_completeness', 0) or 0):.2f}"
                )
                penalty = float(r.get("metadata_penalty", 0) or 0)
                if penalty > 0:
                    metadata_suffix += (
                        f", adj={float(r.get('adjusted_score', score) or 0):.1f}"
                    )
            print(
                f"  {badge} {i:3d}. {r['code']} {name}: {score:.1f}"
                f" (F={f_score}{metadata_suffix})"
            )
        _save_report(
            f"refresh_scan_{market}",
            fmt,
            output_dir,
            data={
                "market": market,
                "regime": regime,
                "top_n": top_n,
                "mode": "snapshot",
                "results": results,
                "summary": summary,
                "refreshed": True,
            },
            metadata={"command": "refresh-scan", "market": market, "top_n": top_n},
        )
    except Exception as exc:
        print(f"Refresh scan failed: {exc}", file=sys.stderr)


def cmd_portfolio(args: argparse.Namespace) -> None:
    """Build an investment portfolio."""
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    capital = args.capital or 1000000
    market = getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)

    print(f"Building portfolio with {len(codes)} stocks, capital={capital:,.0f}")
    regime = _safe_market_regime(market)
    print("  " + summarize_market_regime(regime))
    try:
        from data_engine import sync_portfolio_data
        from portfolio.builder import PortfolioBuilder

        # Phase 1: sync only missing data
        print(f"  Syncing {len(codes)} symbols...")
        sync_result = sync_portfolio_data(codes, market=market, history_days=365)
        print(
            f"  Sync done: {sync_result['ready']}/{sync_result['requested']} ready, "
            f"cache_hits={sync_result['cache_hits']}"
        )

        # Phase 2: all analysis reads cache only
        builder = PortfolioBuilder("My Portfolio", capital=capital)
        for c in codes:
            builder.add_from_strategy(c, market, cached_only=True)
        portfolio = builder.build(
            capital_fraction=float(regime.get("risk_budget", 1.0) or 1.0)
        )
        print(portfolio.summary())

        positions_data = []
        for p in portfolio.positions:
            positions_data.append(
                {
                    "code": p.code,
                    "name": p.name,
                    "weight": p.weight,
                    "shares": p.shares,
                    "cost": p.cost,
                }
            )
        port_data = {
            "name": portfolio.name,
            "capital": capital,
            "market": market,
            "regime": regime,
            "positions": positions_data,
            "metrics": portfolio.metrics,
        }
        md = format_portfolio_summary(
            portfolio.name,
            capital,
            positions_data,
            portfolio.metrics,
            regime=regime,
        )
        _save_report(
            f"portfolio_{market}",
            fmt,
            output_dir,
            data=port_data,
            md=md,
            metadata={"command": "portfolio", "market": market},
        )
    except Exception as exc:
        print(f"Portfolio build failed: {exc}", file=sys.stderr)


def cmd_fetch(args: argparse.Namespace) -> None:
    """Manually refresh data."""
    fetch_type = args.type
    code = getattr(args, "code", "")
    market = getattr(args, "market", "A") or "A"

    if fetch_type == "pool":
        print("Refreshing stock pool (local-first)...")
        for mkt in ["A", "HK", "US", "FUND"]:
            if mkt == "FUND":
                get_fund_pool(force_refresh=False)
            else:
                get_stock_pool(mkt, force_refresh=False)
            _print_pool_summary(mkt)
    elif fetch_type == "kline":
        print(f"Fetching K-line for {code}...")
        from data_engine import get_kline

        kline = get_kline(code, market, days=730, force_refresh=True)
        print(f"  Cached {len(kline)} days")
    elif fetch_type == "fundamentals":
        print(f"Fetching fundamentals for {code}...")
        from data_engine import get_fundamentals

        fund = get_fundamentals(code, market, force_refresh=True)
        if fund:
            print(f"  PE(TTM): {fund.get('pe_ttm', 'N/A')}")
        else:
            print("  No data")
    else:
        print(f"Unknown fetch type: {fetch_type}")


def cmd_sync(args: argparse.Namespace) -> None:
    """Synchronize bounded local data for a specific scope."""
    sync_type = args.type
    output_dir, fmt = _cmd_output(args)
    market = getattr(args, "market", "A") or "A"
    history_days = getattr(args, "days", 365) or 365
    need_fundamentals = not bool(getattr(args, "skip_fundamentals", False))
    full_history = bool(getattr(args, "full_history", False))
    if sync_type == "symbol":
        code = args.code
        print(
            f"Synchronizing symbol {code} (market={market}, days={history_days}, "
            f"full_history={'yes' if full_history else 'no'})..."
        )
        result = sync_symbol_data(
            code,
            market,
            history_days=history_days,
            need_fundamentals=need_fundamentals,
            full_history=full_history,
        )
        _print_symbol_sync_summary(result)
        report_name = f"sync_symbol_{result['code']}_{market}"
        metadata = {
            "command": "sync",
            "type": sync_type,
            "market": market,
            "code": result["code"],
        }
    elif sync_type == "watchlist":
        if full_history:
            print(
                f"Synchronizing watchlist (market={market}, target=全量历史)..."
            )
        else:
            print(
                f"Synchronizing watchlist (market={market}, days={history_days})..."
            )
        result = sync_watchlist_data(
            market=market,
            history_days=history_days,
            need_fundamentals=need_fundamentals,
            full_history=full_history,
        )
        _print_scope_sync_summary(result, label="watchlist")
        report_name = f"sync_watchlist_{market}"
        metadata = {"command": "sync", "type": sync_type, "market": market}
    elif sync_type == "portfolio":
        codes = [c.strip() for c in getattr(args, "codes", "").split(",") if c.strip()]
        if full_history:
            print(
                f"Synchronizing portfolio ({len(codes)} symbols, market={market}, "
                f"target=全量历史)..."
            )
        else:
            print(
                f"Synchronizing portfolio ({len(codes)} symbols, market={market}, "
                f"days={history_days})..."
            )
        result = sync_portfolio_data(
            codes,
            market=market,
            history_days=history_days,
            need_fundamentals=need_fundamentals,
            full_history=full_history,
        )
        _print_scope_sync_summary(result, label="portfolio")
        report_name = f"sync_portfolio_{market}"
        metadata = {
            "command": "sync",
            "type": sync_type,
            "market": market,
            "codes": codes,
        }
    elif sync_type == "etf":
        codes = [c.strip() for c in getattr(args, "codes", "").split(",") if c.strip()]
        print(
            f"Synchronizing ETFs ({len(codes)} symbols, days={history_days}, "
            f"full_history={'yes' if full_history else 'no'})..."
        )
        result = sync_etf_data(
            codes,
            history_days=history_days,
            full_history=full_history,
        )
        _print_scope_sync_summary(result, label="etf")
        report_name = "sync_etf"
        metadata = {
            "command": "sync",
            "type": sync_type,
            "market": "FUND",
            "codes": codes,
        }
    elif sync_type == "scan-universe":
        limit = getattr(args, "limit", 200) or 200
        if full_history:
            print(
                f"Synchronizing scan universe (market={market}, limit={limit}, "
                f"target=全量历史)..."
            )
        else:
            print(
                f"Synchronizing scan universe (market={market}, limit={limit}, "
                f"days={history_days})..."
            )
        result = sync_scan_universe_data(
            market=market,
            limit=limit,
            history_days=history_days,
            need_fundamentals=need_fundamentals,
            full_history=full_history,
        )
        _print_scope_sync_summary(result, label="scan-universe")
        report_name = f"sync_scan_universe_{market}"
        metadata = {
            "command": "sync",
            "type": sync_type,
            "market": market,
            "limit": limit,
        }
    else:
        print(f"Unknown sync type: {sync_type}")
        return

    _save_report(report_name, fmt, output_dir, data=result, metadata=metadata)


def _print_symbol_sync_summary(result: dict) -> None:
    """Print a concise symbol-sync summary."""
    print(
        "  History:"
        f" before={result.get('history_before', 0)},"
        f" after={result.get('history_after', 0)},"
        f" ready={'yes' if result.get('history_ready') else 'no'},"
        f" covered_through={result.get('history_covered_through', '?') or '?'}"
    )
    if result.get("fundamentals_required"):
        print(
            "  Fundamentals:"
            f" before={'yes' if result.get('fundamentals_before') else 'no'},"
            f" after={'yes' if result.get('fundamentals_after') else 'no'},"
            " covered_through="
            f"{result.get('fundamentals_covered_through', '?') or '?'}"
        )
    if result.get("errors"):
        print("  Errors:")
        for err in result["errors"]:
            print(f"    - {err}")
    print(f"  Ready: {'yes' if result.get('ready') else 'no'}")


def _print_scope_sync_summary(result: dict, label: str) -> None:
    """Print a concise summary for a bounded multi-symbol sync scope."""
    earliest = result.get("earliest_date", "") or ""
    latest = result.get("latest_date", "") or ""
    total_rows = result.get("total_history_rows", 0)
    covered_through = result.get("covered_through", "") or ""
    requested = result.get("requested", 0)
    ready = result.get("ready", 0)
    elapsed = result.get("elapsed_seconds", 0)
    failed = max(0, requested - ready)

    print(
        f"  同步汇总 [{label}]: "
        f"总数={requested}, "
        f"就绪={ready}, "
        f"失败={failed}, "
        f"耗时={_format_elapsed(elapsed)}"
    )
    print(
        f"    缓存命中={result.get('cache_hits', 0)}, "
        f"K线拉取={result.get('history_fetched_count', 0)}, "
        f"基本面拉取={result.get('fundamentals_fetched_count', 0)}"
    )
    if total_rows:
        print(f"    累计K线行数: {total_rows:,}")
    if earliest or latest:
        print(f"    数据日期范围: {earliest or '?'} ~ {latest or '?'}")
    if covered_through:
        print(f"    更新至: {covered_through}")
    if result.get("missing_codes"):
        print(f"    未就绪: {len(result['missing_codes'])} 只")
        print("    未就绪代码: " + ", ".join(result["missing_codes"][:10]))

    # Data completeness report
    market = result.get("market", "")
    if market:
        completeness = check_data_completeness(market)
        if completeness:
            top_incomplete = sorted(
                completeness, key=lambda x: x["missing_days"], reverse=True
            )[:5]
            print(
                f"    数据完整性: {len(completeness)} 只股票缺失交易日"
            )
            for item in top_incomplete:
                print(
                    f"      {item['code']}: "
                    f"{item['actual_days']}/{item['expected_days']} 天 "
                    f"(缺失 {item['missing_days']})"
                )
        else:
            print("    数据完整性: 全部完成")


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as Xm Ys."""
    m, s = divmod(int(seconds), 60)
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def cmd_status(args: argparse.Namespace) -> None:
    """Show bounded sync-state diagnostics."""
    status_type = args.type
    cache = get_cache()
    market = getattr(args, "market", "A") or "A"

    if status_type == "symbol":
        code = normalize_code_for_market(args.code, market)
        rows = cache.get_sync_state(
            "symbol",
            f"{market}:{code}",
            market=market,
            code=code,
        )
        _print_status_summary(rows, label=f"symbol {code}", requested=1)
        _print_market_metadata_summary(_scope_pool_rows([code], market), label="symbol")
    elif status_type == "watchlist":
        rows = cache.get_sync_state("watchlist", market, market=market)
        codes = _normalized_watchlist(market)
        symbol_rows = _collect_symbol_scope_rows(cache, codes, market)
        _print_status_summary(symbol_rows, label="watchlist", requested=len(codes))
        _print_market_metadata_summary(
            _scope_pool_rows(codes, market),
            label="watchlist",
        )
        rows.extend(symbol_rows)
    elif status_type == "portfolio":
        codes = [
            normalize_code_for_market(c.strip(), market)
            for c in getattr(args, "codes", "").split(",")
            if c.strip()
        ]
        rows = cache.get_sync_state(
            "portfolio",
            ",".join(codes),
            market=market,
        )
        symbol_rows = _collect_symbol_scope_rows(cache, codes, market)
        _print_status_summary(symbol_rows, label="portfolio", requested=len(codes))
        _print_market_metadata_summary(
            _scope_pool_rows(codes, market),
            label="portfolio",
        )
        rows.extend(symbol_rows)
    elif status_type == "scan-universe":
        limit = getattr(args, "limit", 200) or 200
        rows = cache.get_sync_state(
            "scan-universe",
            f"{market}:{limit}",
            market=market,
        )
        codes = _scan_universe_codes(market, limit)
        symbol_rows = _collect_symbol_scope_rows(cache, codes, market)
        _print_status_summary(
            symbol_rows,
            label=f"scan-universe {market}:{limit}",
            requested=len(codes),
        )
        _print_market_metadata_summary(
            _scope_pool_rows(codes, market),
            label="scan-universe",
        )
        rows.extend(symbol_rows)
    elif status_type == "etf":
        market = "FUND"
        codes = [
            normalize_code_for_market(c.strip(), market)
            for c in getattr(args, "codes", "").split(",")
            if c.strip()
        ]
        rows = cache.get_sync_state(
            "etf",
            ",".join(codes),
            market=market,
        )
        symbol_rows = _collect_symbol_scope_rows(cache, codes, market)
        _print_status_summary(symbol_rows, label="etf", requested=len(codes))
        _print_market_metadata_summary(_scope_pool_rows(codes, market), label="etf")
        rows.extend(symbol_rows)
    elif status_type == "pool":
        pool = get_stock_pool(market)
        pool_count = len(pool) if pool else 0
        needs_refresh = cache.pool_needs_refresh(market)
        print(f"  Pool: {market}")
        print(f"  Count: {pool_count}")
        print(f"  Needs refresh: {needs_refresh}")
        if pool:
            dates = sorted(
                r.get("updated_at", "")
                for r in pool
                if r.get("updated_at")
            )
            if dates:
                print(f"  Last updated: {dates[-1]}")
                print(f"  Oldest entry: {dates[0]}")
        rows: List[dict] = []
    else:
        print(f"Unknown status type: {status_type}")
        return

    if not rows:
        if status_type != "pool":
            print("No sync state found.")
        return
    print(f"Sync state for {status_type} (market={market}):")
    for row in rows:
        code_label = row.get("code", "") or "-"
        print(
            f"  {row.get('data_kind', '?')}:"
            f" code={code_label},"
            f" status={row.get('status', '?')},"
            f" covered={row.get('last_covered_date', '?') or '?'},"
            f" last_success={row.get('last_success_at', '?') or '?'}"
        )
        if row.get("last_error"):
            print(f"    error={row['last_error']}")


def _normalized_watchlist(market: str) -> list[str]:
    """Return normalized watchlist codes for a market."""
    return [
        normalize_code_for_market(code, market)
        for code in cfg_get("watchlist", [])
        if str(code).strip()
    ]


def _scan_universe_codes(market: str, limit: int) -> List[str]:
    """Return normalized codes for a bounded scan universe."""
    if market == "FUND":
        pool = get_etf_pool()
    else:
        pool = get_stock_pool(market)
    return [
        normalize_code_for_market(str(item.get("code", "")), market)
        for item in pool[:limit]
        if str(item.get("code", "")).strip()
    ]


def _collect_symbol_scope_rows(
    cache: Any,
    codes: List[str],
    market: str,
) -> List[dict]:
    """Collect symbol sync-state rows for a bounded scope."""
    rows: List[dict] = []
    for code in codes:
        rows.extend(
            cache.get_sync_state(
                "symbol",
                f"{market}:{code}",
                market=market,
                code=code,
            )
        )
    return rows


def _scope_pool_rows(
    codes: List[str],
    market: str,
) -> List[dict]:
    """Return cached pool rows for the provided scope codes."""
    if market == "FUND":
        pool = get_etf_pool()
    else:
        pool = get_stock_pool(market)
    pool_by_code = {
        normalize_code_for_market(str(item.get("code", "")), market): item
        for item in pool
        if str(item.get("code", "")).strip()
    }
    return [pool_by_code[code] for code in codes if code in pool_by_code]


def _print_market_metadata_summary(pool_rows: List[dict], label: str) -> None:
    """Print a compact metadata-quality summary for a market scope."""
    if not pool_rows:
        return
    complete = 0
    partial = 0
    low = 0
    inactive = 0
    total_completeness = 0.0
    source_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    for row in pool_rows:
        completeness = float(row.get("metadata_completeness", 0) or 0)
        total_completeness += completeness
        if completeness >= 0.75:
            complete += 1
        elif completeness >= 0.5:
            partial += 1
        else:
            low += 1
        if not bool(row.get("is_active", 1)):
            inactive += 1
        source = str(row.get("metadata_source", "")).strip() or "unknown"
        status = str(row.get("metadata_status", "")).strip() or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1
    top_source = max(source_counts.items(), key=lambda item: item[1])[0]
    top_status = max(status_counts.items(), key=lambda item: item[1])[0]
    avg_completeness = total_completeness / max(len(pool_rows), 1)
    print(
        f"  Metadata {label}:"
        f" complete={complete}, partial={partial}, low={low},"
        f" inactive={inactive}, avg={avg_completeness:.2f},"
        f" top_source={top_source}, top_status={top_status}"
    )


def _status_freshness(row: dict) -> str:
    """Classify a sync-state row as fresh, stale, or missing."""
    ttl_map = {
        "history": int(cfg_get("cache_ttl.daily_kline", 3600) or 3600),
        "fundamentals": int(cfg_get("cache_ttl.financial", 604800) or 604800),
        "nav": int(cfg_get("cache_ttl.fund_nav", 3600) or 3600),
        "summary": int(cfg_get("cache_ttl.daily_kline", 3600) or 3600),
    }
    last_success = str(row.get("last_success_at", "")).strip()
    if not last_success:
        return "missing"
    try:
        timestamp = datetime.strptime(last_success, "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return "unknown"
    ttl = ttl_map.get(str(row.get("data_kind", "")), 3600)
    return "fresh" if (time.time() - timestamp) <= ttl else "stale"


def _print_status_summary(rows: List[dict], label: str, requested: int) -> None:
    """Print aggregate freshness/error summary for a scope."""
    if not rows:
        print(f"  Scope {label}: no symbol sync rows found")
        return
    by_code: Dict[str, List[dict]] = {}
    stale = 0
    fresh = 0
    errors = 0
    for row in rows:
        code = str(row.get("code", "")).strip() or "-"
        by_code.setdefault(code, []).append(row)
        freshness = _status_freshness(row)
        if freshness == "fresh":
            fresh += 1
        elif freshness == "stale":
            stale += 1
        if row.get("last_error"):
            errors += 1
    problem_codes = []
    for code, code_rows in by_code.items():
        if any(
            row.get("status") != "ok"
            or _status_freshness(row) != "fresh"
            or row.get("last_error")
            for row in code_rows
        ):
            problem_codes.append(code)
    print(
        f"  Scope {label}: requested={requested},"
        f" symbol_rows={len(rows)}, fresh={fresh}, stale={stale},"
        f" errors={errors}, symbols_with_issues={len(problem_codes)}"
    )
    if problem_codes:
        print("  Top missing/problem symbols: " + ", ".join(problem_codes[:10]))


def cmd_alpha(args: argparse.Namespace) -> None:
    """Alpha momentum scan: rank stocks by optimized multi-factor strategy."""
    market = args.market
    top_n = args.top or 10
    output_dir, fmt = _cmd_output(args)

    print(f"Alpha Momentum scan on {market}, top {top_n}...")
    regime = _safe_market_regime(market)
    print("  " + summarize_market_regime(regime))

    # Risk alert for cautious/defensive market states
    posture = regime.get("posture", "neutral")
    if posture in ("cautious", "defensive"):
        actions = {
            "cautious": "谨慎，建议减少候选数量",
            "defensive": "防御，建议暂停扫描，避免追高",
        }
        risk_budget = float(regime.get("risk_budget", 1.0) or 1.0)
        print(
            f"  ⚠️  市场风险预警: {regime.get('posture_label', '中性')}",
            flush=True,
        )
        print(f"  建议: {actions.get(posture, '观望')}", flush=True)
        print(f"  风险预算: {risk_budget:.0%}", flush=True)
        print(flush=True)

    try:
        pool = get_stock_pool(market)
        max_candidates = getattr(args, "candidates", 0) or cfg_get("scan_max_candidates", 0)
        candidates = pool[:max_candidates]

        # Concurrent pre-sync: fetch missing kline + fundamentals in parallel
        from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

        from data_engine import sync_symbol_data

        actual_n = len(candidates)
        print(f"  Pre-syncing {actual_n} candidates (8 workers)...", flush=True)
        sync_done = 0
        sync_errors = 0

        def sync_one(stock):
            try:
                sync_symbol_data(stock["code"], market, history_days=365)
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool_exec:
            sync_futures = {pool_exec.submit(sync_one, s): s for s in candidates}
            for f in as_completed(sync_futures):
                sync_done += 1
                if f.result():
                    sync_errors += 0
                else:
                    sync_errors += 1
                if sync_done % 50 == 0 or sync_done == actual_n:
                    print(f"    Sync progress: {sync_done}/{actual_n}", flush=True)
        if sync_errors:
            print(f"    Sync errors: {sync_errors}/{actual_n} (will skip in scoring)", flush=True)

        from strategies.alpha_momentum import AlphaMomentumStrategy

        results = []
        strat = AlphaMomentumStrategy()

        def score_one(stock):
            code = stock["code"]
            try:
                r = strat.analyze(code, market, cached_only=True)
                return (
                    code,
                    stock.get("name", ""),
                    r["score"],
                    r["signal"],
                    r["detail"]["f_score"],
                    r["detail"]["factors"],
                )
            except Exception:
                return None

        print(f"  Scoring {actual_n} candidates (8 workers)...", flush=True)
        score_done = 0
        with ThreadPoolExecutor(max_workers=8) as exec:
            futures = {exec.submit(score_one, s): s for s in candidates}
            for f in as_completed(futures):
                score_done += 1
                if score_done % 50 == 0 or score_done == actual_n:
                    print(f"    Score progress: {score_done}/{actual_n}", flush=True)
                result = f.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x[2], reverse=True)
        header = f"{'#':<4} {'代码':<10} {'名称':<10} "
        header += f"{'得分':<6} {'信号':<6} {'F':<4}"
        print(f"\n{header}")
        print("-" * 45)
        top_results = results[:top_n]
        for i, (code, name, score, signal, fsc, _) in enumerate(top_results, 1):
            sig_badge = {"BUY": "##", "SELL": "!!"}.get(signal, "--")
            print(f"{i:<4} {code:<10} {name:<10} {score:<6.1f} {sig_badge:<6} {fsc:<4}")

        print("\n## BUY signals:")
        buys = [(c, n, s, f) for c, n, s, sig, f, _ in top_results if sig == "BUY"]
        for c, n, s, f in buys:
            print(f"  ## {c} {n} (score={s:.1f}, F={f})")
        if not buys:
            print("  -- No BUY signals")

        ranked = []
        for code, name, score, signal, fsc, factors in top_results:
            ranked.append(
                {
                    "code": code,
                    "name": name,
                    "score": score,
                    "signal": signal,
                    "f_score": fsc,
                    "factors": factors,
                }
            )
        _save_report(
            f"alpha_{market}",
            fmt,
            output_dir,
            data={
                "market": market,
                "regime": regime,
                "top_n": top_n,
                "results": ranked,
                "buys": buys,
            },
            metadata={"command": "alpha", "market": market, "top_n": top_n},
        )
    except Exception as exc:
        print(f"Alpha scan failed: {exc}", file=sys.stderr)


def cmd_backtest(args: argparse.Namespace) -> None:
    """Run Alpha Momentum backtest (2018-2026)."""
    output_dir, fmt = _cmd_output(args)
    market = getattr(args, "market", "A") or "A"
    print(f"Running Alpha Momentum backtest ({market})...")
    try:
        from portfolio.backtest_engine import AlphaMomentumBacktest

        engine = AlphaMomentumBacktest(
            capital=cfg_get("backtest_capital", 1_000_000),
            low_vol_min=cfg_get("low_vol_min", 0.4),
            top_k=cfg_get("alpha_momentum.top_k", 6),
            max_per_board=cfg_get("alpha_momentum.max_per_board", 3),
            market=market,
        )
        result = engine.run()

        pool_size = result.get("pool_size", 0)
        years = result.get("years", 0)
        print(f"  Pool: {pool_size} stocks, {years} years")
        period_start = result.get("period_start", "?")
        period_end = result.get("period_end", "?")
        print(f"  Period: {period_start} ~ {period_end}")
        cagr_val = result.get("cagr", 0)
        total_ret = result.get("total_return", 0)
        sharpe_val = result.get("sharpe", 0)
        mdd_val = result.get("max_drawdown", 0)
        monthly_avg = result.get("monthly_avg", 0)
        print(f"  CAGR: {cagr_val * 100:.2f}%")
        print(f"  Total Return: {total_ret * 100:.2f}%")
        print(f"  Sharpe: {sharpe_val:.2f}")
        print(f"  Max Drawdown: {mdd_val * 100:.2f}%")
        print(f"  Monthly Avg: {monthly_avg:.2f}%")

        if cagr_val > 0.12:
            print(f"  Result: ## PASS (CAGR {cagr_val * 100:.2f}% > 12% target)")
        else:
            print(f"  Result: !! FAIL (CAGR {cagr_val * 100:.2f}% < 12% target)")

        md = format_backtest_summary(result)
        _save_report(
            "backtest",
            fmt,
            output_dir,
            data=result,
            md=md,
            metadata={
                "command": "backtest",
                "engine": "AlphaMomentumBacktest",
            },
        )
    except Exception as exc:
        print(f"Backtest failed: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()


def cmd_backtest_enhanced(args: argparse.Namespace) -> None:
    """Run Enhanced Core-Satellite backtest (2018-2026)."""
    output_dir, fmt = _cmd_output(args)
    print("Running Enhanced Core-Satellite backtest...")
    try:
        import importlib

        bt = importlib.import_module("backtest_enhanced")
        result = bt.run_backtest()
        print(
            f"\n  Result: CAGR={result.get('cagr', 0) * 100:.2f}%, "
            f"Sharpe={result.get('sharpe', 0):.2f}, "
            f"MaxDD={result.get('max_drawdown', 0) * 100:.2f}%"
        )

        md = format_backtest_summary(result)
        _save_report(
            "backtest_enhanced",
            fmt,
            output_dir,
            data=result,
            md=md,
            metadata={
                "command": "backtest-enhanced",
                "engine": "CoreSatellite",
            },
        )
    except Exception as exc:
        print(f"Enhanced backtest failed: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()


def cmd_portfolio_enhanced(args: argparse.Namespace) -> None:
    """Build ETF(3) + Alpha Momentum Top3 = 6 positions portfolio."""
    capital = args.capital or 1000000
    output_dir, fmt = _cmd_output(args)
    print(f"Building Enhanced Core-Satellite portfolio, capital={capital:,.0f}")
    regime = _safe_market_regime("A")
    print("  " + summarize_market_regime(regime))
    try:
        from data_engine import get_stock_pool, sync_portfolio_data
        from portfolio.builder import PortfolioBuilder
        from strategies.momentum_enhanced import MomentumEnhancedStrategy

        strat = MomentumEnhancedStrategy()
        pool = get_stock_pool("A")
        candidates = pool[:200]

        # Phase 1: sync only missing data for candidates + ETFs
        etf_codes = [e["code"] for e in MomentumEnhancedStrategy.get_etf_allocation()]
        codes_to_sync = [c["code"] for c in candidates] + etf_codes
        print(f"  Syncing {len(codes_to_sync)} symbols (pool + ETFs)...")
        sync_result = sync_portfolio_data(codes_to_sync, market="A", history_days=365)
        print(
            f"  Sync done: {sync_result['ready']}/{sync_result['requested']} ready, "
            f"cache_hits={sync_result['cache_hits']}, "
            f"history_fetched={sync_result['history_fetched_count']}, "
            f"fundamentals_fetched={sync_result['fundamentals_fetched_count']}"
        )

        # Phase 2: all analysis reads cache only
        selected = strat.select_top_stocks(candidates, max_picks=3, cached_only=True)

        etfs = MomentumEnhancedStrategy.get_etf_allocation()
        codes = [e["code"] for e in etfs] + selected
        print(f"  ETFs (core): {[e['code'] for e in etfs]}")
        print(f"  Stocks (satellite): {selected}")

        builder = PortfolioBuilder("Core-Satellite", capital=capital)
        for code in codes:
            builder.add_from_strategy(code, "A", cached_only=True)
        portfolio = builder.build(
            capital_fraction=float(regime.get("risk_budget", 1.0) or 1.0)
        )
        print(portfolio.summary())

        positions_data = []
        for p in portfolio.positions:
            positions_data.append(
                {
                    "code": p.code,
                    "name": p.name,
                    "weight": p.weight,
                    "shares": p.shares,
                    "cost": p.cost,
                }
            )
        port_data = {
            "name": "Core-Satellite",
            "capital": capital,
            "regime": regime,
            "etfs": [e["code"] for e in etfs],
            "stocks": selected,
            "positions": positions_data,
            "metrics": portfolio.metrics,
        }
        md = format_portfolio_summary(
            "Core-Satellite",
            capital,
            positions_data,
            portfolio.metrics,
            regime=regime,
        )
        _save_report(
            "portfolio_enhanced",
            fmt,
            output_dir,
            data=port_data,
            md=md,
            metadata={"command": "portfolio-enhanced"},
        )
    except Exception as exc:
        _cmd_error(f"Enhanced portfolio build failed: {exc}")


def cmd_scheduler(args: argparse.Namespace) -> None:
    """Run scheduled analysis."""
    watchlist = cfg_get("watchlist", [])
    if not watchlist:
        print("No watchlist configured")
        return

    if args.run_now:
        print(f"Running scheduled analysis for {len(watchlist)} stocks...")
        for code in watchlist:
            if is_api_limit_exhausted():
                print(f"  [INFO] API limit reached, skipping remaining stocks.", flush=True)
                break
            print(f"\n--- {code} ---")
            fake_args = argparse.Namespace(code=code, market="A", output_dir="reports")
            cmd_analyze(fake_args)
    else:
        print("Scheduler mode: use --run-now for immediate execution")
        print("In production, integrate with cron/systemd Task Scheduler")
        print(f"Watching: {', '.join(watchlist)}")


def cmd_cache(args: argparse.Namespace) -> None:
    """Cache management: stats, cleanup."""
    action = args.action
    cache = get_cache()

    if action == "stats":
        s = cache.stats()
        print(f"DB size: {s['db_size_mb']:.1f} MB")
        if is_api_limit_exhausted():
            print("[WARN] Some upstream APIs are currently rate-limited.")
        print("Table row counts:")
        for tbl, cnt in sorted(s.items()):
            if tbl in ("db_size_mb", "api_calls_today"):
                continue
            print(f"  {tbl}: {cnt}")
    elif action == "cleanup":
        days = getattr(args, "days", 30)
        removed = cache.cleanup(max_age_days=days)
        total = sum(removed.values())
        print(f"Cleaned up {total} old entries:")
        for tbl, cnt in removed.items():
            if cnt:
                print(f"  {tbl}: {cnt} rows removed")
    else:
        print(f"Unknown cache action: {action}")


def cmd_market_regime(args: argparse.Namespace) -> None:
    """Analyze current market posture and risk budget."""
    market = getattr(args, "market_flag", None) or getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)

    regime = analyze_market_regime(market)
    print(summarize_market_regime(regime))
    confidence = regime.get("confidence", {}) or {}
    provenance = regime.get("provenance", {}) or {}
    if confidence:
        print(
            "  Confidence:"
            f" {confidence.get('level', 'medium')}"
            f" ({float(confidence.get('score', 0.5) or 0.5):.2f})"
        )
    if provenance:
        print(
            "  Provenance:"
            f" source={provenance.get('source', 'unknown')},"
            f" status={provenance.get('source_status', 'unknown')},"
            f" freshness={provenance.get('freshness', 'unknown')}"
        )
    technical = regime.get("technical", {}) or {}
    breadth = regime.get("breadth", {}) or {}
    if technical:
        print(
            "  技术面:"
            f" current={technical.get('current', 'N/A')},"
            f" ma20={technical.get('ma20', 'N/A')},"
            f" ma60={technical.get('ma60', 'N/A')},"
            f" ret20={float(technical.get('ret20', 0) or 0) * 100:.2f}%"
        )
    if breadth:
        above_ma20 = float(breadth.get("above_ma20_ratio", 0.5) or 0.5) * 100
        above_ma60 = float(breadth.get("above_ma60_ratio", 0.5) or 0.5) * 100
        print(
            "  Breadth:"
            f" sample={breadth.get('sample_size', 0)}/{breadth.get('sample_limit', 0)},"
            f" above_ma20={above_ma20:.1f}%,"
            f" above_ma60={above_ma60:.1f}%"
        )
    for reason in regime.get("reasons", [])[:5]:
        print(f"  - {reason}")

    md = format_market_regime_summary(regime)
    _save_report(
        f"market_regime_{market}",
        fmt,
        output_dir,
        data=regime,
        md=md,
        metadata={"command": "market-regime", "market": market},
    )


def cmd_risk_alert(args: argparse.Namespace) -> None:
    """Show market risk alert with actionable suggestions."""
    market = getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)

    regime = _safe_market_regime(market)
    posture = regime.get("posture", "neutral")
    score = float(regime.get("score", 50) or 50)
    label = regime.get("posture_label", "中性")
    risk_budget = float(regime.get("risk_budget", 1.0) or 1.0)
    allowed = regime.get("new_positions_allowed", True)

    actions = {
        "offensive": "市场积极，可正常操作",
        "constructive": "市场偏积极，可适当加仓",
        "neutral": "市场中性，控制节奏",
        "cautious": "市场谨慎，建议减仓至60%以下",
        "defensive": "市场防御，建议降至25%以下仓位，避免新仓",
    }

    print(f"\n市场风险预警 ({market})")
    print(f"  状态: {label} (score={score:.1f}/100)")
    print(f"  风险预算: {risk_budget:.0%}")
    print(f"  建议: {actions.get(posture, '观望')}")
    print(f"  新开仓: {'允许' if allowed else '不建议'}")
    print()

    technical = regime.get("technical", {}) or {}
    if technical:
        print(
            f"  技术面: 当前={technical.get('current', 'N/A')}, "
            f"MA20={technical.get('ma20', 'N/A')}, "
            f"MA60={technical.get('ma60', 'N/A')}"
        )

    for reason in regime.get("reasons", [])[:5]:
        print(f"  - {reason}")

    alert_data = {
        "market": market,
        "posture": posture,
        "posture_label": label,
        "score": score,
        "risk_budget": risk_budget,
        "new_positions_allowed": allowed,
        "suggested_action": actions.get(posture, "观望"),
        "technical": technical,
        "reasons": regime.get("reasons", [])[:5],
    }
    md = f"# 市场风险预警 ({market})\n\n"
    md += f"- 状态: {label} (score={score:.1f}/100)\n"
    md += f"- 风险预算: {risk_budget:.0%}\n"
    md += f"- 建议: {actions.get(posture, '观望')}\n"
    md += f"- 新开仓: {'允许' if allowed else '不建议'}\n"
    _save_report(
        f"risk_alert_{market}",
        fmt,
        output_dir,
        data=alert_data,
        md=md,
        metadata={"command": "risk-alert", "market": market},
    )


def main() -> None:
    from cli import build_parser

    parser = build_parser(
        cmd_route=cmd_route,
        cmd_workflow=cmd_workflow,
        cmd_scorecard=cmd_scorecard,
        cmd_thesis=cmd_thesis,
        cmd_theme_scan=cmd_theme_scan,
        cmd_analyze=cmd_analyze,
        cmd_diagnose=cmd_diagnose,
        cmd_deep_diagnose=cmd_deep_diagnose,
        cmd_scan=cmd_scan,
        cmd_refresh_scan=cmd_refresh_scan,
        cmd_portfolio=cmd_portfolio,
        cmd_market_regime=cmd_market_regime,
        cmd_risk_alert=cmd_risk_alert,
        cmd_fetch=cmd_fetch,
        cmd_sync=cmd_sync,
        cmd_status=cmd_status,
        cmd_alpha=cmd_alpha,
        cmd_backtest=cmd_backtest,
        cmd_backtest_enhanced=cmd_backtest_enhanced,
        cmd_portfolio_enhanced=cmd_portfolio_enhanced,
        cmd_scheduler=cmd_scheduler,
        cmd_cache=cmd_cache,
        cmd_track=cmd_track,
    )
    args = parser.parse_args()
    args.func(args)


def cmd_track(args: argparse.Namespace) -> None:
    """Manage portfolio stop-loss/take-profit tracking."""
    action = getattr(args, "action", "")
    output_dir, fmt = _cmd_output(args)

    if action == "start":
        code = args.code
        market = getattr(args, "market", "A") or "A"
        price = getattr(args, "price", 0) or 0
        stop_loss = (getattr(args, "stop_loss", 15) or 15) / 100.0
        take_profit = (getattr(args, "take_profit", 30) or 30) / 100.0
        notes = getattr(args, "notes", "") or ""

        from tracker import start_tracking
        record = start_tracking(code, market, price, stop_loss, take_profit, notes)

        print(f"开始跟踪: {record['code']} ({record['market']})")
        print(f"  跟踪ID: {record['tracking_id']}")
        print(f"  买入价: {record['entry_price']}")
        print(f"  止损价: {record['stop_loss_price']} ({record['stop_loss_pct']:.0%})")
        print(f"  止盈价: {record['take_profit_price']} ({record['take_profit_pct']:.0%})")
        print(f"  日期: {record['entry_date']}")
        if notes:
            print(f"  备注: {notes}")

        if fmt != "none":
            _save_report(
                f"track_start_{record['tracking_id']}",
                fmt,
                output_dir,
                data=record,
                metadata={"command": "track-start", "code": code},
            )
        return

    if action == "status":
        from tracker import list_trackings
        status_filter = getattr(args, "status", "active") or "active"
        market = getattr(args, "market", "A") or "A"
        trackings = list_trackings(status_filter)
        trackings = [t for t in trackings if t.get("market") == market]

        if not trackings:
            print(f"无跟踪记录 ({market}, {status_filter})")
            return

        print(f"跟踪记录 ({market}, {status_filter}, 共{len(trackings)}条):")
        for t in trackings:
            pnl_str = ""
            if t.get("pnl_pct") is not None:
                pnl_str = f" | 盈亏={t['pnl_pct']:+.2f}%"
            elif t.get("status") == "closed" and t.get("exit_pnl_pct") is not None:
                pnl_str = f" | 已平仓 盈亏={t['exit_pnl_pct']:+.2f}%"
            alert_str = f" | ⚠️ {t['alert']}" if t.get("alert") else ""
            print(
                f"  [{t['tracking_id']}] {t['code']}: 买入价={t['entry_price']}"
                f" | 止损={t['stop_loss_price']} | 止盈={t['take_profit_price']}"
                f"{pnl_str}{alert_str}"
            )

        if fmt != "none":
            _save_report(
                "track_status",
                fmt,
                output_dir,
                data={"trackings": trackings},
                metadata={"command": "track-status", "market": market},
            )
        return

    if action == "check":
        from tracker import check_trackings
        market = getattr(args, "market", "A") or "A"
        days = getattr(args, "days", 5) or 5

        print(f"检查持仓预警 ({market})...")
        alerts = check_trackings(market, days)

        if not alerts:
            print("  无活跃跟踪")
            return

        triggered = [a for a in alerts if a.get("alert")]
        print(f"  共 {len(alerts)} 个持仓:")
        for a in alerts:
            price_str = f"当前价={a['last_price']}" if a.get("last_price") else "价格未知"
            pnl_str = ""
            if a.get("pnl_pct") is not None:
                pnl_str = f" | 盈亏={a['pnl_pct']:+.2f}%"
            alert_str = f" | ⚠️ {a['alert']}" if a.get("alert") else " | 正常"
            print(f"    {a['code']}: {price_str}{pnl_str}{alert_str}")

        if triggered:
            print(f"\n  ⚠️ {len(triggered)} 个持仓触发预警!")
            for a in triggered:
                advice = "止损离场" if "止损" in str(a["alert"]) else "止盈减仓"
                print(f"    {a['code']}: {a['alert']} (建议: {advice})")

        if fmt != "none":
            _save_report(
                "track_check",
                fmt,
                output_dir,
                data={"alerts": alerts},
                metadata={"command": "track-check", "market": market},
            )
        return

    if action == "close":
        from tracker import close_tracking
        tid = args.tracking_id
        price = getattr(args, "price", 0) or 0
        notes = getattr(args, "notes", "") or ""

        result = close_tracking(tid, price, notes)
        if result:
            print(f"已平仓: {result['code']} (跟踪ID: {tid})")
            if price > 0:
                print(f"  平仓价: {price}")
                if result.get("exit_pnl_pct") is not None:
                    print(f"  盈亏: {result['exit_pnl_pct']:+.2f}%")
            if notes:
                print(f"  备注: {notes}")
        else:
            print(f"未找到跟踪记录: {tid}", file=sys.stderr)
        return

    print(f"Unknown track action: {action}", file=sys.stderr)


if __name__ == "__main__":
    main()
