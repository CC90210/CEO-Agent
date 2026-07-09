"""cron_health_check.py — meta-monitoring for the Automations tab.

Runs nightly at 22:00 via SEED_JOBS entry "Bravo — Daily Cron Health Check".
Scans `public.cron_jobs` for any active row whose `last_result` starts with
ERROR or FAILED. If any found, ships a single consolidated Telegram alert
to CC so a broken cron doesn't sit dead for a week (which is exactly how
the MRR sync gap went unnoticed until 2026-05-22).

Two reasons this is the *meta* cron, not just another business cron:
  1. It guards the OTHER crons. A silent break in any of the 14+ active
     business automations would be invisible without this; CC only catches
     them by happening to look at the dashboard.
  2. It self-monitors: if this script itself fails, the FAILED row in
     cron_jobs surfaces in the dashboard's red-border treatment — so the
     watchdog watches itself.

Flags:
  --alert   actually send the Telegram alert (default in production cron)
  --json    machine-readable output (default for dry-run)
  --dry-run scan + print, but suppress the Telegram send

Exit code:
  0 = scan succeeded (regardless of whether bad crons were found)
  1 = scan itself errored (DB unreachable etc.)

Author: Bravo · 2026-05-22
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from lib.secret_loader import bootstrap  # noqa: E402
bootstrap()

from supabase_tool import get_client, load_env  # noqa: E402


def find_bad_crons() -> list[dict]:
    """Return list of {name, last_result, last_run_at} for any active
    cron whose last_result indicates failure."""
    db = get_client(load_env())
    r = (
        db.table("cron_jobs")
        .select("id,name,is_active,last_result,last_run_at")
        .eq("is_active", True)
        .execute()
    )
    bad: list[dict] = []
    for row in r.data or []:
        lr = (row.get("last_result") or "").strip()
        if not lr:
            continue
        upper = lr.upper()
        if upper.startswith("ERROR") or upper.startswith("FAILED"):
            bad.append({
                "name": row["name"],
                "last_result": lr[:200],
                "last_run_at": row.get("last_run_at"),
            })
    return bad


def telegram_alert(bad: list[dict]) -> tuple[bool, str]:
    """Ship a consolidated failure alert through the same notify() path the
    rest of the fleet uses. Returns (sent, detail).

    The old path read TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID straight off
    os.environ and built its own urllib send. But under the PYTHONW scheduler
    those creds live in .env.agents (loaded by secret_loader), NOT the process
    env, and the real chat id is TELEGRAM_ALLOWED_USERS — so the watchdog
    always returned 'telegram_not_configured' and CC never saw a single failure
    alert (the watchdog was itself the silently-broken cron). notify() loads via
    secret_loader, resolves the chat id, and uses parse_mode=HTML — so we
    html-escape the tracebacks (which contain <module> etc.)."""
    lines = [f"🚨 {len(bad)} cron(s) failing:\n"]
    for b in bad[:10]:
        name = html.escape(str(b["name"]), quote=False)
        snippet = html.escape(b["last_result"][:120].replace("\n", " "), quote=False)
        lines.append(f"• {name}")
        lines.append(f"  {snippet}")
    if len(bad) > 10:
        lines.append(f"... and {len(bad) - 10} more.")
    text = "\n".join(lines)

    try:
        from notify import notify  # type: ignore
        ok = notify(text, category="system", silent=False, force=True)
        return ok, "sent" if ok else "notify_failed"
    except Exception as exc:  # noqa: BLE001
        return False, f"telegram_error:{type(exc).__name__}:{str(exc)[:80]}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--alert", action="store_true",
                   help="Send Telegram alert if bad crons found (default in prod)")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--dry-run", action="store_true",
                   help="Scan + print, suppress Telegram send")
    args = p.parse_args()

    try:
        bad = find_bad_crons()
    except Exception as exc:  # noqa: BLE001
        msg = f"ERROR: scan failed: {type(exc).__name__}: {exc}"
        print(msg, file=sys.stderr)
        return 1

    sent = False
    send_detail = "not_attempted"
    if bad and args.alert and not args.dry_run:
        sent, send_detail = telegram_alert(bad)

    summary = {
        "bad_count": len(bad),
        "bad": bad,
        "alert_sent": sent,
        "alert_detail": send_detail,
    }

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    elif not bad:
        print("ok: all crons healthy")
    else:
        print(f"WARN: {len(bad)} cron(s) failing")
        for b in bad:
            print(f"  • {b['name']}: {b['last_result'][:100]}")
        if args.alert and not args.dry_run:
            print(f"  telegram_alert: {send_detail}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
