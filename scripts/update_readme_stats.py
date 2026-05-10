"""update_readme_stats.py — keep README.md (and any other doc) honest about
what's actually in this repo.

The system should never lie about itself. README claims "152 skills, 93 scripts"
but disk reality drifts every commit. This script walks the filesystem, builds
a fresh stats dict, and either rewrites the README in-place (--apply) or fails
loudly when the README is stale (--check, used by CI / self-audit).

Stats counted:
  - skills          (skills/*/SKILL.md)
  - scripts         (scripts/*.py, top-level only — excludes tests, internal)
  - sub_agents      (agents/*.md + .claude/agents/*.md)
  - workflows       (.agents/workflows/*.md)
  - mcp_servers     (parsed from .claude/mcp.json)

Markers in README.md:
  Each replaceable line is wrapped with HTML comment markers like:
      <!-- STATS:skills-->153 skills<!-- /STATS -->
  Lines without markers are left alone.

Usage:
    python scripts/update_readme_stats.py            # dry-run, prints what would change
    python scripts/update_readme_stats.py --apply    # rewrite README.md
    python scripts/update_readme_stats.py --check    # exit 1 if stale (for CI / hooks)
    python scripts/update_readme_stats.py --json     # emit current counts as JSON
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
MCP_CONFIG = ROOT / ".claude" / "mcp.json"


def count_skills() -> int:
    return len(list((ROOT / "skills").glob("*/SKILL.md")))


def count_scripts() -> int:
    """Top-level scripts/ Python files only. Excludes tests, internal helpers
    (leading underscore), and the cli_templates subdirectory."""
    out = 0
    for p in (ROOT / "scripts").glob("*.py"):
        name = p.name
        if name.startswith("_"):
            continue
        if name.startswith("test_") or name == "conftest.py":
            continue
        out += 1
    return out


def count_sub_agents() -> int:
    """Markdown agent personas in agents/ + .claude/agents/. Excludes
    voltagent/ (drop-in community personas) and INDEX.md."""
    out = 0
    for d in [ROOT / "agents", ROOT / ".claude" / "agents"]:
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            if p.name.upper() == "INDEX.MD":
                continue
            out += 1
    return out


def count_workflows() -> int:
    d = ROOT / ".agents" / "workflows"
    if not d.is_dir():
        return 0
    return sum(1 for p in d.glob("*.md") if not p.name.startswith("_"))


def count_mcp_servers() -> int:
    if not MCP_CONFIG.is_file():
        return 0
    try:
        data = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return 0
    return len(data.get("mcpServers") or {})


def collect_stats() -> dict[str, int]:
    return {
        "skills": count_skills(),
        "scripts": count_scripts(),
        "sub_agents": count_sub_agents(),
        "workflows": count_workflows(),
        "mcp_servers": count_mcp_servers(),
    }


# ---------------------------------------------------------------------------
# README rewriter
# ---------------------------------------------------------------------------
# Pattern: <!-- STATS:KEY-->some text<!-- /STATS -->
# Replacement is the value the script computes, formatted via formatter below.
_MARKER_RE = re.compile(
    r"<!--\s*STATS:([a-z_]+)\s*-->(.*?)<!--\s*/STATS\s*-->",
    flags=re.DOTALL,
)


def _format_value(key: str, value: int) -> str:
    """Human-readable string per stat key. Default is just the number."""
    formats = {
        "skills":      f"**{value} skills**",
        "scripts":     f"**{value} scripts**",
        "sub_agents":  f"**{value} sub-agents**",
        "workflows":   f"**{value} workflows**",
        "mcp_servers": f"**{value} MCP servers**",
    }
    return formats.get(key, str(value))


def rewrite_readme(stats: dict[str, int], *, dry_run: bool = True) -> tuple[bool, list[str]]:
    """Returns (changed, diff_lines). Idempotent."""
    if not README.is_file():
        return False, [f"README not found at {README}"]
    text = README.read_text(encoding="utf-8")
    new_text = text
    changes: list[str] = []
    for m in _MARKER_RE.finditer(text):
        key = m.group(1).strip()
        old_inner = m.group(2)
        if key not in stats:
            continue
        new_inner = _format_value(key, stats[key])
        if new_inner != old_inner:
            old_block = m.group(0)
            new_block = f"<!-- STATS:{key}-->{new_inner}<!-- /STATS -->"
            new_text = new_text.replace(old_block, new_block, 1)
            changes.append(f"  {key}: {old_inner!r} -> {new_inner!r}")
    if new_text == text:
        return False, []
    if not dry_run:
        README.write_text(new_text, encoding="utf-8")
    return True, changes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true",
                   help="Rewrite README.md in place")
    g.add_argument("--check", action="store_true",
                   help="Exit 1 if README is stale (no writes)")
    g.add_argument("--json", action="store_true",
                   help="Print current stats as JSON, no README touch")
    args = ap.parse_args()

    stats = collect_stats()

    if args.json:
        print(json.dumps(stats, indent=2))
        return 0

    if args.check:
        # Re-render against current; if anything would change, README is stale
        changed, diff = rewrite_readme(stats, dry_run=True)
        if changed:
            print("README is STALE. Run: python scripts/update_readme_stats.py --apply")
            for line in diff:
                print(line)
            return 1
        print("README stats are in sync with disk.")
        return 0

    # Default + --apply paths share rewrite, differ on dry_run
    changed, diff = rewrite_readme(stats, dry_run=not args.apply)
    if not changed:
        print("README already in sync. No changes.")
        return 0
    label = "Would update" if not args.apply else "Updated"
    print(f"{label} README.md:")
    for line in diff:
        print(line)
    if not args.apply:
        print("\nRun with --apply to write the changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
