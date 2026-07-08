#!/usr/bin/env python3
"""cloudflare_admin.py — Cloudflare DNS helper for OASIS domains.

Why this exists: 2026-04-30 incident — moved oasisai.work between Vercel
projects, the verification TXT token rotated, marketing site went 404
until we updated CF DNS. This module wraps the recovery so any future
domain juggle is a one-liner.

Token: CLOUDFLARE_TOKEN in .env.agents (scoped to Edit zone DNS for the
target zone).

Usage:
    # As a library
    from cloudflare_admin import sync_vercel_verify_txt
    sync_vercel_verify_txt('oasisai.work', 'oasis-ai-platform')

    # As a CLI
    python scripts/integrations/cloudflare_admin.py sync-vercel-txt --domain oasisai.work --vercel-project oasis-ai-platform
    python scripts/integrations/cloudflare_admin.py list-zone --domain oasisai.work
    python scripts/integrations/cloudflare_admin.py upsert-txt --domain oasisai.work --name _vercel --value "vc-domain-verify=..."
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# V6.8.3: migrated from python-dotenv to lib.secret_loader.
# scripts/integrations/<file>.py → parents[2] is the repo root.
_REPO = Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_REPO / 'scripts'))
from lib.secret_loader import load_env as _load_env  # noqa: E402

_env = _load_env()
import os as _os
for _k, _v in _env.items():
    _os.environ.setdefault(_k, str(_v))

CF_BASE = "https://api.cloudflare.com/client/v4"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _cf_headers() -> dict:
    token = os.environ.get("CLOUDFLARE_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        raise RuntimeError("CLOUDFLARE_TOKEN missing in .env.agents")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": UA,
    }


def _cf(method: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
    url = f"{CF_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_cf_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"CF {method} {path} -> {e.code}: {e.read().decode()[:300]}") from e
    if not out.get("success"):
        raise RuntimeError(f"CF API error: {json.dumps(out)[:300]}")
    return out


def get_zone_id(apex: str) -> str:
    out = _cf("GET", f"/zones?name={apex}")
    results = out.get("result") or []
    if not results:
        raise RuntimeError(f"No CF zone found for {apex}")
    return results[0]["id"]


def list_records(apex: str, *, type_: str | None = None, name: str | None = None) -> list[dict]:
    zone_id = get_zone_id(apex)
    qs = []
    if type_:
        qs.append(f"type={type_}")
    if name:
        qs.append(f"name={name}")
    q = ("?" + "&".join(qs)) if qs else ""
    out = _cf("GET", f"/zones/{zone_id}/dns_records{q}")
    return out.get("result") or []


def upsert_txt(apex: str, name: str, value: str, ttl: int = 60) -> dict:
    """Create or update a TXT record. Returns the record."""
    zone_id = get_zone_id(apex)
    full_name = name if name.endswith(apex) else f"{name}.{apex}"

    existing = list_records(apex, type_="TXT", name=full_name)
    body = {"type": "TXT", "name": name, "content": value, "ttl": ttl}
    if existing:
        rec_id = existing[0]["id"]
        out = _cf("PUT", f"/zones/{zone_id}/dns_records/{rec_id}", body)
    else:
        out = _cf("POST", f"/zones/{zone_id}/dns_records", body)
    return out["result"]


# ============================================================================
# Cloudflare Tunnel routing — expose a local VPS service on a public hostname
# (used to wire agent chat-bridges, e.g. breeze-bridge.oasisai.work -> :3100)
# ============================================================================
def list_tunnels(account_id: str) -> list[dict]:
    """List the account's cloudflared tunnels (id, name, status)."""
    out = _cf("GET", f"/accounts/{account_id}/cfd_tunnel?is_deleted=false")
    return out.get("result") or []


def get_tunnel_ingress(account_id: str, tunnel_id: str) -> list[dict]:
    out = _cf("GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations")
    return (((out.get("result") or {}).get("config")) or {}).get("ingress", [])


def add_tunnel_route(account_id: str, tunnel_id: str, hostname: str, service: str) -> list[dict]:
    """Add `hostname -> service` to a tunnel's ingress, PRESERVING every existing
    rule and keeping the catch-all last. Idempotent. Returns the new ingress.

    NOTE: a tunnel route also needs a *proxied* CNAME
    `hostname -> <tunnel_id>.cfargotunnel.com`. This token may be tunnel-scoped
    without zone access — create that DNS record with a zone-scoped token or in
    the dashboard.
    """
    out = _cf("GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations")
    config = (out.get("result") or {}).get("config") or {}
    ingress = list(config.get("ingress") or [])
    if any(r.get("hostname") == hostname for r in ingress):
        return ingress  # already routed
    rule = {"hostname": hostname, "service": service}
    if ingress and not ingress[-1].get("hostname"):
        ingress = ingress[:-1] + [rule, ingress[-1]]  # keep catch-all last
    else:
        ingress = ingress + [rule, {"service": "http_status:404"}]
    config["ingress"] = ingress
    _cf("PUT", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations", {"config": config})
    return ingress


# ============================================================================
# Vercel verification rescue — the 2026-04-30 incident workflow
# ============================================================================
def sync_vercel_verify_txt(apex: str, vercel_project: str, *, wait_seconds: int = 8) -> bool:
    """Read the verification TXT value Vercel currently expects for a domain
    and put it on CF DNS, then trigger Vercel re-verify. Returns True on
    success.
    """
    vc_token = os.environ.get("VERCEL_TOKEN")
    if not vc_token:
        raise RuntimeError("VERCEL_TOKEN missing")

    # 1. What does Vercel want?
    vreq = urllib.request.Request(
        f"https://api.vercel.com/v9/projects/{vercel_project}/domains/{apex}",
        headers={"Authorization": f"Bearer {vc_token}", "User-Agent": UA},
    )
    vout = json.loads(urllib.request.urlopen(vreq, timeout=30).read())
    if vout.get("verified"):
        print(f"[sync] {apex} already verified on {vercel_project}")
        return True

    needed = vout.get("verification") or []
    txt_entries = [v for v in needed if v.get("type") == "TXT"]
    if not txt_entries:
        raise RuntimeError(f"No TXT verification needed but verified=False — manual check required: {needed}")
    txt_entry = txt_entries[0]
    expected_value = txt_entry["value"]
    expected_name = txt_entry["domain"]
    short_name = expected_name.replace(f".{apex}", "")  # _vercel.oasisai.work -> _vercel

    print(f"[sync] Vercel expects {expected_name} TXT = {expected_value}")

    # 2. Upsert on Cloudflare
    rec = upsert_txt(apex, short_name, expected_value)
    print(f"[sync] CF TXT set: {rec['name']} -> {rec['content'][:80]}")

    # 3. Wait for propagation
    if wait_seconds > 0:
        print(f"[sync] sleeping {wait_seconds}s for DNS propagation...")
        time.sleep(wait_seconds)

    # 4. Trigger Vercel verify
    for attempt in range(8):
        vreq2 = urllib.request.Request(
            f"https://api.vercel.com/v9/projects/{vercel_project}/domains/{apex}/verify",
            method="POST",
            data=b"",
            headers={
                "Authorization": f"Bearer {vc_token}",
                "User-Agent": UA,
                "Content-Type": "application/json",
            },
        )
        try:
            vr = urllib.request.urlopen(vreq2, timeout=30)
            out = json.loads(vr.read())
            if out.get("verified"):
                print(f"[sync] verified on attempt {attempt + 1}")
                return True
            print(f"[sync] attempt {attempt + 1}: verified=False, retrying...")
        except urllib.error.HTTPError as e:
            print(f"[sync] attempt {attempt + 1} {e.code}: {e.read().decode()[:120]}")
        time.sleep(5)
    return False


def main() -> int:
    p = argparse.ArgumentParser(description="Cloudflare DNS admin helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list-zone")
    p_list.add_argument("--domain", required=True)
    p_list.add_argument("--type", default=None)

    p_upsert = sub.add_parser("upsert-txt")
    p_upsert.add_argument("--domain", required=True)
    p_upsert.add_argument("--name", required=True)
    p_upsert.add_argument("--value", required=True)
    p_upsert.add_argument("--ttl", type=int, default=60)

    p_sync = sub.add_parser("sync-vercel-txt")
    p_sync.add_argument("--domain", required=True)
    p_sync.add_argument("--vercel-project", required=True)

    p_lt = sub.add_parser("list-tunnels")
    p_lt.add_argument("--account", required=True)

    p_rt = sub.add_parser("add-tunnel-route")
    p_rt.add_argument("--account", required=True)
    p_rt.add_argument("--tunnel", required=True)
    p_rt.add_argument("--hostname", required=True)
    p_rt.add_argument("--service", required=True)

    args = p.parse_args()

    if args.cmd == "list-zone":
        for r in list_records(args.domain, type_=args.type):
            print(f"{r['type']:<6} {r['name']:<40} {r.get('content', '')[:80]}")
    elif args.cmd == "upsert-txt":
        rec = upsert_txt(args.domain, args.name, args.value, args.ttl)
        print(f"OK: {rec['name']} = {rec['content'][:80]}")
    elif args.cmd == "sync-vercel-txt":
        ok = sync_vercel_verify_txt(args.domain, args.vercel_project)
        return 0 if ok else 1
    elif args.cmd == "list-tunnels":
        for t in list_tunnels(args.account):
            print(f"{t['id']}  {t.get('name', ''):<20} {t.get('status', '')}")
    elif args.cmd == "add-tunnel-route":
        ingress = add_tunnel_route(args.account, args.tunnel, args.hostname, args.service)
        print("ingress now:")
        for r in ingress:
            print("  ", r.get("hostname", "(catch-all)"), "->", r.get("service"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
