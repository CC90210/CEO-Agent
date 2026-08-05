"""Push Turso connection env vars to Vercel projects — values never displayed.

vercel_env_tool.py can set arbitrary vars but takes the value on the command
line, which would put a database credential into the agent's context and the
session transcript. This tool moves the values internally: secret_loader reads
them, the Vercel API receives them, stdout gets key NAMES and status codes only.
Same posture as turso_admin --write-env.

What it does NOT do: set EMPIRE_DATA_BACKEND=turso_cloud. That is the cutover
switch, and flipping it belongs to the operator after verifying the loaded data —
pushing connection material is additive and inert until that switch flips.

Usage:
  python scripts/integrations/vercel_turso_sync.py --project agent-dashboard --db bravo [--env production preview development] [--json]
  python scripts/integrations/vercel_turso_sync.py --plan   # show mapping, push nothing
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

import requests  # noqa: E402

from lib.db_turso import PROJECT_ENV_VARS  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402

VERCEL_API = "https://api.vercel.com"
TIMEOUT_S = 30

# Vercel project slug -> empire db key. agent-dashboard is the LIVE
# oasis-command-center project (oasis-ai-platform's Vercel project is the
# archived decoy — reference_oasis_command_center_deploy_facts).
DEFAULT_TARGETS = {
    "agent-dashboard": "bravo",
    "breeze-portal": "breeze",
    "nostalgic-requests": "nostalgic",
}
# Apps always read the UNPREFIXED pair; the per-db prefix only exists in the
# agents env where all five live side by side.
APP_VAR_NAMES = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")


def vercel_headers(env: dict) -> tuple[dict, str]:
    token = env.get("VERCEL_TOKEN")
    if not token:
        raise SystemExit("ERROR: VERCEL_TOKEN absent from agents env")
    team = env.get("VERCEL_TEAM_ID")
    return {"Authorization": f"Bearer {token}"}, (f"?teamId={team}" if team else "")


def upsert_env(project: str, key: str, value: str, targets: list[str],
               headers: dict, teamq: str) -> tuple[str, int]:
    """Create-or-update one env var. Returns (action, status)."""
    base = f"{VERCEL_API}/v10/projects/{project}/env"
    r = requests.post(
        f"{base}{teamq}&upsert=true" if teamq else f"{base}?upsert=true",
        headers=headers,
        json={"key": key, "value": value, "type": "encrypted", "target": targets},
        timeout=TIMEOUT_S,
    )
    return ("upsert", r.status_code)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", help="Vercel project slug")
    ap.add_argument("--db", choices=sorted(PROJECT_ENV_VARS),
                    help="which empire database's pair to push")
    ap.add_argument("--env", nargs="+", default=["production", "preview", "development"])
    ap.add_argument("--plan", action="store_true", help="print the mapping, push nothing")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    targets = {args.project: args.db} if args.project and args.db else DEFAULT_TARGETS
    if args.plan:
        print(json.dumps({"would_push": targets, "vars": APP_VAR_NAMES,
                          "environments": args.env}, indent=2))
        return 0

    env = load_env()
    headers, teamq = vercel_headers(env)

    results = []
    failed = False
    for vercel_project, db_name in targets.items():
        url_var, tok_var = PROJECT_ENV_VARS[db_name]
        url_val, tok_val = env.get(url_var), env.get(tok_var)
        if not url_val or not tok_val:
            results.append({"project": vercel_project, "db": db_name,
                            "status": "SKIP — source pair missing in agents env",
                            "missing": [v for v, val in ((url_var, url_val), (tok_var, tok_val)) if not val]})
            failed = True
            continue
        for app_key, val in zip(APP_VAR_NAMES, (url_val, tok_val)):
            action, code = upsert_env(vercel_project, app_key, val, args.env, headers, teamq)
            ok = code in (200, 201)
            results.append({"project": vercel_project, "key": app_key,
                            "action": action, "http": code, "ok": ok})
            if not ok:
                failed = True

    if args.json:
        print(json.dumps({"ok": not failed, "results": results}, indent=2))
    else:
        for r in results:
            if "key" in r:
                print(f"  {'ok ' if r['ok'] else 'FAIL'} {r['project']}: {r['key']} ({r['http']})")
            else:
                print(f"  {r['status']}: {r['project']} <- {r['db']} missing={r.get('missing')}")
        print("NOTE: EMPIRE_DATA_BACKEND was NOT set — the cutover switch is the operator's.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
