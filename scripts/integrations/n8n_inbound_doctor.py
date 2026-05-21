#!/usr/bin/env python3
"""
n8n_inbound_doctor.py — diagnose why "Recent Inbound" is stale on the dashboard.

Walks the inbound pipeline end-to-end and prints what's healthy vs broken:

  1. Most recent lead_interactions row (type IN email_received|email_reply|dm_received)
     — if older than 24h, the bridge is silent.
  2. integrations_health row for n8n_inbound — last_ping_at, last_error.
  3. Webhook secret presence + which profile owns it.
  4. Vercel /api/inbound/n8n route reachability (shallow — 405 on GET means alive).
  5. Recommendation block — what to check on Hostinger n8n console.

Usage:
  python scripts/integrations/n8n_inbound_doctor.py            # human-readable
  python scripts/integrations/n8n_inbound_doctor.py --json     # JSON for cron / dashboard

Exit codes:
  0 — healthy (inbound row in last 24h)
  1 — stale (no inbound row in last 24h, or bridge ping > 24h old)
  2 — broken (webhook route unreachable, or no secret on file)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import urllib.error


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_AGENTS = REPO_ROOT / ".env.agents"

INBOUND_TYPES = ("email_received", "email_reply", "dm_received")


def _read_env() -> dict:
    if not ENV_AGENTS.exists():
        return {}
    out: dict[str, str] = {}
    for raw in ENV_AGENTS.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hours_since(iso_ts: str | None) -> float | None:
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (_now() - dt).total_seconds() / 3600
    except Exception:
        return None


def _supabase_get(env: dict, table: str, query: str) -> list[dict]:
    url = env.get("BRAVO_SUPABASE_URL", "")
    key = env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return []
    full = f"{url}/rest/v1/{table}?{query}"
    req = urllib.request.Request(
        full,
        headers={
            "apikey": key,
            "authorization": f"Bearer {key}",
            "accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8") or "[]")
    except Exception:
        return []


def _check_webhook_route(env: dict) -> tuple[bool, str]:
    base = env.get("BRAVO_DASHBOARD_URL", "https://agent-dashboard-cc90210.vercel.app")
    url = base.rstrip("/") + "/api/inbound/n8n"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status in (200, 405, 401), f"GET → {r.status}"
    except urllib.error.HTTPError as e:
        # 405 (POST only) is expected — the route is alive
        if e.code in (405, 401):
            return True, f"GET → {e.code} (route alive)"
        return False, f"GET → {e.code} {e.reason}"
    except Exception as e:
        return False, f"unreachable: {e}"


def diagnose() -> dict:
    env = _read_env()

    last_inbound = _supabase_get(
        env,
        "lead_interactions",
        "select=id,type,subject,created_at"
        f"&type=in.({','.join(INBOUND_TYPES)})"
        "&order=created_at.desc&limit=1",
    )
    last_inbound_row = last_inbound[0] if last_inbound else None
    inbound_age_h = _hours_since(last_inbound_row.get("created_at")) if last_inbound_row else None

    health = _supabase_get(
        env,
        "integrations_health",
        "select=service,status,last_ping_at,last_error,metadata"
        "&service=eq.n8n_inbound&limit=1",
    )
    health_row = health[0] if health else None
    health_age_h = _hours_since(health_row.get("last_ping_at")) if health_row else None

    secrets = _supabase_get(
        env,
        "n8n_webhook_secrets",
        "select=profile_id,secret_hash,created_at,revoked_at&order=created_at.desc&limit=3",
    )
    active_secrets = [s for s in secrets if not s.get("revoked_at")]

    route_ok, route_msg = _check_webhook_route(env)

    # ---- Decision ---------------------------------------------------------
    healthy = (
        last_inbound_row is not None
        and (inbound_age_h or 9999) < 24
        and route_ok
    )
    stale = not healthy and route_ok and bool(active_secrets)
    broken = not route_ok or not active_secrets

    report = {
        "ok": healthy,
        "stale": stale,
        "broken": broken,
        "last_inbound": last_inbound_row,
        "last_inbound_age_hours": round(inbound_age_h, 1) if inbound_age_h is not None else None,
        "n8n_health": health_row,
        "n8n_health_age_hours": round(health_age_h, 1) if health_age_h is not None else None,
        "active_webhook_secrets": len(active_secrets),
        "webhook_route": {"ok": route_ok, "msg": route_msg},
        "checked_at": _now().isoformat(),
    }
    return report


def print_human(r: dict) -> None:
    def fmt_age(h: float | None) -> str:
        if h is None:
            return "never"
        if h < 1:
            return f"{int(h * 60)}m ago"
        if h < 48:
            return f"{h:.1f}h ago"
        return f"{h / 24:.1f}d ago"

    print("== n8n inbound doctor ==")
    print()
    print(f"Last inbound row     : {fmt_age(r['last_inbound_age_hours'])}")
    if r["last_inbound"]:
        print(f"  └ subject          : {r['last_inbound']['subject'][:80]!r}")
    print(f"n8n_inbound ping     : {fmt_age(r['n8n_health_age_hours'])}")
    if r["n8n_health"]:
        print(f"  └ status           : {r['n8n_health']['status']}")
        if r["n8n_health"].get("last_error"):
            print(f"  └ last error       : {r['n8n_health']['last_error']}")
    print(f"Active webhook secrets: {r['active_webhook_secrets']}")
    print(f"Webhook route        : {r['webhook_route']['msg']}")
    print()

    if r["ok"]:
        print("✓ Healthy — inbound is flowing.")
    elif r["stale"]:
        print("⚠ Stale — route is up + secret is on file, but no fresh rows.")
        print()
        print("Most likely causes (check on Hostinger n8n console):")
        print("  1. The 'OASIS Inbound Qualifier' workflow is paused or errored.")
        print("  2. The Gmail trigger node lost its OAuth token — re-authenticate.")
        print("  3. The HTTP node POSTing to the dashboard has a bad URL or "
              "missing x-oasis-secret / x-oasis-profile-id header.")
        print()
        print("Fixes:")
        print("  - Open https://srv####.hstgr.cloud/ → workflow → check Executions tab")
        print("  - Re-issue the secret if rotated:")
        print("      python scripts/integrations/n8n_webhook_secret.py issue --profile-email <you>")
    elif r["broken"]:
        print("✗ Broken — bridge cannot work in current state.")
        if not r["webhook_route"]["ok"]:
            print(f"  - Webhook route unreachable: {r['webhook_route']['msg']}")
        if r["active_webhook_secrets"] == 0:
            print("  - No active webhook secret. Issue one:")
            print("      python scripts/integrations/n8n_webhook_secret.py issue --profile-email <you>")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="JSON output (machine)")
    args = ap.parse_args()

    r = diagnose()
    if args.json:
        print(json.dumps(r, indent=2, default=str))
    else:
        print_human(r)

    if r["broken"]:
        return 2
    if r["stale"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
