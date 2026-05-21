#!/usr/bin/env python3
"""Sync root entry point files into .gemini/rules/ so Gemini CLI sees the canonical versions.

Gemini CLI only reads files inside .gemini/ — it cannot follow ../ references.
This script force-copies the 5 root entry points into .gemini/rules/ to prevent
stale duplicates from drifting out of sync.

Run manually or wire into a pre-commit / session-start hook.
"""

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_DIR = REPO_ROOT / ".gemini" / "rules"

# (source relative to repo root, destination name inside .gemini/rules/)
SYNC_MAP = [
    ("CLAUDE.md", "CLAUDE.md"),
    ("GEMINI.md", "GEMINI.md"),
    ("ANTIGRAVITY.md", "ANTIGRAVITY.md"),
    ("AGENTS.md", "AGENTS.md"),
    ("OPENCODE.md", "OPENCODE.md"),
]


def main() -> None:
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    synced = 0
    for src_name, dst_name in SYNC_MAP:
        src = REPO_ROOT / src_name
        if not src.exists():
            print(f"  SKIP: {src_name} (not found)")
            continue
        dst = RULES_DIR / dst_name
        shutil.copy2(src, dst)
        synced += 1
        print(f"  SYNC: {src_name} -> .gemini/rules/{dst_name}")
    print(f"\nDone. {synced}/{len(SYNC_MAP)} files synced to .gemini/rules/")


if __name__ == "__main__":
    main()
