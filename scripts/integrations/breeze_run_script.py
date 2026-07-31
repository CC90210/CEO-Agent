#!/usr/bin/env python3
"""Run a breeze-portal tsx script with Breeze Supabase creds injected from the
agents env file (keys stay in the subprocess env, never printed).

Usage: python scripts/integrations/breeze_run_script.py <script-relative-to-breeze-portal> [args...]
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import supabase_tool as t  # noqa: E402
from lib.subprocess_helpers import safe_run  # noqa: E402

BREEZE_PORTAL = r"C:\Users\User\APPS\breeze-portal"


def main():
    if len(sys.argv) < 2:
        print("usage: breeze_run_script.py <script.ts> [args...]", file=sys.stderr)
        sys.exit(1)
    env = t.load_env()
    url = env.get("Breeze_SUPABASE_URL")
    anon = env.get("Breeze_SUPABASE_ANON_KEY")
    svc = env.get("Breeze_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not svc:
        print("ERROR: Breeze creds missing", file=sys.stderr)
        sys.exit(1)
    child = os.environ.copy()
    child["BREEZE_SUPABASE_URL"] = url
    child["BREEZE_SUPABASE_ANON_KEY"] = anon or ""
    child["BREEZE_SUPABASE_SERVICE_ROLE_KEY"] = svc
    child["NEXT_PUBLIC_SUPABASE_URL"] = url
    child["NEXT_PUBLIC_SUPABASE_ANON_KEY"] = anon or ""
    r = safe_run(
        ["npx", "tsx", *sys.argv[1:]], cwd=BREEZE_PORTAL, env=child, shell=True
    )
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
