#!/usr/bin/env python3
"""
autoDream — Memory Consolidation Engine (Inspired by Claude Code internals)

Runs during idle/session-end to consolidate what the agent learned.
Four phases: Orient → Gather → Consolidate → Prune

Usage:
  python scripts/auto_dream.py run           Full 4-phase consolidation
  python scripts/auto_dream.py status        Show memory state without changing
  python scripts/auto_dream.py --dry-run     Preview what would change
  python scripts/auto_dream.py --json        Machine-readable output
"""

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"
BRAIN_DIR = PROJECT_ROOT / "brain"
ARCHIVE_DIR = MEMORY_DIR / "ARCHIVES"

# Budget caps (from memory-management skill)
BUDGETS = {
    "SESSION_LOG.md": 200,
    "ACTIVE_TASKS.md": 50,
    "MISTAKES.md": 30,
    "PATTERNS.md": 30,
}

# Files to consolidate
CONSOLIDATION_TARGETS = [
    MEMORY_DIR / "MISTAKES.md",
    MEMORY_DIR / "PATTERNS.md",
    MEMORY_DIR / "ACTIVE_TASKS.md",
    MEMORY_DIR / "SESSION_LOG.md",
    MEMORY_DIR / "SELF_REFLECTIONS.md",
    MEMORY_DIR / "DECISIONS.md",
]


def phase_orient():
    """Phase 1: Orient — Assess current memory state."""
    report = {
        "phase": "orient",
        "files": {},
        "total_lines": 0,
        "over_budget": [],
        "stale_entries": 0,
    }

    for target in CONSOLIDATION_TARGETS:
        if not target.exists():
            continue
        lines = target.read_text(encoding="utf-8").splitlines()
        line_count = len(lines)
        fname = target.name
        budget = BUDGETS.get(fname)

        report["files"][fname] = {
            "lines": line_count,
            "budget": budget,
            "over": (line_count - budget) if budget and line_count > budget else 0,
        }
        report["total_lines"] += line_count

        if budget and line_count > budget:
            report["over_budget"].append(fname)

    # Check for stale entries (dates older than 30 days)
    today = date.today()
    date_pattern = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
    for target in CONSOLIDATION_TARGETS:
        if not target.exists():
            continue
        for line in target.read_text(encoding="utf-8").splitlines():
            match = date_pattern.search(line)
            if match:
                try:
                    entry_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if (today - entry_date).days > 30:
                        report["stale_entries"] += 1
                except ValueError:
                    pass

    return report


def phase_gather():
    """Phase 2: Gather — Extract all discrete knowledge entries."""
    entries = {
        "mistakes": [],
        "patterns": [],
        "reflections": [],
        "decisions": [],
    }

    # Parse MISTAKES.md
    mistakes_file = MEMORY_DIR / "MISTAKES.md"
    if mistakes_file.exists():
        content = mistakes_file.read_text(encoding="utf-8")
        for block in re.split(r"\n### ", content):
            block = block.strip()
            if not block or block.startswith("---") or block.startswith("#"):
                continue
            title_line = block.split("\n")[0]
            entries["mistakes"].append({
                "title": title_line.strip(),
                "content": block,
                "hash": hashlib.md5(block.encode()).hexdigest()[:8],
            })

    # Parse PATTERNS.md
    patterns_file = MEMORY_DIR / "PATTERNS.md"
    if patterns_file.exists():
        content = patterns_file.read_text(encoding="utf-8")
        for block in re.split(r"\n### ", content):
            block = block.strip()
            if not block or block.startswith("---") or block.startswith("#"):
                continue
            title_line = block.split("\n")[0]
            is_validated = "[V]" in title_line or "[VALIDATED]" in title_line
            entries["patterns"].append({
                "title": title_line.strip(),
                "content": block,
                "validated": is_validated,
                "hash": hashlib.md5(block.encode()).hexdigest()[:8],
            })

    # Parse SELF_REFLECTIONS.md
    reflections_file = MEMORY_DIR / "SELF_REFLECTIONS.md"
    if reflections_file.exists():
        content = reflections_file.read_text(encoding="utf-8")
        for block in re.split(r"\n### ", content):
            block = block.strip()
            if not block or block.startswith("---") or block.startswith("#"):
                continue
            title_line = block.split("\n")[0]
            entries["reflections"].append({
                "title": title_line.strip(),
                "content": block,
                "hash": hashlib.md5(block.encode()).hexdigest()[:8],
            })

    # Parse DECISIONS.md
    decisions_file = MEMORY_DIR / "DECISIONS.md"
    if decisions_file.exists():
        content = decisions_file.read_text(encoding="utf-8")
        for block in re.split(r"\n### ", content):
            block = block.strip()
            if not block or block.startswith("---") or block.startswith("#"):
                continue
            title_line = block.split("\n")[0]
            entries["decisions"].append({
                "title": title_line.strip(),
                "content": block,
                "hash": hashlib.md5(block.encode()).hexdigest()[:8],
            })

    return entries


def phase_consolidate(entries, dry_run=False):
    """Phase 3: Consolidate — Merge related entries, resolve contradictions."""
    actions = []

    # 1. Find duplicate mistakes (same root cause)
    mistake_hashes = set()
    for m in entries["mistakes"]:
        if m["hash"] in mistake_hashes:
            actions.append({
                "type": "deduplicate",
                "file": "MISTAKES.md",
                "entry": m["title"],
                "reason": "Duplicate hash detected",
            })
        mistake_hashes.add(m["hash"])

    # 2. Find patterns that should be promoted
    # A pattern with [P] that has been around for 30+ days and not contradicted
    today = date.today()
    date_pattern = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
    for p in entries["patterns"]:
        if not p["validated"]:
            match = date_pattern.search(p["title"])
            if match:
                try:
                    entry_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    age_days = (today - entry_date).days
                    if age_days >= 21:
                        actions.append({
                            "type": "promote",
                            "file": "PATTERNS.md",
                            "entry": p["title"],
                            "reason": f"Probationary for {age_days} days — candidate for validation",
                        })
                except ValueError:
                    pass

    # 3. Find reflections that overlap with existing mistakes
    mistake_keywords = set()
    for m in entries["mistakes"]:
        words = set(re.findall(r"\b\w{5,}\b", m["content"].lower()))
        mistake_keywords.update(words)

    for r in entries["reflections"]:
        r_words = set(re.findall(r"\b\w{5,}\b", r["content"].lower()))
        overlap = r_words & mistake_keywords
        if len(overlap) > 5:
            actions.append({
                "type": "merge_candidate",
                "file": "SELF_REFLECTIONS.md",
                "entry": r["title"],
                "reason": f"Overlaps with existing mistake ({len(overlap)} shared keywords) — can be archived",
            })

    # 4. Check for stale decisions (> 60 days old)
    for d in entries["decisions"]:
        match = date_pattern.search(d["title"])
        if match:
            try:
                entry_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                if (today - entry_date).days > 60:
                    actions.append({
                        "type": "review_needed",
                        "file": "DECISIONS.md",
                        "entry": d["title"],
                        "reason": f"Decision is {(today - entry_date).days} days old — may need re-evaluation",
                    })
            except ValueError:
                pass

    return actions


def phase_prune(orient_report, dry_run=False):
    """Phase 4: Prune — Trim files to budget, archive overflow."""
    actions = []
    today_str = date.today().strftime("%Y-%m-%d")

    for fname, info in orient_report["files"].items():
        if info["over"] > 0:
            actions.append({
                "type": "over_budget",
                "file": fname,
                "lines": info["lines"],
                "budget": info["budget"],
                "over_by": info["over"],
                "action": f"Needs {info['over']} lines trimmed",
            })

    # Archive completed tasks from ACTIVE_TASKS.md
    tasks_file = MEMORY_DIR / "ACTIVE_TASKS.md"
    if tasks_file.exists():
        content = tasks_file.read_text(encoding="utf-8")
        completed = re.findall(r"- \[x\].*", content)
        if len(completed) > 3:
            actions.append({
                "type": "archive_completed",
                "file": "ACTIVE_TASKS.md",
                "count": len(completed),
                "action": f"Archive {len(completed) - 2} completed tasks (keep 2 most recent)",
            })

    return actions


def run_consolidation(dry_run=False, output_json=False):
    """Run the full 4-phase autoDream consolidation."""
    results = {"timestamp": datetime.now().isoformat(), "phases": {}}

    # Phase 1: Orient
    orient = phase_orient()
    results["phases"]["orient"] = orient

    # Phase 2: Gather
    entries = phase_gather()
    results["phases"]["gather"] = {
        "mistakes": len(entries["mistakes"]),
        "patterns": len(entries["patterns"]),
        "reflections": len(entries["reflections"]),
        "decisions": len(entries["decisions"]),
    }

    # Phase 3: Consolidate
    consolidate_actions = phase_consolidate(entries, dry_run)
    results["phases"]["consolidate"] = consolidate_actions

    # Phase 4: Prune
    prune_actions = phase_prune(orient, dry_run)
    results["phases"]["prune"] = prune_actions

    # Summary
    total_actions = len(consolidate_actions) + len(prune_actions)
    results["summary"] = {
        "total_entries": sum(results["phases"]["gather"].values()),
        "consolidation_actions": len(consolidate_actions),
        "prune_actions": len(prune_actions),
        "total_actions": total_actions,
        "stale_entries": orient["stale_entries"],
        "files_over_budget": len(orient["over_budget"]),
        "status": "clean" if total_actions == 0 else "needs_attention",
    }

    if output_json:
        print(json.dumps(results, indent=2, default=str))
    else:
        _print_report(results, dry_run)

    return results


def show_status(output_json=False):
    """Show current memory state without making changes."""
    orient = phase_orient()
    entries = phase_gather()

    status = {
        "memory_files": orient["files"],
        "total_lines": orient["total_lines"],
        "over_budget": orient["over_budget"],
        "stale_entries": orient["stale_entries"],
        "entry_counts": {
            "mistakes": len(entries["mistakes"]),
            "patterns": len(entries["patterns"]),
            "reflections": len(entries["reflections"]),
            "decisions": len(entries["decisions"]),
        },
    }

    if output_json:
        print(json.dumps(status, indent=2))
    else:
        print(f"autoDream Status -- {date.today()}")
        print("=" * 50)
        print(f"  Total memory lines: {orient['total_lines']}")
        print(f"  Files over budget:  {len(orient['over_budget'])}")
        print(f"  Stale entries:      {orient['stale_entries']}")
        print()
        for fname, info in orient["files"].items():
            marker = " OVER" if info["over"] > 0 else ""
            budget_str = f"/{info['budget']}" if info["budget"] else ""
            print(f"  {fname:<25} {info['lines']}{budget_str} lines{marker}")
        print()
        for cat, count in status["entry_counts"].items():
            print(f"  {cat}: {count} entries")


def _print_report(results, dry_run):
    """Pretty-print the consolidation report."""
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}autoDream Consolidation -- {date.today()}")
    print("=" * 55)

    # Orient
    orient = results["phases"]["orient"]
    print(f"\n  Phase 1 - Orient:")
    print(f"    Total lines: {orient['total_lines']}")
    print(f"    Over budget: {len(orient['over_budget'])} files")
    print(f"    Stale (>30d): {orient['stale_entries']} entries")

    # Gather
    gather = results["phases"]["gather"]
    print(f"\n  Phase 2 - Gather:")
    for cat, count in gather.items():
        print(f"    {cat}: {count}")

    # Consolidate
    consol = results["phases"]["consolidate"]
    print(f"\n  Phase 3 - Consolidate: {len(consol)} actions")
    for action in consol:
        print(f"    [{action['type']}] {action['file']}: {action['entry'][:60]}")
        print(f"      -> {action['reason']}")

    # Prune
    prune = results["phases"]["prune"]
    print(f"\n  Phase 4 - Prune: {len(prune)} actions")
    for action in prune:
        print(f"    [{action['type']}] {action['file']}: {action.get('action', '')}")

    # Summary
    summary = results["summary"]
    print(f"\n  Status: {summary['status'].upper()}")
    print(f"  Total actions: {summary['total_actions']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="autoDream — Memory Consolidation Engine")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "status"])
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.command == "status":
        show_status(output_json=args.json)
    else:
        run_consolidation(dry_run=args.dry_run, output_json=args.json)
