"""
Inventory Generator — live repo counts for brain/INVENTORY.md

Auto-scans the repository and writes brain/INVENTORY.md (overwritten each run)
with a generated-at timestamp and the current counts for:
  - skills (active under skills/, archived under skills/_archive/)
  - scripts (top-level scripts/*.py, and total .py under scripts/ recursively,
    excluding _archive/ and __pycache__/)
  - cron seed jobs (SEED_JOBS entries in scripts/core/cron_engine.py)
  - workflows (.agents/workflows/)
  - subagents (.claude/agents/ entries)
  - MCP servers (.claude/mcp.json mcpServers)

Usage:
  python scripts/core/generate_inventory.py           # write brain/INVENTORY.md + print counts
  python scripts/core/generate_inventory.py --json    # print counts as JSON too
  python scripts/core/generate_inventory.py --check   # exit 1 if INVENTORY.md missing/stale (>35 days)
"""

import argparse
import ast
import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

# Force UTF-8 output on Windows (cp1252 terminal chokes on em-dash, arrows, etc.)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Walk up from this script's directory until we find .git or CLAUDE.md."""
    candidate = Path(__file__).resolve().parent
    for _ in range(8):
        if (candidate / ".git").exists() or (candidate / "CLAUDE.md").exists():
            return candidate
        candidate = candidate.parent
    # Fallback: directory containing this script's parent
    return Path(__file__).resolve().parent.parent.parent


ROOT = _find_project_root()
TODAY = date.today()

INVENTORY_PATH = ROOT / "brain" / "INVENTORY.md"
STALE_DAYS = 35


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------

def _count_skills() -> dict:
    """Active skill dirs under skills/ (excluding _archive) and archived dirs."""
    skills_dir = ROOT / "skills"
    active = sum(
        1
        for p in skills_dir.iterdir()
        if p.is_dir() and p.name != "_archive"
    )
    archive_dir = skills_dir / "_archive"
    archived = (
        sum(1 for p in archive_dir.iterdir() if p.is_dir())
        if archive_dir.exists()
        else 0
    )
    return {"active": active, "archived": archived}


def _count_scripts() -> dict:
    """Top-level scripts/*.py and total .py under scripts/ recursively,
    excluding _archive/ and __pycache__/."""
    scripts_dir = ROOT / "scripts"
    top_level = sum(1 for p in scripts_dir.glob("*.py") if p.is_file())
    total = 0
    for p in scripts_dir.rglob("*.py"):
        if not p.is_file():
            continue
        parts = set(p.relative_to(scripts_dir).parts[:-1])
        if "_archive" in parts or "__pycache__" in parts:
            continue
        total += 1
    return {"top_level": top_level, "total": total}


def _count_seed_jobs() -> int:
    """Parse SEED_JOBS out of scripts/core/cron_engine.py via AST (no import)."""
    engine = ROOT / "scripts" / "core" / "cron_engine.py"
    tree = ast.parse(engine.read_text(encoding="utf-8"))
    for node in tree.body:
        target = node
        if isinstance(node, ast.AnnAssign):
            target = node
            names = [node.target]
        elif isinstance(node, ast.Assign):
            names = node.targets
        else:
            continue
        for name in names:
            if isinstance(name, ast.Name) and name.id == "SEED_JOBS":
                value = target.value  # type: ignore[attr-defined]
                if isinstance(value, ast.List):
                    return len(value.elts)
    return 0


def _count_workflows() -> int:
    """Files in .agents/workflows/."""
    wf_dir = ROOT / ".agents" / "workflows"
    if not wf_dir.exists():
        return 0
    return sum(1 for p in wf_dir.iterdir() if p.is_file())


def _count_subagents() -> dict:
    """Entries in .claude/agents/ (agent .md files + INDEX.md)."""
    agents_dir = ROOT / ".claude" / "agents"
    if not agents_dir.exists():
        return {"total": 0, "agents": 0, "index": 0}
    entries = [p for p in agents_dir.iterdir() if p.is_file()]
    index = sum(1 for p in entries if p.name.upper().startswith("INDEX"))
    return {"total": len(entries), "agents": len(entries) - index, "index": index}


def _count_mcp_servers() -> int:
    """mcpServers entries in .claude/mcp.json."""
    mcp = ROOT / ".claude" / "mcp.json"
    if not mcp.exists():
        return 0
    data = json.loads(mcp.read_text(encoding="utf-8"))
    servers = data.get("mcpServers", {})
    return len(servers)


def collect_counts() -> dict:
    return {
        "skills": _count_skills(),
        "scripts": _count_scripts(),
        "cron_seed_jobs": _count_seed_jobs(),
        "workflows": _count_workflows(),
        "subagents": _count_subagents(),
        "mcp_servers": _count_mcp_servers(),
    }


# ---------------------------------------------------------------------------
# INVENTORY.md rendering
# ---------------------------------------------------------------------------

def render_inventory(counts: dict) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s = counts["skills"]
    sc = counts["scripts"]
    sa = counts["subagents"]
    return f"""# INVENTORY.md — Live Repo Inventory (auto-generated)

> Generated by `scripts/core/generate_inventory.py` — do not hand-edit.
> Re-run monthly via the `Monthly Inventory Sync` cron seed job, or on demand.

- **Generated at:** {generated_at}
- **Skills:** {s['active']} active ({s['archived']} archived in `skills/_archive/`)
- **Python scripts:** {sc['top_level']} top-level production CLI tools under `scripts/` ({sc['total']} total inc. subpackages, excluding `_archive/` and `__pycache__/`)
- **Cron seed jobs:** {counts['cron_seed_jobs']} in `scripts/core/cron_engine.py` SEED_JOBS
- **Workflows:** {counts['workflows']} in `.agents/workflows/`
- **Subagents:** {sa['total']} in `.claude/agents/` ({sa['agents']} agents + INDEX.md)
- **MCP servers:** {counts['mcp_servers']} in `.claude/mcp.json`

The hard numbers quoted in the six entry-point files (AGENTS.md, CLAUDE.md,
GEMINI.md, ANTIGRAVITY.md, OPENCODE.md, ZCODE.md) are snapshots — this file is
the live source of truth between syncs.
"""


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_generate(args: argparse.Namespace) -> int:
    counts = collect_counts()
    INVENTORY_PATH.write_text(render_inventory(counts), encoding="utf-8")

    if args.json:
        print(json.dumps({"counts": counts, "written": str(INVENTORY_PATH.relative_to(ROOT))}, indent=2))
    else:
        print(f"Wrote brain/INVENTORY.md — {TODAY.isoformat()}")
        print(f"  Skills        : {counts['skills']['active']} active / {counts['skills']['archived']} archived")
        print(f"  Scripts       : {counts['scripts']['top_level']} top-level / {counts['scripts']['total']} total")
        print(f"  Cron seed jobs: {counts['cron_seed_jobs']} in SEED_JOBS")
        print(f"  Workflows     : {counts['workflows']}")
        print(f"  Subagents     : {counts['subagents']['total']} ({counts['subagents']['agents']} agents + INDEX.md)")
        print(f"  MCP servers   : {counts['mcp_servers']}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Exit 1 if brain/INVENTORY.md is missing or older than STALE_DAYS."""
    if not INVENTORY_PATH.exists():
        print("STALE: brain/INVENTORY.md is missing — run scripts/core/generate_inventory.py")
        return 1
    mtime = date.fromtimestamp(INVENTORY_PATH.stat().st_mtime)
    age = (TODAY - mtime).days
    if age > STALE_DAYS:
        print(f"STALE: brain/INVENTORY.md is {age} days old (threshold {STALE_DAYS}) — re-run scripts/core/generate_inventory.py")
        return 1
    print(f"FRESH: brain/INVENTORY.md is {age} days old (threshold {STALE_DAYS})")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate_inventory",
        description="Bravo inventory generator — writes brain/INVENTORY.md with live repo counts.",
    )
    parser.add_argument("--json", action="store_true", help="Also print counts as JSON")
    parser.add_argument(
        "--check",
        action="store_true",
        help=f"Do not write; exit 1 if brain/INVENTORY.md is missing or older than {STALE_DAYS} days",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.check:
        sys.exit(cmd_check(args))
    sys.exit(cmd_generate(args))


if __name__ == "__main__":
    main()
