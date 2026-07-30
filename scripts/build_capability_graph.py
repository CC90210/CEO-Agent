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
      "schema_version": "1.2",
      "agent": "bravo",
      "generated_at": "2026-05-02T...",
      "totals": { "skills": N, "scripts": N, "agents": N, "mcp_servers": N, "workflows": N },
      "nodes": [
        {
          "id": "skill:autonomous-loop",
          "kind": "skill",                    # skill | script | agent | mcp | workflow | resource | runtime
          "name": "autonomous-loop",
          "path": "skills/autonomous-loop/SKILL.md",
          "description": "...",               # from frontmatter or docstring
          "tier": "specialized",              # core | specialized | meta | safety
          "owner": "bravo",
          "category": "outbound.safety",      # script operating domain
          "lifecycle": "active",              # active | manual | one_off | deprecated
          "risk": "external_write",           # read_only | local_write | external_write | destructive
          "triggers": ["..."],
          "project": "sunbiz",
          "bridge": {"visible": true, "confirm": true},
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
RESOURCES — rows of the Free-Tier Radar table in brain/TOOL_SHED.md (V7.1)
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

from lib.capability_metadata import (
    capability_meta_declared,
    capability_meta_from_tree,
    read_capability_meta,
    validate_capability_meta,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = PROJECT_ROOT / "brain" / "CAPABILITY_GRAPH.json"

RUNTIME_ENTRYPOINTS = (
    {
        "id": "runtime:bridge_chat_server",
        "name": "bridge_chat_server",
        "path": "bravo_cli/bridge_chat_server.py",
        "role": "chat_bridge",
        "language": "python",
        "description": "Guarded chat-to-CLI execution runtime.",
    },
    {
        "id": "runtime:cron_engine",
        "name": "cron_engine",
        "path": "scripts/core/cron_engine.py",
        "role": "scheduler_registry",
        "language": "python",
        "description": "Canonical scheduled-job registry and operator CLI.",
    },
    {
        "id": "runtime:telegram_agent",
        "name": "telegram_agent",
        "path": "telegram_agent.js",
        "role": "telegram_gateway",
        "language": "javascript",
        "description": "Telegram operator gateway and guarded command router.",
    },
)
NESTED_SCRIPT_SKIP_PARTS = frozenset({"_archive", "__pycache__", "tests"})

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
    out: list[dict[str, Any]] = []
    by_stem: dict[str, dict[str, Any]] = {}
    top_level = sorted(scripts_dir.glob("*.py"))
    nested = sorted(py for py in scripts_dir.rglob("*.py") if py.parent != scripts_dir)
    for py in [*top_level, *nested]:
        rel_to_scripts = py.relative_to(scripts_dir)
        if py.name.startswith("_") or py.name.startswith("test_"):
            continue
        if any(part in NESTED_SCRIPT_SKIP_PARTS for part in rel_to_scripts.parts[:-1]):
            continue
        try:
            source = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            source = ""
        try:
            tree: ast.Module | None = ast.parse(source)
        except (SyntaxError, ValueError):
            tree = None
        is_nested = len(rel_to_scripts.parts) > 1
        if is_nested and (tree is None or not capability_meta_declared(tree)):
            continue
        doc = _python_docstring(py)
        metadata_error = ""
        try:
            meta = capability_meta_from_tree(tree) if tree is not None else None
        except ValueError as exc:
            meta = None
            metadata_error = str(exc)
        node: dict[str, Any] = {
            "id": f"script:{py.stem}",
            "kind": "script",
            "name": py.stem,
            "path": str(py.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "description": doc[:280] if doc else "(no docstring)",
            "tier": "tool",
            "owner": _agent_name(),
            "discovery": "auto-docstring" if doc else "auto-filename",
            "_source": source,
        }
        if meta is not None:
            node.update({
                "category": meta.get("category"),
                "lifecycle": meta.get("lifecycle"),
                "risk": meta.get("risk"),
                "triggers": meta.get("triggers", []),
                "owner": meta.get("owner", _agent_name()),
                "project": meta.get("project"),
                "bridge": meta.get("bridge", {}),
                "discovery": "auto-capability-meta",
                "_metadata_errors": validate_capability_meta(meta),
            })
        elif metadata_error:
            node["_metadata_errors"] = [metadata_error]
        if py.stem in by_stem:
            existing = by_stem[py.stem]
            existing.setdefault("_metadata_errors", []).append(
                f"duplicate script stem also declared at {node['path']}"
            )
            continue
        out.append(node)
        by_stem[py.stem] = node
    return out


def discover_runtime_entrypoints() -> list[dict[str, Any]]:
    """Emit the small, explicit set of long-lived orchestration runtimes."""
    out: list[dict[str, Any]] = []
    for spec in RUNTIME_ENTRYPOINTS:
        path = PROJECT_ROOT / spec["path"]
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            source = ""
        out.append({
            **spec,
            "kind": "runtime",
            "owner": _agent_name(),
            "available": path.is_file(),
            "discovery": "explicit-runtime-registry",
            "_source": source,
        })
    return out


def discover_agents() -> list[dict[str, Any]]:
    # V7.2.0: recursive (rglob) so subdirs like agents/voltagent/ are graph-visible
    # (they were silently invisible from 2026-04-21 to V7.2.0). Node ids are
    # `agent:<stem>` with no dir qualifier, so stems are deduped with explicit
    # precedence: .claude/agents/ (native spawnable definitions) wins collisions;
    # shadowed copies (architect/debugger/researcher in agents/, voltagent
    # code-reviewer) are skipped rather than emitted as duplicate node ids.
    out = []
    seen: set[str] = set()
    for agents_dir in (PROJECT_ROOT / ".claude" / "agents", PROJECT_ROOT / "agents"):
        if not agents_dir.exists():
            continue
        for md in sorted(agents_dir.rglob("*.md")):
            if md.name.startswith(("README", "INDEX", "_")):
                continue
            if md.stem in seen:
                continue
            seen.add(md.stem)
            fm, body = _read_frontmatter(md)
            # V7.4: surface triggers/tags/model/tools so the resolver can score
            # agents like it scores skills (trigger overlap weighs 2×) and so
            # tool scoping is graph-visible for orchestration decisions.
            triggers = fm.get("triggers", [])
            if isinstance(triggers, str):
                triggers = [t.strip() for t in triggers.strip("[]").split(",") if t.strip()]
            tags = fm.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.strip("[]").split(",") if t.strip()]
            tools = fm.get("tools", [])
            if isinstance(tools, str):
                tools = [t.strip() for t in tools.strip("[]").split(",") if t.strip()]
            out.append({
                "id": f"agent:{md.stem}",
                "kind": "agent",
                "name": fm.get("name") or md.stem,
                "path": str(md.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "description": (fm.get("description") or "")[:280],
                "owner": fm.get("owner", _agent_name()),
                "tier": fm.get("tier", "specialized"),
                "model": fm.get("model", ""),
                "tools": tools,
                "triggers": triggers,
                "tags": tags,
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
        if md.name.startswith(("INDEX", "README", "_")):
            continue
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


# V7.1: external-resource radar (brain/TOOL_SHED.md § Free-Tier Radar).
# The table's row contract is documented in the section header itself; slugs are
# stable IDs so `resource:` nodes survive rebuilds. Status enum kept in sync with
# ADR-0010.
RADAR_SECTION_RE = re.compile(r"^##\s+.*Free-Tier Radar\s*$", re.MULTILINE)
RADAR_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
RADAR_STATUSES = {"candidate", "adopted", "rejected", "policy"}


def discover_resources() -> list[dict[str, Any]]:
    """Parse the Free-Tier Radar table in brain/TOOL_SHED.md into resource nodes."""
    shed = PROJECT_ROOT / "brain" / "TOOL_SHED.md"
    if not shed.exists():
        return []
    text = shed.read_text(encoding="utf-8", errors="ignore")
    m = RADAR_SECTION_RE.search(text)
    if not m:
        return []
    section = text[m.end():]
    nxt = re.search(r"^##\s+", section, re.MULTILINE)
    if nxt:
        section = section[:nxt.start()]
    out: list[dict[str, Any]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 8 or cells[0].lower() == "slug" or set(cells[0]) <= {"-", ":", " "}:
            continue
        slug, capability, service, free_tier, auth, status, conflicts, verified = cells[:8]
        link = RADAR_LINK_RE.search(service)
        name = link.group(1) if link else service
        out.append({
            "id": f"resource:{slug}",
            "kind": "resource",
            "name": name,
            "path": "brain/TOOL_SHED.md",
            "description": f"{capability} — free tier: {free_tier} — {conflicts}"[:280],
            "capability": capability,
            "status": status,
            "auth": auth,
            "source_url": link.group(2) if link else None,
            "verified": verified,
            "owner": _agent_name(),
            "triggers": [capability],
            "tags": ["free-tier", "radar", status],
            "discovery": "auto-radar-table",
        })
    return out


# ── Edge inference ──────────────────────────────────────────────────────────

def infer_edges(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Infer static routing, execution, scheduling, and exposure relationships."""
    scripts = [n for n in nodes if n["kind"] == "script"]
    script_ids = {n["name"]: n["id"] for n in scripts}
    skill_ids = {n["name"]: n["id"] for n in nodes if n["kind"] == "skill"}
    runtime_ids = {n["name"]: n["id"] for n in nodes if n["kind"] == "runtime"}
    edges: list[dict[str, str]] = []

    def literal_target_ids(node: ast.AST) -> set[str]:
        targets: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Constant) or not isinstance(child.value, str):
                continue
            literal = child.value.replace("\\", "/")
            for script in scripts:
                path = str(script.get("path", "")).replace("\\", "/")
                basename = path.rsplit("/", 1)[-1]
                if (
                    literal == path
                    or literal.endswith(f"/{path}")
                    or re.search(rf"(?:^|/){re.escape(basename)}(?:$|\b)", literal)
                ):
                    targets.add(script["id"])
        return targets

    def python_relationships(node: dict[str, Any]) -> tuple[set[str], set[str], ast.Module]:
        source = node.get("_source", "")
        called: set[str] = set()
        configured: set[str] = set()
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            tree = ast.Module(body=[], type_ignores=[])

        assigned_targets: dict[str, set[str]] = {}
        for item in ast.walk(tree):
            if isinstance(item, ast.Import):
                for alias in item.names:
                    target = script_ids.get(alias.name.rsplit(".", 1)[-1])
                    if target:
                        called.add(target)
            elif isinstance(item, ast.ImportFrom):
                if item.module:
                    target = script_ids.get(item.module.rsplit(".", 1)[-1])
                    if target:
                        called.add(target)
                for alias in item.names:
                    target = script_ids.get(alias.name)
                    if target:
                        called.add(target)
            elif isinstance(item, (ast.Assign, ast.AnnAssign)):
                value = item.value
                targets = literal_target_ids(value) if value is not None else set()
                names: list[str] = []
                if isinstance(item, ast.Assign):
                    names = [target.id for target in item.targets if isinstance(target, ast.Name)]
                elif isinstance(item.target, ast.Name):
                    names = [item.target.id]
                for name in names:
                    assigned_targets.setdefault(name, set()).update(targets)
                    if name.endswith(("_SCRIPT", "_TOOL", "_PATH", "_CMD", "_EXECUTABLE")):
                        configured.update(targets)

        subprocess_attrs = {"run", "Popen", "call", "check_call", "check_output"}
        subprocess_names = {"_safe_popen"}
        for item in ast.walk(tree):
            if not isinstance(item, ast.Call):
                continue
            is_subprocess = (
                isinstance(item.func, ast.Attribute) and item.func.attr in subprocess_attrs
            ) or (
                isinstance(item.func, ast.Name) and item.func.id in subprocess_names
            )
            if not is_subprocess:
                continue
            called.update(literal_target_ids(item))
            for child in ast.walk(item):
                if isinstance(child, ast.Name):
                    called.update(assigned_targets.get(child.id, set()))
        return called, configured, tree

    def javascript_exposed_targets(source: str) -> set[str]:
        """Find script paths passed to child-process calls, excluding prompt text."""
        paths: set[str] = set()
        path_re = re.compile(r"scripts/[A-Za-z0-9_./-]+\.py")
        call_re = re.compile(r"\b(?:exec|execFile[A-Za-z0-9_]*|spawn[A-Za-z0-9_]*)\s*\(")
        for segment in source.split(";"):
            if call_re.search(segment):
                paths.update(path_re.findall(segment))
        assignment_re = re.compile(
            r"(?:const|let|var)\s+(\w+)\s*=\s*`[^`\n]*(scripts/[A-Za-z0-9_./-]+\.py)[^`]*`"
        )
        for match in assignment_re.finditer(source):
            variable, path = match.groups()
            tail = source[match.end():match.end() + 2000]
            if re.search(
                rf"\bexecFile[A-Za-z0-9_]*\s*\([\s\S]{{0,1000}}\b{re.escape(variable)}\b",
                tail,
            ):
                paths.add(path)
        targets: set[str] = set()
        for path in paths:
            targets.update(literal_target_ids(ast.Constant(value=path)))
        return targets

    for n in nodes:
        if n["kind"] == "skill":
            body = n.get("_body", "")
            for script in scripts:
                path = str(script.get("path", ""))
                basename = path.rsplit("/", 1)[-1]
                if path in body or f"`{basename}`" in body:
                    edges.append({"from": n["id"], "to": script["id"], "kind": "uses"})
            for skill_name, skill_id in skill_ids.items():
                if skill_id == n["id"]:
                    continue
                if f"skills/{skill_name}/" in body or f"[[skill:{skill_name}]]" in body:
                    edges.append({"from": n["id"], "to": skill_id, "kind": "requires"})
        elif n["kind"] in {"script", "runtime"} and n.get("language", "python") == "python":
            called, configured, tree = python_relationships(n)
            for script_id in sorted(called):
                if script_id != n["id"]:
                    edges.append({"from": n["id"], "to": script_id, "kind": "calls"})
            for script_id in sorted(configured - called):
                if script_id != n["id"]:
                    edges.append({"from": n["id"], "to": script_id, "kind": "references"})
            bridge = n.get("bridge") or {}
            bridge_runtime = runtime_ids.get("bridge_chat_server")
            if bridge.get("visible") is True and bridge_runtime:
                edges.append({"from": n["id"], "to": bridge_runtime, "kind": "exposed_via"})
            if n["id"] == runtime_ids.get("cron_engine"):
                for item in ast.walk(tree):
                    if not isinstance(item, ast.Dict):
                        continue
                    for key, value in zip(item.keys, item.values):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value == "script"
                            and isinstance(value, ast.Constant)
                            and isinstance(value.value, str)
                        ):
                            for script_id in literal_target_ids(value):
                                edges.append({
                                    "from": n["id"],
                                    "to": script_id,
                                    "kind": "schedules",
                                })
        elif n["id"] == runtime_ids.get("telegram_agent"):
            for script_id in javascript_exposed_targets(n.get("_source", "")):
                edges.append({"from": n["id"], "to": script_id, "kind": "exposes"})
    # Dedupe
    seen = set()
    unique: list[dict[str, str]] = []
    for e in edges:
        k = (e["from"], e["to"], e["kind"])
        if k not in seen:
            seen.add(k)
            unique.append(e)
    return sorted(unique, key=lambda edge: (edge["from"], edge["to"], edge["kind"]))


# ── Drift detection ─────────────────────────────────────────────────────────

def detect_drift(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    for n in nodes:
        # '>' / '|' = a YAML block-scalar marker captured verbatim by the naive
        # line parser — the real description was on the continuation lines and
        # got lost. Six skills shipped routing-blind for weeks because this
        # condition didn't treat that as drift (2026-07-09 audit).
        if n["kind"] == "skill" and n.get("description") in ("", ">", "|", "(no docstring)"):
            drift.append({"node": n["id"], "issue": "skill missing description in frontmatter"})
        if n["kind"] == "skill" and not n.get("triggers"):
            drift.append({"node": n["id"], "issue": "skill has no triggers — agent can't route to it"})
        if n["kind"] == "script" and n.get("discovery") == "auto-filename":
            drift.append({"node": n["id"], "issue": "script missing module docstring"})
        for issue in n.get("_metadata_errors", []):
            drift.append({"node": n["id"], "issue": f"invalid CAPABILITY_META: {issue}"})
        if n["kind"] == "runtime" and not n.get("available"):
            drift.append({"node": n["id"], "issue": f"runtime entrypoint missing: {n.get('path')}"})
        if n["kind"] == "resource" and n.get("status") not in RADAR_STATUSES:
            drift.append({"node": n["id"],
                          "issue": f"radar row status '{n.get('status')}' not in {sorted(RADAR_STATUSES)}"})
    return drift


# ── Build ───────────────────────────────────────────────────────────────────

def build() -> dict[str, Any]:
    skills = discover_skills()
    scripts = discover_scripts()
    agents = discover_agents()
    mcp = discover_mcp_servers()
    workflows = discover_workflows()
    resources = discover_resources()
    runtimes = discover_runtime_entrypoints()
    nodes = skills + scripts + agents + mcp + workflows + resources + runtimes
    edges = infer_edges(nodes)
    drift = detect_drift(nodes)
    # Strip private fields (_body) before output
    public_nodes = [{k: v for k, v in n.items() if not k.startswith("_")} for n in nodes]
    return {
        "schema_version": "1.2",
        "agent": _agent_name(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "skills": len(skills),
            "scripts": len(scripts),
            "agents": len(agents),
            "mcp_servers": len(mcp),
            "workflows": len(workflows),
            "resources": len(resources),
            "runtime_entrypoints": len(runtimes),
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


def normalize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic graph view with volatile timestamps removed."""
    normalized = {
        key: value for key, value in graph.items()
        if key not in {"generated_at", "generated_at_iso"}
    }
    normalized["nodes"] = sorted(normalized.get("nodes", []), key=lambda node: node["id"])
    normalized["edges"] = sorted(
        normalized.get("edges", []),
        key=lambda edge: (edge["from"], edge["to"], edge["kind"]),
    )
    normalized["drift"] = sorted(
        normalized.get("drift", []),
        key=lambda item: json.dumps(item, sort_keys=True),
    )
    return normalized


def cmd_check(graph: dict[str, Any]) -> int:
    """Compare the full normalized graph against disk. Exit 1 on any drift."""
    if not GRAPH_PATH.exists():
        print("CAPABILITY_GRAPH.json missing — run without --check to build.")
        return 1
    old = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    if normalize_graph(old) != normalize_graph(graph):
        old_nodes = {n["id"]: n for n in old.get("nodes", [])}
        new_nodes = {n["id"]: n for n in graph.get("nodes", [])}
        added = sorted(set(new_nodes) - set(old_nodes))
        removed = sorted(set(old_nodes) - set(new_nodes))
        changed = sorted(
            node_id for node_id in set(old_nodes) & set(new_nodes)
            if old_nodes[node_id] != new_nodes[node_id]
        )
        print(f"DRIFT: {len(added)} added, {len(removed)} removed, {len(changed)} changed")
        for node_id in added:
            print(f"  + {node_id}")
        for node_id in removed:
            print(f"  - {node_id}")
        for node_id in changed[:25]:
            print(f"  ~ {node_id}")
        if old.get("edges", []) != graph.get("edges", []):
            print("  ~ graph edges")
        if old.get("drift", []) != graph.get("drift", []):
            print("  ~ drift findings")
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
    """Versioned or new, non-ignored Markdown files directly under *subdir*."""
    import subprocess
    from lib.subprocess_helpers import WINDOWLESS_FLAGS, windowless_startupinfo
    base = PROJECT_ROOT / subdir
    try:
        # creationflags + startupinfo — capability graph builds run from
        # the cron daemon; without windowless flags the git ls-files spawn
        # flashed a conhost window on every rebuild.
        proc = subprocess.run(
            [
                "git", "-C", str(PROJECT_ROOT), "ls-files",
                "--cached", "--others", "--exclude-standard", "--", subdir,
            ],
            capture_output=True, text=True, encoding="utf-8", errors="ignore",
            creationflags=WINDOWLESS_FLAGS, startupinfo=windowless_startupinfo(),
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"git ls-files failed for {subdir}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"git ls-files failed for {subdir}: {detail}")
    result = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        path = PROJECT_ROOT / line
        if path.is_file() and path.parent == base and path.suffix == ".md":
            result.append(path)
    return sorted(result, key=lambda path: path.name)


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
        link_target = s['path'].removesuffix('.md')
        out.append(f"## [[{link_target}|{s['name']}]]{flag}")
        out.append(f"- **Use when:** {desc}")
        out.append(f"- **Triggers:** {trig}")
        out.append(f"- **Path:** `{s['path']}` · tier `{s.get('tier','specialized')}` · risk `{s.get('risk','low')}`")
        out.append("")
    return "\n".join(out) + "\n"


def emit_when_to_use_agents(graph: dict[str, Any]) -> str:
    # V7.4: agents get the same generated routing surface skills have had since
    # V6.6 — hand-maintained delegation matrices drift (the 2026-07-19 currency
    # audit found three of them disagreeing); this one regenerates from
    # frontmatter on every graph build.
    agents = sorted((n for n in graph["nodes"] if n["kind"] == "agent"), key=lambda n: n["name"])
    out = [GENERATED_HEADER.rstrip(), "", "# When To Use Agents", "",
           f"Auto-generated from `brain/CAPABILITY_GRAPH.json` — **{len(agents)} agent personas**. "
           "Each entry: what it's for → trigger phrases → model/tools scoping → path. Resolve at "
           "runtime with `python scripts/capability_query.py resolve \"<intent>\" --kind agent`. "
           "Cross-agent delegation (Maven/Atlas/Codex/apps) stays in "
           "`brain/ORCHESTRATION_DECISION_TABLE.md` §A — this file covers spawnable personas only.", ""]
    for a in agents:
        trig = ", ".join(a.get("triggers") or []) or "—"
        desc = (a.get("description") or "").strip() or "—"
        tools = ", ".join(a.get("tools") or []) or "(unscoped — full default surface)"
        model = a.get("model") or "inherit"
        out.append(f"## {a['name']}")
        out.append(f"- **Use when:** {desc}")
        out.append(f"- **Triggers:** {trig}")
        out.append(f"- **Scoping:** model `{model}` · tools: {tools}")
        out.append(f"- **Path:** `{a['path']}` · tier `{a.get('tier','specialized')}`")
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
    "brain/WHEN_TO_USE_AGENTS.md": lambda g: emit_when_to_use_agents(g),
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
    p.add_argument(
        "--query",
        choices=["skill", "script", "agent", "mcp", "workflow", "resource", "runtime"],
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
          f"{t['agents']} agents, {t['mcp_servers']} MCP, {t['workflows']} workflows, "
          f"{t['resources']} resources, {t['runtime_entrypoints']} runtimes)")
    print(f"  Edges: {t['edges_total']}")
    if t["drift_count"]:
        print(f"  Drift: {t['drift_count']} (run with --json to see details)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
