#!/usr/bin/env python3
"""deploy_command_center.py — one-shot production deploy for the OASIS AI
Agent Command Center.

Note: Supabase Management API calls from Python urllib MUST set a real
User-Agent header — Cloudflare (in front of api.supabase.com) returns
403 error code 1010 for the default 'Python-urllib/3.x' UA. Use
SUPABASE_API_HEADERS below for any direct Management API calls.

What it does (idempotent — safe to re-run):
  1. Loads VERCEL_TOKEN from .env.agents
  2. Ensures apps/command-center/ is linked to the cc90210/agent-dashboard
     Vercel project (writes .vercel/project.json if missing)
  3. Syncs production env vars from .env.agents -> Vercel
       BRAVO_SUPABASE_URL, BRAVO_SUPABASE_SERVICE_ROLE_KEY, OPERATOR_EMAIL
  4. Runs `vercel deploy --prod`
  5. Curls the aliased URL to verify it's reachable (expects 200 or 401-SSO)

Usage:
  python scripts/deploy_command_center.py             # full deploy
  python scripts/deploy_command_center.py --env-only  # sync env vars, skip deploy
  python scripts/deploy_command_center.py --link-only # link the folder, skip everything else

Exit codes:
  0  deploy succeeded + URL reachable
  1  Vercel CLI errored
  2  env / config missing
  3  deploy succeeded but URL is unreachable (something off in runtime)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "apps" / "command-center"

VERCEL_PROJECT_NAME = "agent-dashboard"
PROD_URL = "https://agent-dashboard-cc90210.vercel.app"

REQUIRED_ENV_KEYS = [
    "BRAVO_SUPABASE_URL",
    "BRAVO_SUPABASE_SERVICE_ROLE_KEY",
]
EXTRA_ENV_KEYS = {
    "OPERATOR_EMAIL": "conaugh@oasisai.work",
}

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def step(msg: str) -> None:
    print(f"\n{DIM}>>>{RESET} {msg}")


def ok(msg: str) -> None:
    print(f"  {GREEN}OK{RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}!!{RESET}  {msg}")


def load_env() -> dict:
    """Load .env.agents through python-dotenv. Returns a dict of values used."""
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(ROOT / ".env.agents")

    token = os.environ.get("VERCEL_TOKEN") or os.environ.get("VERCEL_API_TOKEN")
    if not token:
        fail("VERCEL_TOKEN not found in .env.agents — generate one at https://vercel.com/account/tokens")
        sys.exit(2)

    sb_url = (
        os.environ.get("BRAVO_SUPABASE_URL")
        or os.environ.get("SUPABASE_URL_BRAVO")
        or os.environ.get("SUPABASE_URL")
    )
    sb_key = (
        os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY_BRAVO")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )
    if not sb_url or not sb_key:
        fail("BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY missing — see .env.agents")
        sys.exit(2)

    return {
        "VERCEL_TOKEN": token,
        "BRAVO_SUPABASE_URL": sb_url,
        "BRAVO_SUPABASE_SERVICE_ROLE_KEY": sb_key,
        **EXTRA_ENV_KEYS,
    }


def vercel(args: list[str], token: str, *, input_text: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run npx vercel <args> with the token, in the app dir, on Windows-shell."""
    cmd = ["npx", "vercel"] + args + ["--token", token]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(APP_DIR),
        shell=(os.name == "nt"),
        input=input_text,
        timeout=timeout,
    )


def link_project(token: str) -> None:
    step(f"Linking {APP_DIR.name} to Vercel project '{VERCEL_PROJECT_NAME}'")
    project_json = APP_DIR / ".vercel" / "project.json"
    if project_json.exists():
        try:
            data = json.loads(project_json.read_text())
            if data.get("projectName") == VERCEL_PROJECT_NAME or "agent-dashboard" in (data.get("projectId", "") + data.get("projectName", "")):
                ok(f"already linked ({data.get('projectName') or data.get('projectId')})")
                return
        except Exception:
            pass

    r = vercel(["link", "--yes", "--project", VERCEL_PROJECT_NAME], token, timeout=120)
    if r.returncode != 0:
        fail(f"link failed: {(r.stderr or r.stdout)[-400:]}")
        sys.exit(1)
    ok("linked")


def env_var_present(name: str, token: str) -> bool:
    r = vercel(["env", "ls"], token)
    return name in (r.stdout + r.stderr)


def set_env_var(name: str, value: str, token: str) -> None:
    if env_var_present(name, token):
        # Remove the existing prod entry so the value is fresh (idempotent re-runs).
        vercel(["env", "rm", name, "production", "--yes"], token, timeout=60)
    r = vercel(["env", "add", name, "production"], token, input_text=value, timeout=60)
    if r.returncode != 0:
        fail(f"could not set {name}: {(r.stderr or r.stdout)[-200:]}")
        sys.exit(1)
    ok(f"set {name} (prod)")


def sync_env(env: dict, token: str) -> None:
    step("Syncing production env vars")
    for key in REQUIRED_ENV_KEYS:
        set_env_var(key, env[key], token)
    for key in EXTRA_ENV_KEYS:
        set_env_var(key, env[key], token)


def deploy(token: str) -> str | None:
    step("Deploying production")
    r = vercel(["deploy", "--prod", "--yes"], token, timeout=600)
    if r.returncode != 0:
        fail(f"deploy failed:\n{(r.stderr or r.stdout)[-1500:]}")
        sys.exit(1)
    # Vercel CLI prints the production URL (it's also Aliased: …). Pull it from output.
    url = None
    for line in (r.stdout + r.stderr).splitlines():
        line = line.strip()
        if line.startswith("https://") and "vercel.app" in line and "agent-dashboard" in line:
            url = line.split()[0]
            break
        if "Aliased:" in line:
            tail = line.split("Aliased:")[1].strip()
            if tail.startswith("https://"):
                url = tail.split()[0]
    ok(f"deployed -> {url or PROD_URL}")
    return url or PROD_URL


def verify_url(url: str) -> bool:
    step(f"Verifying {url}")
    try:
        r = subprocess.run(
            ["curl", "-sIo", "/dev/null", "-w", "%{http_code}", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        code = (r.stdout or "").strip()
        if code in ("200", "401"):
            # 401 is the Vercel SSO gate — that's the correct secured-state response
            ok(f"reachable ({code}{' · SSO-gated' if code == '401' else ''})")
            return True
        fail(f"unexpected status {code}")
        return False
    except Exception as exc:  # noqa: BLE001
        fail(f"curl error: {exc}")
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Deploy OASIS AI Agent Command Center to Vercel")
    p.add_argument("--env-only", action="store_true", help="Sync env vars only, skip the deploy")
    p.add_argument("--link-only", action="store_true", help="Just link the folder, then exit")
    p.add_argument("--no-verify", action="store_true", help="Skip the post-deploy URL curl")
    args = p.parse_args()

    print(f"\n=== OASIS AI Agent Command Center · production deploy ===")

    env = load_env()
    token = env["VERCEL_TOKEN"]

    link_project(token)
    if args.link_only:
        print("\nDone — linked only.")
        return 0

    sync_env(env, token)
    if args.env_only:
        print("\nDone — env vars synced.")
        return 0

    url = deploy(token)
    if not args.no_verify and url:
        if not verify_url(url):
            print(f"\n{RED}Deploy succeeded but URL is unreachable.{RESET} Check Vercel logs.")
            return 3

    print(f"\n{GREEN}=== DEPLOY COMPLETE ==={RESET}")
    print(f"\nDashboard: {PROD_URL}")
    print("(401 on first hit is normal — Vercel SSO. Log in once.)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
