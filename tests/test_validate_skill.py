from pathlib import Path


def test_validate_skill_detects_backtick_reference_paths(tmp_path: Path):
    skill_dir = tmp_path / "demo-skill"
    refs_dir = skill_dir / "references"
    skill_dir.mkdir()
    refs_dir.mkdir()
    (refs_dir / "existing.md").write_text("# ok\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: demo-skill",
                "description: demo",
                "---",
                "",
                "Load `references/existing.md` and `references/missing.md`.",
            ]
        ),
        encoding="utf-8",
    )

    from validate_skill import validate

    errors = validate(str(skill_dir))

    assert "Reference not found: references/missing.md" in errors
    assert "Reference not found: references/existing.md" not in errors
