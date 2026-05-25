"""follow_up_generator.py — generate follow_up_tasks for stuck/missing-info/no-response leads.

Part of the SunBiz second-meeting (2026-05-25) expansion.
Migration dependency: 069 (adds follow_up_tasks table to tenant schema).

Reads:
  - tenant_records where entity_type='lead' (hot_lead / missing_info / follow_ups stage)
  - tenant_records where entity_type='application' (application_in / shopping /
    missing_info / requested_docs / docs_out status)
  - follow_up_tasks (to avoid double-creating for same lead on same calendar day)

Writes:
  - follow_up_tasks rows with source='auto'

Idempotency:
  - UNIQUE constraint assumed on (tenant_id, lead_id, DATE(created_at), source='auto').
    The daemon guards this in Python with a pre-fetch check as a belt-and-suspenders
    measure — even without the DB constraint, running twice in the same day is safe.

Environment:
  - FOLLOW_UP_TENANT_SLUG=sun  → restricts processing to the tenant whose
    manifest slug matches. Omit to process every SunBiz tenant.

Schedule recommendation (cron):
  0 6 * * * cd /home/sunbiz && python scripts/follow_up_generator.py once
Or via claude-bridge-ping cron poller with manifest key: follow_up_generator_once

CLI:
  python scripts/follow_up_generator.py once
  python scripts/follow_up_generator.py loop --interval 86400
  python scripts/follow_up_generator.py tail --count 50
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────
# Paths + constants
# ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
LOG_PATH = STATE_DIR / "follow_up_generator.log"

DAEMON_NAME = "follow_up_generator"

# Leads in these stages that haven't been contacted in LEAD_STALE_DAYS get a task.
STALE_LEAD_STAGES = {"hot_lead", "missing_info", "follow_ups"}
LEAD_STALE_DAYS = 3

# Applications in these statuses that haven't progressed in APP_STUCK_DAYS get a task.
STUCK_APP_STATUSES = {"application_in", "shopping", "missing_info", "requested_docs", "docs_out"}
APP_STUCK_DAYS = 5

# Reason mapping from lead stage → task reason
_STAGE_REASON: dict[str, str] = {
    "hot_lead": "stalled",
    "missing_info": "missing_info",
    "follow_ups": "no_response",
}


# ─────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────


def _log(msg: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] [{DAEMON_NAME}] {msg}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass
    print(line.rstrip())


# ─────────────────────────────────────────────────────────────────────
# Env + Supabase client (service-role)
# ─────────────────────────────────────────────────────────────────────


def _load_env() -> dict[str, str]:
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env  # type: ignore
        return load_env()
    except Exception:
        return {}


def _supabase():
    env = _load_env()
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        _log("missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        return None
    try:
        from supabase import create_client  # type: ignore
        return create_client(url, key)
    except Exception as e:
        _log(f"supabase client init failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────
# Tenant resolution
# ─────────────────────────────────────────────────────────────────────


def _resolve_tenant_ids(sb, slug_filter: str) -> list[str]:
    """Return a list of tenant_id UUIDs to process.

    If slug_filter is non-empty, only the tenant whose manifest slug
    matches is returned. Otherwise all tenants with an active manifest
    are returned.
    """
    try:
        q = sb.table("tenant_manifests").select("tenant_id, slug")
        if slug_filter:
            q = q.eq("slug", slug_filter)
        rows = q.execute()
        return [r["tenant_id"] for r in (rows.data or []) if r.get("tenant_id")]
    except Exception as e:
        _log(f"tenant resolution failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────
# Open-task guard — avoid double-creating for same lead today
# ─────────────────────────────────────────────────────────────────────


def _open_auto_task_ids(sb, tenant_id: str) -> set[str]:
    """Return set of lead_id / application_id values that already have
    an open auto-generated follow_up_task created today."""
    today = date.today().isoformat()
    try:
        rows = (
            sb.table("follow_up_tasks")
            .select("lead_id")
            .eq("tenant_id", tenant_id)
            .eq("source", "auto")
            .eq("status", "open")
            .gte("created_at", today)
            .execute()
        )
        return {r["lead_id"] for r in (rows.data or []) if r.get("lead_id")}
    except Exception as e:
        _log(f"open-task guard query failed tenant={tenant_id}: {e}")
        return set()


# ─────────────────────────────────────────────────────────────────────
# Task insertion
# ─────────────────────────────────────────────────────────────────────


def _due_at_today_9am() -> str:
    """ISO datetime for 9am UTC today (good-enough proxy for 9am ET
    for server-side generation; operators see local time on dashboard)."""
    today = date.today()
    return datetime(today.year, today.month, today.day, 14, 0, 0, tzinfo=timezone.utc).isoformat()


def _insert_task(sb, tenant_id: str, lead_id: str, reason: str) -> bool:
    """Insert a follow_up_tasks row. Returns True on success."""
    try:
        sb.table("follow_up_tasks").insert(
            {
                "tenant_id": tenant_id,
                "lead_id": lead_id,
                "reason": reason,
                "due_at": _due_at_today_9am(),
                "status": "open",
                "source": "auto",
            }
        ).execute()
        return True
    except Exception as e:
        _log(f"insert task failed tenant={tenant_id} lead={lead_id}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────
# Lead sweep
# ─────────────────────────────────────────────────────────────────────


def _is_stale_lead(data: dict[str, Any]) -> bool:
    """True if the lead has not been contacted in LEAD_STALE_DAYS days (or ever)."""
    last_contact = data.get("last_contacted_at")
    if not last_contact:
        return True
    try:
        dt = datetime.fromisoformat(last_contact.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return True
    return (datetime.now(timezone.utc) - dt) > timedelta(days=LEAD_STALE_DAYS)


def _sweep_leads(sb, tenant_id: str, existing_ids: set[str]) -> int:
    """Generate tasks for stale leads. Returns count of new tasks inserted."""
    try:
        rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "lead")
            .execute()
        )
    except Exception as e:
        _log(f"lead fetch failed tenant={tenant_id}: {e}")
        return 0

    created = 0
    for row in rows.data or []:
        lead_id = row.get("id", "")
        data: dict[str, Any] = row.get("data") or {}
        stage = data.get("stage", "")

        if stage not in STALE_LEAD_STAGES:
            continue
        if lead_id in existing_ids:
            continue
        if not _is_stale_lead(data):
            continue

        reason = _STAGE_REASON.get(stage, "stalled")
        if _insert_task(sb, tenant_id, lead_id, reason):
            existing_ids.add(lead_id)
            created += 1

    return created


# ─────────────────────────────────────────────────────────────────────
# Application sweep
# ─────────────────────────────────────────────────────────────────────


def _is_stuck_application(data: dict[str, Any]) -> bool:
    """True if the application has had no progress in APP_STUCK_DAYS days."""
    # Use updated_at first, then created_at as a fallback.
    for key in ("updated_at", "created_at"):
        ts = data.get(key)
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return (datetime.now(timezone.utc) - dt) > timedelta(days=APP_STUCK_DAYS)
            except (ValueError, AttributeError):
                continue
    return True  # no timestamp at all → treat as stuck


def _sweep_applications(sb, tenant_id: str, existing_ids: set[str]) -> int:
    """Generate tasks for stuck applications. Returns count of new tasks inserted."""
    try:
        rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "application")
            .execute()
        )
    except Exception as e:
        _log(f"application fetch failed tenant={tenant_id}: {e}")
        return 0

    created = 0
    for row in rows.data or []:
        app_id = row.get("id", "")
        data: dict[str, Any] = row.get("data") or {}
        status = data.get("status", "")

        if status not in STUCK_APP_STATUSES:
            continue
        if app_id in existing_ids:
            continue
        if not _is_stuck_application(data):
            continue

        # Derive reason from status
        if status == "missing_info":
            reason = "missing_info"
        elif status in {"docs_out", "requested_docs"}:
            reason = "no_response"
        else:
            reason = "stalled"

        if _insert_task(sb, tenant_id, app_id, reason):
            existing_ids.add(app_id)
            created += 1

    return created


# ─────────────────────────────────────────────────────────────────────
# Core tick
# ─────────────────────────────────────────────────────────────────────


def tick() -> int:
    sb = _supabase()
    if not sb:
        _log("supabase unavailable — skipping tick")
        return 0

    env = _load_env()
    slug_filter = (env.get("FOLLOW_UP_TENANT_SLUG") or "").strip()

    tenant_ids = _resolve_tenant_ids(sb, slug_filter)
    if not tenant_ids:
        _log("no tenants found — nothing to process")
        return 0

    total = 0
    for tid in tenant_ids:
        existing = _open_auto_task_ids(sb, tid)
        lead_count = _sweep_leads(sb, tid, existing)
        app_count = _sweep_applications(sb, tid, existing)
        sub_total = lead_count + app_count
        _log(
            f"tenant={tid[:8]}...: {sub_total} new tasks "
            f"({lead_count} stale leads + {app_count} stuck applications)"
        )
        total += sub_total

    _log(f"tick complete — {total} total new follow_up_tasks")
    return total


# ─────────────────────────────────────────────────────────────────────
# Daemon subcommands
# ─────────────────────────────────────────────────────────────────────


def loop(interval: int) -> int:
    interval = max(3600, int(interval))
    _log(f"follow_up_generator up; tick interval = {interval}s")
    while True:
        try:
            tick()
        except Exception as e:
            _log(f"tick crashed: {e}")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            _log("follow_up_generator shutting down (SIGINT)")
            return 0


def tail_cmd(count: int) -> int:
    if not LOG_PATH.exists():
        print("(no log yet)")
        return 0
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-count:]
    except OSError as e:
        print(f"read failed: {e}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="follow_up_generator — create follow_up_tasks for stale leads + stuck applications"
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("once", help="Run one tick and exit").set_defaults(
        func=lambda _a: 0 if tick() is not None else 1
    )

    lp = sub.add_parser("loop", help="Run continuously")
    lp.add_argument(
        "--interval",
        type=int,
        default=86400,
        help="seconds between ticks (default: 86400 = 24h)",
    )
    lp.set_defaults(func=lambda a: loop(a.interval))

    tl = sub.add_parser("tail", help="Print the last N log lines")
    tl.add_argument("--count", type=int, default=50)
    tl.set_defaults(func=lambda a: tail_cmd(a.count))

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
