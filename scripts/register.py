"""
Register — one-command "add a new skill or tool" wizard.

Solves the "where does this go and how do I wire it?" problem. Drop this
script with a name and a description; it scaffolds the file with the right
frontmatter, links it into the capability graph, and runs validation.

Replaces the previous 6-step ritual:
  1. Create skills/<name>/SKILL.md by hand
  2. Add YAML frontmatter (and remember every required field)
  3. Add reference in brain/CAPABILITIES.md
  4. Add reference in CLAUDE.md if user-facing
  5. Add wiki-link from somewhere indexed (or self_audit flags as orphan)
  6. Run register_skill.py to update Supabase registry

Now:
  python scripts/register.py skill outreach-followup
    --description "Send a value-first follow-up to a warm lead"
    --tier specialized
    --triggers "follow up,nudge,follow-up email"
    --tags outreach,sales

Or for a script:
  python scripts/register.py script lead_scorer
    --description "Score inbound leads 0-100 by intent + fit signals"

The wizard:
  1. Validates the name (not already taken, slugified)
  2. Generates the file with proper frontmatter / docstring
  3. Adds it to the agent's CLAUDE.md V6 stack section if registered to a known tier
  4. Triggers `build_capability_graph.py` so the graph picks it up
  5. Runs `self_audit.py` to confirm no drift
  6. Prints next-steps (e.g., "Implement the actual logic in ...")

USAGE
-----
    python scripts/register.py skill <name>     [options]
    python scripts/register.py script <name>    [options]
    python scripts/register.py agent <name>     [options]
    python scripts/register.py workflow <name>  [options]
    python scripts/register.py list              # show every registered capability
    python scripts/register.py validate <name>   # re-run validation on existing

RELATED — `scripts/register_skill.py` (legacy)
----------------------------------------------
The older `register_skill.py` writes a row to the Supabase `skills_registry`
table and remains the right tool when an existing skill needs to be resynced
to the database (e.g., after editing its frontmatter). Use cases split as:

  scripts/register.py        — CREATE a new skill/script/agent/workflow on disk
                               with proper frontmatter + auto-graph rebuild.
  scripts/register_skill.py  — SYNC an existing skill folder to Supabase
                               (sync-one, sync-all, audit, validate).

`register.py skill` does NOT call `register_skill.py register` automatically
— Supabase write is opt-in. After scaffolding, run
`python scripts/register_skill.py register <name>` if you want the
skills_registry row.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
AGENTS_DIR = PROJECT_ROOT / "agents"
WORKFLOWS_DIR = PROJECT_ROOT / ".agents" / "workflows"

VALID_TIERS = {"core", "specialized", "meta", "safety", "tool"}
VALID_RISKS = {"low", "medium", "high"}


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _parse_csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


# Reuse the canonical detector from build_capability_graph.py instead of
# duplicating the logic. Falls back to a local equivalent if the import
# path isn't available (e.g., running this script in a partial checkout).
try:
    sys.path.insert(0, str(SCRIPTS_DIR))
    from build_capability_graph import _agent_name  # type: ignore
except Exception:  # noqa: BLE001
    def _agent_name() -> str:
        claude_md = PROJECT_ROOT / "CLAUDE.md"
        if claude_md.exists():
            head = claude_md.read_text(encoding="utf-8", errors="ignore")[:500].lower()
            for n in ("bravo", "atlas", "maven", "aura", "hermes"):
                if n in head:
                    return n
        return PROJECT_ROOT.name.lower()


# ── Skill creation ──────────────────────────────────────────────────────────

def create_skill(args) -> int:
    slug = _slug(args.name)
    skill_dir = SKILLS_DIR / slug
    if skill_dir.exists():
        print(f"ERROR: skills/{slug}/ already exists", file=sys.stderr)
        return 1
    triggers = _parse_csv(args.triggers)
    tags = _parse_csv(args.tags) or [args.tier]
    if args.tier not in VALID_TIERS:
        print(f"ERROR: --tier must be one of {sorted(VALID_TIERS)}", file=sys.stderr)
        return 2
    if args.risk not in VALID_RISKS:
        print(f"ERROR: --risk must be one of {sorted(VALID_RISKS)}", file=sys.stderr)
        return 2

    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    fm_lines = [
        "---",
        f"name: {slug}",
        f"description: {args.description}",
        f"tier: {args.tier}",
        f"owner: {args.owner or _agent_name()}",
        f"risk: {args.risk}",
    ]
    if triggers:
        fm_lines.append("triggers: [" + ", ".join(f'"{t}"' for t in triggers) + "]")
    if tags:
        fm_lines.append("tags: [" + ", ".join(tags) + "]")
    fm_lines += [
        f"status: '[NEW]'",
        f"created_at: {datetime.now(timezone.utc).isoformat()}",
        "---",
        "",
        f"# {slug.replace('-', ' ').title()}",
        "",
        f"> {args.description}",
        "",
        "## When to use",
        "",
        "- (Add 2-3 concrete situations where this skill fires.)",
        "",
        "## How it works",
        "",
        "1. (First step.)",
        "2. (Second step.)",
        "",
        "## Tools used",
        "",
        "- (Reference any `scripts/<name>.py` this skill calls.)",
        "",
        "## Related skills",
        "",
        "- (Wiki-link other skills this one composes with.)",
        "",
    ]
    skill_md.write_text("\n".join(fm_lines), encoding="utf-8")
    print(f"  Created {skill_md.relative_to(PROJECT_ROOT)}")
    return _post_create(["skill", slug, str(skill_md.relative_to(PROJECT_ROOT))])


# ── Script creation ─────────────────────────────────────────────────────────

def create_script(args) -> int:
    slug = _slug(args.name).replace("-", "_")
    py = SCRIPTS_DIR / f"{slug}.py"
    if py.exists():
        print(f"ERROR: scripts/{slug}.py already exists", file=sys.stderr)
        return 1
    docstring = f'"""\n{args.description}\n\n'
    docstring += "USAGE\n-----\n"
    docstring += f"    python scripts/{slug}.py --help\n"
    docstring += '"""\n'
    body = (
        docstring
        + "from __future__ import annotations\n"
        + "\nimport argparse\nimport json\nimport sys\n"
        + "\n\ndef main() -> int:\n"
        + f"    p = argparse.ArgumentParser(description={args.description!r})\n"
        + "    p.add_argument('--json', dest='output_json', action='store_true')\n"
        + "    args = p.parse_args()\n"
        + "    result = {\"ok\": True, \"message\": \"" + slug + " stub — implement me\"}\n"
        + "    if args.output_json:\n"
        + "        print(json.dumps(result, indent=2))\n"
        + "    else:\n"
        + "        print(result)\n"
        + "    return 0\n"
        + "\n\nif __name__ == '__main__':\n"
        + "    sys.exit(main())\n"
    )
    py.write_text(body, encoding="utf-8")
    print(f"  Created {py.relative_to(PROJECT_ROOT)}")
    return _post_create(["script", slug, str(py.relative_to(PROJECT_ROOT))])


# ── Agent creation ──────────────────────────────────────────────────────────

def create_agent(args) -> int:
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(args.name)
    md = AGENTS_DIR / f"{slug}.md"
    if md.exists():
        print(f"ERROR: agents/{slug}.md already exists", file=sys.stderr)
        return 1
    text = (
        "---\n"
        f"name: {slug}\n"
        f"description: {args.description}\n"
        f"owner: {args.owner or _agent_name()}\n"
        f"tier: {args.tier}\n"
        "tools:\n  - Read\n  - Write\n  - Edit\n  - Bash\n"
        "---\n\n"
        f"# {slug.replace('-', ' ').title()}\n\n"
        f"> {args.description}\n\n"
        "## When to spawn this agent\n\n- (Triggers.)\n\n"
        "## What this agent owns\n\n- (Scope.)\n\n"
        "## What this agent must NOT do\n\n- (Boundaries.)\n"
    )
    md.write_text(text, encoding="utf-8")
    print(f"  Created {md.relative_to(PROJECT_ROOT)}")
    return _post_create(["agent", slug, str(md.relative_to(PROJECT_ROOT))])


# ── Workflow creation ───────────────────────────────────────────────────────

def create_workflow(args) -> int:
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(args.name)
    md = WORKFLOWS_DIR / f"{slug}.md"
    if md.exists():
        print(f"ERROR: .agents/workflows/{slug}.md already exists", file=sys.stderr)
        return 1
    text = (
        "---\n"
        f"name: {slug}\n"
        f"description: {args.description}\n"
        f"trigger: /{slug}\n"
        "---\n\n"
        f"# /{slug}\n\n"
        f"> {args.description}\n\n"
        "## Steps\n\n1. (First step.)\n2. (Second step.)\n3. (Last step — verify + commit.)\n"
    )
    md.write_text(text, encoding="utf-8")
    print(f"  Created {md.relative_to(PROJECT_ROOT)}")
    return _post_create(["workflow", slug, str(md.relative_to(PROJECT_ROOT))])


# ── Post-create hook: rebuild graph + audit ────────────────────────────────

def _post_create(meta: list[str]) -> int:
    """Rebuild the capability graph + run self_audit. Returns 0 on full green."""
    print("  Rebuilding capability graph...")
    r = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "build_capability_graph.py")],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        print(f"  WARN: graph build returned {r.returncode}: {r.stderr[:200]}")
    else:
        print("  " + r.stdout.strip().splitlines()[0])

    print("  Running self-audit...")
    audit_path = SCRIPTS_DIR / "self_audit.py"
    if audit_path.exists():
        r = subprocess.run(
            [sys.executable, str(audit_path), "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            try:
                data = json.loads(r.stdout)
                score = data.get("health_score", 0)
                print(f"  Health: {score}/100")
            except json.JSONDecodeError:
                print("  WARN: could not parse self_audit output")
        else:
            print(f"  WARN: self_audit exited {r.returncode}")

    print(f"\n  NEXT STEPS for {meta[0]} '{meta[1]}':")
    if meta[0] == "skill":
        print(f"    1. Edit {meta[2]} — fill in 'When to use', 'How it works', 'Tools used'")
        print(f"    2. If destructive (sends/posts/pays/deletes): set `disable-model-invocation: true` in frontmatter")
        print(f"    3. Reference real `scripts/<name>.py` in 'Tools used' so the graph builder infers an edge")
    elif meta[0] == "script":
        print(f"    1. Implement the real CLI in {meta[2]} — replace the stub `result = {{...}}` line")
        print(f"    2. Always support `--json` flag for agent consumption")
        print(f"    3. Run `python {meta[2]} --help` to verify argparse setup")
    elif meta[0] == "agent":
        print(f"    1. Edit {meta[2]} — define 'When to spawn', 'Scope', 'Boundaries'")
        print(f"    2. Set `tools:` frontmatter to the minimum needed (Anthropic safety pattern)")
    elif meta[0] == "workflow":
        print(f"    1. Edit {meta[2]} — write the actual numbered steps")
        print(f"    2. The trigger `/{meta[1]}` is now discoverable via capability_query")
    return 0


def cmd_list(_args) -> int:
    """List every registered capability via the graph."""
    cmd = [sys.executable, str(SCRIPTS_DIR / "capability_query.py"), "stats", "--json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        print(r.stdout.strip())
    else:
        print(f"ERROR: {r.stderr[:200]}", file=sys.stderr)
        return 1
    return 0


def cmd_validate(args) -> int:
    """Re-run capability graph build + audit on existing capability."""
    return _post_create(["validate", args.name, args.name])


def main() -> int:
    p = argparse.ArgumentParser(description="Register a new capability (skill/script/agent/workflow).")
    sub = p.add_subparsers(dest="command")

    common_create = argparse.ArgumentParser(add_help=False)
    common_create.add_argument("name")
    common_create.add_argument("--description", "-d", required=True,
                               help="One-sentence summary")
    common_create.add_argument("--tier", default="specialized",
                               choices=sorted(VALID_TIERS))
    common_create.add_argument("--risk", default="low",
                               choices=sorted(VALID_RISKS))
    common_create.add_argument("--owner", default=None)
    common_create.add_argument("--triggers", default=None,
                               help="Comma-separated trigger phrases")
    common_create.add_argument("--tags", default=None,
                               help="Comma-separated tags")

    sub.add_parser("skill", parents=[common_create], help="Scaffold a new skill")
    sub.add_parser("script", parents=[common_create], help="Scaffold a new script")
    sub.add_parser("agent", parents=[common_create], help="Scaffold a new sub-agent")
    sub.add_parser("workflow", parents=[common_create], help="Scaffold a new workflow")
    sub.add_parser("list", help="List every registered capability")
    pv = sub.add_parser("validate", help="Re-validate an existing capability")
    pv.add_argument("name")

    args = p.parse_args()
    if args.command == "skill":     return create_skill(args)
    if args.command == "script":    return create_script(args)
    if args.command == "agent":     return create_agent(args)
    if args.command == "workflow":  return create_workflow(args)
    if args.command == "list":      return cmd_list(args)
    if args.command == "validate":  return cmd_validate(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
