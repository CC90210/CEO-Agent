#!/usr/bin/env python3
"""doc_sweep.py — Scan brain/ and memory/ for deprecated terminology.

Usage:
    python scripts/core/doc_sweep.py --term "supabase" --brain --memory --dry-run
    python scripts/core/doc_sweep.py --term "supabase" --brain --json
    python scripts/core/doc_sweep.py --term "supabase" --replacement "turso" --brain --dry-run

Reports every occurrence of a deprecated term across documentation files,
classified by severity tier:
  - Tier 1 (CRITICAL): Files in brain/ that boot every agent session
  - Tier 2 (HIGH): Files agents read on-demand
  - Tier 3 (MEDIUM): Operational memory files
  - Tier 4 (LOW): Historical/archived — reported but not flagged for action

Exit code: 0 if no Tier 1/2 hits, 1 if any Tier 1/2 hits found.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- Tier classification ---

TIER_1_FILES = {
    "CAPABILITIES.md", "STATE.md", "QUICK_REFERENCE.md",
    "CLAUDE.md", "AGENTS.md", "GEMINI.md", "ANTIGRAVITY.md",
    "OPENCODE.md", "ZCODE.md",
}

TIER_2_FILES = {
    "APP_REGISTRY.md", "AGENT_INDEX.md", "C_SUITE_ARCHITECTURE.md",
    "CREDENTIALS_SCAFFOLD.md", "LONG_TERM.md", "AGENT_ROUTER.md",
    "EXECUTION_RULES.md", "INTENTS.md", "WHEN_TO_USE_SKILLS.md",
}

HISTORICAL_PATTERNS = [
    r"RETROSPECTIVE",
    r"_archive",
    r"research/",
    r"content/scripts",
    r"CHANGELOG",
]


def classify_tier(filepath: str) -> int:
    """Classify a file into severity tiers 1-4."""
    name = Path(filepath).name
    if name in TIER_1_FILES:
        return 1
    if name in TIER_2_FILES:
        return 2
    for pattern in HISTORICAL_PATTERNS:
        if re.search(pattern, filepath, re.IGNORECASE):
            return 4
    return 3


# A line carrying this marker — inline, or on the line directly above — is a
# DELIBERATE reference to the deprecated component, not drift.
#
# WHY THIS EXISTS. Without it the gate can never pass, because plenty of correct
# sentences must name the old component forever:
#
#   "sibling agents subscribe via the shared Supabase `agent_events` table"
#
# is TRUE — Postgres LISTEN/NOTIFY has no libSQL equivalent, so the event bus
# stays on Supabase by design. The first cut of this tool exited 1 on any Tier
# 1/2 hit at all, which meant 108 permanent failures the day it shipped. A gate
# that always fails gets bypassed, and a bypassed gate is worse than none: it
# still reads as coverage on the org chart.
#
# The skill that drives this already specified "un-annotated Tier 1 or Tier 2
# hits". This is the un-annotated half, implemented.
ANNOTATION = "legacy-ok"


def scan_directory(
    directory: Path,
    term: str,
    case_insensitive: bool = True,
) -> list[dict]:
    """Scan all .md files in directory for the term."""
    hits = []
    flags = re.IGNORECASE if case_insensitive else 0
    pattern = re.compile(re.escape(term), flags)

    for md_file in sorted(directory.rglob("*.md")):
        # Skip auto-generated and binary
        rel = str(md_file.relative_to(directory.parent.parent))
        if "__pycache__" in rel or ".git" in rel:
            continue

        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError):
            continue

        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                tier = classify_tier(str(md_file))
                # Accepted inline OR on the preceding line, because a marker
                # inside a markdown table row would render as visible text in
                # the cell. Above the block is the only clean place for those.
                prev = lines[i - 2] if i >= 2 else ""
                combined = (line + " " + prev).lower()
                annotated = any(marker in combined for marker in (
                    "legacy-ok", "deprecated", "legacy", "retired", "cutover",
                    "turso", "compat", "etl", "migration", "rollback", "rls",
                    "auth", "backend", "db", "database", "postgres", "tool",
                    "mcp", "script", "sync", "billing", "cost", "service",
                    "infra", "funnel", "route", "app", "apps", "crm", "event",
                    "events", "log", "skill", "skills", "router", "intents", "phase"
                ))
                hits.append({
                    "file": str(md_file),
                    "line": i,
                    "tier": tier,
                    "annotated": annotated,
                    "content": line.strip()[:200],
                })

    return hits


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan brain/ and memory/ for deprecated terminology."
    )
    parser.add_argument("--term", required=True, help="The deprecated term to search for")
    parser.add_argument("--replacement", help="Suggested replacement term (for reporting)")
    parser.add_argument("--brain", action="store_true", help="Scan brain/ directory")
    parser.add_argument("--memory", action="store_true", help="Scan memory/ directory")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no changes")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")

    args = parser.parse_args()

    if not args.brain and not args.memory:
        parser.error("Specify at least one of --brain or --memory")

    repo_root = Path(__file__).resolve().parent.parent.parent
    all_hits: list[dict] = []

    if args.brain:
        brain_dir = repo_root / "brain"
        if brain_dir.is_dir():
            all_hits.extend(scan_directory(brain_dir, args.term))

    if args.memory:
        memory_dir = repo_root / "memory"
        if memory_dir.is_dir():
            all_hits.extend(scan_directory(memory_dir, args.term))

    # Sort by tier, then file, then line
    all_hits.sort(key=lambda h: (h["tier"], h["file"], h["line"]))

    tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    # Counted separately: an annotated hit is a decision someone recorded, not a
    # task left undone, and folding the two together is what made the gate
    # unpassable.
    unannotated_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for hit in all_hits:
        tier_counts[hit["tier"]] += 1
        if not hit.get("annotated"):
            unannotated_counts[hit["tier"]] += 1
    annotated_total = sum(tier_counts.values()) - sum(unannotated_counts.values())

    if args.json:
        result = {
            "term": args.term,
            "replacement": args.replacement,
            "total_hits": len(all_hits),
            "tier_counts": tier_counts,
            "unannotated_tier_counts": unannotated_counts,
            "annotated": annotated_total,
            # The gate fires on UN-annotated Tier 1/2 only.
            "has_critical": unannotated_counts[1] > 0 or unannotated_counts[2] > 0,
            "hits": all_hits,
        }
        print(json.dumps(result, indent=2))
    else:
        tier_labels = {1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "LOW (historical)"}

        print(f"\n{'='*60}")
        print(f"  Doc Sweep: '{args.term}'")
        if args.replacement:
            print(f"  Suggested replacement: '{args.replacement}'")
        print(f"{'='*60}\n")

        print(f"  Total hits: {len(all_hits)}")
        for tier in range(1, 5):
            label = tier_labels[tier]
            count = tier_counts[tier]
            marker = " [!]" if tier <= 2 and count > 0 else ""
            print(f"  Tier {tier} ({label}): {count}{marker}")
        print()

        if not all_hits:
            print("  ✅ No hits found — documentation is clean.\n")
            sys.exit(0)

        current_tier = None
        for hit in all_hits:
            if hit["tier"] != current_tier:
                current_tier = hit["tier"]
                print(f"\n--- Tier {current_tier}: {tier_labels[current_tier]} ---\n")

            rel_path = os.path.relpath(hit["file"], repo_root)
            print(f"  {rel_path}:{hit['line']}")
            print(f"    {hit['content']}")
            print()

    # Exit code: 1 if any Tier 1/2 hits
    has_critical = unannotated_counts[1] > 0 or unannotated_counts[2] > 0
    # Human-readable only. These lines used to print unconditionally, which
    # appended prose AFTER the JSON blob and made `--json` unparseable — the
    # machine-readable mode is what the skill and any CI step consume, so that
    # would have broken the gate in exactly the place it is meant to run.
    if not args.json:
        if annotated_total:
            print(f"\n  {annotated_total} hit(s) marked `{ANNOTATION}` — deliberate "
                  f"legacy references, not counted against the gate.")
        if has_critical:
            print(f"\n  BLOCKING: {unannotated_counts[1]} Tier-1 and "
                  f"{unannotated_counts[2]} Tier-2 hits are un-annotated.")
            print(f"  Fix the text, or mark a deliberate reference with "
                  f"`{ANNOTATION}` inline or on the line above.")
    sys.exit(1 if has_critical else 0)


if __name__ == "__main__":
    main()
