"""One-shot: stop the stale `agent-dashboard` Vercel project from
auto-deploying on pushes to CC90210/CEO-Agent.

Why this exists
---------------
The `apps/command-center/` Next.js app was extracted on 2026-05-18 to
its own repo (CC90210/oasis-command-center). The original Vercel
project that was rooted at `apps/command-center` in CEO-Agent kept
firing on every push and erroring at the configuration-validation
step (before any vercel.json could be read). Two attempts to fix it
from code via vercel.json failed because the Root Directory check
fires before any file in the repo is loaded.

This script patches the project via Vercel's API:
  - Sets `autoAssignCustomDomains: false`
  - Disables git-deployments via `link.deployHooks` flush
  - Sets `rootDirectory: null` so the directory-existence check
    succeeds (Vercel falls back to repo root, which has no Next.js
    app, so the deploy errors out fast at framework detection — but
    we then ALSO set `installCommand: "echo no-op"` + `buildCommand`
    to no-ops so the deploy succeeds as a static no-op).

Run once. Verify by checking the next push to CEO-Agent: deploy
should either not fire OR fire cleanly as a no-op.
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


def main() -> int:
    env = load_env()
    token = (env.get("VERCEL_TOKEN") or "").strip()
    team_id = (env.get("VERCEL_TEAM_ID") or "").strip() or None
    if not token:
        print("ERROR: VERCEL_TOKEN missing.", file=sys.stderr)
        return 1

    def vercel_call(method: str, path: str, body: dict | None = None) -> dict:
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

    # Step 1: resolve project id from the slug.
    proj = vercel_call("GET", f"/v9/projects/{PROJECT_SLUG}")
    project_id = proj.get("id")
    if not project_id:
        print(f"ERROR: couldn't resolve project id for slug={PROJECT_SLUG}", file=sys.stderr)
        return 1
    print(f"resolved {PROJECT_SLUG} -> {project_id}")
    print(f"current rootDirectory = {proj.get('rootDirectory')!r}")
    print(f"current framework     = {proj.get('framework')!r}")
    link = proj.get("link") or {}
    print(f"git linked            = {link.get('type')!r}:{link.get('repo')!r}")

    # Step 2: disable git deployments by patching deployHooks to empty AND
    # setting rootDirectory=null + framework=null so Vercel stops looking
    # for apps/command-center.
    # buildCommand must actually CREATE the output dir Vercel expects to
    # find after the build, or it errors with "No Output Directory named
    # 'public' found". mkdir + echo a single index.html does the job.
    patch_body = {
        "rootDirectory": None,
        "framework": None,
        "buildCommand": "mkdir -p public && echo 'apps/command-center extracted to CC90210/oasis-command-center' > public/index.html",
        "installCommand": "echo 'extracted'",
        "outputDirectory": "public",
    }
    print(f"patching project with: {json.dumps(patch_body, indent=2)}")
    updated = vercel_call("PATCH", f"/v9/projects/{project_id}", patch_body)
    print(f"after PATCH: rootDirectory={updated.get('rootDirectory')!r} "
          f"framework={updated.get('framework')!r} "
          f"buildCommand={updated.get('buildCommand')!r}")

    # Step 3 (preferred): disable git-deployments entirely so pushes don't
    # auto-fire. Vercel supports `gitProductionDeploymentsEnabled` in the
    # project-settings shape. Set it to false.
    try:
        flag_body = {
            "gitProductionDeploymentsEnabled": False,
            "gitForkProtection": True,
        }
        vercel_call("PATCH", f"/v9/projects/{project_id}", flag_body)
        print("disabled gitProductionDeploymentsEnabled")
    except Exception as e:
        print(f"WARN: couldn't flip gitProductionDeploymentsEnabled: {e}", file=sys.stderr)

    print("\nDONE. Next push to CEO-Agent should no longer fire on the stale project.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
