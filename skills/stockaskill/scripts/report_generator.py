"""Report generator for stock selection system.

Provides consistent file-saving and formatting for all analysis outputs.
Reports saved as JSON + Markdown with timestamped filenames.

Usage:
    from report_generator import save_report, ReportMetadata
    md = ReportMetadata(command="analyze", market="A")
    report = save_report(data, "analyze", metadata=asdict(md))
    print(f"Report saved to {report['json_path']}")
"""

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"


@dataclass
class ReportMetadata:
    """Structured metadata for analysis reports.

    Provides a typed contract for report metadata,
    ensuring consistent field names across all reports.
    """

    command: str = ""
    market: str = ""
    top_n: int = 0
    engine: str = ""
    extra: Optional[Dict[str, Any]] = None


def _ensure_dir(output_dir: str) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    return output_dir


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H%M")


def report_filename(title: str, ext: str, output_dir: str = "reports") -> str:
    """Generate a timestamped report filename."""
    _ensure_dir(output_dir)
    ts = _timestamp()
    return os.path.join(output_dir, f"{ts}_{title}.{ext}")


def save_json(data: Any, title: str, output_dir: str = "reports") -> str:
    """Save data as a JSON report file."""
    path = report_filename(title, "json", output_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"  JSON report: {path}")
    return path


def save_markdown(text: str, title: str, output_dir: str = "reports") -> str:
    """Save text as a Markdown report file."""
    path = report_filename(title, "md", output_dir)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  Markdown report: {path}")
    return path


def save_report(
    data: Dict[str, Any],
    report_type: str,
    output_dir: str = "reports",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Save a structured report (JSON) with optional metadata wrapper."""
    wrapped: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_type": report_type,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if metadata:
        wrapped["metadata"] = metadata
    wrapped["data"] = data

    json_path = save_json(wrapped, report_type, output_dir)
    return {"json_path": json_path, "md_path": ""}


def format_score_table(headers: List[str], rows: List[List[str]]) -> str:
    """Format a markdown score table with aligned columns."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def format_scan_results(results: List[Dict[str, Any]]) -> str:
    """Format scan results as a human-readable Markdown table."""
    if not results:
        return "*(No results)*"
    headers = ["排名", "代码", "名称", "得分", "信号"]
    rows = []
    for i, r in enumerate(results, 1):
        score = r.get("total_score", 0)
        signal = r.get("signal", r.get("f_score", "—"))
        rows.append(
            [
                str(i),
                r.get("code", "?"),
                r.get("name", "?"),
                f"{score:.1f}" if isinstance(score, (int, float)) else str(score),
                str(signal),
            ]
        )
    return format_score_table(headers, rows)


def format_portfolio_summary(
    name: str,
    capital: float,
    positions: List[Dict[str, Any]],
    metrics: Optional[Dict[str, float]] = None,
    regime: Optional[Dict[str, Any]] = None,
) -> str:
    """Format portfolio summary as Markdown."""
    lines = [f"# Portfolio: {name}", "", f"**Capital:** {capital:,.0f}", ""]
    total_pct = sum(p.get("weight", 0) * 100 for p in positions)
    lines.append(f"**Allocated:** {total_pct:.1f}%")
    if regime:
        lines.append(
            f"**Market posture:** {regime.get('posture_label', '中性')} "
            f"(score={float(regime.get('score', 50) or 50):.1f}, "
            f"risk_budget={float(regime.get('risk_budget', 1.0) or 1.0):.2f})"
        )
        lines.append(
            f"**New positions allowed:** "
            f"{'yes' if regime.get('new_positions_allowed') else 'no'}"
        )
    lines.append(f"**Positions:** {len(positions)}")
    lines.append("")
    if positions:
        lines.append("| Code | Name | Weight | Shares | Price |")
        lines.append("|------|------|-------:|------:|------:|")
        for p in positions:
            code = p.get("code", "?")
            name = p.get("name", "")
            wt = p.get("weight", 0) * 100
            shares = p.get("shares", 0)
            price = p.get("cost", 0)
            lines.append(f"| {code} | {name} | {wt:.1f}% | {shares} | {price:.2f} |")
    if metrics:
        lines.append("")
        lines.append("## Risk Metrics")
        for k, v in metrics.items():
            lines.append(f"- **{k}:** {v:.4f}")
    lines.append("")
    return "\n".join(lines)


def format_market_regime_summary(regime: Dict[str, Any]) -> str:
    """Format market-regime analysis as Markdown."""
    lines = [f"# Market Regime: {regime.get('market', '?')}", ""]
    lines.append(f"**Posture:** {regime.get('posture_label', '中性')}")
    lines.append(f"**Score:** {float(regime.get('score', 50) or 50):.1f}/100")
    lines.append(f"**Risk budget:** {float(regime.get('risk_budget', 1.0) or 1.0):.2f}")
    lines.append(
        f"**New positions allowed:** "
        f"{'yes' if regime.get('new_positions_allowed') else 'no'}"
    )
    lines.append("")

    technical = regime.get("technical", {}) or {}
    if technical:
        lines.append("## Technical")
        lines.append(
            f"- Current / MA20 / MA60 / MA120: "
            f"{technical.get('current', 'N/A')} / "
            f"{technical.get('ma20', 'N/A')} / "
            f"{technical.get('ma60', 'N/A')} / "
            f"{technical.get('ma120', 'N/A')}"
        )
        lines.append(
            f"- 20D Return: {float(technical.get('ret20', 0) or 0) * 100:.2f}%"
        )
        lines.append(
            f"- 60D Drawdown: {float(technical.get('drawdown60', 0) or 0) * 100:.2f}%"
        )
        lines.append(
            f"- Volatility20: {float(technical.get('volatility20', 0) or 0) * 100:.2f}%"
        )
        lines.append("")

    breadth = regime.get("breadth", {}) or {}
    if breadth:
        lines.append("## Breadth")
        lines.append(
            f"- Sample size: {breadth.get('sample_size', 0)} / "
            f"{breadth.get('sample_limit', 0)}"
        )
        lines.append(
            "- Above MA20: "
            f"{float(breadth.get('above_ma20_ratio', 0.5) or 0.5) * 100:.1f}%"
        )
        lines.append(
            "- Above MA60: "
            f"{float(breadth.get('above_ma60_ratio', 0.5) or 0.5) * 100:.1f}%"
        )
        lines.append("")

    reasons = regime.get("reasons", []) or []
    if reasons:
        lines.append("## Reasons")
        for reason in reasons:
            lines.append(f"- {reason}")
        lines.append("")

    extra = format_confidence_provenance(
        regime.get("confidence", {}),
        regime.get("provenance", {}),
    )
    if extra:
        lines.append(extra)

    return "\n".join(lines)


def format_diagnosis_summary(report: Dict[str, Any]) -> str:
    """Format diagnosis report as a concise Markdown summary."""
    lines = []
    decision = report.get("final_decision", {})
    signal = decision.get("signal", "HOLD")
    score = decision.get("adjusted_score", 50)
    lines.append(
        f"# Diagnosis: {report.get('code', '?')} ({report.get('market', '?')})"
    )
    lines.append("")
    lines.append(f"**Signal:** {signal} | **Score:** {score:.1f}/100")
    lines.append("")
    confidence_block = format_confidence_provenance(
        report.get("confidence", {}),
        report.get("provenance", {}),
    )
    if confidence_block:
        lines.append(confidence_block)

    factors = report.get("factors", {})
    if factors:
        lines.append("## Factors")
        lines.append("| Factor | Score |")
        lines.append("|--------|------:|")
        for k, v in factors.get("factors", {}).items():
            if isinstance(v, (int, float)):
                lines.append(f"| {k} | {v:.1f} |")
    lines.append("")

    tech = report.get("technical", {})
    if tech and tech.get("status") != "insufficient_data":
        lines.append("## Technical")
        lines.append(f"- Trend: {tech.get('trend', 'N/A')}")
        lines.append(f"- RSI(14): {tech.get('rsi_14', 'N/A')}")
        lines.append(f"- Support: {tech.get('support_20d', 'N/A')}")
        lines.append(f"- Resistance: {tech.get('resistance_20d', 'N/A')}")
    lines.append("")

    risks = report.get("risks", {})
    if risks:
        lines.append("## Risks")
        lines.append(f"- Level: {risks.get('risk_level', 'N/A')}")
        for r in risks.get("risks", []):
            lines.append(f"- {r}")
        lines.append("")

    bull_case = decision.get("bull_case", []) or []
    if bull_case:
        lines.append("## Bull Case")
        for item in bull_case:
            lines.append(f"- {item}")
        lines.append("")

    bear_case = decision.get("bear_case", []) or []
    if bear_case:
        lines.append("## Bear Case")
        for item in bear_case:
            lines.append(f"- {item}")
        lines.append("")

    invalidation = decision.get("invalidation_conditions", []) or []
    if invalidation:
        lines.append("## Invalidation")
        for item in invalidation:
            lines.append(f"- {item}")

    lines.append("")
    if decision.get("stop_loss"):
        lines.append(f"**Stop-loss:** {decision['stop_loss']}")
    if decision.get("take_profit"):
        lines.append(f"**Take-profit:** {decision['take_profit']}")
    lines.append("")
    return "\n".join(lines)


def format_deep_diagnosis_summary(report: Dict[str, Any]) -> str:
    """Format a long-form deep diagnosis report as Markdown."""
    lines = [
        f"# Deep Diagnosis: {report.get('code', '?')} ({report.get('market', '?')})",
        "",
        f"**Mode:** {report.get('mode', 'deep-diagnose')}",
        "",
        "## Executive Summary",
        str(report.get("executive_summary", "")),
        "",
    ]
    decision = report.get("final_decision", {}) or {}
    if decision:
        lines.append(
            f"**Signal / Score:** {decision.get('signal', 'HOLD')} / "
            f"{float(decision.get('adjusted_score', 50) or 50):.1f}"
        )
        lines.append("")

    confidence_block = format_confidence_provenance(
        report.get("confidence", {}),
        report.get("provenance", {}),
    )
    if confidence_block:
        lines.append(confidence_block)

    variant = report.get("variant_perception", {}) or {}
    if variant:
        lines.append("## Variant Perception")
        if variant.get("summary"):
            lines.append(str(variant.get("summary")))
        for item in variant.get("market_misread", []) or []:
            lines.append(f"- 市场可能误读: {item}")
        for item in variant.get("what_has_to_be_true", []) or []:
            lines.append(f"- 这笔判断成立的前提: {item}")
        lines.append("")

    evidence = report.get("supporting_evidence", []) or []
    if evidence:
        lines.append("## Supporting Evidence")
        lines.append("| Category | Strength | Detail |")
        lines.append("|---|---|---|")
        for item in evidence:
            lines.append(
                "| "
                f"{item.get('category', '')} | "
                f"{item.get('strength', '')} | "
                f"{item.get('detail', '')} |"
            )
        lines.append("")

    conflicts = report.get("conflict_matrix", []) or []
    if conflicts:
        lines.append("## Conflict Matrix")
        lines.append("| Topic | Bull | Bear | Status | Implication |")
        lines.append("|---|---|---|---|---|")
        for item in conflicts:
            lines.append(
                "| "
                f"{item.get('topic', '')} | "
                f"{item.get('bull', '')} | "
                f"{item.get('bear', '')} | "
                f"{item.get('status', '')} | "
                f"{item.get('implication', '')} |"
            )
        lines.append("")

    bear_case = report.get("bear_case", []) or []
    if bear_case:
        lines.append("## Bear Case")
        for item in bear_case:
            lines.append(f"- {item}")
        lines.append("")

    invalidation = report.get("invalidation_conditions", []) or []
    if invalidation:
        lines.append("## Invalidation")
        for item in invalidation:
            lines.append(f"- {item}")
        lines.append("")

    next_checks = report.get("next_checks", []) or []
    if next_checks:
        lines.append("## Next Checks")
        for item in next_checks:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def format_backtest_summary(result: Dict[str, Any]) -> str:
    """Format backtest results as Markdown."""
    lines = ["# Backtest Results", ""]
    lines.append("| Metric | Value |")
    lines.append("|--------|------:|")
    for k, v in result.items():
        if isinstance(v, float):
            if "cagr" in k or "return" in k or "drawdown" in k:
                lines.append(f"| {k} | {v * 100:.2f}% |")
            else:
                lines.append(f"| {k} | {v:.4f} |")
        else:
            lines.append(f"| {k} | {v} |")
    lines.append("")
    return "\n".join(lines)


def format_scorecard(scorecard: Dict[str, Any]) -> str:
    """Format a generic scorecard block as Markdown."""
    if not scorecard:
        return ""
    lines = [
        "## Scorecard",
        f"- Name: {scorecard.get('name', 'scorecard')}",
        f"- Score: {float(scorecard.get('score', 0) or 0):.1f}/100",
        f"- Level: {scorecard.get('level', 'medium')}",
    ]
    if scorecard.get("summary"):
        lines.append(f"- Summary: {scorecard.get('summary')}")
    dimensions = scorecard.get("dimensions", []) or []
    if dimensions:
        lines.append("")
        lines.append("| Dimension | Score | Verdict | Evidence |")
        lines.append("|---|---:|---|---|")
        for item in dimensions:
            evidence = "；".join(item.get("evidence", []) or []) or "-"
            lines.append(
                "| "
                f"{item.get('name', '')} | "
                f"{float(item.get('score', 0) or 0):.1f} | "
                f"{item.get('verdict', '')} | "
                f"{evidence} |"
            )
    strengths = scorecard.get("strengths", []) or []
    if strengths:
        lines.append("")
        lines.append("### Strengths")
        for item in strengths:
            lines.append(f"- {item}")
    gaps = scorecard.get("gaps", []) or []
    if gaps:
        lines.append("")
        lines.append("### Gaps")
        for item in gaps:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def format_attribution(attribution: Dict[str, Any]) -> str:
    """Format a postmortem attribution block as Markdown."""
    if not attribution:
        return ""
    lines = [
        "## Attribution",
        f"- Outcome: {attribution.get('outcome', 'neutral')}",
        f"- Primary Driver: {attribution.get('primary_driver', 'mixed')}",
        f"- Summary: {attribution.get('summary', '')}",
    ]
    positives = attribution.get("positives", []) or []
    if positives:
        lines.append("")
        lines.append("### Positives")
        for item in positives:
            lines.append(f"- {item}")
    negatives = attribution.get("negatives", []) or []
    if negatives:
        lines.append("")
        lines.append("### Negatives")
        for item in negatives:
            lines.append(f"- {item}")
    adjustments = attribution.get("adjustments", []) or []
    if adjustments:
        lines.append("")
        lines.append("### Adjustments")
        for item in adjustments:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def format_thesis_summary(record: Dict[str, Any]) -> str:
    """Format a thesis-memory record as Markdown."""
    lines = [
        f"# Thesis: {record.get('code', '?')} ({record.get('market', '?')})",
        "",
        f"**Thesis ID:** {record.get('thesis_id', '?')}",
        f"**Created At:** {record.get('created_at', '?')}",
        f"**Status:** {record.get('thesis_status', 'active')}",
        f"**Source:** {record.get('source', 'diagnose')}",
        f"**Signal / Score:** {record.get('signal', 'HOLD')} / "
        f"{float(record.get('score', 50) or 50):.1f}",
        "",
        f"**Summary:** {record.get('summary', '')}",
        "",
    ]
    confidence_block = format_confidence_provenance(
        {
            "level": record.get("confidence_level", "medium"),
            "score": record.get("confidence_score", 0.5),
            "notes": [],
        },
        record.get("provenance", {}),
    )
    if confidence_block:
        lines.append(confidence_block)
    scorecard_block = format_scorecard(record.get("scorecard", {}) or {})
    if scorecard_block:
        lines.append(scorecard_block)

    if record.get("notes"):
        lines.append("## Notes")
        lines.append(str(record["notes"]))
        lines.append("")

    bull_case = record.get("bull_case", []) or []
    if bull_case:
        lines.append("## Bull Case")
        for item in bull_case:
            lines.append(f"- {item}")
        lines.append("")

    bear_case = record.get("bear_case", []) or []
    if bear_case:
        lines.append("## Bear Case")
        for item in bear_case:
            lines.append(f"- {item}")
        lines.append("")

    invalidation = record.get("invalidation_conditions", []) or []
    if invalidation:
        lines.append("## Invalidation")
        for item in invalidation:
            lines.append(f"- {item}")
        lines.append("")

    postmortem = record.get("postmortem", {}) or {}
    if postmortem:
        lines.append("## Postmortem")
        lines.append(f"- Outcome: {postmortem.get('outcome', 'unknown')}")
        lines.append(f"- Reviewed At: {postmortem.get('reviewed_at', '?')}")
        lines.append(f"- Thesis Status: {postmortem.get('thesis_status', 'closed')}")
        if postmortem.get("notes"):
            lines.append(f"- Notes: {postmortem.get('notes')}")
        lines.append("")
    attribution_block = format_attribution(record.get("attribution", {}) or {})
    if attribution_block:
        lines.append(attribution_block)

    return "\n".join(lines)


def format_theme_research(report: Dict[str, Any]) -> str:
    """Format a theme-research report as Markdown."""
    lines = [
        f"# Theme Research: {report.get('theme', '?')} ({report.get('market', '?')})",
        "",
        f"**Resolved Theme:** {report.get('resolved_theme', 'custom')}",
        f"**Summary:** {report.get('summary', '')}",
        f"**Key Question:** {report.get('key_question', '')}",
        "",
    ]
    confidence_block = format_confidence_provenance(
        report.get("confidence", {}),
        report.get("provenance", {}),
    )
    if confidence_block:
        lines.append(confidence_block)
    scorecard_block = format_scorecard(report.get("scorecard", {}) or {})
    if scorecard_block:
        lines.append(scorecard_block)

    layers = report.get("layers", []) or []
    if layers:
        lines.append("## Ranked Layers")
        lines.append("| 排名 | 产业链层 | 产业链卡点 | 为什么排这里 |")
        lines.append("|---:|---|---|---|")
        for layer in layers:
            lines.append(
                "| "
                f"{layer.get('rank', 0)} | "
                f"{layer.get('layer', '')} | "
                f"{layer.get('scarce_layer', '')} | "
                f"{layer.get('why_here', '')} |"
            )
        lines.append("")

    for layer in layers:
        lines.append(f"## {layer.get('rank', '?')}. {layer.get('layer', '')}")
        lines.append(f"- 产业链卡点: {layer.get('scarce_layer', '')}")
        for item in layer.get("evidence", []) or []:
            lines.append(f"- 支持证据: {item}")
        for item in layer.get("disconfirming_signals", []) or []:
            lines.append(f"- 反证/降级信号: {item}")
        candidates = layer.get("candidates", []) or []
        if candidates:
            lines.append("")
            lines.append("| 标的 | 为什么排这里 | 主要风险 |")
            lines.append("|---|---|---|")
            for candidate in candidates:
                evidence = "；".join((candidate.get("evidence", []) or [])[:2]) or "-"
                risk = (
                    "；".join(candidate.get("disconfirming_signals", []) or []) or "-"
                )
                lines.append(
                    "| "
                    f"{candidate.get('code', '?')} {candidate.get('name', '')} | "
                    f"{evidence} | {risk} |"
                )
        lines.append("")

    lower_priority = report.get("lower_priority_areas", []) or []
    if lower_priority:
        lines.append("## Lower Priority")
        for item in lower_priority:
            lines.append(f"- {item}")
        lines.append("")

    next_checks = report.get("next_checks", []) or []
    if next_checks:
        lines.append("## Next Checks")
        for item in next_checks:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def format_workflow_run_summary(report: Dict[str, Any]) -> str:
    """Format a manifest-based workflow plan as Markdown."""
    lines = [
        f"# Workflow Run: {report.get('name', '?')}",
        "",
        f"**Market:** {report.get('market', '?')}",
        f"**Manifest:** {report.get('manifest_path', '')}",
        f"**Summary:** {report.get('summary', '')}",
        "",
    ]
    if report.get("description"):
        lines.append(str(report.get("description")))
        lines.append("")

    context = report.get("context", {}) or {}
    if context:
        lines.append("## Context")
        for key in sorted(context):
            lines.append(f"- {key}: {context.get(key)}")
        lines.append("")

    missing_params = report.get("missing_params", []) or []
    if missing_params:
        lines.append("## Missing Params")
        for item in missing_params:
            lines.append(f"- {item}")
        lines.append("")

    steps = report.get("steps", []) or []
    if steps:
        lines.append("## Steps")
        for idx, step in enumerate(steps, 1):
            lines.append(f"### {idx}. {step.get('title', 'step')}")
            lines.append(f"- Command: `{step.get('command', '')}`")
            lines.append(f"- Purpose: {step.get('purpose', '')}")
            if step.get("artifact"):
                lines.append(f"- Artifact: {step.get('artifact', '')}")
            if step.get("when"):
                lines.append(f"- When: {step.get('when', '')}")
            lines.append("")

    notes = report.get("notes", []) or []
    if notes:
        lines.append("## Notes")
        for item in notes:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def format_confidence_provenance(
    confidence: Dict[str, Any] | None,
    provenance: Dict[str, Any] | None,
) -> str:
    """Format a shared confidence/provenance block."""
    lines: List[str] = []
    confidence = confidence or {}
    provenance = provenance or {}
    if confidence:
        lines.append("## Confidence")
        lines.append(
            f"- Level: {confidence.get('level', 'medium')} "
            f"({float(confidence.get('score', 0.5) or 0.5):.2f})"
        )
        for note in confidence.get("notes", [])[:4]:
            lines.append(f"- {note}")
        lines.append("")
    if provenance:
        lines.append("## Provenance")
        if provenance.get("scope"):
            lines.append(f"- Scope: {provenance.get('scope')}")
        if provenance.get("source"):
            lines.append(f"- Source: {provenance.get('source')}")
        if provenance.get("source_status"):
            lines.append(f"- Source Status: {provenance.get('source_status')}")
        if provenance.get("covered_through"):
            lines.append(
                f"- Covered Through: {provenance.get('covered_through')} "
                f"({provenance.get('freshness', 'unknown')})"
            )
        elif provenance.get("freshness"):
            lines.append(f"- Freshness: {provenance.get('freshness')}")
        if provenance.get("metadata_completeness", None) is not None:
            lines.append(
                "- Metadata Completeness: "
                f"{float(provenance.get('metadata_completeness', 0) or 0):.2f}"
            )
        inputs = provenance.get("inputs", []) or []
        if inputs:
            lines.append(f"- Inputs: {', '.join(str(item) for item in inputs)}")
        lines.append("")
    return "\n".join(lines)
