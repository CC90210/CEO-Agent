#!/usr/bin/env python3
"""Run the Breeze demo-user seeder with credentials injected from .env.agents.

The breeze-portal seeder (scripts/seed-demo-users.ts) expects BREEZE_SUPABASE_*
(uppercase) in its env; .env.agents stores them as Breeze_* (mixed case). This
bridge loads them via the sanctioned loader and injects them into the child
process — the service-role key stays in the subprocess env, never printed. Only
the demo emails/passwords the seeder prints reach stdout.

Usage: python scripts/integrations/breeze_seed_users.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import supabase_tool as t  # noqa: E402
from lib.subprocess_helpers import safe_run  # noqa: E402

BREEZE_PORTAL = r"C:\Users\User\APPS\breeze-portal"


def main():
    env = t.load_env()
    url = env.get("Breeze_SUPABASE_URL")
    anon = env.get("Breeze_SUPABASE_ANON_KEY")
    svc = env.get("Breeze_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not svc:
        print("ERROR: Breeze_SUPABASE_URL / Breeze_SUPABASE_SERVICE_ROLE_KEY missing", file=sys.stderr)
        sys.exit(1)

    child = os.environ.copy()
    child["BREEZE_SUPABASE_URL"] = url
    child["BREEZE_SUPABASE_ANON_KEY"] = anon or ""
    child["BREEZE_SUPABASE_SERVICE_ROLE_KEY"] = svc
    child["NEXT_PUBLIC_SUPABASE_URL"] = url
    child["NEXT_PUBLIC_SUPABASE_ANON_KEY"] = anon or ""

    r = safe_run(
        ["npx", "tsx", "scripts/seed-demo-users.ts"],
        cwd=BREEZE_PORTAL, env=child, shell=True,
    )
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
