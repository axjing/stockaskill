"""Manifest-based workflow routines for stockaskill."""

import json
from pathlib import Path
from string import Formatter
from typing import Any

from models import WorkflowManifest, WorkflowManifestStep, WorkflowRunPlan


class _SafeFormatDict(dict):
    """Format-map dict that preserves missing placeholders."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _default_workflows_dir() -> Path:
    """Return the repository workflow-manifest directory."""
    return Path(__file__).resolve().parent.parent / "workflows"


def list_workflow_manifests(workflows_dir: Path | None = None) -> list[str]:
    """List available workflow manifest names."""
    base_dir = workflows_dir or _default_workflows_dir()
    return sorted(path.stem for path in base_dir.glob("*.yaml"))


def load_workflow_manifest(
    name: str,
    workflows_dir: Path | None = None,
) -> WorkflowManifest:
    """Load one workflow manifest from disk.

    Args:
        name: Manifest stem without `.yaml`.
        workflows_dir: Optional manifest directory override.

    Returns:
        Parsed workflow manifest.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        ValueError: If the manifest schema is invalid.
    """
    base_dir = workflows_dir or _default_workflows_dir()
    path = base_dir / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Workflow manifest not found: {name}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    steps = [
        WorkflowManifestStep(
            title=str(item.get("title", "")),
            command=str(item.get("command", "")),
            purpose=str(item.get("purpose", "")),
            artifact=str(item.get("artifact", "")),
            when=str(item.get("when", "")),
        )
        for item in (payload.get("steps", []) or [])
    ]
    if not payload.get("name") or not steps:
        raise ValueError(f"Invalid workflow manifest: {name}")

    return WorkflowManifest(
        name=str(payload.get("name", name)),
        summary=str(payload.get("summary", "")),
        description=str(payload.get("description", "")),
        defaults=dict(payload.get("defaults", {}) or {}),
        required_params=[
            str(item).strip()
            for item in (payload.get("required_params", []) or [])
            if str(item).strip()
        ],
        steps=steps,
        notes=[str(item) for item in (payload.get("notes", []) or [])],
        tags=[str(item) for item in (payload.get("tags", []) or [])],
    )


def build_workflow_run_plan(
    name: str,
    market: str = "A",
    code: str = "",
    codes: str = "",
    theme: str = "",
    top: int = 10,
    capital: float = 1_000_000,
    workflows_dir: Path | None = None,
) -> WorkflowRunPlan:
    """Resolve a manifest into a runnable plan with concrete parameters."""
    manifest = load_workflow_manifest(name, workflows_dir=workflows_dir)
    context = dict(manifest.defaults)
    context.update(
        {
            "market": market or str(context.get("market", "A") or "A"),
            "code": code.strip(),
            "codes": codes.strip(),
            "theme": theme.strip(),
            "top": int(top or context.get("top", 10) or 10),
            "capital": int(capital or context.get("capital", 1_000_000) or 1_000_000),
        }
    )

    missing_params = sorted(
        {
            param
            for param in manifest.required_params
            if not str(context.get(param, "")).strip()
        }
    )
    format_context = _SafeFormatDict(context)
    for item in missing_params:
        format_context[item] = "{" + item + "}"
    rendered_steps = [
        WorkflowManifestStep(
            title=step.title.format_map(format_context),
            command=step.command.format_map(format_context),
            purpose=step.purpose.format_map(format_context),
            artifact=step.artifact.format_map(format_context),
            when=step.when.format_map(format_context),
        )
        for step in manifest.steps
    ]

    auto_missing = sorted(
        {
            field_name
            for step in rendered_steps
            for template in (step.title, step.command, step.purpose, step.artifact)
            for _, field_name, _, _ in Formatter().parse(template)
            if field_name
        }
    )
    if auto_missing:
        for item in auto_missing:
            if item not in missing_params:
                missing_params.append(item)

    notes = list(manifest.notes)
    if missing_params:
        notes.insert(
            0,
            "缺少必要参数时，命令会保留占位符；先补齐参数再执行对应 step。",
        )

    manifest_path = str((workflows_dir or _default_workflows_dir()) / f"{name}.yaml")
    return WorkflowRunPlan(
        name=manifest.name,
        summary=manifest.summary,
        description=manifest.description,
        market=str(context.get("market", market)),
        manifest_path=manifest_path,
        context=context,
        missing_params=missing_params,
        steps=rendered_steps,
        notes=notes,
        tags=manifest.tags,
    )
