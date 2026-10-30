"""CLI command handlers for thesis functionality."""

import argparse
import sys

from config import get as cfg_get
from report_generator import format_thesis_summary
from thesis_memory import (
    build_thesis_record,
    check_active_theses,
    get_thesis_record,
    list_thesis_records,
    save_thesis_record,
    update_thesis_postmortem,
)
from utils import normalize_code_for_market

from commands._common import _cmd_output, _save_report


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

    if action == "check":
        code = (
            normalize_code_for_market(args.code, market)
            if getattr(args, "code", "")
            else ""
        )
        auto_close = getattr(args, "auto_close", False)
        target_m = market or "ALL"
        print(
            f"Checking active theses against invalidation criteria "
            f"(market={target_m})..."
        )
        results = check_active_theses(
            market=market if getattr(args, "market", "") else "",
            code=code,
            auto_close=auto_close,
        )
        if not results:
            print("No active thesis records found.")
            return

        print(f"Active Thesis Health Status ({len(results)}):")
        for idx, item in enumerate(results, 1):
            close_info = " [AUTO-CLOSED]" if item.get("auto_closed") else ""
            c_code = item["code"]
            c_mkt = item["market"]
            c_st = item["status"]
            c_sig = item["signal"]
            c_entry = item["entry_price"]
            c_now = item["latest_price"]
            c_pnl = item["pnl_pct"]
            c_ma = item["ma20"]
            print(
                f"  {idx}. [{c_st}]{close_info} {c_code} ({c_mkt}) | "
                f"{c_sig} | Entry: {c_entry:.2f} -> Current: {c_now:.2f} "
                f"({c_pnl:+.2f}%) | MA20: {c_ma:.2f}"
            )
            print(f"     Diagnosis: {item['reason']}")
            rules = item.get("invalidation_conditions", [])
            if rules:
                rule_text = ", ".join(rules[:2])
                print(f"     Invalidation Rules: {rule_text}")

        _save_report(
            "thesis_check",
            fmt,
            output_dir,
            data={"results": results},
            metadata={"command": "thesis-check", "market": market},
        )
        return

    print(f"Unknown thesis action: {action}")



