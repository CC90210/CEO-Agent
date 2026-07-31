#!/usr/bin/env python3
"""Audit broken Obsidian [[wikilinks]] in brain/ and memory/ directories.

SUPERSEDED (2026-07-28) by `scripts/obsidian_graph_doctor.py`. Kept working for
any existing caller, but do not trust its output for a clean-graph claim:

  * It resolves links repo-root-relative only. Obsidian resolves by BASENAME
    anywhere in the vault, so `[[QUICK_REFERENCE]]` is reported broken here
    while Obsidian resolves it fine  -> false positives.
  * It scans brain/ and memory/ only, and ignores `.obsidian/app.json`
    userIgnoreFilters, so links into vault-excluded dirs (`.claude/`, `tmp/`)
    look fine here and are red in Obsidian  -> false negatives.
  * It has no orphan, weak-node, or frontmatter detection.

Measured on this repo the same day: this script reported 20 broken links; the
doctor found 85 real ones across the whole vault. Use the doctor.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKILINK_RE = re.compile(r"\[\[(.*?)\]\]")
SCAN_DIRS = ["brain", "memory"]
IGNORED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".mp3", ".mp4", ".wav"}


def resolve_target(link_text: str, repo_root: Path) -> Path | None:
    """Resolve a wikilink target to an absolute path, ignoring anchors."""
    target = link_text.strip()
    if not target:
        return None

    # Strip anchor
    target = target.split("#")[0].strip()
    if not target:
        return None

    # Skip images / binary
    ext = Path(target).suffix.lower()
    if ext in IGNORED_EXTENSIONS:
        return None

    candidate = repo_root / target
    # 1. Direct path check
    if candidate.is_dir():
        return candidate
    if not candidate.suffix:
        candidate = candidate.with_suffix(".md")
    if candidate.is_file():
        return candidate

    return candidate


def audit() -> dict[str, list[tuple[str, Path]]]:
    """Return {source_file: [(broken_link_text, resolved_path), ...]}."""
    broken: dict[str, list[tuple[str, Path]]] = defaultdict(list)

    for scan_dir in SCAN_DIRS:
        dir_path = REPO_ROOT / scan_dir
        if not dir_path.is_dir():
            continue
        for md_file in sorted(dir_path.rglob("*.md")):
            content = md_file.read_text(encoding="utf-8", errors="replace")
            # Strip code blocks to avoid false positives
            content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
            content = re.sub(r"`.*?`", "", content)
            
            for match in WIKILINK_RE.finditer(content):
                raw = match.group(1)
                resolved = resolve_target(raw, REPO_ROOT)
                if resolved is None:
                    continue
                if not resolved.exists():
                    rel_source = md_file.relative_to(REPO_ROOT)
                    broken[str(rel_source)].append((raw, resolved))

    return broken


def main() -> None:
    broken = audit()
    if not broken:
        print("No broken wikilinks found.")
        return

    total_broken = sum(len(v) for v in broken.values())
    print(f"Found {total_broken} broken wikilink(s) across {len(broken)} file(s).\n")

    # Sort by count descending
    sorted_files = sorted(broken.items(), key=lambda x: len(x[1]), reverse=True)

    print("=== TOP FILES BY BROKEN LINK COUNT ===\n")
    for i, (src, links) in enumerate(sorted_files[:3], 1):
        print(f"  #{i}: {src}  ({len(links)} broken links)")

    print("\n=== FULL BREAKDOWN ===\n")
    for src, links in sorted_files:
        print(f"--- {src} ({len(links)} broken) ---")
        seen: set[str] = set()
        for raw, resolved in links:
            if resolved not in seen:
                print(f"  [[{raw}]]  ->  {resolved.relative_to(REPO_ROOT)}")
                seen.add(resolved)
            else:
                print(f"  [[{raw}]]  ->  (duplicate target)")
        print()


if __name__ == "__main__":
    main()
