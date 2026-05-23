#!/usr/bin/env python3
"""sync_slash_commands.py — drift-detect the dashboard slash-command catalog
against the actual `.agents/workflows/` directories on disk.

Why this is detect-only, not auto-rewrite: the hand-curated catalog at
lib/slash-commands.ts in the oasis-command-center repo has nicer
descriptions, custom CLI invocations (e.g. `python scripts/ceo_dashboard.py
briefing` instead of the default `claude /ceo-briefing`), and per-command
notes. Auto-regeneration would clobber that craftsmanship. Instead, this
script reports drift so a human (or a future Codex pass) can patch the
catalog deliberately.

The catalog now lives in a sibling checkout of the extracted dashboard repo
(default: ~/APPS/oasis-command-center). Override with
COMMAND_CENTER_REPO=<path> if you keep it elsewhere. The script no-ops
gracefully when the catalog isn't reachable.

Reads:
- c:/Users/User/Business-Empire-Agent/.agents/workflows/*.md  (Bravo)
- c:/Users/User/CMO-Agent/.agents/workflows/*.md              (Maven)

Reports:
- workflows present on disk but missing from catalog (NEW)
- catalog entries referencing workflows that no longer exist (STALE)
- count of each agent's commands

Exit code 0 if in sync, 1 if drift detected.

Usage:
    python scripts/core/sync_slash_commands.py
    python scripts/core/sync_slash_commands.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BRAVO_WORKFLOWS = ROOT / ".agents" / "workflows"

# Sibling-repo resolution lives in scripts/sibling_repos.py — single source
# of truth across the codebase. Adding the repo path to sys.path so this
# script works whether invoked from repo-root or anywhere else.
sys.path.insert(0, str(ROOT / "scripts"))
from sibling_repos import SIBLING_REPOS  # noqa: E402

MAVEN_WORKFLOWS = SIBLING_REPOS["maven"] / ".agents" / "workflows"
_COMMAND_CENTER_REPO = SIBLING_REPOS["oasis-command-center"]
CATALOG = _COMMAND_CENTER_REPO / "lib" / "slash-commands.ts"


def workflow_slugs(workflow_dir: Path) -> set[str]:
    if not workflow_dir.exists():
        return set()
    return {
        md.stem.lower()
        for md in workflow_dir.glob("*.md")
        if md.stem.upper() != "INDEX"
    }


def catalog_slugs(text: str, agent: str) -> set[str]:
    """Extract slug values from the catalog block for a given agent."""
    block = re.search(
        rf"^const {agent.upper()}: SlashCommand\[\] = \[(.*?)^\];",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not block:
        return set()
    return set(re.findall(r'slug:\s*"([^"]+)"', block.group(1)))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if not CATALOG.exists():
        msg = (
            f"command-center catalog not found at {CATALOG}\n"
            "Either clone https://github.com/CC90210/oasis-command-center to "
            "~/APPS/oasis-command-center, or set COMMAND_CENTER_REPO=<path>."
        )
        if args.json:
            print(json.dumps({"status": "catalog_missing", "expected_at": str(CATALOG)}, indent=2))
        else:
            print(msg)
        return 0
    src = CATALOG.read_text(encoding="utf-8")
    drift_found = False
    report: dict = {"agents": {}}

    for agent, wf_dir in [("bravo", BRAVO_WORKFLOWS), ("maven", MAVEN_WORKFLOWS)]:
        on_disk = workflow_slugs(wf_dir)
        in_catalog = catalog_slugs(src, agent)
        new = sorted(on_disk - in_catalog)
        stale = sorted(in_catalog - on_disk)
        report["agents"][agent] = {
            "workflow_dir": str(wf_dir),
            "on_disk": len(on_disk),
            "in_catalog": len(in_catalog),
            "new": new,
            "stale": stale,
        }
        if new or stale:
            drift_found = True

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print()
        for agent, info in report["agents"].items():
            print(f"=== {agent.upper()} ===")
            print(f"  workflow_dir: {info['workflow_dir']}")
            print(f"  on_disk: {info['on_disk']} workflows · catalog: {info['in_catalog']} entries")
            if info["new"]:
                print(f"  NEW (on disk, not in catalog): {info['new']}")
            if info["stale"]:
                print(f"  STALE (in catalog, not on disk): {info['stale']}")
            if not info["new"] and not info["stale"]:
                print(f"  in sync")
            print()

        if drift_found:
            print(f"Drift detected. Patch {CATALOG}")
            print("manually with proper descriptions/cli_invocations/notes (don't")
            print("blindly auto-generate — hand-curated entries beat default stubs).")
        else:
            print("All catalogs in sync")

    return 1 if drift_found else 0


if __name__ == "__main__":
    sys.exit(main())
