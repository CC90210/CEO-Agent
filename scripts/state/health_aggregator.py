"""Empire health aggregator — one command, full subsystem report.

Aggregates 10 health checks into a single dashboard view. Designed to be
called from `/system-health` in the Command Center, from cron alerting,
and from the pre-deploy gate.

Usage:
    python scripts/state/health_aggregator.py          # human report
    python scripts/state/health_aggregator.py --json   # machine-readable
    python scripts/state/health_aggregator.py --quiet  # exit 0 healthy, 1 not

Checks:
  1. State DB             — empire_state.db reachable, WAL mode, expected tables
  2. Memory Index         — memory_index.db reachable, FTS5 has rows
  3. Site Reputation      — site_reputation.db reachable
  4. Backups              — most recent backup < 24h old, integrity check passes
  5. Guard Modes          — env-var posture matches expectation
  6. Daemons              — PM2 process list has the expected daemons
  7. API Endpoints        — state-api /health responds < 5s
  8. Disk Space           — state/ < 80%, tmp/ < 90%
  9. Git Status           — working tree clean, last commit < 7 days
 10. Credentials          — .env.agents present, required keys non-empty
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.subprocess_helpers import safe_run  # noqa: E402

STATE_DIR = PROJECT_ROOT / "state"
BACKUP_DIR = STATE_DIR / "backups"
TMP_DIR = PROJECT_ROOT / "tmp"
ENV_FILE = PROJECT_ROOT / ".env.agents"

EXPECTED_STATE_TABLES = {"agent_state", "session_log", "active_task"}
EXPECTED_DAEMONS = {"event-router", "override-consumer"}  # core pair from PLAYBOOK
REQUIRED_ENV_KEYS = (
    "BRAVO_SUPABASE_URL",
    "BRAVO_SUPABASE_SERVICE_ROLE_KEY",
)


# ── Check primitives ────────────────────────────────────────────────────

def _ok(detail: str = "") -> dict[str, Any]:
    return {"status": "ok", "detail": detail}


def _warn(detail: str) -> dict[str, Any]:
    return {"status": "warn", "detail": detail}


def _fail(detail: str) -> dict[str, Any]:
    return {"status": "fail", "detail": detail}


def check_state_db() -> dict[str, Any]:
    path = STATE_DIR / "empire_state.db"
    if not path.exists():
        return _fail(f"missing: {path}")
    try:
        conn = sqlite3.connect(str(path))
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return _fail(f"unreadable: {exc}")
    mode_str = mode[0] if mode else "unknown"
    missing = EXPECTED_STATE_TABLES - tables
    if missing:
        return _warn(f"WAL={mode_str}, missing tables: {sorted(missing)}")
    return _ok(f"journal={mode_str}, {len(tables)} tables")


def check_memory_index() -> dict[str, Any]:
    path = STATE_DIR / "memory_index.db"
    if not path.exists():
        return _warn(f"missing: {path} (FTS5 not built)")
    try:
        conn = sqlite3.connect(str(path))
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            chunks = 0
            for table in ("chunks", "memory_chunks", "fts"):
                if table in tables:
                    try:
                        chunks = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        break
                    except sqlite3.OperationalError:
                        continue
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return _fail(f"unreadable: {exc}")
    if chunks == 0:
        return _warn("index reachable but empty (rebuild needed)")
    return _ok(f"{chunks} chunks")


def check_site_reputation() -> dict[str, Any]:
    path = STATE_DIR / "site_reputation.db"
    if not path.exists():
        return _warn(f"missing: {path} (research_fetch will build on first use)")
    try:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return _fail(f"unreadable: {exc}")
    return _ok("reachable")


def check_backups() -> dict[str, Any]:
    if not BACKUP_DIR.exists():
        return _warn("no backups directory")
    backups = sorted(BACKUP_DIR.glob("backup_*.db"))
    if not backups:
        return _warn("no backups present")
    newest = max(backups, key=lambda p: p.stat().st_mtime)
    age_h = (time.time() - newest.stat().st_mtime) / 3600
    if age_h > 24:
        return _warn(f"newest backup is {age_h:.1f}h old (> 24h)")
    # Quick integrity check on the newest
    try:
        conn = sqlite3.connect(str(newest))
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
        integrity = row[0] if row else "no_result"
    except sqlite3.DatabaseError as exc:
        return _fail(f"newest backup corrupt: {exc}")
    if integrity != "ok":
        return _fail(f"newest backup integrity={integrity}")
    return _ok(f"{len(backups)} backups, newest {age_h:.1f}h old, integrity ok")


def check_guard_modes() -> dict[str, Any]:
    secret = os.environ.get("EMPIRE_HOOK_SECRET_GUARD", "report").lower()
    exec_g = os.environ.get("EMPIRE_HOOK_EXEC_GUARD", "report").lower()
    state_g = os.environ.get("EMPIRE_HOOK_STATE_GUARD", "off").lower()
    notes = []
    if secret == "off":
        return _fail("secret_guard=off (must be report or enforce)")
    if exec_g == "off":
        notes.append("exec_guard=off")
    notes.append(f"secret={secret}, exec={exec_g}, state={state_g}")
    if exec_g == "report" or state_g == "off":
        return _warn(", ".join(notes) + " — production should be enforce")
    return _ok(", ".join(notes))


def check_daemons() -> dict[str, Any]:
    # PM2 list — best-effort. Missing PM2 is a warning (dev/test environment).
    pm2 = shutil.which("pm2")
    if not pm2:
        return _warn("pm2 not installed (dev environment)")
    try:
        result = safe_run(
            [pm2, "jlist"], capture_output=True, text=True, timeout=10
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return _warn(f"pm2 jlist failed: {exc}")
    if result.returncode != 0:
        return _warn(f"pm2 jlist exit {result.returncode}")
    try:
        procs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _warn("pm2 jlist returned non-JSON")
    running = {p.get("name") for p in procs if p.get("pm2_env", {}).get("status") == "online"}
    missing = EXPECTED_DAEMONS - running
    if missing:
        return _warn(f"missing daemons: {sorted(missing)} (running: {sorted(running)})")
    return _ok(f"{len(running)} daemons online")


def check_api_endpoints() -> dict[str, Any]:
    """Probe state-api /health, best-effort. localhost only — never hits the
    public domain from the health check."""
    try:
        import urllib.request  # stdlib
        start = time.monotonic()
        with urllib.request.urlopen("http://127.0.0.1:8500/health", timeout=5) as resp:
            payload = json.loads(resp.read())
        elapsed_ms = (time.monotonic() - start) * 1000
    except Exception as exc:
        return _warn(f"state-api /health unreachable: {type(exc).__name__}")
    status = (payload or {}).get("status", "unknown")
    if status != "healthy":
        return _warn(f"state-api reported {status}")
    return _ok(f"state-api healthy, latency {elapsed_ms:.0f}ms")


def check_disk_space() -> dict[str, Any]:
    notes = []
    for name, path in (("state", STATE_DIR), ("tmp", TMP_DIR)):
        if not path.exists():
            continue
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        pct_used = (usage.used / usage.total) * 100 if usage.total else 0
        limit = 80 if name == "state" else 90
        if pct_used > limit:
            return _fail(f"{name}/ {pct_used:.0f}% full (> {limit}%)")
        notes.append(f"{name}/ {pct_used:.0f}%")
    return _ok(", ".join(notes))


def check_git_status() -> dict[str, Any]:
    if not shutil.which("git"):
        return _warn("git not installed")
    try:
        # Working tree clean?
        status = safe_run(
            ["git", "-C", str(PROJECT_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
        # Last commit age
        log = safe_run(
            ["git", "-C", str(PROJECT_ROOT), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=10,
        )
        last_commit_ts = int(log.stdout.strip()) if log.returncode == 0 and log.stdout.strip() else 0
    except (subprocess.SubprocessError, ValueError) as exc:
        return _warn(f"git probe failed: {exc}")
    age_days = (time.time() - last_commit_ts) / 86400 if last_commit_ts else 999
    notes = []
    if dirty:
        notes.append("working tree dirty")
    if age_days > 7:
        notes.append(f"last commit {age_days:.0f}d ago")
    if notes:
        return _warn(", ".join(notes))
    return _ok(f"clean, last commit {age_days:.1f}d ago")


def check_credentials() -> dict[str, Any]:
    if not ENV_FILE.exists():
        return _fail(".env.agents missing")
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        return _fail(f".env.agents unreadable: {exc}")
    present = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if v.strip().strip('"').strip("'"):
            present.add(k.strip())
    missing = [k for k in REQUIRED_ENV_KEYS if k not in present]
    if missing:
        return _fail(f"missing required keys: {missing}")
    return _ok(f"{len(present)} keys set")


CHECKS = [
    ("State DB",        check_state_db),
    ("Memory Index",    check_memory_index),
    ("Site Reputation", check_site_reputation),
    ("Backups",         check_backups),
    ("Guard Modes",     check_guard_modes),
    ("Daemons",         check_daemons),
    ("API Endpoints",   check_api_endpoints),
    ("Disk Space",      check_disk_space),
    ("Git Status",      check_git_status),
    ("Credentials",     check_credentials),
]


# ── Aggregation + output ────────────────────────────────────────────────

def run_all() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for label, fn in CHECKS:
        try:
            r = fn()
        except Exception as exc:  # never crash the aggregator
            r = _fail(f"check raised: {type(exc).__name__}: {exc}")
        results.append({"name": label, **r})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "summary": _summarize(results),
    }


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"ok": 0, "warn": 0, "fail": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    if counts["fail"]:
        overall = "DEGRADED"
    elif counts["warn"]:
        overall = "HEALTHY_WITH_WARNINGS"
    else:
        overall = "HEALTHY"
    return {"overall": overall, **counts, "total": len(results)}


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Empire Health Report — {report['timestamp']}",
        "=" * 60,
    ]
    glyph = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}
    for r in report["results"]:
        lines.append(f"{r['name']:18s} {glyph.get(r['status'], '[??]')} {r['detail']}")
    s = report["summary"]
    lines.append("=" * 60)
    lines.append(
        f"Overall: {s['overall']} ({s['ok']}/{s['total']} ok, "
        f"{s['warn']} warn, {s['fail']} fail)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--quiet", action="store_true",
                        help="no output; exit 0 if healthy, 1 otherwise")
    args = parser.parse_args(argv)

    report = run_all()
    if args.quiet:
        return 0 if report["summary"]["overall"] == "HEALTHY" else 1
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render_text(report))
    return 0 if report["summary"]["overall"] in ("HEALTHY", "HEALTHY_WITH_WARNINGS") else 1


if __name__ == "__main__":
    sys.exit(main())
