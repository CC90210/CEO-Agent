#!/usr/bin/env python3
"""
Codex Health Check — Verify Codex integration is fully operational.
Usage: python scripts/codex_health.py [--json] [--fix]
"""

import subprocess
import json
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GLOBAL_PLUGIN = Path.home() / ".claude" / "codex-plugin"
LOCAL_PLUGIN = PROJECT_ROOT / ".claude" / "plugins" / "codex"
GLOBAL_SKILLS = Path.home() / ".claude" / "skills"
LOCAL_SKILLS = PROJECT_ROOT / ".claude" / "skills"
GLOBAL_SETTINGS = Path.home() / ".claude" / "settings.json"
LOCAL_SETTINGS = PROJECT_ROOT / ".claude" / "settings.local.json"


def check_codex_cli():
    """Check if Codex CLI is installed and accessible."""
    try:
        result = subprocess.run(
            ["codex", "--version"],
            capture_output=True, text=True, timeout=10
        )
        version = result.stdout.strip()
        return {"status": "ok", "version": version}
    except FileNotFoundError:
        return {"status": "missing", "fix": "npm install -g @openai/codex"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}


def check_codex_auth():
    """Check if Codex is authenticated."""
    plugin_root = str(GLOBAL_PLUGIN) if GLOBAL_PLUGIN.exists() else str(LOCAL_PLUGIN)
    try:
        result = subprocess.run(
            ["node", f"{plugin_root}/scripts/codex-companion.mjs", "setup", "--json"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "CLAUDE_PLUGIN_ROOT": plugin_root}
        )
        data = json.loads(result.stdout)
        return {
            "status": "ok" if data.get("ready") else "not_ready",
            "ready": data.get("ready", False),
            "auth": data.get("auth", {}).get("loggedIn", False),
            "runtime": data.get("sessionRuntime", {}).get("mode", "unknown"),
        }
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"status": "error", "error": str(e)}


def check_plugin_files():
    """Check plugin installations."""
    checks = {}

    # Global plugin
    companion = GLOBAL_PLUGIN / "scripts" / "codex-companion.mjs"
    checks["global_plugin"] = {
        "exists": GLOBAL_PLUGIN.exists(),
        "companion": companion.exists(),
        "path": str(GLOBAL_PLUGIN),
    }

    # Local plugin
    local_companion = LOCAL_PLUGIN / "scripts" / "codex-companion.mjs"
    checks["local_plugin"] = {
        "exists": LOCAL_PLUGIN.exists(),
        "companion": local_companion.exists(),
        "path": str(LOCAL_PLUGIN),
    }

    return checks


def check_skills():
    """Check skill file presence."""
    expected = [
        "codex-review.md", "codex-adversarial-review.md", "codex-rescue.md",
        "codex-setup.md", "codex-status.md", "codex-result.md", "codex-cancel.md"
    ]

    global_skills = {s: (GLOBAL_SKILLS / s).exists() for s in expected}
    local_skills = {s: (LOCAL_SKILLS / s).exists() for s in expected}

    return {
        "global": {"path": str(GLOBAL_SKILLS), "skills": global_skills, "count": sum(global_skills.values())},
        "local": {"path": str(LOCAL_SKILLS), "skills": local_skills, "count": sum(local_skills.values())},
    }


def check_hooks():
    """Check session lifecycle hooks."""
    hooks = {"global": False, "local": False}

    for path, key in [(GLOBAL_SETTINGS, "global"), (LOCAL_SETTINGS, "local")]:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                hook_config = data.get("hooks", {})
                has_start = "SessionStart" in hook_config
                has_end = "SessionEnd" in hook_config
                hooks[key] = has_start and has_end
            except (json.JSONDecodeError, KeyError):
                pass

    return hooks


def check_agent():
    """Check codex-agent registration."""
    agent_file = PROJECT_ROOT / "agents" / "codex-agent.md"
    global_agent = Path.home() / ".claude" / "agents" / "codex-agent.md"

    return {
        "project_agent": agent_file.exists(),
        "global_agent": global_agent.exists(),
    }


def run_health_check(output_json=False):
    """Run complete health check."""
    results = {
        "cli": check_codex_cli(),
        "auth": check_codex_auth(),
        "plugins": check_plugin_files(),
        "skills": check_skills(),
        "hooks": check_hooks(),
        "agent": check_agent(),
    }

    # Calculate overall score
    checks = [
        results["cli"]["status"] == "ok",
        results["auth"].get("ready", False),
        results["auth"].get("auth", False),
        results["plugins"]["global_plugin"]["exists"],
        results["plugins"]["global_plugin"]["companion"],
        results["plugins"]["local_plugin"]["exists"],
        results["plugins"]["local_plugin"]["companion"],
        results["skills"]["global"]["count"] == 7,
        results["skills"]["local"]["count"] == 7,
        results["hooks"]["global"],
        results["hooks"]["local"],
        results["agent"]["project_agent"],
        results["agent"]["global_agent"],
    ]
    score = sum(checks)
    total = len(checks)
    grade = "A" if score == total else "B" if score >= total - 2 else "C" if score >= total - 4 else "F"

    results["score"] = f"{score}/{total}"
    results["grade"] = grade

    if output_json:
        print(json.dumps(results, indent=2))
    else:
        print(f"# Codex Health Check — Grade: {grade} ({score}/{total})")
        print()

        # CLI
        cli = results["cli"]
        icon = "OK" if cli["status"] == "ok" else "FAIL"
        print(f"  {icon} CLI: {cli.get('version', cli['status'])}")

        # Auth
        auth = results["auth"]
        icon = "OK" if auth.get("ready") else "FAIL"
        print(f"  {icon} Auth: {'authenticated' if auth.get('auth') else 'NOT authenticated'}")
        print(f"  {icon} Runtime: {auth.get('runtime', 'unknown')}")

        # Plugins
        for loc in ["global_plugin", "local_plugin"]:
            p = results["plugins"][loc]
            icon = "OK" if p["companion"] else "FAIL"
            label = "Global" if "global" in loc else "Local"
            print(f"  {icon} {label} plugin: {p['path']}")

        # Skills
        for loc in ["global", "local"]:
            s = results["skills"][loc]
            icon = "OK" if s["count"] == 7 else "FAIL"
            label = loc.title()
            print(f"  {icon} {label} skills: {s['count']}/7")

        # Hooks
        for loc in ["global", "local"]:
            icon = "OK" if results["hooks"][loc] else "FAIL"
            print(f"  {icon} {loc.title()} hooks: {'active' if results['hooks'][loc] else 'MISSING'}")

        # Agent
        for loc, key in [("Project", "project_agent"), ("Global", "global_agent")]:
            icon = "OK" if results["agent"][key] else "FAIL"
            print(f"  {icon} {loc} agent: {'registered' if results['agent'][key] else 'MISSING'}")

    return results


if __name__ == "__main__":
    output_json = "--json" in sys.argv
    run_health_check(output_json=output_json)
