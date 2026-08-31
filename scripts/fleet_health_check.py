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

DO NOT SCHEDULE THIS AS AN ALARM. It reports the truth, which today includes a
pre-existing failure (apply.sunbizfunding.com has never had a DNS record), so
its exit code is non-zero on a healthy fleet and a cron wired to it would page
on every run until that domain is fixed or detached. Deliberate: a health check
that hides a broken hostname because someone wrote it down is worse than a noisy
one. The alarm belongs one level up, where policy lives — schedule
`scripts/vercel_exit_report.py`, which holds the documented known-broken
baseline and exits 1 ONLY on a new regression.
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
    # Probing only "/" here was a hole that cost a real outage. On 2026-08-31 a
    # router change made every /api/* request throw (Cloudflare 1101), taking
    # down all five Stripe flow rewrites while the Vercel origin behind them was
    # healthy — and this check reported the fleet 10/11 OK throughout, because
    # the static landing page it probed was served by the assets binding and
    # never touched the failing code path.
    #
    # The three surfaces here are served by three DIFFERENT mechanisms in the
    # router (assets binding, service binding to the dashboard, proxy to
    # Vercel), so one of them being healthy says nothing about the other two.
    # All GETs, no mutation: the Stripe rewrites return session/portal state.
    "oasis-ai-platform": {
        "paths": ["/",                       # assets binding
                  "/app", "/app/login",      # service binding -> dashboard Worker
                  "/api/health",             # proxy -> Vercel functions
                  "/api/stripe/session",     # the five flow rewrites, which are
                  "/api/stripe/portal",      # the revenue path and were the ones
                  "/api/stripe/checkout"],   # that silently broke
        "api": [],
    },
    # Added 2026-08-30. These were absent while their hostnames were being cut
    # over to Workers, so bluerisebusinesscapital.com — a live customer domain
    # that had already moved — was not checked by the tool reporting the fleet
    # healthy. An app missing from this table is invisible, not passing.
    "blue-rise-website": {"paths": ["/"], "api": []},
    "sunbiz-funding": {"paths": ["/"], "api": []},
    "arthrisil-website": {"paths": ["/"], "api": []},
    "breezeadvance-website": {"paths": ["/"], "api": []},
    "tiktik": {"paths": ["/"], "api": []},
    "ig-setter-pro": {"paths": ["/"], "api": []},
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


def _cf_state() -> dict:
    """Ask Cloudflare what is ACTUALLY deployed and bound. Cached per run.

    Both halves must come from Cloudflare, not from the registry:

      * DEPLOYED WORKERS — workers.dev is a wildcard, so an undeployed worker's
        URL still resolves and answers 404. classify() reads 404 as "ok", so
        probing an app that was never deployed produced a false GREEN.
      * BOUND HOSTNAMES — the registry's custom_domains is regenerated from
        VERCEL, i.e. "domains this app has", which is not "domains bound to its
        Worker". Probing the difference reported apply.sunbizfunding.com (a
        Vercel-only host) as a broken Cloudflare worker.

    Returns {} when no token is configured, so the check still runs Vercel-only
    in a checkout without migration credentials.
    """
    reg = Path(__file__).resolve().parent.parent / "config" / "cloudflare" / "apps.json"
    if not reg.exists():
        return {}
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    env = load_env()
    tok = next((str(env.get(k)).strip() for k in
                ("CLOUDFLARE_WORKERS_API_TOKEN", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_TOKEN")
                if str(env.get(k) or "").strip()), "")
    # REGISTRY WINS. The env store's CLOUDFLARE_ACCOUNT_ID still names the old
    # account (it is correct there for R2), so letting it take precedence made
    # this list the wrong fleet — it reported the three most recently migrated
    # workers as absent. Same trap already fixed in wrangler_tool.py; the fix
    # belongs anywhere the deploy target is resolved.
    acct = str(data.get("account_id") or "").strip() or str(env.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    if not (tok and acct):
        return {}

    def cf(path):
        req = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/accounts/{acct}{path}",
            headers={"Authorization": f"Bearer {tok}", "User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.load(r).get("result") or []
        except Exception:
            return []

    deployed = {s.get("id") for s in cf("/workers/scripts")}
    bound: dict[str, list[str]] = {}
    for d in cf("/workers/domains"):
        bound.setdefault(d.get("service"), []).append(d.get("hostname"))
    return {"registry": data, "deployed": deployed, "bound": bound}


_CF_CACHE: dict | None = None


def cloudflare_hosts(vercel_project: str) -> list[str]:
    """Hostnames this project actually serves from Workers — deployed only."""
    global _CF_CACHE
    if _CF_CACHE is None:
        _CF_CACHE = _cf_state()
    if not _CF_CACHE:
        return []
    data = _CF_CACHE["registry"]
    subdomain = data.get("workers_subdomain", "oasisaisolutions")
    hosts: list[str] = []
    for slug, app in (data.get("apps") or {}).items():
        if app.get("dropped") or app.get("vercel_project") != vercel_project:
            continue
        worker = app.get("worker_name", slug)
        if worker not in _CF_CACHE["deployed"]:
            continue  # not migrated yet — silence is correct, not a failure
        if slug != "oasis-cc-cron":  # cron companion has no "/" surface
            hosts.append(f"{worker}.{subdomain}.workers.dev")
        hosts.extend(_CF_CACHE["bound"].get(worker) or [])
    return sorted(set(hosts))


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

        # Cloudflare Workers hosts, merged in from the migration registry.
        # WHY: during the migration a hostname can move to Workers while Vercel
        # still lists it, and the Vercel API is then no longer the authority on
        # where production actually is. Without this the check probed only the
        # OLD stack and reported the fleet healthy while saying nothing at all
        # about the seven hostnames that had already moved (found 2026-08-30).
        cf_hosts = cloudflare_hosts(project)
        entry = {"app": project, "custom": [], "vercel": [], "cloudflare": []}
        for host in custom:
            entry["custom"].append(check_host(host, probes))
        for host in vercel[:1]:  # the stable project alias is enough
            entry["vercel"].append(check_host(host, probes))
        for host in cf_hosts:
            entry["cloudflare"].append(check_host(host, probes))

        def bad(blocks):
            return [c for b in blocks for c in b["checks"] if c["verdict"] != "ok"]

        cust_bad, verc_bad = bad(entry["custom"]), bad(entry["vercel"])
        cf_bad = bad(entry["cloudflare"])
        mig = [c for c in cust_bad + verc_bad + cf_bad if c["verdict"] == "MIGRATION-ERROR"]

        if mig:
            entry["verdict"] = "MIGRATION REGRESSION"
        elif cf_bad:
            # Named separately from DOMAIN/APP BROKEN: during the migration the
            # Workers side can fail while Vercel still serves fine, and calling
            # that "ok" is how a half-migrated app looks healthy.
            entry["verdict"] = "CLOUDFLARE WORKER BROKEN"
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
        for kind in ("custom", "vercel", "cloudflare"):
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
