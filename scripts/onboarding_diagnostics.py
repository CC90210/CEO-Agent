"""Bravo onboarding diagnostics.

Safe, read-only checks for the productized agent foundation: local tooling,
repo health, Browser Harness, and required structure. This is the first draft
of the future `bravo doctor` command.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import browser_harness_doctor
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], timeout: int = 60) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout, creationflags=WINDOWLESS_FLAGS)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}


def _tool(name: str, version_args: list[str] | None = None) -> dict[str, Any]:
    path = shutil.which(name)
    result: dict[str, Any] = {"name": name, "ok": bool(path), "path": path, "version": None}
    if path and version_args:
        result["version"] = _run([path, *version_args], timeout=20)
    return result


def diagnose() -> dict[str, Any]:
    tools = [
        _tool("python", ["--version"]),
        _tool("git", ["--version"]),
        _tool("uv", ["--version"]),
        _tool("node", ["--version"]),
        _tool("npm", ["--version"]),
        _tool("rg", ["--version"]),
    ]

    required_paths = [
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "ANTIGRAVITY.md",
        "brain/STATE.md",
        "memory/SESSION_LOG.md",
        "skills/browser-harness/SKILL.md",
        "browser/README.md",
        "browser/domain-skills",
        "browser/interaction-skills",
        "config/bravo-config.example.toml",
        "install/README.md",
        "runtime/README.md",
    ]
    path_checks = [
        {"path": p, "ok": (ROOT / p).exists()}
        for p in required_paths
    ]

    self_audit = _run([sys.executable, "scripts/core/self_audit.py"], timeout=90)
    browser = browser_harness_doctor.diagnose()

    ok = (
        all(t["ok"] for t in tools[:4])
        and all(p["ok"] for p in path_checks)
        and self_audit["ok"]
        and browser["install_ok"]
    )

    return {
        "ok": ok,
        "tools": tools,
        "paths": path_checks,
        "self_audit": self_audit,
        "browser_harness": browser,
    }


def print_human(report: dict[str, Any]) -> None:
    print("Bravo onboarding diagnostics")
    print(f"  overall: {'OK' if report['ok'] else 'FAIL'}")
    print()
    print("Tools")
    for tool in report["tools"]:
        print(f"  [{'OK' if tool['ok'] else 'FAIL'}] {tool['name']} - {tool.get('path') or 'missing'}")
    print()
    print("Required structure")
    for item in report["paths"]:
        print(f"  [{'OK' if item['ok'] else 'FAIL'}] {item['path']}")
    print()
    print(f"Self-audit: {'OK' if report['self_audit']['ok'] else 'FAIL'}")
    print(f"Browser Harness install: {'OK' if report['browser_harness']['install_ok'] else 'FAIL'}")
    print(f"Browser Harness attach: {'OK' if report['browser_harness']['attach_ok'] else 'PENDING'}")
    if report["browser_harness"].get("attach_hint"):
        print(f"Next: {report['browser_harness']['attach_hint']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run safe Bravo onboarding diagnostics")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()

    report = diagnose()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
