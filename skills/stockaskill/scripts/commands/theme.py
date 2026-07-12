"""CLI command handlers for theme functionality."""

import argparse

from report_generator import format_theme_research
from theme_research import build_theme_report

from commands._common import _cmd_output, _save_report


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



