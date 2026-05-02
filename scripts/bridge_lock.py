"""
Bridge Lock — multi-machine arbitration for Telegram (and future Discord/Slack)
bridges.

Problem: CC switches between Mac and Windows. If both machines have PM2 set to
auto-start the bridge, they'll both poll the same Telegram bot token. Telegram
returns 409 Conflict to whichever loses the race; the loser previously went
"dormant" and stayed silent for days. Even after the dormant-mode fix (exit 1
+ PM2 autorestart), the loser will keep restarting and conflicting with the
winner. This module is the active arbiter.

Architecture: a single lockfile per agent, stored in `~/.oasis/bridge_locks/`,
holds `{pid, host, agent, started_at, last_heartbeat}` as JSON. Each bridge:

  1. On start  → call `acquire()`. If another host has a fresh heartbeat
                 (< stale_after_seconds), exit 1 (PM2 retries with backoff).
                 If lockfile is stale (host died without releasing), reclaim it.
                 If lockfile is mine (PM2 restart), reclaim it.
  2. Every 15s → call `heartbeat()` to refresh last_heartbeat.
  3. On exit   → call `release()` to delete the lockfile.

Production-grade properties:
  - File-based, no DB dependency (works on first install before Supabase wiring).
  - Atomic write via tempfile + rename.
  - Stale detection (60s default) — host can die without proper cleanup.
  - Cross-platform (Windows + macOS + Linux): writes to ~/.oasis/bridge_locks/.
  - Cross-language: Python + JS (telegram_agent.js) call this module the same way.

USAGE FROM PYTHON
-----------------
    from bridge_lock import acquire, heartbeat, release

    if not acquire(agent="atlas", stale_after=60):
        sys.exit(1)
    # ... start polling ...
    # background timer:
    threading.Timer(15.0, lambda: heartbeat("atlas")).start()

USAGE FROM SHELL (JS bridges call this via subprocess)
------------------------------------------------------
    python scripts/bridge_lock.py acquire --agent bravo
        → exit 0 = acquired (this machine owns the bridge)
        → exit 1 = another machine holds it (caller should sleep + retry, or PM2 will)
        → exit 2 = bad args / config error

    python scripts/bridge_lock.py heartbeat --agent bravo
    python scripts/bridge_lock.py release --agent bravo
    python scripts/bridge_lock.py status --agent bravo --json
        → emits {agent, host, pid, age_seconds, is_mine, is_stale}
    python scripts/bridge_lock.py status --json
        → all locks at once
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any, Optional

LOCK_DIR = Path.home() / ".oasis" / "bridge_locks"
DEFAULT_STALE_SECONDS = 60
HOSTNAME = socket.gethostname() or "unknown"
PID = os.getpid()


def _lock_path(agent: str) -> Path:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    return LOCK_DIR / f"{agent}.json"


def _read_lock(agent: str) -> Optional[dict[str, Any]]:
    p = _lock_path(agent)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _write_lock_atomic(agent: str, payload: dict[str, Any]) -> None:
    p = _lock_path(agent)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(p)


def _now() -> float:
    return time.time()


def status(agent: Optional[str] = None) -> Any:
    """Return one or all lock states. None for missing."""
    if agent:
        data = _read_lock(agent)
        if data is None:
            return {"agent": agent, "exists": False}
        age = _now() - float(data.get("last_heartbeat", 0))
        return {
            **data, "exists": True,
            "age_seconds": round(age, 1),
            "is_mine": data.get("host") == HOSTNAME and data.get("pid") == PID,
            "is_stale": age > DEFAULT_STALE_SECONDS,
        }
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    return [status(p.stem) for p in LOCK_DIR.glob("*.json")]


def acquire(agent: str, stale_after: int = DEFAULT_STALE_SECONDS) -> bool:
    """Try to claim the lock. Returns True if we own it after this call."""
    existing = _read_lock(agent)
    now = _now()
    if existing:
        host = existing.get("host")
        pid = existing.get("pid")
        last = float(existing.get("last_heartbeat", 0))
        age = now - last
        # Same host + same pid = we already own it (idempotent re-acquire).
        if host == HOSTNAME and pid == PID:
            existing["last_heartbeat"] = now
            _write_lock_atomic(agent, existing)
            return True
        # Same host, different pid = old crashed process on this machine. Reclaim.
        if host == HOSTNAME:
            # If the old PID is still alive AND fresh, refuse to clobber.
            if age < stale_after and _pid_alive(pid):
                return False
            # Otherwise reclaim (typical PM2 restart path).
        # Different host: must be stale to take over.
        elif age < stale_after:
            return False
    # Write fresh lock.
    _write_lock_atomic(agent, {
        "agent": agent, "host": HOSTNAME, "pid": PID,
        "started_at": now, "last_heartbeat": now,
    })
    return True


def heartbeat(agent: str) -> bool:
    """Refresh our last_heartbeat. Same-host always succeeds — different Python
    invocations on the same machine each have their own pid, but they're all
    serving the same bridge. Only fail if a DIFFERENT host took over the lock.
    """
    existing = _read_lock(agent)
    if not existing:
        # Lock vanished — recreate (race-safe; another startup will see fresh).
        return acquire(agent)
    if existing.get("host") != HOSTNAME:
        return False  # different host owns it now — we lost the race
    existing["last_heartbeat"] = _now()
    _write_lock_atomic(agent, existing)
    return True


def release(agent: str) -> bool:
    """Delete the lockfile if same host owns it. Different host = no-op."""
    existing = _read_lock(agent)
    if not existing:
        return True
    if existing.get("host") == HOSTNAME:
        try:
            _lock_path(agent).unlink()
        except FileNotFoundError:
            pass
        return True
    return False


def _pid_alive(pid: Optional[int]) -> bool:
    """Best-effort PID-alive check. Returns False if pid is None or process gone."""
    if not pid:
        return False
    try:
        if os.name == "nt":
            import subprocess
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=3,
            )
            return str(pid) in r.stdout
        os.kill(int(pid), 0)
        return True
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Bridge lock — multi-machine arbitration.")
    sub = p.add_subparsers(dest="command")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--agent", required=False, help="bravo | atlas | maven | aura | hermes")
    common.add_argument("--json", dest="output_json", action="store_true")

    pa = sub.add_parser("acquire", parents=[common])
    pa.add_argument("--stale-after", type=int, default=DEFAULT_STALE_SECONDS)

    sub.add_parser("heartbeat", parents=[common])
    sub.add_parser("release", parents=[common])
    sub.add_parser("status", parents=[common])

    args = p.parse_args()
    out_json = getattr(args, "output_json", False)

    if args.command == "acquire":
        if not args.agent: print("ERROR: --agent required", file=sys.stderr); return 2
        ok = acquire(args.agent, stale_after=args.stale_after)
        result = {"agent": args.agent, "acquired": ok, "host": HOSTNAME, "pid": PID}
        if out_json: print(json.dumps(result))
        else: print(f"{'ACQUIRED' if ok else 'CONFLICT'}: {args.agent} on {HOSTNAME}:{PID}")
        return 0 if ok else 1

    if args.command == "heartbeat":
        if not args.agent: print("ERROR: --agent required", file=sys.stderr); return 2
        ok = heartbeat(args.agent)
        if out_json: print(json.dumps({"agent": args.agent, "heartbeat": ok}))
        else: print(f"{'OK' if ok else 'LOST_LOCK'}: {args.agent}")
        return 0 if ok else 1

    if args.command == "release":
        if not args.agent: print("ERROR: --agent required", file=sys.stderr); return 2
        ok = release(args.agent)
        if out_json: print(json.dumps({"agent": args.agent, "released": ok}))
        else: print(f"{'RELEASED' if ok else 'NOT_OWNED'}: {args.agent}")
        return 0

    if args.command == "status":
        result = status(args.agent) if args.agent else status()
        if out_json: print(json.dumps(result, indent=2))
        else:
            rows = result if isinstance(result, list) else [result]
            for r in rows:
                if not r.get("exists"):
                    print(f"  {r['agent']:10s} <no lock>"); continue
                staleness = "STALE" if r.get("is_stale") else "fresh"
                mine = "(mine)" if r.get("is_mine") else f"@ {r.get('host')}:{r.get('pid')}"
                print(f"  {r['agent']:10s} {mine:30s} age={r.get('age_seconds')}s {staleness}")
        return 0

    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
