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

# Windows CA-bundle fix (2026-07-28) — see lib/tls_trust.py. Without it this
# watchdog died with CERTIFICATE_VERIFY_FAILED before it could read cron_jobs,
# so the meta-cron that exists to surface broken crons was itself broken and
# silent — exactly the failure mode it was built to prevent.
from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from supabase_tool import get_client, load_env  # noqa: E402

# Single source of truth for "this failure is the harness scoring itself".
# Guarded import: this watchdog must still run and alert if harness_eval is
# mid-edit or missing — degrading to "report everything" is the safe direction
# for a watchdog, so the fallback never suppresses anything.
try:
    from harness_eval import is_self_scored_failure as _is_self_scored_failure  # noqa: E402
except Exception as _exc:  # noqa: BLE001
    print(f"[cron_health_check] WARNING: harness_eval import failed ({type(_exc).__name__}: {_exc}); "
          "self-scored suppression DISABLED — the nightly eval's own row may alert.",
          file=sys.stderr)

    def _is_self_scored_failure(job: dict) -> bool:  # type: ignore[misc]
        return False


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
        lr = str(row.get("last_result") or "").strip()
        if not lr:
            continue
        upper = lr.upper()
        if not (upper.startswith("ERROR") or upper.startswith("FAILED")):
            continue
        # Same suppression harness_eval.check_cron_health already applied — the
        # nightly eval scoring ITSELF 10/11 is not a broken cron, it is the eval
        # reporting a fleet gap that has usually been fixed by the time this
        # runs. Without this the watchdog paged CC hourly (12:02, 12:30, 13:30,
        # 14:02 on 2026-08-13) about run ffb0b9a0e90d, a result already stale.
        # Imported, never re-implemented: two copies of this rule drifting apart
        # is exactly how the alert and the eval ended up disagreeing.
        if _is_self_scored_failure(row):
            continue
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
    secret_loader and resolves the chat id.

    Tracebacks contain <module> and would break parse_mode=HTML. That escaping
    moved INTO notify() on 2026-08-04 so every caller gets it — escaping here as
    well would double-encode and show CC a literal "&lt;module&gt;"."""
    lines = [f"🚨 {len(bad)} cron(s) failing:\n"]
    for b in bad[:10]:
        name = str(b["name"])
        snippet = b["last_result"][:120].replace("\n", " ")
        lines.append(f"• {name}")
        lines.append(f"  {snippet}")
    if len(bad) > 10:
        lines.append(f"... and {len(bad) - 10} more.")
    text = "\n".join(lines)

    # Key on WHICH jobs are failing, not on the rendered text. The message embeds a
    # 120-char last_result snippet that carries counts and tracebacks, so any drift
    # in that snippet minted a fresh identity and reset the backoff — which is how
    # this watchdog paged CC at 08:35, 09:00 and 10:01 for one unchanged condition
    # (2026-08-03). Same set of failing jobs → same key → the 1h→2h→4h→8h→24h ladder
    # actually engages. A NEW job joining the failure set is a new condition, and
    # correctly alerts immediately.
    dedup_key = f"cron_failing:{'|'.join(sorted(str(b['name']) for b in bad))}"
    try:
        import notify as _nf  # type: ignore
        # A SUPPRESSED alert is not a failed one. notify()'s bare bool conflates
        # them, and reading False as failure made this watchdog exit 1 and turn
        # itself into a failing cron — so CC got "cron failures detected but
        # alert delivery failed" from an alert that had worked exactly as
        # designed, and the watchdog then reported its own red row on the next
        # tick as a brand-new condition (2026-08-03).
        _, reason = _nf.notify_result(text, category="system", silent=False,
                                      force=True, dedup_key=dedup_key)
        aware = reason in _nf.DELIVERED_REASONS
        return aware, reason if reason != "failed" else "notify_failed"
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

    # If we found failures and TRIED to alert but the send didn't land, the
    # watchdog itself must go RED (nonzero exit → cron_jobs.last_result starts
    # with ERROR). Otherwise the meta-cron shows green while CC gets no alert —
    # the exact silent-failure this guard exists to prevent.
    if bad and args.alert and not args.dry_run and not sent:
        print(f"ERROR: cron failures detected but alert delivery failed "
              f"({send_detail})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
