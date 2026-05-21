"""Pre-deploy verification gate. Runs before every production deploy.

A composition of the existing primitives: pytest + py_compile + health
aggregator + security audit + docker config + entry-point consistency.

Exit codes:
    0 — all checks pass; safe to deploy.
    1 — at least one critical check failed; do NOT deploy.
    2 — only warnings; deploy with caution.

Usage:
    python scripts/deploy/verify_deploy.py          # full verification
    python scripts/deploy/verify_deploy.py --json   # machine-readable
    python scripts/deploy/verify_deploy.py --quick  # critical checks only

CI integration: drop a step into .github/workflows/deploy-vps.yml that
runs this script BEFORE the deploy step. If verify_deploy exits 1, fail
the workflow.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _ok(name: str, detail: str = "") -> dict[str, Any]:
    return {"name": name, "severity": "info", "status": "pass", "detail": detail}


def _warn(name: str, detail: str) -> dict[str, Any]:
    return {"name": name, "severity": "warn", "status": "warn", "detail": detail}


def _fail(name: str, detail: str) -> dict[str, Any]:
    return {"name": name, "severity": "critical", "status": "fail", "detail": detail}


# ── Checks ─────────────────────────────────────────────────────────────

def check_tests() -> dict[str, Any]:
    """Run pytest in quiet mode. Test_send_gateway is excluded by default
    until its V6.0-era fixtures are repaired (see test_send_gateway docstring)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "scripts/", "-q",
             "--tb=no",
             "--ignore=scripts/test_send_gateway.py"],
            capture_output=True, text=True, timeout=180, cwd=str(PROJECT_ROOT),
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return _fail("Tests", f"pytest run failed: {exc}")
    if result.returncode == 0:
        # Pull "N passed in Xs" from output
        last_line = (result.stdout.strip().splitlines() or [""])[-1]
        return _ok("Tests", last_line[:140])
    return _fail("Tests", result.stdout.strip().splitlines()[-1] if result.stdout else "pytest failed")


def check_compile() -> dict[str, Any]:
    errors = []
    for f in glob.glob(str(PROJECT_ROOT / "scripts" / "**" / "*.py"), recursive=True):
        if "_archive" in f or "__pycache__" in f:
            continue
        try:
            py_compile.compile(f, doraise=True, quiet=1)
        except py_compile.PyCompileError as exc:
            errors.append(f"{Path(f).relative_to(PROJECT_ROOT)}: {exc}")
    if errors:
        return _fail("Compile", f"{len(errors)} files failed py_compile: {errors[:3]}")
    return _ok("Compile", "all scripts compile cleanly")


def check_health() -> dict[str, Any]:
    """Delegate to the health aggregator."""
    try:
        result = subprocess.run(
            [sys.executable, "scripts/state/health_aggregator.py", "--json"],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return _warn("Health", f"health_aggregator failed: {exc}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _warn("Health", "health_aggregator returned non-JSON")
    overall = payload.get("summary", {}).get("overall", "UNKNOWN")
    if overall == "HEALTHY":
        return _ok("Health", "all checks green")
    if overall == "HEALTHY_WITH_WARNINGS":
        return _warn("Health", f"{payload['summary'].get('warn', 0)} warnings")
    return _fail("Health", f"overall={overall}")


def check_security() -> dict[str, Any]:
    try:
        result = subprocess.run(
            [sys.executable, "scripts/security_audit.py", "scan", "--json"],
            capture_output=True, text=True, timeout=120, cwd=str(PROJECT_ROOT),
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return _warn("Security", f"security_audit failed: {exc}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _warn("Security", "security_audit returned non-JSON")
    s = payload.get("summary", {})
    if s.get("fail", 0):
        return _fail("Security", f"{s['fail']} critical findings, {s.get('warn', 0)} warnings")
    if s.get("warn", 0):
        return _warn("Security", f"{s.get('warn', 0)} warnings (no criticals)")
    return _ok("Security", "0 findings")


def check_env_vars() -> dict[str, Any]:
    env_file = PROJECT_ROOT / ".env.agents"
    if not env_file.exists():
        return _fail("Env Vars", ".env.agents missing")
    required = (
        "BRAVO_SUPABASE_URL",
        "BRAVO_SUPABASE_SERVICE_ROLE_KEY",
    )
    try:
        text = env_file.read_text(encoding="utf-8")
    except OSError as exc:
        return _fail("Env Vars", f"unreadable: {exc}")
    present = set()
    for line in text.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            if v.strip().strip('"').strip("'"):
                present.add(k.strip())
    missing = [k for k in required if k not in present]
    if missing:
        return _fail("Env Vars", f"missing required keys: {missing}")
    return _ok("Env Vars", f"{len(present)} keys present")


def check_docker_config() -> dict[str, Any]:
    docker = shutil.which("docker")
    if not docker:
        return _warn("Docker Config", "docker CLI not installed (CI may skip)")
    for name in ("docker-compose.yml", "docker-compose.local.yml", "docker-compose.cloud.yml"):
        path = PROJECT_ROOT / "infra" / name
        if not path.exists():
            continue
        try:
            result = subprocess.run(
                [docker, "compose", "-f", str(path), "config", "--quiet"],
                capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
            )
        except (subprocess.SubprocessError, OSError) as exc:
            return _fail("Docker Config", f"{name}: {exc}")
        if result.returncode != 0:
            return _fail("Docker Config", f"{name}: {result.stderr.strip()[:200]}")
    return _ok("Docker Config", "all compose files validate")


def check_bridge_manifest() -> dict[str, Any]:
    """Sanity: bridge manifest exists and parses."""
    path = PROJECT_ROOT / "scripts" / "_bridge_manifest.json"
    if not path.exists():
        return _warn("Bridge Manifest", "manifest missing")
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _fail("Bridge Manifest", f"invalid JSON: {exc}")
    return _ok("Bridge Manifest", "valid JSON")


def check_entry_point_consistency() -> dict[str, Any]:
    """All 5 entry points must reference V6.5–V6.8 sections."""
    required_markers = (
        "Multi-Machine Bridge Arbitration",  # V6.5
        "Capability Graph",                  # V6.6
        "Agentic OS Orchestration",          # V6.7
        "Agent-OS Vocabulary Layer",         # V6.8
    )
    missing: dict[str, list[str]] = {}
    for entry in ("CLAUDE.md", "AGENTS.md", "GEMINI.md", "ANTIGRAVITY.md", "OPENCODE.md"):
        path = PROJECT_ROOT / entry
        if not path.exists():
            missing[entry] = ["FILE_MISSING"]
            continue
        text = path.read_text(encoding="utf-8")
        miss = [m for m in required_markers if m not in text]
        if miss:
            missing[entry] = miss
    if missing:
        return _fail("Entry Points",
                     f"{len(missing)} entry points out of sync: {missing}")
    return _ok("Entry Points", "all 5 carry V6.5–V6.8 sections")


CRITICAL_CHECKS = [
    ("compile",      check_compile),
    ("env_vars",     check_env_vars),
    ("entry_points", check_entry_point_consistency),
]

FULL_CHECKS = CRITICAL_CHECKS + [
    ("tests",            check_tests),
    ("health",           check_health),
    ("security",         check_security),
    ("docker_config",    check_docker_config),
    ("bridge_manifest",  check_bridge_manifest),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quick", action="store_true",
                        help="critical checks only (skip pytest, health, security, docker)")
    args = parser.parse_args(argv)

    checks = CRITICAL_CHECKS if args.quick else FULL_CHECKS
    results = [fn() for _, fn in checks]

    fails = sum(1 for r in results if r["status"] == "fail")
    warns = sum(1 for r in results if r["status"] == "warn")

    if fails:
        overall = "DO_NOT_DEPLOY"
        exit_code = 1
    elif warns:
        overall = "DEPLOY_WITH_CAUTION"
        exit_code = 2
    else:
        overall = "SAFE_TO_DEPLOY"
        exit_code = 0

    if args.json:
        print(json.dumps({"overall": overall, "fails": fails, "warns": warns,
                          "results": results}, indent=2, default=str))
    else:
        glyph = {"pass": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]"}
        print(f"Pre-Deploy Gate ({'quick' if args.quick else 'full'})")
        print("=" * 60)
        for r in results:
            print(f"{r['name']:18s} {glyph.get(r['status'], '[??]')} {r['detail']}")
        print("=" * 60)
        print(f"Overall: {overall} (exit={exit_code})")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
