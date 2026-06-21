"""Harness Plugin — unified chassis interface for multi-model agent operation.

Every chassis (Claude Code, Gemini CLI, Antigravity, ZCode, OpenCode) implements
the same abstract interface but with different capabilities. This module provides:

1. Plugin registry — enumerate available chassis and their capabilities
2. Capability negotiation — what can this chassis do? (MCP, CLI, browser, etc.)
3. Handoff protocol — seamless context transfer between chassis
4. Health probes — verify a chassis is operational

Usage:
    python scripts/harness_plugin.py list                    # list all chassis
    python scripts/harness_plugin.py capabilities --chassis zcode
    python scripts/harness_plugin.py health --chassis all    # health check
    python scripts/harness_plugin.py handoff --from claude --to zcode --note "..."
    python scripts/harness_plugin.py resolve --task "send email" --json

Design:
    Every chassis entry point (CLAUDE.md, GEMINI.md, ZCODE.md, etc.) is a "plugin."
    This module is the runtime that bridges them — it doesn't replace the entry points,
    it provides programmatic access to what each chassis can and can't do, so the
    model_router and state_sync systems can make informed decisions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Chassis Registry ────────────────────────────────────────────────────

@dataclass
class ChassisPlugin:
    """A single chassis (runtime environment) definition."""
    name: str
    entry_point: str  # relative path from PROJECT_ROOT
    model_family: str  # claude, gemini, glm, openai, local, any
    has_mcp: bool
    has_cli: bool
    has_browser: bool  # native browser control (Playwright MCP, etc.)
    has_file_edit: bool  # can edit files directly
    has_shell: bool  # can run shell commands
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    best_for: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CHASSIS_REGISTRY: dict[str, ChassisPlugin] = {
    "claude": ChassisPlugin(
        name="claude",
        entry_point="CLAUDE.md",
        model_family="claude",
        has_mcp=True,
        has_cli=True,
        has_browser=True,
        has_file_edit=True,
        has_shell=True,
        strengths=["multi-file refactors", "brand voice", "long context",
                   "architectural judgment", "MCP ecosystem"],
        weaknesses=["cloud-dependent", "cost per token"],
        mcp_servers=["playwright", "context7", "memory", "sequential-thinking",
                     "github", "firecrawl", "obsidian", "filesystem",
                     "knowledge-graph"],
        best_for=["frontend/UI", "content writing", "complex architecture",
                 "client comms", "memory writes", "multi-agent orchestration"],
    ),
    "gemini": ChassisPlugin(
        name="gemini",
        entry_point="GEMINI.md",
        model_family="gemini",
        has_mcp=True,
        has_cli=True,
        has_browser=True,
        has_file_edit=True,
        has_shell=True,
        strengths=["fast queries", "diagnostics", "data retrieval",
                   "long context window", "multimodal"],
        weaknesses=["less precise on multi-file refactors"],
        mcp_servers=["playwright", "context7", "memory", "sequential-thinking"],
        best_for=["quick lookups", "diagnostics", "content drafting",
                 "data analysis", "speed-critical tasks"],
    ),
    "antigravity": ChassisPlugin(
        name="antigravity",
        entry_point="ANTIGRAVITY.md",
        model_family="gemini",
        has_mcp=True,
        has_cli=True,
        has_browser=True,
        has_file_edit=True,
        has_shell=True,
        strengths=["IDE integration", "visual feedback", "Chrome DevTools",
                   "image generation", "browser recording"],
        weaknesses=["heavier startup", "IDE-dependent"],
        mcp_servers=["chrome-devtools-mcp", "context7", "memory",
                     "sequential-thinking", "playwright",
                     "gmp-code-assist"],
        best_for=["visual debugging", "UI development", "browser automation",
                 "screenshot analysis", "web app building"],
    ),
    "zcode": ChassisPlugin(
        name="zcode",
        entry_point="ZCODE.md",
        model_family="glm",
        has_mcp=False,
        has_cli=True,
        has_browser=False,
        has_file_edit=True,
        has_shell=True,
        strengths=["local execution", "no cloud dependency", "fast inference",
                   "strong reasoning", "code generation", "offline-tolerant"],
        weaknesses=["no MCP access", "no native browser", "less tested on brand voice"],
        mcp_servers=[],
        best_for=["CLI tool runs", "code edits", "state sync", "capability graph rebuilds",
                 "fast refactors", "offline work", "sequential planning"],
    ),
    "opencode": ChassisPlugin(
        name="opencode",
        entry_point="OPENCODE.md",
        model_family="any",
        has_mcp=False,
        has_cli=True,
        has_browser=False,
        has_file_edit=True,
        has_shell=True,
        strengths=["model-agnostic", "lightweight", "swappable models"],
        weaknesses=["no MCP", "no browser", "depends on model quality"],
        mcp_servers=[],
        best_for=["model experimentation", "quick edits", "CLI-driven work"],
    ),
    "codex": ChassisPlugin(
        name="codex",
        entry_point="AGENTS.md",
        model_family="openai",
        has_mcp=False,
        has_cli=True,
        has_browser=False,
        has_file_edit=True,
        has_shell=True,
        strengths=["backend implementation", "deep debugging",
                   "adversarial code review", "pattern matching"],
        weaknesses=["no MCP", "no browser", "no brand voice"],
        mcp_servers=[],
        best_for=["backend code", "API routes", "DB queries", "deep debug",
                 "adversarial review", "stack trace analysis"],
    ),
}


# ── Capability Negotiation ──────────────────────────────────────────────

def get_capabilities(chassis_name: str) -> dict[str, Any]:
    """Return the full capability profile for a chassis."""
    chassis = CHASSIS_REGISTRY.get(chassis_name)
    if not chassis:
        return {"error": f"Unknown chassis: {chassis_name}"}
    return chassis.to_dict()


def resolve_best_chassis(task: str) -> dict[str, Any]:
    """Given a task description, recommend the best chassis."""
    task_lower = task.lower()
    scores: dict[str, int] = {}

    for name, chassis in CHASSIS_REGISTRY.items():
        score = 0
        for strength in chassis.best_for:
            if any(word in task_lower for word in strength.lower().split()):
                score += 10
        for strength in chassis.strengths:
            if any(word in task_lower for word in strength.lower().split()):
                score += 5

        # Penalty for missing capabilities the task might need
        if "browser" in task_lower and not chassis.has_browser:
            score -= 20
        if "mcp" in task_lower and not chassis.has_mcp:
            score -= 15
        if any(kw in task_lower for kw in ["email", "send", "outbound"]):
            if chassis.has_cli:
                score += 5  # all CLI chassis can use send_gateway
        if any(kw in task_lower for kw in ["frontend", "ui", "design", "css"]):
            if chassis.has_browser:
                score += 10

        scores[name] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_name = ranked[0][0]
    best = CHASSIS_REGISTRY[best_name]

    return {
        "task": task,
        "recommended": best_name,
        "entry_point": best.entry_point,
        "model_family": best.model_family,
        "score": ranked[0][1],
        "reason": f"Best match for '{task}' based on capabilities: {', '.join(best.best_for[:3])}",
        "alternatives": [
            {"chassis": name, "score": s}
            for name, s in ranked[1:3] if s > 0
        ],
    }


# ── Health Probes ───────────────────────────────────────────────────────

def health_check(chassis_name: str) -> dict[str, Any]:
    """Verify a chassis entry point exists and is well-formed."""
    chassis = CHASSIS_REGISTRY.get(chassis_name)
    if not chassis:
        return {"chassis": chassis_name, "status": "unknown", "detail": "Not in registry"}

    entry_path = PROJECT_ROOT / chassis.entry_point
    if not entry_path.exists():
        return {
            "chassis": chassis_name,
            "status": "missing",
            "detail": f"Entry point {chassis.entry_point} not found",
        }

    text = entry_path.read_text(encoding="utf-8", errors="replace")
    checks = {
        "has_identity": "bravo" in text.lower() or "identity" in text.lower(),
        "has_tool_discipline": "tool" in text.lower() and "discipline" in text.lower(),
        "has_security": "security" in text.lower() or "credential" in text.lower(),
        "has_state_sync": "state_sync" in text.lower() or "state sync" in text.lower(),
        "has_session_bookends": "session" in text.lower(),
        "line_count": text.count("\n"),
    }
    passed = sum(1 for k, v in checks.items() if isinstance(v, bool) and v)
    total = sum(1 for v in checks.values() if isinstance(v, bool))

    return {
        "chassis": chassis_name,
        "status": "healthy" if passed == total else "degraded",
        "entry_point": chassis.entry_point,
        "checks": checks,
        "score": f"{passed}/{total}",
    }


def health_all() -> list[dict[str, Any]]:
    """Health check all registered chassis."""
    return [health_check(name) for name in CHASSIS_REGISTRY]


# ── Handoff Protocol ───────────────────────────────────────────────────

def generate_handoff(from_chassis: str, to_chassis: str,
                     note: str) -> dict[str, Any]:
    """Generate a handoff context packet for chassis transition."""
    source = CHASSIS_REGISTRY.get(from_chassis)
    target = CHASSIS_REGISTRY.get(to_chassis)

    if not source:
        return {"error": f"Unknown source chassis: {from_chassis}"}
    if not target:
        return {"error": f"Unknown target chassis: {to_chassis}"}

    # What capabilities are gained/lost in the transition
    gained = []
    lost = []
    if target.has_mcp and not source.has_mcp:
        gained.append("MCP servers (Playwright, Memory, Context7, etc.)")
    if source.has_mcp and not target.has_mcp:
        lost.append("MCP servers — use CLI equivalents in scripts/")
    if target.has_browser and not source.has_browser:
        gained.append("Native browser control")
    if source.has_browser and not target.has_browser:
        lost.append("Native browser — use cloak_browser_tool.py or research_fetch.py")

    return {
        "from": from_chassis,
        "to": to_chassis,
        "note": note,
        "target_entry_point": target.entry_point,
        "target_model_family": target.model_family,
        "capabilities_gained": gained,
        "capabilities_lost": lost,
        "instructions": [
            f"1. Open {target.entry_point} in the target chassis",
            "2. Run: python scripts/state/state_sync.py --note 'handoff from "
            f"{from_chassis}'",
            "3. Run: python scripts/core/agent_inbox.py list --to bravo",
            f"4. Context note: {note}",
        ],
    }


# ── CLI ─────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all registered chassis")

    p_cap = sub.add_parser("capabilities", help="Show chassis capabilities")
    p_cap.add_argument("--chassis", required=True)
    p_cap.add_argument("--json", action="store_true", dest="output_json")

    p_health = sub.add_parser("health", help="Health check chassis")
    p_health.add_argument("--chassis", required=True,
                          help="Chassis name or 'all'")
    p_health.add_argument("--json", action="store_true", dest="output_json")

    p_handoff = sub.add_parser("handoff", help="Generate handoff context")
    p_handoff.add_argument("--from", required=True, dest="from_chassis")
    p_handoff.add_argument("--to", required=True, dest="to_chassis")
    p_handoff.add_argument("--note", required=True)
    p_handoff.add_argument("--json", action="store_true", dest="output_json")

    p_resolve = sub.add_parser("resolve", help="Recommend best chassis for task")
    p_resolve.add_argument("--task", required=True)
    p_resolve.add_argument("--json", action="store_true", dest="output_json")

    args = parser.parse_args(argv)

    if args.command == "list":
        for name, chassis in CHASSIS_REGISTRY.items():
            mcp_tag = "[Y] MCP" if chassis.has_mcp else "[N] MCP"
            browser_tag = "[Y] Browser" if chassis.has_browser else "[N] Browser"
            print(f"  {name:14s} [{chassis.model_family:8s}] "
                  f"{mcp_tag}  {browser_tag}  -> {chassis.entry_point}")
        return 0

    elif args.command == "capabilities":
        result = get_capabilities(args.chassis)
        print(json.dumps(result, indent=2, default=str))
        return 0

    elif args.command == "health":
        if args.chassis == "all":
            results = health_all()
        else:
            results = [health_check(args.chassis)]
        if args.output_json:
            print(json.dumps(results, indent=2, default=str))
        else:
            for r in results:
                status_icon = {"healthy": "[OK]", "degraded": "[!!]",
                               "missing": "[XX]", "unknown": "[??]"}.get(
                    r["status"], "?")
                print(f"  {status_icon} {r['chassis']:14s} "
                      f"{r['status']:10s} {r.get('score', '')}")
        return 0

    elif args.command == "handoff":
        result = generate_handoff(args.from_chassis, args.to_chassis,
                                  args.note)
        if args.output_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if "error" in result:
                print(f"Error: {result['error']}")
                return 1
            print(f"Handoff: {result['from']} → {result['to']}")
            print(f"Note: {result['note']}")
            if result["capabilities_gained"]:
                print(f"Gained: {', '.join(result['capabilities_gained'])}")
            if result["capabilities_lost"]:
                print(f"Lost: {', '.join(result['capabilities_lost'])}")
            for inst in result["instructions"]:
                print(f"  {inst}")
        return 0

    elif args.command == "resolve":
        result = resolve_best_chassis(args.task)
        if args.output_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"Recommended: {result['recommended']} "
                  f"({result['model_family']}) — {result['reason']}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
