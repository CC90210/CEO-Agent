"""System health check — Bravo's self-sustaining maintenance loop.

Runs on a Task Scheduler interval. Each pass:
  1. Reap orphan/duplicate MCP server processes (default: keep 4 per signature).
  2. Clean Temp files older than 14 days.
  3. Verify Bravo state (self_audit + audit_mcp_secrets).
  4. Surface any unexpected findings to the Bravo agent inbox.

Logs to tmp/logs/system_health.log so issues compound visibly over time.

Usage:
    python scripts/core/system_health_check.py            # full pass
    python scripts/core/system_health_check.py --json     # machine-readable
    python scripts/core/system_health_check.py --dry-run  # diagnose only
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"
TMP = ROOT / "tmp"
LOG_DIR = TMP / "logs"
LOG_FILE = LOG_DIR / "system_health.log"

PYTHON = sys.executable

# Shared Windows console-suppression flag — see scripts/_subprocess_helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from _subprocess_helpers import WINDOWLESS_FLAGS as CREATE_NO_WINDOW  # noqa: E402

KEEP_MCPS_PER_SIGNATURE = 4
TEMP_AGE_DAYS = 14


def _log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{_dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(line)


def _run(cmd: list, timeout: int = 60) -> dict:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        return {"ok": r.returncode == 0, "stdout": r.stdout, "stderr": r.stderr, "code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"timeout after {timeout}s", "code": -1}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "code": -1}


def reap_mcps(dry_run: bool) -> dict:
    args = [PYTHON, str(SCRIPTS / "reap_orphan_mcps.py"), "--keep", str(KEEP_MCPS_PER_SIGNATURE), "--json"]
    if not dry_run:
        args.append("--apply")
    r = _run(args, timeout=60)
    if not r["ok"] and not r["stdout"]:
        return {"ok": False, "error": r["stderr"][:300]}
    try:
        data = json.loads(r["stdout"])
    except json.JSONDecodeError:
        return {"ok": False, "error": "non-json output", "raw": r["stdout"][:200]}
    return {
        "ok": True,
        "total_mcps": data.get("total_mcps", 0),
        "orphans_found": data.get("orphans", 0),
        "killed": len(data.get("killed", [])),
        "failed": len(data.get("failed", [])),
        "applied": data.get("applied", False),
    }


def clean_temp(dry_run: bool) -> dict:
    """Delete Temp items older than TEMP_AGE_DAYS days."""
    temp = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp"
    if not temp.exists():
        return {"ok": False, "error": "Temp not found"}
    cutoff = _dt.datetime.now() - _dt.timedelta(days=TEMP_AGE_DAYS)
    deleted, skipped, freed = 0, 0, 0
    for entry in temp.iterdir():
        try:
            stat = entry.stat()
            mtime = _dt.datetime.fromtimestamp(stat.st_mtime)
            if mtime >= cutoff:
                continue
            size = stat.st_size if entry.is_file() else sum(
                f.stat().st_size for f in entry.rglob("*") if f.is_file()
            )
            if dry_run:
                deleted += 1
                freed += size
                continue
            if entry.is_dir():
                import shutil
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            deleted += 1
            freed += size
        except (OSError, PermissionError):
            skipped += 1
    return {
        "ok": True,
        "deleted": deleted,
        "skipped_locked": skipped,
        "freed_mb": round(freed / 1024 / 1024, 1),
        "applied": not dry_run,
    }


def verify_bravo() -> dict:
    audit = _run([PYTHON, str(SCRIPTS / "core" / "self_audit.py")], timeout=30)
    secrets = _run([PYTHON, str(SCRIPTS / "audit_mcp_secrets.py")], timeout=30)
    audit_out = audit.get("stdout") or ""
    secrets_out = secrets.get("stdout") or ""
    return {
        "self_audit_healthy": "VERDICT: HEALTHY" in audit_out,
        "mcp_secrets_clean": "zero plaintext" in secrets_out,
        "self_audit_score": _extract_score(audit_out),
    }


def _extract_score(text: str) -> int | None:
    import re
    m = re.search(r"health score:\s*(\d+)", text)
    return int(m.group(1)) if m else None


def write_inbox_alert(issue: str, detail: str) -> None:
    """Post an issue to the Bravo agent inbox so it surfaces next session."""
    inbox_script = SCRIPTS / "agent_inbox.py"
    if not inbox_script.exists():
        return
    _run(
        [PYTHON, str(inbox_script), "post", "--from", "system_health", "--to", "bravo",
         "--priority", "medium", "--subject", issue, "--body", detail],
        timeout=15,
    )


def main(argv) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="diagnose only, no mutations")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    started = _dt.datetime.now()
    report = {
        "started": started.isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "reap": reap_mcps(args.dry_run),
        "temp": clean_temp(args.dry_run),
        "bravo": verify_bravo(),
    }
    report["duration_s"] = round((_dt.datetime.now() - started).total_seconds(), 1)

    # Compose log line
    summary = (
        f"reap={report['reap'].get('killed', 0)}/{report['reap'].get('orphans_found', 0)} "
        f"temp={report['temp'].get('deleted', 0)}files/{report['temp'].get('freed_mb', 0)}MB "
        f"audit={report['bravo']['self_audit_score']} "
        f"secrets={'OK' if report['bravo']['mcp_secrets_clean'] else 'LEAK'} "
        f"({report['duration_s']}s)"
    )
    _log(summary)

    # Surface to inbox if anything looks degraded
    if not report["bravo"]["self_audit_healthy"]:
        write_inbox_alert("self_audit degraded", json.dumps(report["bravo"], indent=2))
    if not report["bravo"]["mcp_secrets_clean"]:
        write_inbox_alert("MCP credential leak", "audit_mcp_secrets reported plaintext")
    if report["reap"].get("orphans_found", 0) > 50:
        write_inbox_alert(
            "MCP leak above threshold",
            f"{report['reap']['orphans_found']} orphans found this run; consider closing extra editors",
        )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"system_health: {summary}")
    return 0 if report["bravo"]["self_audit_healthy"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
