#!/usr/bin/env python3
"""Mint a fresh /auth/confirm link for a Breeze merchant login (E2E testing).

Same generateLink call the production invite uses; the one-time token is
written to the output file, never printed. Usage:
  python scripts/integrations/breeze_mint_confirm_link.py <email> <outfile>
"""
import json
import sys
import os
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import supabase_tool as t  # noqa: E402

BASE = "https://breeze-portal-mu.vercel.app"


def main() -> int:
    email, outfile = sys.argv[1], sys.argv[2]
    env = t.load_env()
    url = env["Breeze_SUPABASE_URL"].rstrip("/")
    svc = env["Breeze_SUPABASE_SERVICE_ROLE_KEY"]

    body = json.dumps({"type": "magiclink", "email": email}).encode()
    req = urllib.request.Request(
        f"{url}/auth/v1/admin/generate_link",
        data=body,
        method="POST",
        headers={
            "apikey": svc,
            "Authorization": f"Bearer {svc}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    token = data.get("hashed_token") or (data.get("properties") or {}).get("hashed_token")
    if not token:
        print("ERROR: no hashed_token in response", file=sys.stderr)
        return 1
    link = f"{BASE}/auth/confirm?token_hash={token}&type=magiclink&next=%2Fset-password"
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(link)
    print(f"link written to {outfile} (token not printed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
