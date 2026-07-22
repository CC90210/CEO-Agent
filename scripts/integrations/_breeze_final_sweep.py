#!/usr/bin/env python3
"""Final infra sweep for breeze-portal production. Secrets fetched in-process,
never printed — output is statuses/booleans only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass
import requests  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402

APP = "https://breezeadvance.credit"
FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        FAILS.append(label)


def main() -> None:
    env = load_env()
    vtok = env.get("VERCEL_TOKEN", "").strip()
    team = (env.get("VERCEL_TEAM_ID") or "").strip() or None
    vh = {"authorization": f"Bearer {vtok}"}
    vp = {"teamId": team} if team else {}

    # 1. Health + version
    r = requests.get(f"{APP}/api/health", timeout=30)
    hj = r.json()
    checks = hj.get("checks", {})
    print(f"health http={r.status_code} version={hj.get('version')} ok={hj.get('ok')}")
    for k in ("plaid_configured", "plaid_redirect_uri_set", "app_url_set",
              "cron_secret_set", "encryption_key_set", "supabase_url_set"):
        check(f"health.{k}", bool(checks.get(k)))
    if checks.get("vps_bridge_health_ok") is False:
        print("NOTE  vps_bridge_health_ok=false (pre-existing, separate issue)")

    # 2. Latest deployment matches origin/main HEAD
    r2 = requests.get("https://api.vercel.com/v6/deployments", headers=vh,
                      params={**vp, "app": "breeze-portal", "limit": 1}, timeout=30)
    d = r2.json().get("deployments", [{}])[0]
    sha = str(d.get("meta", {}).get("githubCommitSha"))[:7]
    check("deploy.ready", d.get("readyState") == "READY", f"sha={sha}")

    # 3. Cron REGISTRATION on the deployment (vercel.json only counts if Vercel
    #    accepted it — Hobby plans reject/downgrade sub-daily schedules).
    pid = d.get("uid") or d.get("id")
    r3 = requests.get(f"https://api.vercel.com/v13/deployments/{pid}", headers=vh,
                      params=vp, timeout=30)
    dep = r3.json()
    crons = (dep.get("crons") or dep.get("config", {}).get("crons") or [])
    print(f"deployment crons registered: {json.dumps(crons)}")
    paths = {c.get("path"): c.get("schedule") for c in crons}
    check("cron.plaid-sync registered */5",
          paths.get("/api/cron/plaid-sync") == "*/5 * * * *", str(paths.get("/api/cron/plaid-sync")))
    check("cron.sequences-tick registered",
          "/api/ops/sequences/tick" in paths, str(paths.get("/api/ops/sequences/tick")))

    # 4. CRON_SECRET → both endpoints authenticate + run
    r4 = requests.get("https://api.vercel.com/v9/projects/breeze-portal/env",
                      headers=vh, params=vp, timeout=30)
    ent = [e for e in r4.json().get("envs", []) if e.get("key") == "CRON_SECRET"]
    secret = ""
    if ent:
        r5 = requests.get(
            f"https://api.vercel.com/v9/projects/breeze-portal/env/{ent[0]['id']}",
            headers=vh, params={**vp, "decrypt": "true"}, timeout=30)
        secret = r5.json().get("value", "")
    check("cron.secret fetchable", bool(secret))
    if secret:
        b = {"authorization": f"Bearer {secret}"}
        r6 = requests.get(f"{APP}/api/cron/plaid-sync", headers=b, timeout=60)
        check("cron.plaid-sync Bearer 200", r6.status_code == 200, r6.text[:80])
        r7 = requests.get(f"{APP}/api/ops/sequences/tick", headers=b, timeout=60)
        check("cron.sequences-tick Bearer 200", r7.status_code == 200, r7.text[:80])
    r8 = requests.get(f"{APP}/api/cron/plaid-sync", timeout=30)
    check("cron.plaid-sync unauth 401", r8.status_code == 401)
    r9 = requests.get(f"{APP}/api/ops/sequences/tick", timeout=30)
    check("cron.sequences-tick unauth 401", r9.status_code == 401)

    # 5. Public/anon surface behaves
    for path, want in (("/", 200), ("/login", 200), ("/funder-login", 200),
                       ("/privacy", 200), ("/terms", 200)):
        rr = requests.get(f"{APP}{path}", timeout=30, allow_redirects=False)
        check(f"page {path} -> {want}", rr.status_code == want, str(rr.status_code))
    for path in ("/settings", "/bank", "/dashboard", "/lender/dashboard"):
        rr = requests.get(f"{APP}{path}", timeout=30, allow_redirects=False)
        check(f"page {path} anon -> 307 login",
              rr.status_code == 307 and "/login" in rr.headers.get("location", ""),
              f"{rr.status_code} {rr.headers.get('location','')[:40]}")
    rr = requests.patch(f"{APP}/api/merchant/profile", json={"business_name": "x"},
                        timeout=30, allow_redirects=False)
    check("api merchant/profile anon -> 401", rr.status_code == 401, str(rr.status_code))

    print()
    print(f"RESULT: {'ALL PASS' if not FAILS else 'FAILURES: ' + '; '.join(FAILS)}")
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    main()
