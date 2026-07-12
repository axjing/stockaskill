"""CLI command handlers for scorecard functionality."""

import argparse
import sys

from report_generator import format_scorecard
from scorecards import (
    build_diagnosis_scorecard,
    build_theme_scorecard,
    build_thesis_scorecard,
)
from theme_research import build_theme_report
from thesis_memory import get_thesis_record
from utils import normalize_code_for_market

from commands._common import _cmd_output, _save_report


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



