"""Validate the stockaskill SKILL.md structure and reference files.

Checks:
  - SKILL.md exists and has valid frontmatter
  - name == directory name
  - description is non-empty
  - All reference file paths exist
  - Scripts are importable or PEP 723-compatible
"""

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import argparse
import re
import sys
from pathlib import Path


def _parse_frontmatter(text: str) -> dict | None:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    front = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            front[key.strip()] = val.strip()
    return front


def validate(skill_dir: str = ".") -> list[str]:
    errors: list[str] = []
    root = Path(skill_dir).resolve()
    skill_md = root / "SKILL.md"

    # Check SKILL.md
    if not skill_md.exists():
        errors.append(f"SKILL.md not found in {root}")
        return errors

    text = skill_md.read_text(encoding="utf-8")
    front = _parse_frontmatter(text)
    if front is None:
        errors.append("SKILL.md: missing or invalid YAML frontmatter (must start with ---)")
    else:
        name = front.get("name", "")
        if not name:
            errors.append("SKILL.md: frontmatter 'name' is empty")
        elif name != root.name:
            errors.append(f"SKILL.md: name '{name}' != directory name '{root.name}'")

        if not front.get("description", ""):
            errors.append("SKILL.md: frontmatter 'description' is empty")

    # Check reference file paths ([[ref]] or [text](path) patterns)
    refs = set()
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
        ref_path = m.group(2)
        if ref_path.startswith("http"):
            continue
        refs.add(ref_path)
    for m in re.finditer(r"\[\[([^\]]+)\]\]", text):
        refs.add(m.group(1))

    for ref in sorted(refs):
        ref_file = root / ref
        if not ref_file.exists():
            errors.append(f"Reference not found: {ref}")

    # Check scripts directory
    scripts_dir = root / "scripts"
    if scripts_dir.exists():
        for py_file in sorted(scripts_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            try:
                compile(py_file.read_text(encoding="utf-8"), py_file.name, "exec")
            except SyntaxError as e:
                errors.append(f"Script syntax error: {py_file.name} — {e}")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate stockaskill structure")
    parser.add_argument("dir", nargs="?", default=".", help="Skill directory or '-' for stdin")
    parser.add_argument("--dir", dest="dir_alt", help="(deprecated) use positional arg instead")
    args = parser.parse_args()

    skill_dir = args.dir
    if skill_dir == "-":
        text = sys.stdin.read()
        front = _parse_frontmatter(text)
        if front is None:
            print("FAIL: invalid or missing frontmatter (stdin)")
            sys.exit(1)
        print(f"PASS (stdin): name={front.get('name','?')}, description={front.get('description','?')}")
        return

    errors = validate(skill_dir)
    if errors:
        print(f"FAIL ({len(errors)} issue(s)):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("PASS: all validation checks OK")


if __name__ == "__main__":
    main()
