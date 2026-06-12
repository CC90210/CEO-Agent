"""
Build Capability Graph — auto-discover every skill, script, agent, MCP server,
workflow, and integration in this repo and emit a single machine-readable
graph at brain/CAPABILITY_GRAPH.json.

This is the canonical source of truth for "what can this agent do?" Replaces
six different ad-hoc listings (CLAUDE.md, brain/CAPABILITIES.md, AGENTS.md,
QUICK_REFERENCE.md, skill READMEs, the V6 stack section) with one structured
file. Agents query the graph at runtime to:

  - Resolve a user intent to the right skill/script/agent (routing).
  - Find every capability tagged with a given domain (discovery).
  - Detect unwired skills (no triggers, no inbound references).
  - Validate consistency at audit time.

USAGE
-----
    python scripts/build_capability_graph.py                # build, write JSON
    python scripts/build_capability_graph.py --json         # build + print to stdout
    python scripts/build_capability_graph.py --check        # exit 1 if drift detected
    python scripts/build_capability_graph.py --query <kind> # filter to one kind

OUTPUT FORMAT
-------------
    {
      "schema_version": "1.0",
      "agent": "bravo",
      "generated_at": "2026-05-02T...",
      "totals": { "skills": N, "scripts": N, "agents": N, "mcp_servers": N, "workflows": N },
      "nodes": [
        {
          "id": "skill:autonomous-loop",
          "kind": "skill",                    # skill | script | agent | mcp | workflow | integration
          "name": "autonomous-loop",
          "path": "skills/autonomous-loop/SKILL.md",
          "description": "...",               # from frontmatter or docstring
          "tier": "specialized",              # core | specialized | meta | safety
          "owner": "bravo",
          "risk": "low",                      # low | medium | high
          "triggers": ["..."],
          "tags": [...],
          "tools_used": [...],                # references to script: nodes
          "skills_required": [...],           # references to other skill: nodes
          "discovery": "auto-frontmatter"     # auto-frontmatter | auto-docstring | manual
        }
      ],
      "edges": [
        {"from": "skill:outreach-send", "to": "script:send_gateway.py", "kind": "uses"},
        {"from": "skill:outreach-send", "to": "skill:draft-critic", "kind": "requires"}
      ],
      "drift": [...]   # capabilities the auto-discoverer can't classify
    }

DISCOVERY RULES
---------------
SKILLS    — every skills/<name>/SKILL.md with YAML frontmatter
            (name, description, tier, owner, risk, triggers, tags)
SCRIPTS   — every scripts/*.py with module docstring (excluding _private, test_*)
AGENTS    — every agents/<name>.md and .claude/agents/<name>.md
MCP       — every server in .claude/mcp.json or .vscode/mcp.json
WORKFLOWS — every .agents/workflows/*.md
INTEGRATIONS — env vars in .env.example matched against known providers

EDGES (RELATIONSHIPS)
---------------------
skill -> uses       -> script        (skill body mentions `scripts/<name>.py`)
skill -> requires   -> skill         (skill frontmatter `required_skills: [...]`)
skill -> registered_with -> mcp     (skill body mentions an MCP server name)
agent -> implements -> skill         (agent file mentions a skill it owns)
script -> calls -> script             (Python import or subprocess call)

ADDING A NEW SKILL/SCRIPT (THE ONE WORKFLOW)
--------------------------------------------
1. Drop the file (skills/<name>/SKILL.md or scripts/<name>.py) with proper
   frontmatter or docstring.
2. Run `python scripts/build_capability_graph.py` — graph regenerates.
3. self_audit.py reads the graph; orphans surface immediately.
4. Other agents auto-discover via the graph at next session.

That's it. No more six-file ritual. No more drift between CLAUDE.md and
CAPABILITIES.md. The graph IS the registry.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = PROJECT_ROOT / "brain" / "CAPABILITY_GRAPH.json"

# Frontmatter regex — minimal YAML parser for our specific schema.
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TRIGGER_RE = re.compile(r"^triggers?\s*:\s*(.*)$", re.MULTILINE)
TAGS_RE = re.compile(r"^tags?\s*:\s*\[(.*?)\]", re.MULTILINE | re.DOTALL)


def _agent_name() -> str:
    """Detect which agent this repo belongs to from CLAUDE.md or directory name."""
    claude_md = PROJECT_ROOT / "CLAUDE.md"
    if claude_md.exists():
        head = claude_md.read_text(encoding="utf-8", errors="ignore")[:500].lower()
        for name in ("bravo", "atlas", "maven", "aura", "hermes"):
            if name in head:
                return name
    return PROJECT_ROOT.name.lower()


def _read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_after_frontmatter). Empty dict if no FM."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return {}, ""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = text[m.end():]
    fm: dict[str, Any] = {}
    # Parse simple key: value pairs (no nested objects). Lists in [a, b, c] form.
    for line in fm_text.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # Quoted strings
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        # Inline lists [a, b, c]
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            value = [v.strip().strip("'\"") for v in inner.split(",") if v.strip()]
        fm[key] = value
    return fm, body


def _python_docstring(path: Path) -> str:
    """Extract the module-level docstring's first paragraph.

    Uses ``ast.get_docstring`` so shebangs (``#!/usr/bin/env python3``) and
    encoding declarations (``# -*- coding: utf-8 -*-``) before the docstring
    do not falsely trigger the missing-docstring drift signal.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):  # ValueError: source contains null bytes
        return ""
    doc = ast.get_docstring(tree) or ""
    if not doc:
        return ""
    return doc.split("\n\n", 1)[0].strip().replace("\n", " ")[:280]


# ── Discoverers ──────────────────────────────────────────────────────────────

SKIP_SKILL_DIRS = {"_archive", "in-progress", "deprecated"}


def _parse_requires(value: Any) -> dict[str, list[str]]:
    """Parse the `requires:` frontmatter block per ADR-0001.

    Accepts either an inline form ``[env:STRIPE_KEY, daemon:event-router]``
    or the absence of the field. The frontmatter loader in this script is
    intentionally minimal (no nested YAML), so the inline form is the
    canonical shape skills should use until a real YAML parser lands.

    Returns ``{"env": [...], "daemons": [...], "state": [...]}``.
    """
    out: dict[str, list[str]] = {"env": [], "daemons": [], "state": []}
    if not value:
        return out
    items: list[str] = []
    if isinstance(value, list):
        items = [str(x) for x in value]
    elif isinstance(value, str):
        items = [v.strip() for v in value.strip("[]").split(",") if v.strip()]
    for raw in items:
        if ":" not in raw:
            continue
        kind, _, name = raw.partition(":")
        kind = kind.strip().lower()
        name = name.strip().strip("'\"")
        if kind in ("env", "envvar", "env_var"):
            out["env"].append(name)
        elif kind in ("daemon", "pm2"):
            out["daemons"].append(name)
        elif kind in ("state", "file", "db"):
            out["state"].append(name)
    return out


def discover_skills() -> list[dict[str, Any]]:
    skills_dir = PROJECT_ROOT / "skills"
    if not skills_dir.exists():
        return []
    out = []
    for sub in sorted(skills_dir.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        if sub.name in SKIP_SKILL_DIRS:
            continue
        skill_md = sub / "SKILL.md"
        if not skill_md.exists():
            continue
        fm, body = _read_frontmatter(skill_md)
        triggers = fm.get("triggers", [])
        if isinstance(triggers, str):
            triggers = [t.strip() for t in triggers.strip("[]").split(",") if t.strip()]
        out.append({
            "id": f"skill:{sub.name}",
            "kind": "skill",
            "name": fm.get("name") or sub.name,
            "path": str(skill_md.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "description": (fm.get("description") or "")[:280],
            "tier": fm.get("tier", "specialized"),
            "owner": fm.get("owner", _agent_name()),
            "risk": fm.get("risk", "low"),
            "triggers": triggers if isinstance(triggers, list) else [],
            "tags": fm.get("tags", []) if isinstance(fm.get("tags"), list) else [],
            "status": fm.get("status", "[VALIDATED]"),
            "disable_model_invocation": bool(fm.get("disable-model-invocation") or fm.get("disable_model_invocation")),
            "argument_hint": fm.get("argument-hint") or fm.get("argument_hint"),
            "requires": _parse_requires(fm.get("requires")),
            "archived": fm.get("archived"),
            "superseded_by": fm.get("superseded_by"),
            "discovery": "auto-frontmatter" if fm.get("name") else "auto-foldername",
            "_body": body[:2000],  # used for edge inference, dropped in output
        })
    return out


def discover_scripts() -> list[dict[str, Any]]:
    scripts_dir = PROJECT_ROOT / "scripts"
    if not scripts_dir.exists():
        return []
    out = []
    for py in sorted(scripts_dir.glob("*.py")):
        if py.name.startswith("_") or py.name.startswith("test_"):
            continue
        doc = _python_docstring(py)
        out.append({
            "id": f"script:{py.stem}",
            "kind": "script",
            "name": py.stem,
            "path": str(py.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "description": doc[:280] if doc else "(no docstring)",
            "tier": "tool",
            "owner": _agent_name(),
            "discovery": "auto-docstring" if doc else "auto-filename",
        })
    return out


def discover_agents() -> list[dict[str, Any]]:
    out = []
    for agents_dir in (PROJECT_ROOT / "agents", PROJECT_ROOT / ".claude" / "agents"):
        if not agents_dir.exists():
            continue
        for md in sorted(agents_dir.glob("*.md")):
            if md.name.startswith(("README", "INDEX", "_")):
                continue
            fm, body = _read_frontmatter(md)
            out.append({
                "id": f"agent:{md.stem}",
                "kind": "agent",
                "name": fm.get("name") or md.stem,
                "path": str(md.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "description": (fm.get("description") or "")[:280],
                "owner": fm.get("owner", _agent_name()),
                "tier": fm.get("tier", "specialized"),
                "discovery": "auto-frontmatter" if fm else "auto-filename",
            })
    return out


def discover_mcp_servers() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cfg_path in (
        PROJECT_ROOT / ".claude" / "mcp.json",
        PROJECT_ROOT / ".vscode" / "mcp.json",
    ):
        if not cfg_path.exists():
            continue
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        servers = data.get("mcpServers") or data.get("servers") or {}
        for name in servers:
            if name in seen:
                continue
            seen.add(name)
            out.append({
                "id": f"mcp:{name}",
                "kind": "mcp",
                "name": name,
                "path": str(cfg_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "description": f"MCP server registered in {cfg_path.name}",
                "owner": _agent_name(),
                "discovery": "auto-config",
            })
    return out


def discover_workflows() -> list[dict[str, Any]]:
    wf_dir = PROJECT_ROOT / ".agents" / "workflows"
    if not wf_dir.exists():
        return []
    out = []
    for md in sorted(wf_dir.glob("*.md")):
        fm, body = _read_frontmatter(md)
        out.append({
            "id": f"workflow:{md.stem}",
            "kind": "workflow",
            "name": fm.get("name") or md.stem,
            "path": str(md.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "description": (fm.get("description") or body[:200].strip())[:280],
            "owner": _agent_name(),
            "discovery": "auto-frontmatter" if fm else "auto-body",
        })
    return out


# ── Edge inference ──────────────────────────────────────────────────────────

def infer_edges(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Heuristic: if a skill body mentions `scripts/<name>.py` or another skill
    name in `[[skill:...]]` form, emit an edge."""
    script_ids = {n["name"]: n["id"] for n in nodes if n["kind"] == "script"}
    skill_ids = {n["name"]: n["id"] for n in nodes if n["kind"] == "skill"}
    edges: list[dict[str, str]] = []
    for n in nodes:
        if n["kind"] != "skill":
            continue
        body = n.get("_body", "")
        for script_name, script_id in script_ids.items():
            if f"scripts/{script_name}.py" in body or f"`{script_name}.py`" in body:
                edges.append({"from": n["id"], "to": script_id, "kind": "uses"})
        for skill_name, skill_id in skill_ids.items():
            if skill_id == n["id"]:
                continue
            if f"skills/{skill_name}/" in body or f"[[skill:{skill_name}]]" in body:
                edges.append({"from": n["id"], "to": skill_id, "kind": "requires"})
    # Dedupe
    seen = set()
    unique: list[dict[str, str]] = []
    for e in edges:
        k = (e["from"], e["to"], e["kind"])
        if k not in seen:
            seen.add(k)
            unique.append(e)
    return unique


# ── Drift detection ─────────────────────────────────────────────────────────

def detect_drift(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    for n in nodes:
        if n["kind"] == "skill" and n.get("description") in ("", "(no docstring)"):
            drift.append({"node": n["id"], "issue": "skill missing description in frontmatter"})
        if n["kind"] == "skill" and not n.get("triggers"):
            drift.append({"node": n["id"], "issue": "skill has no triggers — agent can't route to it"})
        if n["kind"] == "script" and n.get("discovery") == "auto-filename":
            drift.append({"node": n["id"], "issue": "script missing module docstring"})
    return drift


# ── Build ───────────────────────────────────────────────────────────────────

def build() -> dict[str, Any]:
    skills = discover_skills()
    scripts = discover_scripts()
    agents = discover_agents()
    mcp = discover_mcp_servers()
    workflows = discover_workflows()
    nodes = skills + scripts + agents + mcp + workflows
    edges = infer_edges(nodes)
    drift = detect_drift(nodes)
    # Strip private fields (_body) before output
    public_nodes = [{k: v for k, v in n.items() if not k.startswith("_")} for n in nodes]
    return {
        "schema_version": "1.0",
        "agent": _agent_name(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "skills": len(skills),
            "scripts": len(scripts),
            "agents": len(agents),
            "mcp_servers": len(mcp),
            "workflows": len(workflows),
            "nodes_total": len(nodes),
            "edges_total": len(edges),
            "drift_count": len(drift),
        },
        "nodes": public_nodes,
        "edges": edges,
        "drift": drift,
    }


def write_graph(graph: dict[str, Any]) -> Path:
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_PATH.write_text(json.dumps(graph, indent=2, default=str), encoding="utf-8")
    return GRAPH_PATH


def cmd_check(graph: dict[str, Any]) -> int:
    """Compare freshly-built graph against on-disk version. Exit 1 if drift."""
    if not GRAPH_PATH.exists():
        print("CAPABILITY_GRAPH.json missing — run without --check to build.")
        return 1
    old = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    old_ids = {n["id"]: n.get("description", "") for n in old.get("nodes", [])}
    new_ids = {n["id"]: n.get("description", "") for n in graph.get("nodes", [])}
    added = sorted(set(new_ids) - set(old_ids))
    removed = sorted(set(old_ids) - set(new_ids))
    if added or removed:
        print(f"DRIFT: {len(added)} added, {len(removed)} removed")
        for a in added: print(f"  + {a}")
        for r in removed: print(f"  - {r}")
        return 1
    print("OK — capability graph matches disk.")
    return 0


# ── Doc generation (--emit-docs) ─────────────────────────────────────────────
# Generated docs are DETERMINISTIC (sorted, no timestamps) so freshness can be a
# test. The capability graph is the only 100%-coverage artifact; hand-written
# routing maps drift, generated ones can't. (Audit Phase 6, 2026-06-09.)

GENERATED_HEADER = (
    "<!-- GENERATED by scripts/build_capability_graph.py --emit-docs — do NOT hand-edit. "
    "Regenerate after adding/removing skills, brain/, or memory/ files. "
    "Freshness is enforced by scripts/tests/test_generated_docs_fresh.py. -->\n"
)


def _tracked_md(subdir: str) -> list[Path]:
    """Tracked *.md files DIRECTLY under <subdir>/ (portable: excludes gitignored
    local-only files like memory/MISTAKES.md so the index is clean in a fresh clone)."""
    import subprocess
    from lib.subprocess_helpers import WINDOWLESS_FLAGS, windowless_startupinfo
    base = PROJECT_ROOT / subdir
    try:
        # creationflags + startupinfo — capability graph builds run from
        # the cron daemon; without windowless flags the git ls-files spawn
        # flashed a conhost window on every rebuild.
        out = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "ls-files", subdir],
            capture_output=True, text=True, encoding="utf-8", errors="ignore",
            creationflags=WINDOWLESS_FLAGS, startupinfo=windowless_startupinfo(),
        ).stdout
        result = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            p = PROJECT_ROOT / line
            if p.parent == base and p.suffix == ".md":
                result.append(p)
        if result:
            return sorted(result, key=lambda x: x.name)
    except Exception:  # noqa: BLE001
        pass
    return sorted(base.glob("*.md"), key=lambda x: x.name)


def _first_heading(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if s.startswith("# "):
                return s[2:].strip()
    except Exception:  # noqa: BLE001
        pass
    return "(no H1 heading)"


def _brain_category(name: str) -> str:
    n = name.upper()
    if any(k in n for k in ("VPS_", "MAC_", "MULTI_MACHINE", "CROSS_MACHINE")):
        return "Deploy & multi-machine"
    if n.endswith("_PROMPT.MD") or "PLAYBOOK" in n or "RUNBOOK" in n:
        return "Prompts & playbooks"
    if any(k in n for k in ("ROUTER", "INTENTS", "WHEN_TO_USE", "CAPABILIT", "QUICK_REFERENCE", "INDEX")):
        return "Routing & capability map"
    if any(k in n for k in ("SOUL", "USER", "STATE", "SECURITY", "EXECUTION_RULES",
                            "ORCHESTRATION", "AGENT", "DECISION", "GROWTH", "HEARTBEAT", "INTERACTION")):
        return "Core identity & governance"
    return "Reference & architecture"


def emit_when_to_use_skills(graph: dict[str, Any]) -> str:
    skills = sorted((n for n in graph["nodes"] if n["kind"] == "skill"), key=lambda n: n["name"])
    out = [GENERATED_HEADER.rstrip(), "", "# When To Use Skills", "",
           f"Auto-generated from `brain/CAPABILITY_GRAPH.json` — **{len(skills)} active skills**. "
           "Each entry: what it's for (use-when) → trigger phrases → path. Resolve an intent at "
           "runtime with `python scripts/capability_query.py resolve \"<intent>\"` instead of grepping this file.", ""]
    for s in skills:
        trig = ", ".join(s.get("triggers") or []) or "—"
        desc = (s.get("description") or "").strip() or "—"
        flag = " — _explicit `/command` only_" if s.get("disable_model_invocation") else ""
        out.append(f"## {s['name']}{flag}")
        out.append(f"- **Use when:** {desc}")
        out.append(f"- **Triggers:** {trig}")
        out.append(f"- **Path:** `{s['path']}` · tier `{s.get('tier','specialized')}` · risk `{s.get('risk','low')}`")
        out.append("")
    return "\n".join(out) + "\n"


def emit_dir_index(subdir: str, title: str, categorize: bool) -> str:
    files = _tracked_md(subdir)
    buckets: dict[str, list[Path]] = {}
    for p in files:
        cat = _brain_category(p.name) if categorize else "Files"
        buckets.setdefault(cat, []).append(p)
    out = [GENERATED_HEADER.rstrip(), "", f"# {title}", "",
           f"Auto-generated index of tracked `{subdir}/*.md` — **{len(files)} files**. "
           "Each file's first H1 is its description. Local-only (gitignored) files are intentionally omitted.", ""]
    for cat in sorted(buckets):
        out.append(f"## {cat}")
        for p in buckets[cat]:
            out.append(f"- [{p.name}]({p.name}) — {_first_heading(p)}")
        out.append("")
    return "\n".join(out) + "\n"


def emit_memory_index_pointer() -> str:
    return (
        GENERATED_HEADER.rstrip() + "\n\n"
        "# Memory Index — moved\n\n"
        "The canonical, auto-generated memory index now lives in "
        "[memory/INDEX.md](INDEX.md) (built from tracked `memory/*.md`).\n\n"
        "This file is kept as a stable pointer only — inbound wiki-links such as "
        "`[[memory/MEMORY_INDEX]]` still resolve here. Do not hand-edit; see INDEX.md.\n"
    )


GENERATED_DOCS = {
    "brain/WHEN_TO_USE_SKILLS.md": lambda g: emit_when_to_use_skills(g),
    "brain/INDEX.md": lambda g: emit_dir_index("brain", "Brain Index", categorize=True),
    "memory/INDEX.md": lambda g: emit_dir_index("memory", "Memory Index", categorize=False),
    "memory/MEMORY_INDEX.md": lambda g: emit_memory_index_pointer(),
}


def render_generated_docs(graph: dict[str, Any]) -> dict[str, str]:
    """Return {relpath: content} for every generated doc — used by --emit-docs
    and by test_generated_docs_fresh.py (no temp files needed)."""
    return {rel: fn(graph) for rel, fn in GENERATED_DOCS.items()}


def cmd_emit_docs(graph: dict[str, Any]) -> int:
    # The brain/memory indexes list the first-H1 of files they THEMSELVES
    # generate (INDEX.md, WHEN_TO_USE_SKILLS.md, MEMORY_INDEX.md), so a single
    # render can lag one step behind. Iterate to a fixed point (bounded) so the
    # output is idempotent — required for the freshness test to be stable.
    last_changed: list[str] = []
    for _ in range(5):
        last_changed = []
        for rel, content in render_generated_docs(graph).items():
            path = PROJECT_ROOT / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            old = path.read_text(encoding="utf-8") if path.exists() else None
            if old != content:
                path.write_text(content, encoding="utf-8")
                last_changed.append(rel)
        if not last_changed:
            break
    for rel in render_generated_docs(graph):
        print(f"  wrote {rel}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Build the capability graph.")
    p.add_argument("--json", dest="output_json", action="store_true",
                   help="Print full graph JSON to stdout instead of writing the file")
    p.add_argument("--check", action="store_true",
                   help="Exit 1 if on-disk graph is out of sync")
    p.add_argument("--query", choices=["skill", "script", "agent", "mcp", "workflow"],
                   help="Filter nodes by kind")
    p.add_argument("--emit-docs", action="store_true",
                   help="Regenerate brain/WHEN_TO_USE_SKILLS.md, brain/INDEX.md, memory/INDEX.md "
                        "from the graph (deterministic; do not hand-edit the outputs)")
    args = p.parse_args()

    graph = build()

    if args.emit_docs:
        print("Emitting generated routing docs from the capability graph:")
        return cmd_emit_docs(graph)

    if args.check:
        return cmd_check(graph)

    if args.query:
        filtered = [n for n in graph["nodes"] if n["kind"] == args.query]
        out = {"agent": graph["agent"], "kind": args.query,
               "count": len(filtered), "nodes": filtered}
        print(json.dumps(out, indent=2))
        return 0

    if args.output_json:
        print(json.dumps(graph, indent=2))
        return 0

    path = write_graph(graph)
    t = graph["totals"]
    print(f"Wrote {path.relative_to(PROJECT_ROOT)}")
    print(f"  Nodes: {t['nodes_total']} ({t['skills']} skills, {t['scripts']} scripts, "
          f"{t['agents']} agents, {t['mcp_servers']} MCP, {t['workflows']} workflows)")
    print(f"  Edges: {t['edges_total']}")
    if t["drift_count"]:
        print(f"  Drift: {t['drift_count']} (run with --json to see details)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
