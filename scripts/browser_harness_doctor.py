"""Browser Harness diagnostics for Bravo.

This checks the installed Browser Harness executable, the stable checkout,
global Codex skill registration, Bravo-local skill wrapper, and current attach
state. It is intentionally read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
HARNESS_REPO = Path.home() / "APPS" / "browser-harness"
HARNESS_EXE = Path.home() / ".local" / "bin" / "browser-harness.exe"
GLOBAL_CODEX_SKILL = Path.home() / ".codex" / "skills" / "browser-harness" / "SKILL.md"
LOCAL_BRAVO_SKILL = ROOT / "skills" / "browser-harness" / "SKILL.md"
BROWSER_ROOT = ROOT / "browser"


def _find_harness() -> Path | None:
    found = shutil.which("browser-harness")
    if found:
        return Path(found)
    if HARNESS_EXE.exists():
        return HARNESS_EXE
    return None


def _run(cmd: list[str], timeout: int = 45) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, creationflags=WINDOWLESS_FLAGS)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}


def _run_harness(harness: Path, args: list[str], timeout: int = 60) -> dict[str, Any]:
    """Run the uv-generated harness executable.

    On this Windows workstation, CreateProcess from Python can return WinError 5
    for uv's generated .exe shim while PowerShell invocation works. Keep the
    fallback here so the doctor remains reliable.
    """
    if os.name == "nt":
        quoted = str(harness).replace("'", "''")
        command = "& '" + quoted + "' " + " ".join(args)
        return _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], timeout=timeout)
    return _run([str(harness), *args], timeout=timeout)


def _check_path(label: str, path: Path, required: bool = True) -> dict[str, Any]:
    exists = path.exists()
    return {
        "label": label,
        "path": str(path),
        "ok": exists or not required,
        "required": required,
        "detail": "present" if exists else "missing",
    }


def diagnose() -> dict[str, Any]:
    harness = _find_harness()
    checks: list[dict[str, Any]] = [
        _check_path("stable checkout", HARNESS_REPO),
        _check_path("global Codex skill", GLOBAL_CODEX_SKILL),
        _check_path("Bravo wrapper skill", LOCAL_BRAVO_SKILL),
        _check_path("Bravo browser directory", BROWSER_ROOT),
        _check_path("domain skills", BROWSER_ROOT / "domain-skills"),
        _check_path("interaction skills", BROWSER_ROOT / "interaction-skills"),
    ]

    if harness:
        checks.append({
            "label": "browser-harness executable",
            "path": str(harness),
            "ok": True,
            "required": True,
            "detail": "present",
        })
        version = _run_harness(harness, ["--version"], timeout=30)
        doctor = _run_harness(harness, ["--doctor"], timeout=60)
    else:
        checks.append({
            "label": "browser-harness executable",
            "path": str(HARNESS_EXE),
            "ok": False,
            "required": True,
            "detail": "missing from PATH and expected uv location",
        })
        version = {"ok": False, "stdout": "", "stderr": "browser-harness not found", "returncode": None}
        doctor = {"ok": False, "stdout": "", "stderr": "browser-harness not found", "returncode": None}

    install_ok = all(c["ok"] for c in checks if c.get("required"))
    attach_ok = bool(doctor.get("ok"))
    attach_hint = None
    doctor_text = "\n".join(x for x in [doctor.get("stdout", ""), doctor.get("stderr", "")] if x)
    if install_ok and not attach_ok:
        attach_hint = (
            "Installed, but Chrome/Edge is not attached yet. Run "
            "`& (Get-Command browser-harness).Source --setup`, then approve remote debugging in Chrome if prompted."
        )

    return {
        "install_ok": install_ok,
        "attach_ok": attach_ok,
        "harness": str(harness) if harness else None,
        "checks": checks,
        "version": version,
        "doctor": doctor,
        "doctor_text": doctor_text,
        "attach_hint": attach_hint,
    }


def print_human(report: dict[str, Any]) -> None:
    print("Browser Harness diagnostics")
    print(f"  install: {'OK' if report['install_ok'] else 'FAIL'}")
    print(f"  attach : {'OK' if report['attach_ok'] else 'PENDING'}")
    if report.get("harness"):
        print(f"  exe    : {report['harness']}")
    print()
    for check in report["checks"]:
        mark = "OK" if check["ok"] else "FAIL"
        print(f"  [{mark}] {check['label']} - {check['detail']}")
        print(f"       {check['path']}")
    if report["version"].get("stdout"):
        print(f"\n  version: {report['version']['stdout']}")
    if report.get("doctor_text"):
        print("\n-- upstream doctor --")
        print(report["doctor_text"])
    if report.get("attach_hint"):
        print(f"\nNext: {report['attach_hint']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Bravo Browser Harness install")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--strict", action="store_true", help="fail if attach is not live")
    args = parser.parse_args()

    report = diagnose()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)

    if not report["install_ok"]:
        return 1
    if args.strict and not report["attach_ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
