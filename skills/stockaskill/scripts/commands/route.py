"""CLI command handlers for route functionality."""

import argparse
import sys

from report_generator import format_workflow_run_summary
from workflow_runner import build_workflow_run_plan, list_workflow_manifests
from workflows import build_workflow_recommendation

from commands._common import _cmd_output, _save_report


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



