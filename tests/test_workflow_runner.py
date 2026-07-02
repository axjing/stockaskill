from pathlib import Path


def test_list_workflow_manifests_includes_builtins():
    from workflow_runner import list_workflow_manifests

    names = list_workflow_manifests()

    assert "market-regime-daily" in names
    assert "portfolio-review-weekly" in names
    assert "theme-research-weekly" in names


def test_build_workflow_run_plan_applies_defaults_and_substitutions():
    from workflow_runner import build_workflow_run_plan

    plan = build_workflow_run_plan(
        "market-regime-daily",
        market="US",
        top=5,
    )

    payload = plan.to_dict()
    assert payload["market"] == "US"
    assert payload["missing_params"] == []
    assert payload["steps"][0]["command"].endswith("--market US")
    assert "scan US --top 5" in payload["steps"][1]["command"]


def test_build_workflow_run_plan_marks_missing_required_params():
    from workflow_runner import build_workflow_run_plan

    plan = build_workflow_run_plan("portfolio-review-weekly", market="A")

    payload = plan.to_dict()
    assert "codes" in payload["missing_params"]
    assert "{codes}" in payload["steps"][2]["command"]


def test_load_workflow_manifest_raises_for_missing_name(tmp_path: Path):
    from workflow_runner import load_workflow_manifest

    empty_dir = tmp_path / "workflows"
    empty_dir.mkdir()

    try:
        load_workflow_manifest("missing", workflows_dir=empty_dir)
    except FileNotFoundError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError")
