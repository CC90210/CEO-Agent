"""
fleet_health.py — Cross-agent health rollup.

Single command that reports the state of CC's full agent fleet:
  - Pulse freshness (Bravo / Atlas / Maven)
  - Agent inbox unread counts (per agent)
  - Recent cron job success/failure
  - Bridge lock status
  - Memory staleness summary

Output is human-readable by default; --json for machine consumption.

Usage:
  python scripts/fleet_health.py
  python scripts/fleet_health.py --json
  python scripts/fleet_health.py --agent bravo|atlas|maven|aura|hermes
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SIBLING_REPOS = {
    "bravo": REPO_ROOT,
    "atlas": REPO_ROOT.parent / "APPS" / "CFO-Agent",
    "maven": REPO_ROOT.parent / "CMO-Agent",
    "aura": REPO_ROOT.parent / "AURA",
    "hermes": REPO_ROOT.parent / "hermes",
}
PULSE_PATHS = {
    "bravo": REPO_ROOT / "data" / "pulse" / "ceo_pulse.json",
    "atlas": REPO_ROOT.parent / "APPS" / "CFO-Agent" / "data" / "pulse" / "cfo_pulse.json",
    "maven": REPO_ROOT.parent / "CMO-Agent" / "data" / "pulse" / "cmo_pulse.json",
}
INBOX_DIR = REPO_ROOT / "tmp" / "agent_inbox"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str) -> datetime | None:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def check_pulse(agent: str) -> dict[str, Any]:
    """Read a pulse file and report its freshness.

    AURA + Hermes are domain-isolated by design — they don't have a pulse
    contract. Returning `status="domain_isolated"` for them keeps the
    rollup honest instead of falsely flagging "missing".
    """
    if agent in {"aura", "hermes"}:
        return {"agent": agent, "status": "domain_isolated", "note": "no pulse by design"}
    path = PULSE_PATHS.get(agent)
    if path is None or not path.exists():
        return {"agent": agent, "status": "missing", "path": str(path) if path else None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"agent": agent, "status": "unreadable", "error": str(exc)}
    updated_at = _parse_iso(data.get("updated_at", ""))
    if updated_at is None:
        return {"agent": agent, "status": "no_timestamp", "data_keys": list(data.keys())}
    age_hours = (_now_utc() - updated_at).total_seconds() / 3600
    if age_hours < 24:
        status = "fresh"
    elif age_hours < 7 * 24:
        status = "aging"
    else:
        status = "stale"
    return {
        "agent": agent,
        "status": status,
        "updated_at": data.get("updated_at"),
        "age_hours": round(age_hours, 1),
        "schema_version": data.get("schema_version"),
    }


def check_inbox(agent: str) -> dict[str, Any]:
    """Count unread inbox messages for an agent.

    Storage layout: tmp/agent_inbox/inbox/<priority>_<timestamp>_<recipient>_<id>.json
    (unread) and tmp/agent_inbox/read/... (read). Recipient is embedded in filename.
    """
    unread_dir = INBOX_DIR / "inbox"
    if not unread_dir.exists():
        return {"agent": agent, "unread": 0, "urgent": 0}
    unread = 0
    urgent = 0
    for m in unread_dir.glob("*.json"):
        try:
            payload = json.loads(m.read_text(encoding="utf-8"))
            if payload.get("to") != agent:
                continue
            unread += 1
            if payload.get("priority", "").upper() in ("HIGH", "URGENT"):
                urgent += 1
        except (json.JSONDecodeError, OSError):
            continue
    return {"agent": agent, "unread": unread, "urgent": urgent}


def check_cron() -> dict[str, Any]:
    """Run cron_engine.py list and parse active vs inactive."""
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "core" / "cron_engine.py"), "list"],
            capture_output=True,
            text=True,
            timeout=15,
         creationflags=WINDOWLESS_FLAGS)
        if result.returncode != 0:
            return {"status": "error", "stderr": result.stderr.strip()[:200]}
        lines = result.stdout.strip().splitlines()
        active = sum(1 for ln in lines if "YES" in ln and "ACTIVE" not in ln)
        inactive = sum(1 for ln in lines if " no " in ln.lower() and "ACTIVE" not in ln)
        return {"status": "ok", "active": active, "inactive": inactive, "total": active + inactive}
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"status": "error", "error": str(exc)}


def check_bridge_locks() -> dict[str, Any]:
    """Inspect ~/.oasis/bridge_locks/*.json for live bridges."""
    lock_dir = Path.home() / ".oasis" / "bridge_locks"
    if not lock_dir.exists():
        return {"status": "no_lockdir", "active_bridges": []}
    active = []
    for lock_file in lock_dir.glob("*.json"):
        try:
            payload = json.loads(lock_file.read_text(encoding="utf-8"))
            heartbeat = _parse_iso(payload.get("heartbeat_at", ""))
            if heartbeat is None:
                continue
            age_seconds = (_now_utc() - heartbeat).total_seconds()
            if age_seconds < 90:
                active.append({
                    "agent": lock_file.stem,
                    "host": payload.get("host"),
                    "pid": payload.get("pid"),
                    "heartbeat_age_seconds": round(age_seconds, 1),
                })
        except (json.JSONDecodeError, OSError):
            continue
    return {"status": "ok", "active_bridges": active}


def check_memory_staleness() -> dict[str, Any]:
    """Run memory_aging.py stale --days 7 --json and summarize."""
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "core" / "memory_aging.py"), "stale", "--days", "7", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
         creationflags=WINDOWLESS_FLAGS)
        if result.returncode != 0:
            return {"status": "error", "stderr": result.stderr.strip()[:200]}
        data = json.loads(result.stdout)
        return {
            "status": "ok",
            "stale_count": data.get("stale_count", 0),
            "threshold_days": data.get("threshold_days", 7),
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        return {"status": "error", "error": str(exc)}


def check_repo_presence() -> dict[str, Any]:
    """Report which sibling repos exist on this machine."""
    return {
        agent: {"exists": path.exists(), "path": str(path)}
        for agent, path in SIBLING_REPOS.items()
    }


def build_report(agents_filter: list[str] | None = None) -> dict[str, Any]:
    all_agents = list(SIBLING_REPOS.keys())
    pulse_agents = all_agents if not agents_filter else [a for a in all_agents if a in agents_filter]
    inbox_agents = list(SIBLING_REPOS.keys()) if not agents_filter else [a for a in SIBLING_REPOS if a in agents_filter]
    return {
        "generated_at": _now_utc().isoformat(),
        "repos": check_repo_presence(),
        "pulses": [check_pulse(a) for a in pulse_agents],
        "inboxes": [check_inbox(a) for a in inbox_agents],
        "cron": check_cron(),
        "bridge_locks": check_bridge_locks(),
        "memory_staleness": check_memory_staleness(),
    }


def render_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f" FLEET HEALTH — {report['generated_at']}")
    lines.append("=" * 72)
    lines.append("")
    lines.append("REPO PRESENCE")
    for agent, info in report["repos"].items():
        marker = "OK" if info["exists"] else "MISSING"
        lines.append(f"  [{marker:>7}] {agent:<8} {info['path']}")
    lines.append("")
    lines.append("PULSE FRESHNESS")
    for p in report["pulses"]:
        if p["status"] == "fresh":
            marker = "FRESH"
        elif p["status"] == "aging":
            marker = "AGING"
        elif p["status"] == "stale":
            marker = "STALE"
        elif p["status"] == "domain_isolated":
            marker = "ISOLATED"
        else:
            marker = p["status"].upper()
        if p["status"] == "domain_isolated":
            lines.append(f"  [{marker:>8}] {p['agent']:<8} no pulse by design")
        else:
            age = f"{p.get('age_hours', '?')}h" if "age_hours" in p else "n/a"
            lines.append(f"  [{marker:>8}] {p['agent']:<8} age={age:<8} updated_at={p.get('updated_at', 'n/a')}")
    lines.append("")
    lines.append("INBOX UNREAD")
    for ib in report["inboxes"]:
        urgent_tag = f" ({ib['urgent']} urgent)" if ib["urgent"] else ""
        lines.append(f"  {ib['agent']:<8} {ib['unread']} unread{urgent_tag}")
    lines.append("")
    lines.append("CRON")
    cron = report["cron"]
    if cron.get("status") == "ok":
        lines.append(f"  {cron['active']} active / {cron['total']} total registered")
    else:
        lines.append(f"  ERROR: {cron.get('error') or cron.get('stderr')}")
    lines.append("")
    lines.append("BRIDGE LOCKS")
    bl = report["bridge_locks"]
    if bl.get("active_bridges"):
        for b in bl["active_bridges"]:
            lines.append(f"  ALIVE  {b['agent']:<8} host={b['host']} pid={b['pid']} heartbeat={b['heartbeat_age_seconds']}s ago")
    else:
        lines.append("  (no live bridges)")
    lines.append("")
    lines.append("MEMORY STALENESS (>7d)")
    ms = report["memory_staleness"]
    if ms.get("status") == "ok":
        lines.append(f"  {ms['stale_count']} stale entries")
    else:
        lines.append(f"  ERROR: {ms.get('error') or ms.get('stderr')}")
    lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-agent health rollup for CC's fleet.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument("--agent", choices=list(SIBLING_REPOS.keys()), help="Filter to one agent")
    args = parser.parse_args()
    agents_filter = [args.agent] if args.agent else None
    report = build_report(agents_filter)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render_text(report))


if __name__ == "__main__":
    main()
