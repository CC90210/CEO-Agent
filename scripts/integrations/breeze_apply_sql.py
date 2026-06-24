#!/usr/bin/env python3
"""Apply SQL to the Breeze (CredPort) Supabase project via the Management API.

Uses SUPABASE_ACCESS_TOKEN (personal access token) + Breeze_SUPABASE_URL from
.env.agents to POST SQL to the project's /database/query endpoint. The token is
loaded internally and never printed.

Usage:
  python scripts/integrations/breeze_apply_sql.py <file.sql> [<file2.sql> ...]
  python scripts/integrations/breeze_apply_sql.py --query "SELECT ..."
"""
import sys
import os
import json
import re
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
import supabase_tool as t  # noqa: E402 — reuse its .env.agents loader


def main():
    env = t.load_env()
    token = env.get("SUPABASE_ACCESS_TOKEN")
    url = env.get("Breeze_SUPABASE_URL")
    if not token or not url:
        print("ERROR: SUPABASE_ACCESS_TOKEN or Breeze_SUPABASE_URL missing in .env.agents", file=sys.stderr)
        sys.exit(1)
    m = re.search(r"https://([a-z0-9]+)\.supabase\.co", url)
    if not m:
        print(f"ERROR: cannot derive project ref from URL", file=sys.stderr)
        sys.exit(1)
    ref = m.group(1)
    api = f"https://api.supabase.com/v1/projects/{ref}/database/query"

    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    if args[0] == "--query":
        items = [("(inline)", " ".join(args[1:]))]
    else:
        items = []
        for path in args:
            with open(path, "r", encoding="utf-8") as f:
                items.append((os.path.basename(path), f.read()))

    for name, sql in items:
        body = json.dumps({"query": sql}).encode("utf-8")
        req = urllib.request.Request(
            api, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                # api.supabase.com is behind Cloudflare which 1010-bans the
                # default Python-urllib UA. Present a normal client UA.
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read().decode("utf-8")
                preview = data if len(data) < 600 else data[:600] + "…"
                print(f"[OK] {name}: {preview}")
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8")
            print(f"[FAIL] {name}: HTTP {e.code} {err[:1000]}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"[FAIL] {name}: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
