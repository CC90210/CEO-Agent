#!/usr/bin/env python3
"""vercel_deploy_tool — read deployment state and build logs via the Vercel CLI.

`vercel_env_tool.py` next door covers environment variables only. Diagnosing a
failed deploy needs the deployment list and the build log, and the alternative —
`npx vercel --token <VERCEL_TOKEN>` — puts the token on a command line where any
process listing can read it and shell history keeps it.

Here the token is loaded through secret_loader and passed to the CLI in the child
process's environment (`VERCEL_TOKEN`, which the CLI reads natively). It never
reaches the agent, the command line, or the terminal.

READ-ONLY BY CONSTRUCTION. The verbs are an allowlist of inspection commands.
Promoting, rolling back, redeploying and removing are deliberately absent:
production deploys of oasisai.work are an operator decision, and a tool that can
diagnose should not also be able to ship.

Usage:
    python scripts/integrations/vercel_deploy_tool.py list --project agent-dashboard
    python scripts/integrations/vercel_deploy_tool.py list --project agent-dashboard --prod
    python scripts/integrations/vercel_deploy_tool.py logs --url <deployment-url-or-id>
    python scripts/integrations/vercel_deploy_tool.py inspect --url <deployment-url-or-id>
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.secret_loader import load_env  # noqa: E402

# NO DEFAULT SCOPE. `--scope cc90210` is rejected outright — "You cannot set your
# Personal Account as the scope" — because these projects live on the operator's
# personal account rather than a team. Left unset, the CLI resolves scope from
# the token itself, which is correct here. `--scope` stays available for the day
# a project moves under a team.
DEFAULT_SCOPE = ""


def _run(args: list[str], token: str) -> int:
    child = os.environ.copy()
    child["VERCEL_TOKEN"] = token
    # Stop the CLI trying to open a browser or prompt on a missing link.
    child["CI"] = "1"
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        print("npx not found on PATH", file=sys.stderr)
        return 2
    # encoding/errors are explicit: the CLI emits box-drawing characters in its
    # update banner, and Python defaults to cp1252 on this platform, which
    # raised UnicodeDecodeError mid-read and truncated the output we came for.
    proc = subprocess.run(
        [npx, "vercel", *args], env=child, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        # The Vercel CLI writes its tables and most diagnostics to stderr, so
        # this is normal output rather than an error channel. Printing it to
        # stderr keeps the streams honest for a caller that redirects.
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="verb", required=True)

    p_list = sub.add_parser("list", help="recent deployments for a project")
    p_list.add_argument("--project", required=True)
    p_list.add_argument("--prod", action="store_true", help="production deployments only")

    p_logs = sub.add_parser("logs", help="build logs for one deployment")
    p_logs.add_argument("--url", required=True)

    p_inspect = sub.add_parser("inspect", help="metadata + state for one deployment")
    p_inspect.add_argument("--url", required=True)

    for p in (p_list, p_logs, p_inspect):
        p.add_argument("--scope", default=DEFAULT_SCOPE)
        # Every other wrapper in scripts/integrations takes --json, and the
        # fleet rule is "CLI-anything, always --json" — a human table is fine to
        # read and miserable to branch on. The Vercel CLI exposes it as
        # `-F json`, verified with `vercel ls --help` rather than assumed.
        #
        # NOT the default: `logs` under --format json emits one JSON object per
        # log line, and the failure diagnosis this tool exists for is far easier
        # to read as plain text.
        p.add_argument("--json", action="store_true", help="machine-readable output (-F json)")

    args = ap.parse_args()
    token = load_env(required=["VERCEL_TOKEN"])["VERCEL_TOKEN"]

    scope = ["--scope", args.scope] if args.scope else []
    fmt = ["-F", "json"] if args.json else []
    if args.verb == "list":
        cmd = ["ls", args.project, *scope, *fmt]
        if args.prod:
            cmd += ["--prod"]
    elif args.verb == "logs":
        cmd = ["inspect", args.url, "--logs", *scope, *fmt]
    else:
        cmd = ["inspect", args.url, *scope, *fmt]

    return _run(cmd, token)


if __name__ == "__main__":
    raise SystemExit(main())
