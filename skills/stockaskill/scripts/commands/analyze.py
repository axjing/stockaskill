"""CLI command handlers for analyze functionality."""

import argparse
import json
import sys

from data_engine import get_fundamentals, get_kline
from data_readiness import ensure_symbol_analysis_ready
from deep_diagnosis import build_deep_diagnosis
from report_generator import (
    format_deep_diagnosis_summary,
    format_diagnosis_summary,
)

from commands._common import _badge, _cmd_output, _save_report


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



