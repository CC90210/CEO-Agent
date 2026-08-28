"""Dashboard-email queue monitor — catches a silent outbound stall.

WHY THIS EXISTS
---------------
On 2026-07-10 we found 62 operator-composed lead emails stranded at
metadata.status='queued' (2026-06-28 .. 07-07): the `dashboard-email-consumer`
daemon that drains them had never been started on the VPS pm2 instance, so
the dashboard "conversations"/bulk-compose path silently failed for ~12 days.
Nothing alerted — the only reason it surfaced was a manual audit.

This monitor closes that blind spot. It watches TWO independent signals so a
failure can't hide behind an empty queue the way the original bug did:

  1. LIVENESS   — the `dashboard-email-consumer` pm2 process is `online`.
                  (Catches "daemon down" even when no emails are queued.)
  2. BACKPRESSURE — no dashboard email row sits status='queued' older than
                  STALE_MINUTES. (Catches "daemon up but wedged / not draining".)

Either signal tripping fires ONE Telegram alert to the operator (EZRA channel),
then goes quiet for ALERT_COOLDOWN_S so a persistent fault can't spam. When both
signals return healthy after an alert, it sends a single "recovered" note.

It deliberately does NOT send email, mutate lead rows, or touch the queue — it
only observes and alerts. Held rows (status='held') are ignored by design.

RUN
---
    pm2 start scripts/dashboard_email_queue_monitor.py \\
        --name dashboard-email-queue-monitor \\
        --interpreter <py> -- loop --interval 300
CLI:
    python scripts/dashboard_email_queue_monitor.py once   # single check, exit
    python scripts/dashboard_email_queue_monitor.py loop    # poll forever
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "state" / "dashboard_email_queue_monitor.json"

CONSUMER_PROC = "dashboard-email-consumer"
STALE_MINUTES = 15          # a queued row older than this ⇒ drain is broken
ALERT_COOLDOWN_S = 3600     # min seconds between repeat alerts for a live fault


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    p = PROJECT_ROOT / ".env.agents"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    # env vars win over the file so a pm2 override or shell export is honored
    for k, v in os.environ.items():
        env.setdefault(k, v)
    return env


def _telegram(env: dict[str, str], text: str) -> bool:
    """Send via the EZRA channel — the one that actually delivers on this box.
    (scripts/notify.py reads TELEGRAM_BOT_TOKEN/TELEGRAM_ALLOWED_USERS which are
    absent here, so it is a silent no-op — do not route alerts through it.)"""
    tok = (env.get("EZRA_TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (env.get("EZRA_TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat:
        print("[queue_monitor] EZRA_TELEGRAM_* missing — cannot alert", file=sys.stderr)
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
            timeout=8,
        )
        ok = bool(r.json().get("ok"))
        if not ok:
            print(f"[queue_monitor] telegram send failed: {r.text[:200]}", file=sys.stderr)
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[queue_monitor] telegram exception: {exc}", file=sys.stderr)
        return False


def _consumer_online() -> bool | None:
    """True/False if the consumer daemon is running; None if unknown (we do NOT
    alert on unknown, to avoid false alarms on a probe hiccup).

    NEVER invokes pm2. This used to shell `pm2 jlist`, and on a machine where
    pm2's named pipe returns EPERM every such call SPAWNS AN ORPHAN PM2 GOD
    DAEMON that never exits — 132 had accumulated by 2026-08-28, from this and
    two sibling probes. A monitor that degrades the machine it monitors is worse
    than no monitor.

    Supervision moved to scripts/ops/fleet_watchdog.py (e7d0a50f); its status()
    reads the OS process table and matches on the script name rather than the
    interpreter, which is the same question this needs answered.
    """
    try:
        _ops = Path(__file__).resolve().parent / "ops"
        if str(_ops.parent) not in sys.path:
            sys.path.insert(0, str(_ops.parent))
        from ops.fleet_watchdog import classify
        from ops.fleet_watchdog import status as fleet_status
        rows = fleet_status()
    except Exception as exc:  # noqa: BLE001
        print(f"[queue_monitor] fleet status unavailable: {exc}", file=sys.stderr)
        return None
    for row in rows:
        if row.get("name") == CONSUMER_PROC:
            # One definition of daemon state — see fleet_watchdog.classify.
            kind = classify(row)
            if kind == "disabled":
                return None  # deliberately stopped — not an outage to alert on
            return kind == "running"
    return False  # fleet readable but process absent ⇒ definitively down


def _stale_queued(env: dict[str, str]) -> tuple[int, str | None]:
    """Count dashboard emails stuck 'queued' older than STALE_MINUTES.
    Returns (count, oldest_created_at). count == -1 ⇒ DB unreadable (unknown)."""
    url = (env.get("BRAVO_SUPABASE_URL") or env.get("SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
           or env.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return -1, None
    try:
        from supabase import create_client
        sb = create_client(url, key)
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES)).isoformat()
        r = (
            sb.table("lead_interactions")
            .select("id, metadata, created_at")
            .eq("channel", "email").eq("direction", "outbound")
            .in_("agent_source", ["dashboard_drawer", "dashboard_bulk_email"])
            .eq("type", "email_queued")
            .lt("created_at", cutoff)
            .order("created_at", desc=False)
            .limit(500)
            .execute()
        )
        rows = [x for x in (r.data or [])
                if (x.get("metadata") or {}).get("status") == "queued"]
        oldest = rows[0]["created_at"] if rows else None
        return len(rows), oldest
    except Exception as exc:  # noqa: BLE001
        print(f"[queue_monitor] db check failed: {exc}", file=sys.stderr)
        return -1, None


def _read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception as exc:  # noqa: BLE001
        print(f"[queue_monitor] state write failed: {exc}", file=sys.stderr)


def check(env: dict[str, str]) -> dict:
    online = _consumer_online()
    stale_count, oldest = _stale_queued(env)

    problems: list[str] = []
    if online is False:
        problems.append(f"consumer pm2 process '{CONSUMER_PROC}' is DOWN")
    if stale_count > 0:
        problems.append(
            f"{stale_count} dashboard email(s) stuck queued >{STALE_MINUTES}m "
            f"(oldest {oldest}) — daemon not draining"
        )

    now = datetime.now(timezone.utc)
    state = _read_state()
    was_alerting = bool(state.get("alerting"))
    last_alert = state.get("last_alert_ts")
    result = {"online": online, "stale_count": stale_count, "problems": problems}

    if problems:
        cooled = True
        if last_alert:
            try:
                cooled = (now - datetime.fromisoformat(last_alert)) >= timedelta(seconds=ALERT_COOLDOWN_S)
            except Exception:
                cooled = True
        if not was_alerting or cooled:
            _telegram(env, "⚠️ SunBiz outbound stalled:\n• " + "\n• ".join(problems))
            state["last_alert_ts"] = now.isoformat()
        state["alerting"] = True
        result["alerted"] = (not was_alerting or cooled)
    else:
        if was_alerting:
            _telegram(env, "✅ SunBiz outbound recovered — dashboard email queue draining normally.")
        state["alerting"] = False
        state.pop("last_alert_ts", None)
        result["alerted"] = False

    state["last_check_ts"] = now.isoformat()
    _write_state(state)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Dashboard-email queue monitor")
    ap.add_argument("mode", choices=["once", "loop"], nargs="?", default="once")
    ap.add_argument("--interval", type=int, default=300, help="seconds between checks in loop mode")
    args = ap.parse_args()
    env = _load_env()
    if args.mode == "once":
        print(json.dumps(check(env)))
        return 0
    print(f"[queue_monitor] starting loop (every {args.interval}s)", file=sys.stderr)
    while True:
        try:
            check(env)
        except Exception as exc:  # noqa: BLE001
            print(f"[queue_monitor] check error: {exc}", file=sys.stderr)
        time.sleep(max(30, args.interval))


if __name__ == "__main__":
    sys.exit(main())
