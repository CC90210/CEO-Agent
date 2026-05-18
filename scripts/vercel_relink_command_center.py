"""URGENT: re-link the `agent-dashboard` Vercel project from CEO-Agent
(now a stub) to the new standalone repo CC90210/oasis-command-center.

The previous patch script (vercel_disable_stale_project.py) turned the
project into a no-op static deploy under the assumption that a SEPARATE
Vercel project was already serving the standalone repo. Listing all
Vercel projects shows that assumption was wrong — there is no project
linked to oasis-command-center. The agent-dashboard project IS the only
deploy of the Command Center, and turning it into a no-op took the
Command Center offline.

This script:
  1. PATCHes agent-dashboard's git link from CEO-Agent -> oasis-command-center
  2. Restores rootDirectory to null (the new repo IS the app)
  3. Restores framework to 'nextjs'
  4. Clears the no-op build/install commands so Vercel uses Next.js defaults
  5. Triggers a fresh deployment from the new repo's main branch

After this runs, the URL CC has bookmarked
(agent-dashboard-cc90210.vercel.app or any production alias) should
once again serve the real Command Center.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib import request, error

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib.secret_loader import load_env  # type: ignore  # noqa: E402

PROJECT_SLUG = "agent-dashboard"
NEW_REPO = "CC90210/oasis-command-center"


def main() -> int:
    env = load_env()
    token = (env.get("VERCEL_TOKEN") or "").strip()
    team_id = (env.get("VERCEL_TEAM_ID") or "").strip() or None
    if not token:
        print("ERROR: VERCEL_TOKEN missing.", file=sys.stderr)
        return 1

    def call(method: str, path: str, body: dict | None = None) -> dict:
        sep = "&" if "?" in path else "?"
        url = f"https://api.vercel.com{path}"
        if team_id:
            url += f"{sep}teamId={team_id}"
        data = json.dumps(body).encode() if body is not None else None
        req = request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
            print(f"HTTP {e.code} on {method} {path}\n{raw}", file=sys.stderr)
            raise

    proj = call("GET", f"/v9/projects/{PROJECT_SLUG}")
    project_id = proj.get("id")
    if not project_id:
        print(f"ERROR: project slug={PROJECT_SLUG} not found", file=sys.stderr)
        return 1
    link = proj.get("link") or {}
    print(f"current link: type={link.get('type')!r} repo={link.get('repo')!r} org={link.get('org')!r}")

    # Step 1: re-link the git repository. Vercel's projects API exposes
    # link configuration; passing `link: null` first then a fresh link
    # avoids stale fields. The simpler path is the dedicated link endpoint.
    print(f"\nUnlinking from current repo...")
    try:
        call("DELETE", f"/v9/projects/{project_id}/link")
    except Exception as e:
        print(f"WARN: unlink soft-fail: {e}")

    print(f"Linking to {NEW_REPO}...")
    link_body = {
        "type": "github",
        "repo": NEW_REPO,
        "productionBranch": "main",
    }
    call("POST", f"/v9/projects/{project_id}/link", link_body)

    # Step 2: restore real build settings. The new repo IS the Next.js
    # app — no rootDirectory subdirectory; framework auto-detect or
    # explicit 'nextjs'.
    print("Restoring framework + build settings...")
    restore_body = {
        "rootDirectory": None,
        "framework": "nextjs",
        "buildCommand": None,    # let Next.js default
        "installCommand": None,  # let Next.js default
        "outputDirectory": None,
        "devCommand": None,
    }
    updated = call("PATCH", f"/v9/projects/{project_id}", restore_body)
    print(f"framework={updated.get('framework')!r} "
          f"rootDirectory={updated.get('rootDirectory')!r} "
          f"buildCommand={updated.get('buildCommand')!r}")

    # Step 3: trigger a deployment from the new repo's main branch tip
    # so the Command Center is back up without waiting for a push.
    print("\nTriggering fresh deploy from new repo main...")
    try:
        deploy_body = {
            "name": "agent-dashboard",
            "gitSource": {
                "type": "github",
                "repo": NEW_REPO,
                "ref": "main",
            },
            "target": "production",
            "projectSettings": {
                "framework": "nextjs",
            },
        }
        deploy = call("POST", "/v13/deployments", deploy_body)
        print(f"deploy id: {deploy.get('id')}")
        print(f"deploy url: https://{deploy.get('url')}")
    except Exception as e:
        print(f"WARN: deploy trigger soft-fail (project link should auto-deploy on next push): {e}")

    print("\nDONE. agent-dashboard now links to oasis-command-center.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
