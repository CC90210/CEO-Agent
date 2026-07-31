#!/usr/bin/env python3
"""Run a breeze-portal tsx script with the Breeze Supabase creds AND the
production at-rest encryption key injected, so a headless script can decrypt the
tenant's Gmail app-password and send branded email AS the tenant
(support@breezeadvance.credit). BREEZE_ENCRYPTION_KEY lives only in Vercel, so we
fetch the PRODUCTION value from the Vercel env API into this subprocess's env —
it stays in the child process, is never printed to the agent (same contract as
the CLI secret wrappers).

Usage: python scripts/integrations/breeze_send_via_tenant.py <script.ts> [args...]
"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
try:
    import truststore  # Windows CA-bundle fix for api.vercel.com

    truststore.inject_into_ssl()
except Exception:
    pass
from lib.secret_loader import load_env as _load_env  # noqa: E402
from lib.subprocess_helpers import safe_run  # noqa: E402

BREEZE_PORTAL = r"C:\Users\User\APPS\breeze-portal"
APP_URL = "https://breezeadvance.credit"


def _find(env: dict, *names: str) -> str:
    low = {k.lower(): v for k, v in env.items()}
    for n in names:
        if env.get(n):
            return env[n]
        if low.get(n.lower()):
            return low[n.lower()]
    return ""


def _fetch_prod_encryption_key(token: str, team: str | None) -> str:
    params = {"teamId": team} if team else {}
    r = requests.get(
        "https://api.vercel.com/v9/projects/breeze-portal/env",
        headers={"authorization": f"Bearer {token}"},
        params={**params, "decrypt": "false"}, timeout=30,
    )
    r.raise_for_status()
    import base64
    all_envs = r.json().get("envs", [])
    entries = [e for e in all_envs if e.get("key") == "BREEZE_ENCRYPTION_KEY"]
    print(f"[breeze_send] vercel env vars: {len(all_envs)}, BREEZE_ENCRYPTION_KEY entries: {len(entries)}", file=sys.stderr)
    # Prefer production. Always fetch the DECRYPTED value by id (the list's own
    # `value` is the masked/encrypted blob, not the key). Accept only a value
    # that base64-decodes to exactly 32 bytes (a real AES-256 key).
    entries.sort(key=lambda e: 0 if "production" in (e.get("target") or []) else 1)
    for e in entries:
        r2 = requests.get(
            f"https://api.vercel.com/v9/projects/breeze-portal/env/{e['id']}",
            headers={"authorization": f"Bearer {token}"},
            params={**params, "decrypt": "true"}, timeout=30,
        )
        val = r2.json().get("value", "") if r2.status_code < 400 else ""
        try:
            n = len(base64.b64decode(val)) if val else 0
        except Exception:
            n = -1
        print(f"[breeze_send] target={e.get('target')} http={r2.status_code} key_bytes={n}", file=sys.stderr)
        if n == 32:
            return val
    return ""


def main():
    if len(sys.argv) < 2:
        print("usage: breeze_send_via_tenant.py <script.ts> [args...]", file=sys.stderr)
        sys.exit(1)
    env = _load_env()
    url = _find(env, "Breeze_SUPABASE_URL")
    anon = _find(env, "Breeze_SUPABASE_ANON_KEY")
    svc = _find(env, "Breeze_SUPABASE_SERVICE_ROLE_KEY")
    vtok = _find(env, "VERCEL_TOKEN")
    vteam = _find(env, "VERCEL_TEAM_ID") or None
    if not (url and svc and vtok):
        print("ERROR: missing Breeze creds or VERCEL_TOKEN", file=sys.stderr)
        sys.exit(1)
    try:
        enc = _fetch_prod_encryption_key(vtok, vteam)
    except Exception as e:
        print(f"ERROR: could not fetch encryption key from Vercel: {e}", file=sys.stderr)
        sys.exit(1)
    if not enc:
        print("ERROR: BREEZE_ENCRYPTION_KEY not found in Vercel", file=sys.stderr)
        sys.exit(1)

    child = os.environ.copy()
    # Node's bundled CA can't verify smtp.gmail.com on this box (same Windows
    # CA gap truststore fixes for Python). --use-system-ca uses the Windows
    # cert store (Node 24+), so the branded SMTP send verifies properly.
    child["NODE_OPTIONS"] = (child.get("NODE_OPTIONS", "") + " --use-system-ca").strip()
    child.update({
        "BREEZE_SUPABASE_URL": url,
        "BREEZE_SUPABASE_ANON_KEY": anon or "",
        "BREEZE_SUPABASE_SERVICE_ROLE_KEY": svc,
        "BREEZE_ENCRYPTION_KEY": enc,
        "BREEZE_APP_URL": APP_URL,
        "NEXT_PUBLIC_SUPABASE_URL": url,
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": anon or "",
    })
    r = safe_run(["npx", "tsx", *sys.argv[1:]], cwd=BREEZE_PORTAL, env=child, shell=True)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
