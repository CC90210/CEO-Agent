#!/usr/bin/env python3
"""breeze_live_watch.py — go-live Telegram watch for the Breeze Advance portal.

Polls every --interval seconds (default 300):
  1. GET https://breezeadvance.credit/api/health — alert on HTTP failure or on
     any check flipping false EXCEPT the two known-acceptable baselines:
     resend_configured (tenant sends via its own Gmail, Resend unused) and
     vps_bridge_health_ok (AI assistant backend arrives with the Mac mini).
  2. Breeze Supabase `interactions` rows with status=failed in the last window
     — a failed merchant/staff email is exactly what CC wants to hear about
     immediately during onboarding week.

Alert discipline: Telegram (scripts/notify.py) on STATE CHANGE only — one ping
when something breaks, one when it recovers, re-ping hourly while still broken.
State in state/breeze_live_watch.json. Read-only against the portal; no writes
to any Breeze table.

Usage:
  python scripts/breeze_live_watch.py once          # single check, prints result
  python scripts/breeze_live_watch.py loop          # 5-min loop (PM2 target)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAPABILITY_META = {
    "category": "monitoring.client_apps",
    "lifecycle": "golive_week",
    "risk": "read_only",
    "triggers": ["watch breeze portal", "breeze go-live monitor", "merchant onboarding watch"],
    "owner": "bravo",
    "project": "breeze",
    "bridge": {"visible": False},
}

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from notify import notify  # noqa: E402
from secret_loader import load_env  # noqa: E402

HEALTH_URL = "https://breezeadvance.credit/api/health"
STATE_FILE = ROOT / "state" / "breeze_live_watch.json"
# Checks allowed to be false without an alert (documented in GO_LIVE_CHECKLIST):
BASELINE_FALSE = {"resend_configured", "vps_bridge_health_ok"}
REALERT_SECONDS = 3600


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def check_health() -> list[str]:
    """Return a list of problem strings (empty = healthy)."""
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "bravo-live-watch"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode("utf-8"))
            status = r.status
    except Exception as e:  # noqa: BLE001
        return [f"health endpoint unreachable: {e}"]
    if status != 200:
        return [f"health endpoint HTTP {status}"]
    problems = []
    for name, ok in (body.get("checks") or {}).items():
        if not ok and name not in BASELINE_FALSE:
            problems.append(f"health check '{name}' is failing")
    return problems


def check_failed_emails(window_min: int) -> list[str]:
    env = load_env()
    url = (env.get("Breeze_SUPABASE_URL") or "").rstrip("/")
    key = env.get("Breeze_SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        return ["Breeze Supabase creds missing in .env.agents (watch cannot see email failures)"]
    since = (datetime.now(timezone.utc) - timedelta(minutes=window_min)).isoformat()
    qs = urllib.parse.urlencode({
        "select": "to_address,subject,status,error,created_at",
        "status": "in.(failed,bounced)",
        "created_at": f"gt.{since}",
        "order": "created_at.desc",
        "limit": "10",
    })
    req = urllib.request.Request(
        f"{url}/rest/v1/interactions?{qs}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:200]
        except Exception:  # noqa: BLE001
            pass
        return [f"could not query interactions: HTTP {e.code} {detail}"]
    except Exception as e:  # noqa: BLE001
        return [f"could not query interactions: {e}"]
    return [
        f"EMAIL FAILED -> {row.get('recipient')} ({row.get('tag')}: {row.get('subject')})"
        for row in rows
    ]


def run_once(window_min: int) -> dict:
    problems = check_health() + check_failed_emails(window_min)
    state = _load_state()
    prev = state.get("problems") or []
    now = time.time()
    changed = sorted(problems) != sorted(prev)
    stale = now - float(state.get("last_alert_ts") or 0) > REALERT_SECONDS

    if problems and (changed or stale):
        notify(
            "BREEZE LIVE WATCH — problem detected:\n- " + "\n- ".join(problems[:8])
            + "\n\nPortal: https://breezeadvance.credit (merchant onboarding in progress)",
            category="system", force=True,
        )
        state["last_alert_ts"] = now
    elif not problems and prev:
        notify("BREEZE LIVE WATCH — recovered. All checks green again.",
               category="system", force=True)
        state["last_alert_ts"] = now

    state["problems"] = problems
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)
    return {"ok": not problems, "problems": problems}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["once", "loop"])
    ap.add_argument("--interval", type=int, default=300)
    args = ap.parse_args()
    if args.mode == "once":
        res = run_once(window_min=max(10, args.interval // 60 + 5))
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1
    while True:
        try:
            run_once(window_min=max(10, args.interval // 60 + 5))
        except Exception as e:  # noqa: BLE001
            print(f"[breeze_live_watch] cycle error: {e}", file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
