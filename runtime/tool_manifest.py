"""Tool manifest — filesystem-truth registry of scripts/ CLI tools.

Replaces hand-maintained counts in brain/CAPABILITIES.md and brain/QUICK_REFERENCE.md.
Hermes-style tool self-registration: scan scripts/, parse docstrings, classify,
emit JSON.

Usage (library):
    from runtime.tool_manifest import build_manifest
    manifest = build_manifest()
    for tool in manifest["tools"]:
        print(tool["name"], tool["category"], tool["description"])

CLI:
    python -m runtime.tool_manifest                # pretty print manifest
    python -m runtime.tool_manifest --json         # emit full JSON
    python -m runtime.tool_manifest --counts       # only counts
    python -m runtime.tool_manifest --category Finance
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
SKILLS_DIR = REPO_ROOT / "skills"
AGENTS_DIR = REPO_ROOT / "agents"
WORKFLOWS_DIR = REPO_ROOT / ".agents" / "workflows"

CATEGORY_KEYWORDS = [
    ("Communication", ["email", "send_gateway", "notify", "outreach", "inbound", "gmail",
                       "telegram", "chat", "gws_"]),
    ("Data & Memory", ["supabase", "lead", "client_", "context", "funnel", "mem0",
                       "memory", "state_sync", "agent_inbox"]),
    ("Finance",       ["stripe", "revenue", "cost", "financial", "budget",
                       "tax", "invoice"]),
    ("Content",       ["late", "instagram", "skool", "content", "transcribe",
                       "generate_covers", "edit_content", "proposal"]),
    ("Browser & Web", ["browser", "firecrawl", "browse", "scrape", "playwright"]),
    ("System",        ["self_audit", "onboarding", "cron", "n8n", "scheduler",
                       "context_manager", "auto_dream", "register_skill",
                       "memory_index", "memory_aging", "apply_migration",
                       "build_maven_env"]),
    ("Governance",    ["draft_critic", "inbound_classifier", "autonomous_agent",
                       "catalog_sync", "codex_health", "hook_", "validator"]),
    ("Google",        ["google_tool", "gws_"]),
]


def _describe_py(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    # Module docstring first line
    m = re.search(r'^"""(.+?)"""', text, re.DOTALL | re.MULTILINE)
    if m:
        return m.group(1).strip().split("\n")[0][:100]
    # Fallback: first non-empty comment
    for line in text.splitlines()[:20]:
        s = line.strip()
        if s.startswith("#") and not s.startswith("#!"):
            return s.lstrip("#").strip()[:100]
    return ""


def _classify(name: str) -> str:
    lower = name.lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return category
    return "Other"


def _collect_scripts() -> list[dict]:
    tools = []
    if not SCRIPTS_DIR.exists():
        return tools
    for py in sorted(SCRIPTS_DIR.glob("*.py")):
        if py.name.startswith("_") or py.name.startswith("test_"):
            continue
        tools.append({
            "name": py.stem,
            "path": str(py.relative_to(REPO_ROOT)),
            "kind": "py",
            "category": _classify(py.stem),
            "description": _describe_py(py),
            "size_bytes": py.stat().st_size,
        })
    for ps1 in sorted(SCRIPTS_DIR.glob("*.ps1")):
        tools.append({
            "name": ps1.stem,
            "path": str(ps1.relative_to(REPO_ROOT)),
            "kind": "ps1",
            "category": _classify(ps1.stem),
            "description": "",
            "size_bytes": ps1.stat().st_size,
        })
    for sh in sorted(SCRIPTS_DIR.glob("*.sh")):
        tools.append({
            "name": sh.stem,
            "path": str(sh.relative_to(REPO_ROOT)),
            "kind": "sh",
            "category": _classify(sh.stem),
            "description": "",
            "size_bytes": sh.stat().st_size,
        })
    return tools


def _collect_skills() -> list[dict]:
    skills = []
    if not SKILLS_DIR.exists():
        return skills
    for sub in sorted(SKILLS_DIR.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        skill_md = sub / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8", errors="ignore")[:1500]
        except Exception:
            text = ""
        desc_m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        name_m = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        flag_m = re.search(r"^disable-model-invocation:\s*(true|false)", text, re.MULTILINE)
        skills.append({
            "name": name_m.group(1).strip() if name_m else sub.name,
            "slug": sub.name,
            "path": str(skill_md.relative_to(REPO_ROOT)),
            "description": desc_m.group(1).strip()[:200] if desc_m else "",
            "destructive": flag_m.group(1) == "true" if flag_m else False,
        })
    return skills


def _collect_agents() -> list[dict]:
    agents = []
    for base in [AGENTS_DIR, REPO_ROOT / ".claude" / "agents"]:
        if not base.exists():
            continue
        for md in sorted(base.glob("*.md")):
            if md.name.upper() == "INDEX.MD":
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="ignore")[:800]
            except Exception:
                text = ""
            desc_m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
            model_m = re.search(r"^model:\s*(.+)$", text, re.MULTILINE)
            agents.append({
                "name": md.stem,
                "location": str(base.relative_to(REPO_ROOT)),
                "path": str(md.relative_to(REPO_ROOT)),
                "description": desc_m.group(1).strip()[:160] if desc_m else "",
                "model": model_m.group(1).strip() if model_m else "unspecified",
            })
    return agents


def _collect_workflows() -> list[dict]:
    workflows = []
    if not WORKFLOWS_DIR.exists():
        return workflows
    for md in sorted(WORKFLOWS_DIR.glob("*.md")):
        if md.name.upper() == "INDEX.MD":
            continue
        workflows.append({
            "name": md.stem,
            "path": str(md.relative_to(REPO_ROOT)),
        })
    return workflows


def build_manifest() -> dict:
    tools = _collect_scripts()
    skills = _collect_skills()
    agents = _collect_agents()
    workflows = _collect_workflows()
    counts_by_category: dict[str, int] = {}
    for t in tools:
        counts_by_category[t["category"]] = counts_by_category.get(t["category"], 0) + 1
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "counts": {
            "scripts_py": sum(1 for t in tools if t["kind"] == "py"),
            "scripts_ps1": sum(1 for t in tools if t["kind"] == "ps1"),
            "scripts_sh": sum(1 for t in tools if t["kind"] == "sh"),
            "scripts_total": len(tools),
            "skills_total": len(skills),
            "skills_destructive": sum(1 for s in skills if s["destructive"]),
            "agents_total": len(agents),
            "workflows_total": len(workflows),
        },
        "counts_by_category": counts_by_category,
        "tools": tools,
        "skills": skills,
        "agents": agents,
        "workflows": workflows,
    }


def _pretty(manifest: dict, category: str | None = None) -> None:
    c = manifest["counts"]
    print(f"Bravo Tool Manifest — generated {manifest['generated_at']}")
    print()
    print(f"  scripts: {c['scripts_total']} "
          f"(py={c['scripts_py']} ps1={c['scripts_ps1']} sh={c['scripts_sh']})")
    print(f"  skills:  {c['skills_total']} (destructive: {c['skills_destructive']})")
    print(f"  agents:  {c['agents_total']}")
    print(f"  workflows: {c['workflows_total']}")
    print()
    tools = manifest["tools"]
    if category:
        tools = [t for t in tools if t["category"].lower() == category.lower()]
        print(f"  Category: {category}")
    grouped: dict[str, list[dict]] = {}
    for t in tools:
        grouped.setdefault(t["category"], []).append(t)
    for cat in sorted(grouped):
        print(f"  {cat}")
        for t in grouped[cat]:
            desc = f" — {t['description']}" if t["description"] else ""
            print(f"    {t['name']:40s} [{t['kind']}]{desc}")
        print()


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="runtime.tool_manifest")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--counts", action="store_true")
    parser.add_argument("--category", help="Filter by category")
    args = parser.parse_args(argv)

    m = build_manifest()
    if args.counts:
        print(json.dumps(m["counts"], indent=2))
        return 0
    if args.json:
        print(json.dumps(m, indent=2))
        return 0
    _pretty(m, args.category)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
