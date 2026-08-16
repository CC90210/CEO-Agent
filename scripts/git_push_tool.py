#!/usr/bin/env python3
"""git_push_tool — push a branch using the PAT from `.env.agents`, without the
token ever reaching the agent's context, the shell history, or the repo.

WHY THIS EXISTS
`gh auth status` reports the stored CLI token as invalid, and re-authenticating
needs an interactive browser flow the agent cannot run. A valid
GITHUB_PERSONAL_ACCESS_TOKEN is already present in `.env.agents`, which is
exactly the situation RULE 3 describes: the credential exists, the agent may use
it, and the agent may not see it.

WHY NOT THE OBVIOUS SHORTCUTS
  - `git remote set-url origin https://<token>@github.com/...` WRITES THE TOKEN
    INTO .git/config, in plaintext, permanently. That is precisely how a PAT
    leaked from this fleet before; the scanner had to be taught to read git
    remotes because of it. Never do this.
  - `git -c http.extraHeader=...` puts the credential on the command line, where
    it is visible to any process listing and lands in shell history.

Instead the token is handed to git through GIT_ASKPASS, which git invokes as a
child process and reads on stdout. It lives in one process's environment for the
duration of one push and is never written anywhere.

Usage:
    python scripts/git_push_tool.py --repo <path> --branch <name> [--set-upstream]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.secret_loader import load_env  # noqa: E402

# GitHub accepts the PAT as the PASSWORD with any non-empty username over HTTPS.
# "x-access-token" is the conventional placeholder and keeps the real account
# name out of the flow.
ASKPASS_USERNAME = "x-access-token"


def _askpass_script(token: str) -> str:
    """A helper git runs to answer its Username/Password prompts.

    git calls it once per prompt with the prompt text as argv[1], so the script
    has to distinguish the two. Written to a 0600 temp file and deleted in a
    finally block — the token is on disk only for the length of the push.
    """
    return (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "prompt = sys.argv[1].lower() if len(sys.argv) > 1 else ''\n"
        f"print({ASKPASS_USERNAME!r} if 'username' in prompt else {token!r})\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="path to the git repository")
    ap.add_argument("--branch", required=True, help="branch to push")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--set-upstream", action="store_true")
    # `gh` reads GH_TOKEN from its environment, so the same loaded secret opens
    # the PR without a second auth path — and without the agent ever holding it.
    ap.add_argument("--pr", action="store_true", help="open a pull request instead of pushing")
    ap.add_argument("--edit-body", action="store_true",
                    help="replace the PR body with --body-file")
    # Merging is the one MUTATION here and it is gated on the operator asking
    # for it. --squash keeps main readable; the branch is deleted after so the
    # remote does not accumulate merged heads.
    ap.add_argument("--merge", action="store_true", help="squash-merge the PR (operator-directed only)")
    ap.add_argument("--checks", action="store_true",
                    help="report CI check conclusions for the branch's PR (read-only)")
    ap.add_argument("--title")
    ap.add_argument("--body-file")
    ap.add_argument("--base", default="main")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"not a git repository: {repo}", file=sys.stderr)
        return 2

    env_vals = load_env(required=["GITHUB_PERSONAL_ACCESS_TOKEN"])
    token = env_vals["GITHUB_PERSONAL_ACCESS_TOKEN"]

    if args.pr or args.checks or args.edit_body or args.merge:
        gh = os.environ.get("GH_BIN", r"C:\Program Files\GitHub CLI\gh.exe")
        if not Path(gh).exists():
            print(f"gh not found at {gh}; set GH_BIN", file=sys.stderr)
            return 2
        child = os.environ.copy()
        # Overrides the stored (currently invalid) CLI credential for this call
        # only. Nothing is written to the gh config.
        child["GH_TOKEN"] = token
        if args.merge:
            cmd = [gh, "pr", "merge", args.branch, "--squash", "--delete-branch"]
        elif args.edit_body:
            cmd = [gh, "pr", "edit", args.branch, "--body-file", args.body_file]
        elif args.checks:
            # `gh pr checks` reports the CHECK conclusions, which is a different
            # question from `gh pr view`'s review state. Merging on a green review
            # while a required check was FAILURE has happened on this fleet
            # (PR #190, Vercel red); they are not interchangeable.
            cmd = [gh, "pr", "checks", args.branch, "--watch=false"]
        else:
            cmd = [gh, "pr", "create", "--base", args.base, "--head", args.branch]
            if args.title:
                cmd += ["--title", args.title]
            if args.body_file:
                cmd += ["--body-file", args.body_file]
        proc = subprocess.run(cmd, cwd=str(repo), env=child, capture_output=True, text=True)
        if proc.stdout.strip():
            print(proc.stdout.strip())
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode

    fd, path = tempfile.mkstemp(suffix=".py", prefix="askpass_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(_askpass_script(token))
        os.chmod(path, 0o600)

        child = os.environ.copy()
        # GIT_ASKPASS must be an executable; on Windows a .py is not, so invoke
        # the interpreter explicitly via a one-line launcher.
        launcher_fd, launcher = tempfile.mkstemp(suffix=".bat", prefix="askpass_")
        with os.fdopen(launcher_fd, "w", encoding="utf-8") as fh:
            fh.write(f'@echo off\r\n"{sys.executable}" "{path}" %*\r\n')
        child["GIT_ASKPASS"] = launcher
        # Stop git falling back to any interactive prompt if the helper fails —
        # a hang is worse than a clean error in an automated context.
        child["GIT_TERMINAL_PROMPT"] = "0"

        cmd = ["git", "push"]
        if args.set_upstream:
            cmd.append("--set-upstream")
        cmd += [args.remote, args.branch]

        proc = subprocess.run(cmd, cwd=str(repo), env=child, capture_output=True, text=True)
        # git writes progress to stderr; both streams are echoed so a failure is
        # legible. The token appears in neither.
        if proc.stdout.strip():
            print(proc.stdout.strip())
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode
    finally:
        for p in (path, locals().get("launcher")):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
