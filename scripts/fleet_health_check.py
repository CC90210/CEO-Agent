"""Fleet health — is every app actually serving, on every hostname it uses?

WHY THIS EXISTS. The SunBiz forms were reported broken and blamed on the Turso
migration. They were not broken: the forms render and validate correctly on the
Vercel URL, but oasisai.work serves a Cloudflare Registrar parking page because
the domain registration lapsed. Nothing about the data layer was involved.

A whole class of "the migration broke it" reports look like that. So this checks
the two things separately and reports them separately:

  1. DOMAIN   does the custom hostname reach the app at all?
  2. APP      does the app work when reached directly (Vercel URL)?

A failure in (1) with (2) healthy is a DNS/registrar problem and no amount of
database work will fix it.

Also flags migration-shaped errors specifically — "no such table", "no such
column", TURSO_RPC_BLOCKED, "misconfigured" — so a real migration regression is
never confused with an infrastructure one.

    python scripts/fleet_health_check.py
    python scripts/fleet_health_check.py --json
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

try:
    import truststore

    CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except Exception:  # pragma: no cover
    CTX = ssl.create_default_context()

# Errors that mean the MIGRATION broke something, as opposed to infrastructure.
MIGRATION_ERRORS = (
    "no such table", "no such column", "TURSO_RPC_BLOCKED", "SQLITE_",
    "misconfigured", "Turso not configured", "unauthorized_no_tenant",
)
# Signs the hostname is not pointing at the app at all.
PARKED_MARKERS = ("Cloudflare Registrar", "domain has expired", "Buy this domain",
                  "This site can’t be reached", "Domain For Sale")

APPS = [
    {
        "name": "oasis-command-center",
        "domain": "https://oasisai.work",
        "direct": "https://agent-dashboard-9ciomdrkk-cc90210.vercel.app",
        "paths": ["/f/submissions/full-application",
                  "/f/submissions/funding-pre-application",
                  "/f/submissions/bank-statement-upload",
                  "/login"],
        "api": [("/api/forms/submit", {"nonsense": True}),
                ("/api/forms/upload-url", {"nonsense": True})],
    },
    {
        "name": "breeze-portal",
        "domain": None,
        "direct": "https://breeze-portal-b5dnf5680-cc90210.vercel.app",
        "paths": ["/login"],
        "api": [],
    },
    {
        "name": "nostalgic-requests",
        "domain": None,
        "direct": "https://nostalgic-requests-8qv0grgov-cc90210.vercel.app",
        "paths": ["/"],
        "api": [],
    },
    {
        "name": "propflow",
        "domain": "https://propflow.pro",
        "direct": None,
        "paths": ["/"],
        "api": [],
    },
]


def fetch(url: str, body=None, timeout=40):
    req = urllib.request.Request(url, method="POST" if body is not None else "GET")
    req.add_header("User-Agent", "fleet-health/1.0")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(
                req, data=json.dumps(body).encode() if body is not None else None,
                timeout=timeout, context=CTX) as r:
            return r.status, r.read(8000).decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(8000).decode("utf-8", "replace"), dict(e.headers)
    except Exception as exc:
        return 0, f"CONNECT-FAIL {exc}", {}


def classify(status: int, text: str) -> tuple[str, list[str]]:
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
    return "ok", []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report = []
    for app in APPS:
        entry = {"app": app["name"], "domain": {}, "direct": {}, "verdict": "ok"}

        for kind in ("domain", "direct"):
            base = app.get(kind)
            if not base:
                continue
            host = base.split("//", 1)[1].split("/", 1)[0]
            try:
                ips = sorted({a[4][0] for a in socket.getaddrinfo(host, 443)})
            except Exception as exc:
                ips = [f"RESOLVE-FAIL {str(exc)[:40]}"]
            checks = []
            for p in app["paths"]:
                st, txt, _ = fetch(base + p)
                verdict, hits = classify(st, txt)
                checks.append({"path": p, "status": st, "verdict": verdict,
                               "markers": hits, "bytes": len(txt)})
            for p, payload in app["api"]:
                st, txt, _ = fetch(base + p, body=payload)
                verdict, hits = classify(st, txt)
                # A 4xx from an intentionally invalid payload is HEALTHY — it
                # proves the route reached its validator.
                if verdict == "ok" and not (400 <= st < 500):
                    verdict = f"unexpected-{st}"
                checks.append({"path": p, "status": st, "verdict": verdict,
                               "markers": hits, "bytes": len(txt)})
            entry[kind] = {"base": base, "ips": ips, "checks": checks}

        dom = entry["domain"].get("checks", [])
        dir_ = entry["direct"].get("checks", [])
        dom_bad = [c for c in dom if c["verdict"] != "ok"]
        dir_bad = [c for c in dir_ if c["verdict"] != "ok"]
        mig_bad = [c for c in dom + dir_ if c["verdict"] == "MIGRATION-ERROR"]

        if mig_bad:
            entry["verdict"] = "MIGRATION REGRESSION"
        elif dom_bad and not dir_bad and dir_:
            entry["verdict"] = "DOMAIN BROKEN — app is healthy"
        elif dir_bad:
            entry["verdict"] = "APP BROKEN"
        elif dom_bad:
            entry["verdict"] = "DOMAIN BROKEN"
        report.append(entry)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if all(r["verdict"] == "ok" for r in report) else 1

    for r in report:
        print(f"\n=== {r['app']}   ->  {r['verdict']}")
        for kind in ("domain", "direct"):
            blk = r.get(kind) or {}
            if not blk:
                continue
            print(f"  {kind:7} {blk['base']}   {blk['ips']}")
            for c in blk["checks"]:
                mark = f"  {c['markers']}" if c["markers"] else ""
                print(f"     {c['status']:4} {c['verdict']:18} {c['path']}{mark}")

    bad = [r for r in report if r["verdict"] != "ok"]
    print(f"\n{len(report) - len(bad)}/{len(report)} apps fully healthy")
    for r in bad:
        print(f"  {r['app']}: {r['verdict']}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
