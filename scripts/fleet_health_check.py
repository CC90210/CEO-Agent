"""Fleet health — is every app serving, on every hostname it actually answers on?

WHY THIS EXISTS. The SunBiz forms were reported broken and blamed on the Turso
migration. They were not broken: every form renders and both API routes validate
correctly when reached directly, but oasisai.work serves a Cloudflare Registrar
parking page because the domain registration lapsed. No amount of database work
would have fixed that.

So this separates two questions that get conflated:

  DOMAIN   does the customer-facing hostname reach the app at all?
  APP      does the app work when reached directly?

DOMAIN failing while APP succeeds is a registrar/DNS problem, reported as such.

Hostnames are resolved from the Vercel API at run time, never hardcoded. The
first version pinned per-DEPLOYMENT URLs (agent-dashboard-9ciomdrkk-...) which
change on every deploy — it would have started reporting UNREACHABLE the next
time anything shipped, and someone would have chased a phantom outage. It also
missed two live customer domains (breezeadvance.credit, nostalgicrequests.com)
purely because they were not in the hardcoded list.

Migration-shaped errors ("no such table", TURSO_RPC_BLOCKED, "misconfigured")
are flagged distinctly from infrastructure ones, so a genuine regression is never
mistaken for a DNS problem or vice versa.

    python scripts/fleet_health_check.py
    python scripts/fleet_health_check.py --json
    python scripts/fleet_health_check.py --project agent-dashboard
"""
from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from lib.secret_loader import load_env  # noqa: E402

try:
    import truststore

    CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except Exception:  # pragma: no cover
    CTX = ssl.create_default_context()

VERCEL_API = "https://api.vercel.com"
DEFAULT_TEAM = "team_wUgw7DERPSKXoiR2iAlgXHTI"

# Errors that mean the MIGRATION broke something, not infrastructure.
MIGRATION_ERRORS = (
    "no such table", "no such column", "TURSO_RPC_BLOCKED", "SQLITE_",
    "misconfigured", "Turso not configured",
)
# Signs a hostname is not pointing at the app at all.
PARKED_MARKERS = ("Cloudflare Registrar", "domain has expired", "Buy this domain",
                  "Domain For Sale", "This domain is parked")

# Per-project probes. Paths must be PUBLIC (no session) so a redirect to /login
# is itself a healthy answer. API probes send intentionally invalid payloads:
# a 4xx proves the route reached its validator, which is the healthy result.
PROBES = {
    "agent-dashboard": {
        "paths": ["/f/submissions/full-application",
                  "/f/submissions/funding-pre-application",
                  "/f/submissions/bank-statement-upload",
                  "/login"],
        "api": [("/api/forms/submit", {"nonsense": True}),
                ("/api/forms/upload-url", {"nonsense": True})],
    },
    "breeze-portal": {"paths": ["/login"], "api": []},
    "nostalgic-requests": {"paths": ["/"], "api": []},
    "real-estate-app": {"paths": ["/"], "api": []},
    "oasis-ai-platform": {"paths": ["/"], "api": []},
}


def vercel_domains(project: str, token: str, team: str) -> list[dict]:
    url = f"{VERCEL_API}/v9/projects/{project}/domains?teamId={team}&limit=50"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=45, context=CTX) as r:
        return json.load(r).get("domains", [])


def fetch(url: str, body=None, timeout=40):
    req = urllib.request.Request(url, method="POST" if body is not None else "GET")
    req.add_header("User-Agent", "fleet-health/1.0")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(
                req, data=json.dumps(body).encode() if body is not None else None,
                timeout=timeout, context=CTX) as r:
            return r.status, r.read(8000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(8000).decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"CONNECT-FAIL {exc}"


def classify(status: int, text: str, is_api: bool) -> tuple[str, list[str]]:
    mig = [w for w in MIGRATION_ERRORS if w in text]
    if mig:
        return "MIGRATION-ERROR", mig
    parked = [w for w in PARKED_MARKERS if w in text]
    if parked:
        return "PARKED", parked
    if status == 0:
        return "UNREACHABLE", []
    if status >= 500:
        return "SERVER-ERROR", []
    if is_api and not (400 <= status < 500):
        # A 200 to a deliberately invalid payload means something intercepted
        # the request before the route's validator — a parking page does this.
        return f"SUSPECT-{status}", []
    return "ok", []


def check_host(host: str, probes: dict) -> dict:
    base = f"https://{host}"
    try:
        ips = sorted({a[4][0] for a in socket.getaddrinfo(host, 443)})
    except Exception as exc:
        ips = [f"RESOLVE-FAIL {str(exc)[:40]}"]
    checks = []
    for p in probes["paths"]:
        st, txt = fetch(base + p)
        v, hits = classify(st, txt, False)
        checks.append({"path": p, "status": st, "verdict": v, "markers": hits})
    for p, payload in probes["api"]:
        st, txt = fetch(base + p, body=payload)
        v, hits = classify(st, txt, True)
        checks.append({"path": p, "status": st, "verdict": v, "markers": hits})
    return {"host": host, "ips": ips, "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", help="one project instead of all")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    env = load_env()
    token = env.get("VERCEL_TOKEN") or env.get("VERCEL_API_TOKEN")
    team = env.get("VERCEL_TEAM_ID") or DEFAULT_TEAM
    if not token:
        print("ERROR: VERCEL_TOKEN absent from the agents env", file=sys.stderr)
        return 2

    projects = [args.project] if args.project else sorted(PROBES)
    report = []

    for project in projects:
        probes = PROBES.get(project, {"paths": ["/"], "api": []})
        try:
            domains = vercel_domains(project, token, team)
        except Exception as exc:
            report.append({"app": project, "verdict": f"VERCEL API FAILED: {str(exc)[:70]}"})
            continue

        # Skip redirect-only aliases: they answer 30x by design and would look
        # broken. Check the target instead, which is already in the list.
        names = [d["name"] for d in domains if not d.get("redirect")]
        custom = [n for n in names if not n.endswith(".vercel.app")]
        vercel = [n for n in names if n.endswith(".vercel.app")]

        entry = {"app": project, "custom": [], "vercel": []}
        for host in custom:
            entry["custom"].append(check_host(host, probes))
        for host in vercel[:1]:  # the stable project alias is enough
            entry["vercel"].append(check_host(host, probes))

        def bad(blocks):
            return [c for b in blocks for c in b["checks"] if c["verdict"] != "ok"]

        cust_bad, verc_bad = bad(entry["custom"]), bad(entry["vercel"])
        mig = [c for c in cust_bad + verc_bad if c["verdict"] == "MIGRATION-ERROR"]

        if mig:
            entry["verdict"] = "MIGRATION REGRESSION"
        elif cust_bad and entry["vercel"] and not verc_bad:
            entry["verdict"] = "DOMAIN BROKEN — app is healthy"
        elif verc_bad:
            entry["verdict"] = "APP BROKEN"
        elif cust_bad:
            entry["verdict"] = "DOMAIN BROKEN"
        else:
            entry["verdict"] = "ok"
        report.append(entry)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if all(r.get("verdict") == "ok" for r in report) else 1

    for r in report:
        print(f"\n=== {r['app']}   ->  {r['verdict']}")
        for kind in ("custom", "vercel"):
            for blk in r.get(kind, []):
                print(f"  {kind:6} {blk['host']}   {blk['ips']}")
                for c in blk["checks"]:
                    mark = f"  {c['markers']}" if c["markers"] else ""
                    print(f"     {c['status']:4} {c['verdict']:17} {c['path']}{mark}")

    bad = [r for r in report if r.get("verdict") != "ok"]
    print(f"\n{len(report) - len(bad)}/{len(report)} apps fully healthy")
    for r in bad:
        print(f"  {r['app']}: {r['verdict']}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
