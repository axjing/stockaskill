"""Sync development changes to the deployment directory.

Copies scripts/ from the dev location (D:\CODE\stockaskill\skills\stockaskill)
to the skill deployment location (%USERPROFILE%\.agents\skills\stockaskill).
"""

import os
import shutil
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY_DIR = os.path.join(os.path.expanduser("~"), ".agents", "skills", "stockaskill")

DEV_SCRIPTS = os.path.join(SKILL_DIR, "scripts")
DEPLOY_SCRIPTS = os.path.join(DEPLOY_DIR, "scripts")

DEV_WORKFLOWS = os.path.join(SKILL_DIR, "workflows")
DEPLOY_WORKFLOWS = os.path.join(DEPLOY_DIR, "workflows")

SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
DEPLOY_SKILL_MD = os.path.join(DEPLOY_DIR, "SKILL.md")


def sync_dir(src: str, dst: str, label: str) -> int:
    """Sync all .py files from src to dst, creating dst if needed."""
    if not os.path.isdir(src):
        print(f"[SKIP] {label} source not found: {src}")
        return 0
    os.makedirs(dst, exist_ok=True)

    count = 0
    for root, dirs, files in os.walk(src):
        for f in files:
            if not f.endswith(".py"):
                continue
            src_file = os.path.join(root, f)
            rel = os.path.relpath(src_file, src)
            dst_file = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.copy2(src_file, dst_file)
            count += 1
    print(f"[SYNC] {label}: {count} files copied to {dst}")
    return count


def sync_file(src: str, dst: str, label: str) -> bool:
    """Sync a single file."""
    if not os.path.isfile(src):
        print(f"[SKIP] {label} source not found: {src}")
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    print(f"[SYNC] {label}: {src} -> {dst}")
    return True


def main():
    print(f"Dev dir:      {SKILL_DIR}")
    print(f"Deploy dir:   {DEPLOY_DIR}")
    print()

    total = 0
    total += sync_dir(DEV_SCRIPTS, DEPLOY_SCRIPTS, "scripts")
    total += sync_file(SKILL_MD, DEPLOY_SKILL_MD, "SKILL.md")

    print(f"\nDone. {total} files synced.")


if __name__ == "__main__":
    main()
