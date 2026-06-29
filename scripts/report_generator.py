"""Report generator for stock selection system.

Provides consistent file-saving and formatting for all analysis outputs.
Reports saved as JSON + Markdown with timestamped filenames.

Usage:
    from report_generator import save_report
    report = save_report(data, "analyze", code="600519", market="A")
    print(f"Report saved to {report['json_path']}")
"""

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"


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
    print(f"  JSON report: {path}", file=sys.stderr)
    return path


def save_markdown(text: str, title: str, output_dir: str = "reports") -> str:
    """Save text as a Markdown report file."""
    path = report_filename(title, "md", output_dir)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  Markdown report: {path}", file=sys.stderr)
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
        rows.append([
            str(i),
            r.get("code", "?"),
            r.get("name", "?"),
            f"{score:.1f}" if isinstance(score, (int, float)) else str(score),
            str(signal),
        ])
    return format_score_table(headers, rows)


def format_portfolio_summary(
    name: str,
    capital: float,
    positions: List[Dict[str, Any]],
    metrics: Optional[Dict[str, float]] = None,
) -> str:
    """Format portfolio summary as Markdown."""
    lines = [f"# Portfolio: {name}", "", f"**Capital:** {capital:,.0f}", ""]
    total_pct = sum(p.get("weight", 0) * 100 for p in positions)
    lines.append(f"**Allocated:** {total_pct:.1f}%")
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


def format_diagnosis_summary(report: Dict[str, Any]) -> str:
    """Format diagnosis report as a concise Markdown summary."""
    lines = []
    decision = report.get("final_decision", {})
    signal = decision.get("signal", "HOLD")
    score = decision.get("adjusted_score", 50)
    lines.append(f"# Diagnosis: {report.get('code', '?')} ({report.get('market', '?')})")
    lines.append("")
    lines.append(f"**Signal:** {signal} | **Score:** {score:.1f}/100")
    lines.append("")

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
    if decision.get("stop_loss"):
        lines.append(f"**Stop-loss:** {decision['stop_loss']}")
    if decision.get("take_profit"):
        lines.append(f"**Take-profit:** {decision['take_profit']}")
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
