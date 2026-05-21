#!/usr/bin/env python3
"""
One-shot repair: every Python file moved from scripts/<name>.py into
scripts/<subdir>/<name>.py during the 2026-05-20 reorg kept its
original `Path(__file__).resolve().parent.parent` lookup, which is
now one parent short — it resolves to scripts/ instead of the repo
root. Same with `parents[1]` (one short of `parents[2]`).

This script walks every .py file under scripts/<subdir>/ (one level
below scripts/, e.g. scripts/core/, scripts/browser/, scripts/hooks/,
scripts/contract_generator/, scripts/state/) and replaces:

  Path(__file__).resolve().parent.parent  ->  Path(__file__).resolve().parent.parent.parent
  Path(__file__).resolve().parents[1]     ->  Path(__file__).resolve().parents[2]

Files DIRECTLY under scripts/ (no subdir) are skipped — those have
the correct depth already. Files in scripts/integrations/ were
already fixed by the prior commit and would no-op here but are
harmless to re-process.

Dry-run by default. Pass --apply to write changes.
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
parser = argparse.ArgumentParser(description="Repair stale .env.agents path depth after scripts/ reorg.")
parser.add_argument("--apply", action="store_true", help="Write repaired files. Default is dry-run only.")
args = parser.parse_args()

# Already-fixed pattern (so we don't double-fix) — `parent.parent.parent`
# matches `parent.parent` too via greedy regex, so we anchor with a
# negative lookahead.
PARENT_RE = re.compile(r"\.resolve\(\)\.parent\.parent(?!\.parent)")
PARENTS_RE = re.compile(r"\.resolve\(\)\.parents\[1\]")

changes: list[tuple[Path, int]] = []
skipped: list[Path] = []

for py in SCRIPTS_DIR.rglob("*.py"):
    # Only sweep files in scripts/<subdir>/... — not directly under scripts/
    try:
        rel = py.relative_to(SCRIPTS_DIR)
    except ValueError:
        continue
    if len(rel.parts) < 2:
        skipped.append(py)
        continue
    # Skip __pycache__
    if "__pycache__" in rel.parts:
        continue
    # Skip ourselves
    if py.name == "_repair_subdir_env_paths.py":
        continue
    text = py.read_text(encoding="utf-8")
    new = PARENT_RE.sub(".resolve().parent.parent.parent", text)
    new = PARENTS_RE.sub(".resolve().parents[2]", new)
    if new != text:
        if args.apply:
            py.write_text(new, encoding="utf-8")
        # Count replacements
        diff = len(PARENT_RE.findall(text)) + len(PARENTS_RE.findall(text))
        changes.append((py, diff))

verb = "Repaired" if args.apply else "Would repair"
print(f"{verb} {len(changes)} files:")
for p, n in sorted(changes):
    print(f"  {p.relative_to(REPO_ROOT)} ({n} replacement{'s' if n != 1 else ''})")
print(f"Skipped {len(skipped)} files directly under scripts/ (already correct depth)")
if changes and not args.apply:
    print("Dry run only. Re-run with --apply to write these changes.")
sys.exit(0)
