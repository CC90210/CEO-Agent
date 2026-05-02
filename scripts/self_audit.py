#!/usr/bin/env python3
"""
Self-Audit — Bravo's automated health check.

Scans the knowledge graph for orphans, broken wiring, stale docs, and
undocumented scripts. Runs fast (seconds), emits a health score + action list.

Usage:
    python scripts/self_audit.py              # human-readable report
    python scripts/self_audit.py --json       # agent-readable JSON
    python scripts/self_audit.py --fix-links  # auto-add reconnection TODOs to orphans

Exit codes:
    0 = healthy (score >= 85)
    1 = warnings (score 70-84)
    2 = degraded (score < 70)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- Scan scope -------------------------------------------------------------

AUDIT_DIRS = ["brain", "memory", "skills", "agents", ".agents/workflows",
              ".agents/commands", ".agents/plans", "APPS_CONTEXT"]
SKIP_DIRS = {"ARCHIVES", "node_modules", ".git", "worktrees", "tmp",
             "__pycache__", ".claude/worktrees"}

# Directories whose contents are historical archives by design — not expected
# to have inbound wiki-links. Skipped for orphan checks.
ARCHIVE_PATH_PARTS = {"outreach_archive", "daily", "research", "content"}

# Files that are allowed to be "orphans" because they're entry points,
# IDE-loaded at boot, or reachable via @import rather than [[wiki-link]].
ORPHAN_ALLOWLIST = {
    "brain/SOUL.md", "brain/USER.md", "brain/STATE.md",
    "brain/DASHBOARD.md", "brain/CAPABILITIES.md", "brain/QUICK_REFERENCE.md",
    "brain/AGENTS.md", "brain/APP_REGISTRY.md", "brain/BRAIN_LOOP.md",
    "brain/INTERACTION_PROTOCOL.md", "brain/HEARTBEAT.md", "brain/GROWTH.md",
    "brain/CHANGELOG.md", "brain/ORCHESTRATION.md", "brain/PERSONALITY.md",
    "memory/ACTIVE_TASKS.md", "memory/SESSION_LOG.md",
    "memory/MISTAKES.md", "memory/PATTERNS.md", "memory/DECISIONS.md",
    "memory/MEMORY_INDEX.md", "memory/content-strategy.md",
}

# ---------------------------------------------------------------------------


@dataclass
class AuditResult:
    total_md_files: int = 0
    orphans: list[str] = field(default_factory=list)
    leaves: list[str] = field(default_factory=list)
    broken_links: list[tuple[str, str]] = field(default_factory=list)
    skills_total: int = 0
    skills_missing_skill_md: list[str] = field(default_factory=list)
    skills_missing_frontmatter: list[str] = field(default_factory=list)
    scripts_total: int = 0
    scripts_undocumented: list[str] = field(default_factory=list)
    mcp_configs_in_sync: bool = True
    mcp_servers: list[str] = field(default_factory=list)
    health_score: int = 0
    warnings: list[str] = field(default_factory=list)


def collect_markdown_files() -> list[Path]:
    files: list[Path] = []
    for d in AUDIT_DIRS:
        base = REPO_ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.md"):
            if any(skip in p.parts for skip in SKIP_DIRS):
                continue
            files.append(p)
    return files


WIKI_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]")
AT_IMPORT_RE = re.compile(r"@([a-zA-Z0-9_\-/.]+\.md)")


def _find_leaves(md_files: list[Path], inbound: dict[str, set[str]]) -> list[str]:
    """Files with degree <= 1 (1 inbound + 0 outbound, OR 0 inbound + 1 outbound).

    Same allowlist as orphan detection — entry points and historical
    archives are exempt. These show up as perimeter dots in Obsidian's
    force-directed graph, indistinguishable from orphans visually. Flag
    them so future drift surfaces in self_audit before the user notices.
    """
    leaves: list[str] = []
    for f in md_files:
        rel = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
        if rel in ORPHAN_ALLOWLIST:
            continue
        if any(part in ARCHIVE_PATH_PARTS for part in rel.split("/")):
            continue
        filename = rel.split("/")[-1]
        # Inbound count (any of the three forms self_audit indexes)
        in_count = (
            len(inbound.get(rel, set()))
            + len(inbound.get(filename, set()))
            + len(inbound.get(rel.removesuffix(".md"), set()))
        )
        # Outbound count: count wiki-links that resolve to other md files
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        out_count = 0
        for m in WIKI_LINK_RE.findall(text):
            target = m.strip()
            if not target.endswith(".md"):
                target = target + ".md"
            # Only count if target is an indexed file (avoid phantom links)
            if target in inbound or target.split("/")[-1] in inbound:
                out_count += 1
        if (in_count + out_count) <= 1:
            leaves.append(rel)
    return leaves


def build_link_index(md_files: list[Path]) -> dict[str, set[str]]:
    """Map 'brain/SOUL.md' -> {set of files that link to it}."""
    inbound: dict[str, set[str]] = {}
    # Also check CLAUDE.md, GEMINI.md, ANTIGRAVITY.md for @imports
    entry_points = [REPO_ROOT / n for n in
                    ("CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md", "AGENTS.md", "README.md")]
    for ep in entry_points:
        if ep.exists():
            md_files = md_files + [ep]

    for f in md_files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        source = str(f.relative_to(REPO_ROOT)).replace("\\", "/")

        for m in WIKI_LINK_RE.findall(text):
            target = m.strip()
            if not target.endswith(".md"):
                target = target + ".md"
            # Obsidian links may omit directory prefix — try both forms
            inbound.setdefault(target, set()).add(source)
            inbound.setdefault(target.split("/")[-1], set()).add(source)

        for m in AT_IMPORT_RE.findall(text):
            inbound.setdefault(m.strip(), set()).add(source)
            inbound.setdefault(m.strip().split("/")[-1], set()).add(source)
    return inbound


def check_skills(result: AuditResult) -> None:
    skills_dir = REPO_ROOT / "skills"
    if not skills_dir.exists():
        return
    for sub in skills_dir.iterdir():
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        result.skills_total += 1
        skill_md = sub / "SKILL.md"
        if not skill_md.exists():
            result.skills_missing_skill_md.append(str(sub.relative_to(REPO_ROOT)))
            continue
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
        # Rough frontmatter check: must have --- at top + name: + description:
        head = text[:800]
        if not (head.startswith("---") and "name:" in head and "description:" in head):
            result.skills_missing_frontmatter.append(str(skill_md.relative_to(REPO_ROOT)))


def check_scripts(result: AuditResult) -> None:
    scripts_dir = REPO_ROOT / "scripts"
    if not scripts_dir.exists():
        return
    # Collect reference text from the docs agents actually read
    doc_text = ""
    for ref_doc in ("brain/CAPABILITIES.md", "brain/QUICK_REFERENCE.md", "CLAUDE.md"):
        p = REPO_ROOT / ref_doc
        if p.exists():
            doc_text += p.read_text(encoding="utf-8", errors="ignore")
    # Also scan skills for references
    for skill_md in (REPO_ROOT / "skills").rglob("SKILL.md"):
        doc_text += skill_md.read_text(encoding="utf-8", errors="ignore")

    for py in scripts_dir.glob("*.py"):
        if py.name.startswith("_") or py.name.startswith("test_"):
            continue
        result.scripts_total += 1
        if py.name not in doc_text and py.stem not in doc_text:
            result.scripts_undocumented.append(str(py.relative_to(REPO_ROOT)))


def check_mcp_sync(result: AuditResult) -> None:
    """Sync rule: project-level configs (.claude/mcp.json + .vscode/mcp.json)
    must agree exactly. The user-level ~/.gemini/settings.json is shared
    across every project on the machine, so it's allowed to be a SUPERSET
    of the project's required servers — extras don't count as drift."""
    project_configs = {
        ".claude/mcp.json": REPO_ROOT / ".claude" / "mcp.json",
        ".vscode/mcp.json": REPO_ROOT / ".vscode" / "mcp.json",
    }
    user_config_label = "~/.gemini/settings.json"
    user_config_path = Path.home() / ".gemini" / "settings.json"

    project_sets: dict[str, set[str]] = {}
    for label, path in project_configs.items():
        if not path.exists():
            result.warnings.append(f"MCP config missing: {label}")
            result.mcp_configs_in_sync = False
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            result.warnings.append(f"MCP config unreadable: {label} ({e})")
            result.mcp_configs_in_sync = False
            continue
        project_sets[label] = set((data.get("mcpServers") or data.get("servers") or {}).keys())

    if project_sets:
        ref = next(iter(project_sets.values()))
        for label, s in project_sets.items():
            if s != ref:
                result.mcp_configs_in_sync = False
                missing = ref - s
                extra = s - ref
                result.warnings.append(
                    f"MCP drift in {label}: missing={sorted(missing)} extra={sorted(extra)}"
                )
        result.mcp_servers = sorted(ref)

        # User-level gemini settings: must be SUPERSET, not exact match.
        # Extras don't count as drift — they're for other projects on the machine.
        if user_config_path.exists():
            try:
                udata = json.loads(user_config_path.read_text(encoding="utf-8"))
                user_servers = set((udata.get("mcpServers") or udata.get("servers") or {}).keys())
                missing_in_user = ref - user_servers
                if missing_in_user:
                    result.mcp_configs_in_sync = False
                    result.warnings.append(
                        f"MCP missing from {user_config_label}: {sorted(missing_in_user)}"
                    )
            except Exception as e:
                result.warnings.append(f"MCP config unreadable: {user_config_label} ({e})")


def compute_health_score(r: AuditResult) -> int:
    score = 100
    score -= min(len(r.orphans) * 2, 20)          # cap orphan penalty at 20
    score -= len(r.broken_links) * 3
    score -= len(r.skills_missing_skill_md) * 5
    score -= len(r.skills_missing_frontmatter) * 2
    score -= min(len(r.scripts_undocumented), 10)  # cap undocumented at 10
    if not r.mcp_configs_in_sync:
        score -= 10
    return max(0, score)


def run_audit() -> AuditResult:
    result = AuditResult()
    md_files = collect_markdown_files()
    result.total_md_files = len(md_files)
    inbound = build_link_index(md_files)

    for f in md_files:
        rel = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
        if rel in ORPHAN_ALLOWLIST:
            continue
        # Historical archive directories don't need inbound links
        if any(part in ARCHIVE_PATH_PARTS for part in rel.split("/")):
            continue
        filename = rel.split("/")[-1]
        # An orphan has no inbound refs under any form we index
        if not inbound.get(rel) and not inbound.get(filename) and not inbound.get(rel.removesuffix(".md")):
            result.orphans.append(rel)

    # Leaf detection: files with degree <= 1 (one inbound, zero outbound)
    # cluster on the perimeter of the Obsidian force-directed graph and
    # look like orphans visually even though they have a link. Flag them
    # so future drift gets caught early. Counted SEPARATELY from orphans
    # — leaves don't reduce the health score (they're well-formed
    # technically), they're just a UI quality signal.
    result.leaves = _find_leaves(md_files, inbound)

    check_skills(result)
    check_scripts(result)
    check_mcp_sync(result)
    check_personalization(result)
    result.health_score = compute_health_score(result)
    return result


def check_personalization(r: AuditResult) -> None:
    """Warn (don't fail) when operator.profile.json is missing.

    A fresh clone hasn't run the wizard yet. The agent works without a
    profile but can't be personalized — surface that as a warning so the
    operator knows to run `python scripts/setup_wizard.py`.
    """
    profile_path = REPO_ROOT / "brain" / "operator.profile.json"
    if not profile_path.exists():
        r.warnings.append(
            "operator.profile.json missing — run `python scripts/setup_wizard.py` "
            "to personalize this clone (or `python scripts/personalize.py seed` "
            "to seed a manual profile)."
        )


def render_human(r: AuditResult) -> str:
    lines = [
        "",
        "=" * 64,
        f" BRAVO SELF-AUDIT   |   health score: {r.health_score}/100",
        "=" * 64,
        f"  Markdown files scanned : {r.total_md_files}",
        f"  Skills registered      : {r.skills_total}",
        f"  Scripts (non-internal) : {r.scripts_total}",
        f"  MCP servers in sync    : {'YES' if r.mcp_configs_in_sync else 'NO — drift detected'}",
        f"  MCP servers registered : {len(r.mcp_servers)} ({', '.join(r.mcp_servers)})",
        "",
    ]
    if r.orphans:
        lines.append(f"  ORPHANS ({len(r.orphans)}) — no inbound links, not allowlisted:")
        for o in sorted(r.orphans):
            lines.append(f"    - {o}")
    else:
        lines.append("  ORPHANS: none OK")
    if r.leaves:
        lines.append(f"  LEAVES ({len(r.leaves)}) — degree <= 1, cluster on graph perimeter (not penalized, UI signal):")
        for o in sorted(r.leaves)[:15]:
            lines.append(f"    - {o}")
        if len(r.leaves) > 15:
            lines.append(f"    ... +{len(r.leaves) - 15} more")
    else:
        lines.append("  LEAVES: none OK (graph is dense)")
    lines.append("")
    if r.skills_missing_skill_md:
        lines.append(f"  SKILLS missing SKILL.md ({len(r.skills_missing_skill_md)}):")
        for s in r.skills_missing_skill_md:
            lines.append(f"    - {s}")
    if r.skills_missing_frontmatter:
        lines.append(f"  SKILLS missing frontmatter ({len(r.skills_missing_frontmatter)}):")
        for s in r.skills_missing_frontmatter:
            lines.append(f"    - {s}")
    if r.scripts_undocumented:
        lines.append(f"  SCRIPTS not referenced by CAPABILITIES/QUICK_REFERENCE/skills ({len(r.scripts_undocumented)}):")
        for s in r.scripts_undocumented[:15]:
            lines.append(f"    - {s}")
        if len(r.scripts_undocumented) > 15:
            lines.append(f"    - (+{len(r.scripts_undocumented)-15} more)")
    if r.warnings:
        lines.append("")
        lines.append("  WARNINGS:")
        for w in r.warnings:
            lines.append(f"    ! {w}")
    lines.append("")
    if r.health_score >= 85:
        verdict = "HEALTHY — ship it."
    elif r.health_score >= 70:
        verdict = "WARN — reconnect orphans, document scripts."
    else:
        verdict = "DEGRADED — stop and clean up."
    lines.append(f"  VERDICT: {verdict}")
    lines.append("=" * 64)
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Bravo self-audit")
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = p.parse_args()

    result = run_audit()
    if args.json:
        print(json.dumps(asdict(result), default=list, indent=2))
    else:
        print(render_human(result))

    if result.health_score >= 85:
        return 0
    if result.health_score >= 70:
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
