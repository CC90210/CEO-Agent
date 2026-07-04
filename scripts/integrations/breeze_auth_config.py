#!/usr/bin/env python3
"""Read/patch the Breeze Supabase project's AUTH config via the Management API.

Sealed-credential wrapper: loads SUPABASE_ACCESS_TOKEN + Breeze_SUPABASE_URL
internally (never printed). Only whitelisted, non-secret auth settings are
readable/patchable so this can't become a secret-exfil vector.

Usage:
  python scripts/integrations/breeze_auth_config.py get
  python scripts/integrations/breeze_auth_config.py set-otp-exp 86400
"""
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.secret_loader import load_env  # noqa: E402

SAFE_KEYS = ("mailer_otp_exp", "mailer_autoconfirm", "sms_otp_exp")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"


def main() -> int:
    env = load_env(required=["SUPABASE_ACCESS_TOKEN", "Breeze_SUPABASE_URL"])
    m = re.search(r"https://([a-z0-9]+)\.supabase\.co", env["Breeze_SUPABASE_URL"])
    if not m:
        print("ERROR: cannot derive project ref", file=sys.stderr)
        return 1
    api = f"https://api.supabase.com/v1/projects/{m.group(1)}/config/auth"
    headers = {
        "Authorization": f"Bearer {env['SUPABASE_ACCESS_TOKEN']}",
        "Content-Type": "application/json",
        "User-Agent": UA,
        "Accept": "application/json",
    }

    cmd = sys.argv[1] if len(sys.argv) > 1 else "get"
    if cmd == "get":
        req = urllib.request.Request(api, headers=headers)
    elif cmd == "set-otp-exp":
        seconds = int(sys.argv[2])
        if not (300 <= seconds <= 86400):
            print("ERROR: expiry must be 300-86400 seconds", file=sys.stderr)
            return 1
        body = json.dumps({"mailer_otp_exp": seconds}).encode()
        req = urllib.request.Request(api, data=body, method="PATCH", headers=headers)
    else:
        print(__doc__)
        return 1

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    print(json.dumps({k: data.get(k) for k in SAFE_KEYS}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
