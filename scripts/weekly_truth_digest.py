#!/usr/bin/env python3
"""Weekly full-truth harness digest, always delivered to CC's private Telegram.

This closes the gap between the narrow nightly harness score and the broader
truth surfaces: self-audit, fleet/pulse/inbox health, and the complete Python
test suite. Each gate has a hard timeout and remains visible on failure.

Usage:
  python scripts/weekly_truth_digest.py
  python scripts/weekly_truth_digest.py --dry-run
  python scripts/weekly_truth_digest.py --json --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

CAPABILITY_META = {
    "category": "governance.health",
    "lifecycle": "active",
    "risk": "external_write",
    "triggers": [
        "run the weekly full truth health digest",
        "report complete harness health",
        "check self audit fleet health and all tests",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": True, "confirm": True},
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))
SELF_AUDIT_TIMEOUT_SEC = 240
FLEET_HEALTH_TIMEOUT_SEC = 90
PYTEST_TIMEOUT_SEC = 1200

try:
    from _subprocess_helpers import WINDOWLESS_FLAGS
except Exception:
    WINDOWLESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class GateResult:
    name: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_gate(name: str, command: list[str], timeout: int) -> GateResult:
    """Run one gate. Timeout/error details are returned, never swallowed."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOTIFY_DISABLED"] = "1"
    try:
        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            creationflags=WINDOWLESS_FLAGS,
        )
        return GateResult(
            name, result.returncode, result.stdout or "", result.stderr or "", False
        )
    except subprocess.TimeoutExpired as exc:
        return GateResult(
            name,
            124,
            _text(exc.stdout),
            f"timed out after {timeout}s" + (f": {_text(exc.stderr)}" if exc.stderr else ""),
            True,
        )
    except OSError as exc:
        return GateResult(name, 127, "", f"{type(exc).__name__}: {exc}", False)


def _assess_fleet(result: GateResult) -> GateResult:
    """Turn fleet_health's report-only JSON into an enforceable gate result."""
    if result.returncode != 0 or result.timed_out:
        return result
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return GateResult(result.name, 1, result.stdout, f"invalid fleet JSON: {exc}", False)

    problems: list[str] = []
    for pulse in report.get("pulses", []):
        if pulse.get("status") not in {"fresh", "domain_isolated"}:
            problems.append(f"{pulse.get('agent')} pulse {pulse.get('status')}")
    urgent = sum(int(box.get("urgent") or 0) for box in report.get("inboxes", []))
    if urgent:
        problems.append(f"{urgent} urgent inbox message(s)")
    if (report.get("cron") or {}).get("status") != "ok":
        problems.append("cron registry check failed")
    memory = report.get("memory_staleness") or {}
    if memory.get("status") != "ok" or int(memory.get("stale_count") or 0):
        problems.append(f"memory stale/error ({memory.get('stale_count', '?')})")
    if not problems:
        return result
    return GateResult(result.name, 1, result.stdout, "; ".join(problems), False)


def collect_results() -> list[GateResult]:
    self_audit = run_gate(
        "Self-audit",
        [PYTHON, "scripts/core/self_audit.py", "--json"],
        SELF_AUDIT_TIMEOUT_SEC,
    )
    fleet = _assess_fleet(run_gate(
        "Fleet health",
        [PYTHON, "scripts/fleet_health.py", "--json"],
        FLEET_HEALTH_TIMEOUT_SEC,
    ))
    pytest = run_gate(
        "Pytest",
        [PYTHON, "-m", "pytest", "scripts", "-q"],
        PYTEST_TIMEOUT_SEC,
    )
    return [self_audit, fleet, pytest]


def _summary(result: GateResult) -> str:
    if result.timed_out:
        return result.stderr.splitlines()[0][:240]
    if result.name == "Self-audit":
        try:
            data = json.loads(result.stdout)
            mandatory = "PASS" if data.get("mandatory_gate_passed") else "FAIL"
            return f"{data.get('health_score', '?')}/100; mandatory {mandatory}"
        except json.JSONDecodeError:
            pass
    if result.name == "Fleet health":
        try:
            data = json.loads(result.stdout)
            pulses = ", ".join(
                f"{p.get('agent')}={p.get('status')}" for p in data.get("pulses", [])
            )
            unread = sum(int(v.get("unread") or 0) for v in data.get("inboxes", []))
            urgent = sum(int(v.get("urgent") or 0) for v in data.get("inboxes", []))
            suffix = f"; issue: {result.stderr}" if result.stderr else ""
            return f"pulses {pulses}; inbox {unread} unread/{urgent} urgent{suffix}"[:500]
        except json.JSONDecodeError:
            pass
    lines = [line.strip() for line in (result.stdout + "\n" + result.stderr).splitlines() if line.strip()]
    return (lines[-1] if lines else "no output")[:500]


def compose_digest(results: list[GateResult]) -> str:
    overall = all(result.ok for result in results)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"Weekly full-truth health digest — {stamp}", ""]
    for result in results:
        lines.append(f"{'✅' if result.ok else '❌'} {result.name}: {_summary(result)}")
    lines.extend(["", f"OVERALL: {'GREEN' if overall else 'RED'}"])
    return "\n".join(lines)


def send_notification(message: str) -> bool:
    from notify import notify

    week = datetime.now(timezone.utc).strftime("%G-W%V")
    return notify(
        message,
        category="system",
        silent=True,
        force=True,
        dedup_key=f"weekly-full-truth-{week}",
        agent="bravo",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run and deliver the weekly full-truth health digest")
    parser.add_argument("--dry-run", action="store_true", help="print only; do not send Telegram")
    parser.add_argument("--json", action="store_true", help="emit structured results")
    args = parser.parse_args(argv)

    results = collect_results()
    message = compose_digest(results)
    if args.json:
        print(json.dumps({
            "overall": "green" if all(r.ok for r in results) else "red",
            "message": message,
            "results": [asdict(r) for r in results],
        }, indent=2))
    else:
        print(message)

    delivered = True if args.dry_run else send_notification(message)
    if not delivered:
        print("weekly digest notification failed", file=sys.stderr)
    return 0 if all(r.ok for r in results) and delivered else 1


if __name__ == "__main__":
    raise SystemExit(main())
