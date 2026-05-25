"""renewal_reminder.py — daily sweep of funded deals approaching renewal window.

Part of the SunBiz second-meeting (2026-05-25) expansion.
Migration dependency: 069 (adds funded_deal support columns to tenant_records).

Reads:
  - tenant_records where entity_type='funded_deal' and data.status='funded'
  - tenant_manifests.settings for per-tenant renewal_eligibility_threshold_pct
  - daily_plan_items (to avoid re-inserting today's items)

Writes:
  - daily_plan_items with category='renewal_eligible' (one row per deal per day)
  - Telegram alert via Bot API (RENEWAL_REMINDER_CHAT_ID or BRAVO_TELEGRAM_CHAT_ID)

Idempotency:
  - state/renewal_reminder.cursor  JSON map:  {funded_deal_id -> last_alerted_at ISO}
  - Alerts are suppressed for 7 days per deal. Re-running the same tick writes
    no new rows if the 7-day window hasn't elapsed.

Schedule recommendation (cron):
  0 9 * * * cd /home/sunbiz && python scripts/renewal_reminder.py once
Or via claude-bridge-ping cron poller with manifest key: renewal_reminder_once

CLI:
  python scripts/renewal_reminder.py once
  python scripts/renewal_reminder.py loop --interval 86400
  python scripts/renewal_reminder.py tail --count 50
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────
# Paths + constants
# ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
CURSOR_PATH = STATE_DIR / "renewal_reminder.cursor"
LOG_PATH = STATE_DIR / "renewal_reminder.log"

DAEMON_NAME = "renewal_reminder"
ALERT_COOLDOWN_DAYS = 7
DEFAULT_THRESHOLD_PCT = 40
# Window upper bound — only alert if progress is at most 50% through term.
WINDOW_HIGH_PCT = 50


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
# Cursor (idempotency store)
# ─────────────────────────────────────────────────────────────────────


def _read_cursor() -> dict[str, str]:
    """Returns {funded_deal_id -> last_alerted_at ISO str}."""
    if CURSOR_PATH.exists():
        try:
            raw = CURSOR_PATH.read_text(encoding="utf-8").strip()
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _write_cursor(cursor: dict[str, str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(json.dumps(cursor, indent=2), encoding="utf-8")


def _within_cooldown(cursor: dict[str, str], deal_id: str) -> bool:
    """True if this deal was alerted within the last ALERT_COOLDOWN_DAYS days."""
    last_iso = cursor.get(deal_id)
    if not last_iso:
        return False
    try:
        last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    return (datetime.now(timezone.utc) - last_dt) < timedelta(days=ALERT_COOLDOWN_DAYS)


# ─────────────────────────────────────────────────────────────────────
# Telegram send
# ─────────────────────────────────────────────────────────────────────


def _send_telegram(token: str, chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API using only stdlib (no third-party dep)."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        _log(f"telegram send failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────
# Tenant manifest settings lookup
# ─────────────────────────────────────────────────────────────────────


def _get_threshold_pct(sb, tenant_id: str) -> int:
    """Resolve renewal_eligibility_threshold_pct from tenant_manifests.settings.
    Falls back to DEFAULT_THRESHOLD_PCT (40) on any error."""
    try:
        rows = (
            sb.table("tenant_manifests")
            .select("settings")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        if rows.data:
            settings = rows.data[0].get("settings") or {}
            val = settings.get("renewal_eligibility_threshold_pct")
            if isinstance(val, (int, float)) and val > 0:
                return int(val)
    except Exception as e:
        _log(f"manifest lookup failed tenant={tenant_id}: {e}")
    return DEFAULT_THRESHOLD_PCT


# ─────────────────────────────────────────────────────────────────────
# Daily-plan item insert (idempotent — upsert by tenant+date+category+lead)
# ─────────────────────────────────────────────────────────────────────


def _log_daily_plan_item(sb, tenant_id: str, deal_id: str, deal_data: dict) -> None:
    today_str = date.today().isoformat()
    try:
        sb.table("daily_plan_items").upsert(
            {
                "tenant_id": tenant_id,
                "plan_date": today_str,
                "lead_id": deal_id,
                "category": "renewal_eligible",
                "status": "open",
                "data": {
                    "business_name": deal_data.get("business_name", ""),
                    "funded_amount": deal_data.get("funded_amount"),
                    "lender_name": deal_data.get("lender_name", ""),
                    "term_days": deal_data.get("term_days"),
                },
                "source": "renewal_reminder",
            },
            on_conflict="tenant_id,plan_date,lead_id,category",
        ).execute()
    except Exception as e:
        _log(f"daily_plan_items upsert failed deal={deal_id}: {e}")


# ─────────────────────────────────────────────────────────────────────
# Core sweep
# ─────────────────────────────────────────────────────────────────────


def _compute_progress(funded_at_iso: str, term_days: int) -> Optional[float]:
    """Returns fraction through term [0.0, 1.0+] or None on bad inputs."""
    if not funded_at_iso or not isinstance(term_days, (int, float)) or term_days <= 0:
        return None
    try:
        funded_at = datetime.fromisoformat(funded_at_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    elapsed = (datetime.now(timezone.utc) - funded_at).total_seconds()
    total = term_days * 86400.0
    return elapsed / total


def tick() -> int:
    """Run one sweep. Returns number of alerts sent."""
    sb = _supabase()
    if not sb:
        _log("supabase unavailable — skipping tick")
        return 0

    env = _load_env()
    tg_token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    tg_chat = (
        env.get("RENEWAL_REMINDER_CHAT_ID")
        or env.get("BRAVO_TELEGRAM_CHAT_ID")
        or ""
    ).strip()
    if not tg_token or not tg_chat:
        _log("TELEGRAM_BOT_TOKEN or chat_id not set — alerts will be skipped")

    cursor = _read_cursor()
    sent = 0
    cursor_dirty = False

    try:
        rows = (
            sb.table("tenant_records")
            .select("id, tenant_id, data")
            .eq("entity_type", "funded_deal")
            .execute()
        )
    except Exception as e:
        _log(f"funded_deal fetch failed: {e}")
        return 0

    for row in rows.data or []:
        deal_id = row.get("id", "")
        tenant_id = row.get("tenant_id", "")
        data: dict[str, Any] = row.get("data") or {}

        if data.get("status") != "funded":
            continue

        funded_at_iso = data.get("funded_at")
        term_days_raw = data.get("term_days")
        term_days = int(term_days_raw) if isinstance(term_days_raw, (int, float)) and term_days_raw > 0 else 0

        progress = _compute_progress(funded_at_iso, term_days)
        if progress is None:
            continue

        progress_pct = progress * 100.0
        threshold_pct = _get_threshold_pct(sb, tenant_id)

        # Only alert if in window [threshold_pct, WINDOW_HIGH_PCT]
        if not (threshold_pct <= progress_pct <= WINDOW_HIGH_PCT):
            continue

        if _within_cooldown(cursor, deal_id):
            continue

        # Compose message
        business_name = data.get("business_name", "Unknown")
        funded_amount = data.get("funded_amount", "?")
        lender_name = data.get("lender_name", "?")
        last_contact_date = data.get("last_contact_date") or data.get("last_contacted_at") or "N/A"
        msg = (
            f"Renewal eligible: {business_name} ({deal_id[:8]}...) is "
            f"{progress_pct:.0f}% through {term_days}d term — eligible to re-shop. "
            f"Last contact: {last_contact_date}. "
            f"Funded $: {funded_amount}. Lender: {lender_name}."
        )

        # Send Telegram (best-effort — don't block daily_plan logging)
        if tg_token and tg_chat:
            ok = _send_telegram(tg_token, tg_chat, msg)
            if ok:
                _log(f"alert sent deal={deal_id} progress={progress_pct:.1f}%")
                sent += 1
            else:
                _log(f"alert failed deal={deal_id} — skipping cursor update")
                continue
        else:
            _log(f"no telegram config — logged deal={deal_id} to daily_plan_items only")
            sent += 1

        # Log to daily_plan_items
        _log_daily_plan_item(sb, tenant_id, deal_id, data)

        # Update cursor
        cursor[deal_id] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cursor_dirty = True

    if cursor_dirty:
        _write_cursor(cursor)

    _log(f"tick complete — {sent} alerts sent")
    return sent


# ─────────────────────────────────────────────────────────────────────
# Daemon subcommands
# ─────────────────────────────────────────────────────────────────────


def loop(interval: int) -> int:
    interval = max(3600, int(interval))  # minimum 1-hour cadence for a daily sweep
    _log(f"renewal_reminder up; tick interval = {interval}s")
    while True:
        try:
            tick()
        except Exception as e:
            _log(f"tick crashed: {e}")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            _log("renewal_reminder shutting down (SIGINT)")
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
    p = argparse.ArgumentParser(description="renewal_reminder — funded-deal renewal window sweep")
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
