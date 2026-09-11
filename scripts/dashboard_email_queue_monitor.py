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

Either signal tripping fires ONE Telegram alert to this company's own operators
(see _ALERT_CHANNEL_KEYS), then goes quiet for ALERT_COOLDOWN_S so a persistent
fault can't spam. When both signals return healthy after an alert, it sends a
single "recovered" note.

ONE COMPANY PER BOX. A box serves the company its host mailbox belongs to
(lib/tenant_brand.host_mailbox), exactly as its consumer does. The monitor
counts only that company's queued rows, names that company in its alerts, and
alerts only that company's channel. It never reads, counts or reports another
company's queue. (CC, 2026-09-11.)

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

from lib.tenant_brand import (
    COMPANY_DISPLAY_NAME,
    company_for_mailbox,
    host_mailbox,
    tenants_for_mailbox,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "state" / "dashboard_email_queue_monitor.json"

CONSUMER_PROC = "dashboard-email-consumer"
STALE_MINUTES = 15          # a queued row older than this ⇒ drain is broken
ALERT_COOLDOWN_S = 3600     # min seconds between repeat alerts for a live fault
BLIND_ALERT_AFTER = 3       # unreadable checks in a row before "blind" alerts (15 min at the 300s loop)


def _load_env() -> dict[str, str]:
    """Load env the way the consumer does: through lib/secret_loader.

    This used to parse the env file by hand. Since the Turso migration
    (2026-08-09) secret_loader is also where the compatibility values
    create_client() needs come from, so on the SunBiz VPS the hand parse saw
    no database URL and _stale_queued() returned -1 ("unknown") on every
    check: the stuck-row alert could not fire. The consumer and its monitor
    must read the same database. (PR #73.) The direct parse stays as a
    fallback and fills only what the loader did not supply.
    """
    env: dict[str, str] = {}
    try:
        from lib.secret_loader import SecretLoaderRefused, load_env as _secret_env  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"[queue_monitor] secret_loader unavailable, parsing the env file directly: {exc}",
              file=sys.stderr)
    else:
        try:
            env.update(_secret_env())
        except SecretLoaderRefused:
            # A refusal is the loader's policy (an interactive shell, a caller
            # under tmp/), not an outage. Reading the file directly here would
            # route around it, so it propagates. (CodeRabbit, PR #73.)
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[queue_monitor] secret_loader failed, parsing the env file directly: {exc}",
                  file=sys.stderr)
    p = PROJECT_ROOT / ".env.agents"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env.setdefault(k.strip(), v.strip())
    for k, v in os.environ.items():
        env.setdefault(k, v)
    return env


# Each company's monitor alerts ONLY that company's own operators. EZRA is
# SunBiz's operations channel: an OASIS box must never use it, even where the
# keys happen to be present. A company with no entry here cannot alert, and
# says so, rather than borrowing another company's channel.
_ALERT_CHANNEL_KEYS: dict[str, tuple[str, str]] = {
    "sunbiz": ("EZRA_TELEGRAM_BOT_TOKEN", "EZRA_TELEGRAM_CHAT_ID"),
}


def _telegram(env: dict[str, str], company: str | None, text: str) -> bool:
    """Send to this company's own alert channel (see _ALERT_CHANNEL_KEYS)."""
    keys = _ALERT_CHANNEL_KEYS.get(company or "")
    if not keys:
        print(f"[queue_monitor] no alert channel is configured for company {company!r} "
              "— cannot alert", file=sys.stderr)
        return False
    tok = (env.get(keys[0]) or "").strip()
    chat = (env.get(keys[1]) or "").strip()
    if not tok or not chat:
        print(f"[queue_monitor] {keys[0]} / {keys[1]} missing — cannot alert", file=sys.stderr)
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


_IS_WINDOWS = os.name == "nt"
_PROC_ROOT = Path("/proc")
_CONSUMER_SCRIPT = "dashboard_email_consumer.py"


def _consumer_running_from_proc() -> bool | None:
    """Linux: is THIS checkout's consumer running? Read from /proc with no pm2
    call, matching the script's path as fleet_watchdog matches its name on
    Windows.

    A process counts only if it is alive (not a zombie), is a Python
    interpreter, and runs this checkout's dashboard_email_consumer.py. A grep or
    an editor with that name in its arguments, or another checkout's consumer,
    does not: any of them would hide a dead daemon. (Codex, PR #73.) None if
    /proc is unreadable, the same "unknown" the Windows path gives.
    """
    if not _PROC_ROOT.is_dir():
        return None
    expected = (PROJECT_ROOT / "scripts" / _CONSUMER_SCRIPT).resolve()
    try:
        entries = [e for e in _PROC_ROOT.iterdir() if e.name.isdigit()]
    except OSError as exc:
        print(f"[queue_monitor] /proc unreadable: {exc}", file=sys.stderr)
        return None
    unreadable = False
    for entry in entries:
        try:
            argv = [a.decode("utf-8", "replace")
                    for a in (entry / "cmdline").read_bytes().split(b"\0") if a]
            state = (entry / "stat").read_text().rsplit(")", 1)[-1].split()[0]
        except (FileNotFoundError, ProcessLookupError, IndexError):
            continue  # exited between the listing and the read
        except OSError:
            # Present but unreadable: it could be the consumer, so the answer
            # is "unknown", which never pages, not "down". (CodeRabbit, PR #73.)
            unreadable = True
            continue
        if state == "Z" or not argv or "python" not in Path(argv[0]).name:
            continue
        for arg in argv[1:]:
            if not arg.endswith(_CONSUMER_SCRIPT):
                continue
            path = Path(arg)
            if not path.is_absolute():
                try:
                    path = Path(os.readlink(entry / "cwd")) / path
                except FileNotFoundError:
                    continue
                except OSError:
                    unreadable = True
                    continue
            try:
                if path.resolve() == expected:
                    return True
            except OSError:
                continue
    return None if unreadable else False


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

    fleet_watchdog reads that table through WMI only, so on Linux it sees
    nothing and this returned None: the SunBiz VPS monitor could never report
    the consumer down. There the table is /proc, read directly. (PR #73.)
    """
    if not _IS_WINDOWS:
        return _consumer_running_from_proc()
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


def _stale_queued(env: dict[str, str], tenant_ids: list[str]) -> tuple[int, str | None]:
    """Count THIS company's dashboard emails stuck 'queued' older than
    STALE_MINUTES. Returns (count, oldest_created_at); count == -1 means the
    queue could not be read. The tenant filter is in the query itself, so
    this box never reads another company's rows."""
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
            .in_("tenant_id", list(tenant_ids))
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
    mailbox = host_mailbox(env)
    company = company_for_mailbox(mailbox)
    scope = tenants_for_mailbox(mailbox)
    label = COMPANY_DISPLAY_NAME.get(company or "", "This box")
    online = _consumer_online()

    state = _read_state()
    problems: list[str] = []
    if scope:
        stale_count, oldest = _stale_queued(env, scope)
    else:
        # The consumer on a box like this refuses to drain anything. Say so
        # rather than watch nothing in silence.
        stale_count, oldest = 0, None
        problems.append("this box's mailbox belongs to no registered company, so no "
                        "dashboard email queue is being sent or watched here")
    if online is False:
        problems.append(f"consumer pm2 process '{CONSUMER_PROC}' is DOWN")
    if stale_count > 0:
        problems.append(
            f"{stale_count} dashboard email(s) stuck queued >{STALE_MINUTES}m "
            f"(oldest {oldest}) — daemon not draining"
        )
    # -1 means the queue could not be read. It used to count as "no stuck
    # rows", which is how this check sat blind on the VPS for a month without
    # a word. An unreadable queue is a problem, not a zero. One failed read is
    # not an outage, though: it alerts after BLIND_ALERT_AFTER checks in a row,
    # so a single DB blip does not page the client's channel. (Codex, PR #73.)
    blind = int(state.get("unreadable_streak") or 0) + 1 if stale_count < 0 else 0
    state["unreadable_streak"] = blind
    if blind >= BLIND_ALERT_AFTER:
        problems.append(
            f"cannot read the dashboard email queue ({blind} checks in a row), so the "
            "stuck-row check is blind — check this monitor's database access"
        )

    now = datetime.now(timezone.utc)
    was_alerting = bool(state.get("alerting"))
    last_alert = state.get("last_alert_ts")
    result = {"company": company, "online": online, "stale_count": stale_count,
              "problems": problems}

    if problems:
        cooled = True
        if last_alert:
            try:
                cooled = (now - datetime.fromisoformat(last_alert)) >= timedelta(seconds=ALERT_COOLDOWN_S)
            except Exception:
                cooled = True
        delivered = False
        if not was_alerting or cooled:
            delivered = _telegram(env, company, f"⚠️ {label} outbound stalled:\n• " + "\n• ".join(problems))
            # Only a DELIVERED alert starts the cooldown. Recording the attempt
            # let a Telegram timeout, a refusal or a missing credential suppress
            # the only notice of a stalled queue for an hour; now the next check
            # retries. (Codex, PR #73.)
            if delivered:
                state["last_alert_ts"] = now.isoformat()
        state["alerting"] = True
        result["alerted"] = delivered
    else:
        if was_alerting:
            _telegram(env, company, f"✅ {label} outbound recovered — dashboard email queue draining normally.")
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
