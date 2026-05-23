#!/usr/bin/env python3
"""One-shot: run a SQL file against oasis via the Supabase Management API.

The supabase_admin module walks looking for 'Business-Empire-Agent' which no
longer matches (repo renamed to CEO-Agent), so we inline the management API
call here. Read-only — used to run the migration verifier diagnostic.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib.secret_loader import load_env  # noqa: E402

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("sql_file")
    p.add_argument("--project", default="oasis")
    args = p.parse_args()

    env = load_env()
    token = env.get("SUPABASE_ACCESS_TOKEN")
    url_key = f"{args.project.upper()}_SUPABASE_URL"
    url = env.get(url_key)
    if not token:
        print("ERROR: SUPABASE_ACCESS_TOKEN missing", file=sys.stderr)
        sys.exit(1)
    if not url:
        print(f"ERROR: {url_key} missing", file=sys.stderr)
        sys.exit(1)

    ref = url.split("https://")[1].split(".")[0]
    sql = Path(args.sql_file).read_text(encoding="utf-8")

    body = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            data = json.loads(raw) if raw else []
            print(json.dumps(data, indent=2))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body[:2000]}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
