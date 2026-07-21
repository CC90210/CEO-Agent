#!/usr/bin/env python3
"""breeze_dns_setup.py — add the missing SPF + DMARC TXT records to the
breezeadvance.credit Vercel DNS zone so mail from support@breezeadvance.credit
authenticates (fixes the go-live 'lands in junk' problem).

The domain is on Vercel DNS (ns1/ns2.vercel-dns.com). DKIM + Google MX are
already present; only SPF and DMARC are missing. Both records added here are
standard Google-Workspace records — SPF mirrors what breezeadvance.com already
has; DMARC starts at p=none (monitoring only, non-enforcing, safe).

Idempotent: lists existing records first and skips any already present.
Reuses VERCEL_TOKEN / VERCEL_TEAM_ID via the sanctioned secret loader.

Usage:
  python scripts/integrations/breeze_dns_setup.py            # dry-run (show plan)
  python scripts/integrations/breeze_dns_setup.py --apply    # create records
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows CA-bundle fix: certifi can't verify api.vercel.com on this box; use the
# OS cert store (same fix as notify.py / reference_windows_supabase_ca_bundle_fix).
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.secret_loader import load_env  # noqa: E402

DOMAIN = "breezeadvance.credit"
API = "https://api.vercel.com"
DESIRED = [
    {"name": "", "type": "TXT", "value": "v=spf1 include:_spf.google.com ~all", "label": "SPF"},
    {
        "name": "_dmarc",
        "type": "TXT",
        "value": "v=DMARC1; p=none; rua=mailto:support@breezeadvance.credit",
        "label": "DMARC",
    },
]


def _creds() -> tuple[str, str | None]:
    env = load_env()
    token = (env.get("VERCEL_TOKEN") or "").strip()
    if not token:
        print("ERROR: VERCEL_TOKEN missing in agents env", file=sys.stderr)
        sys.exit(1)
    team = (env.get("VERCEL_TEAM_ID") or "").strip() or None
    return token, team


def _req(method: str, path: str, token: str, team: str | None, body=None):
    params = {"teamId": team} if team else {}
    r = requests.request(
        method, f"{API}{path}",
        headers={"authorization": f"Bearer {token}", "content-type": "application/json"},
        json=body, params=params, timeout=30,
    )
    if r.status_code >= 400:
        try:
            detail = r.json()
        except ValueError:
            detail = r.text[:400]
        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
    return r.json() if r.text else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    token, team = _creds()

    existing = _req("GET", f"/v4/domains/{DOMAIN}/records", token, team).get("records", [])
    print(f"{DOMAIN}: {len(existing)} existing records")

    def already(rec) -> bool:
        want_val = rec["value"].split()[0].lower()  # match by record kind (v=spf1 / v=dmarc1)
        for e in existing:
            if e.get("type") == "TXT" and (e.get("name") or "") == rec["name"]:
                if str(e.get("value", "")).lower().startswith(want_val):
                    return True
        return False

    plan = []
    for rec in DESIRED:
        if already(rec):
            print(f"  SKIP {rec['label']} — already present at name='{rec['name'] or '@'}'")
        else:
            plan.append(rec)
            print(f"  ADD  {rec['label']} @ name='{rec['name'] or '@'}': {rec['value']}")

    if not plan:
        print("Nothing to do — SPF + DMARC already configured.")
        return 0
    if not args.apply:
        print("\nDRY RUN — re-run with --apply to create the above records.")
        return 0

    for rec in plan:
        res = _req(
            "POST", f"/v2/domains/{DOMAIN}/records", token, team,
            body={"name": rec["name"], "type": rec["type"], "value": rec["value"], "ttl": 3600},
        )
        print(f"  CREATED {rec['label']}: uid={res.get('uid', res)}")
    print("\nDone. Propagation is usually minutes on Vercel DNS; verify with:")
    print(f"  Resolve-DnsName -Type TXT {DOMAIN}")
    print(f"  Resolve-DnsName -Type TXT _dmarc.{DOMAIN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
