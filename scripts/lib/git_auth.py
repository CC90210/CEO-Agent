"""git_auth — hand git the PAT without the agent, the shell history, or the repo seeing it.

Extracted from scripts/git_push_tool.py on 2026-08-19, when
scripts/prune_merged_branches.py needed the same thing and every one of its 111
deletions failed with "could not read Username for 'https://github.com'". The
choice at that point is to copy thirty lines or to share them, and credential
handling is the last place to keep two copies: a fix to one is a fix nobody
applies to the other.

WHY GIT_ASKPASS AND NOT THE OBVIOUS ALTERNATIVES

  - `git remote set-url origin https://<token>@github.com/...` writes the token
    into .git/config in plaintext, permanently. That is exactly how a PAT leaked
    from this fleet before, and why scan_secrets.py had to be taught to read git
    remotes.
  - `git -c http.extraHeader=...` puts the credential on the command line, where
    any process listing can read it and shell history keeps it.

GIT_ASKPASS is a program git executes and reads on stdout. The token lives in one
child process's environment for the duration of one command and is written to a
0600 temp file that is deleted in a finally block.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.secret_loader import load_env  # noqa: E402

# GitHub accepts the PAT as the PASSWORD with any non-empty username over HTTPS.
# "x-access-token" is the conventional placeholder and keeps the real account
# name out of the flow.
ASKPASS_USERNAME = "x-access-token"


def github_token() -> str:
    """The PAT, via the sanctioned loader (audited, never echoed)."""
    return load_env(required=["GITHUB_PERSONAL_ACCESS_TOKEN"])["GITHUB_PERSONAL_ACCESS_TOKEN"]


@contextlib.contextmanager
def git_credential_env(token: str | None = None) -> Iterator[dict[str, str]]:
    """Yield an environment dict that authenticates git, cleaning up after.

    Use as::

        with git_credential_env() as env:
            subprocess.run(["git", "push", ...], env=env)

    The helper script and its launcher are removed on exit whether or not the
    command succeeded.
    """
    token = token or github_token()
    helper = launcher = None
    try:
        fd, helper = tempfile.mkstemp(suffix=".py", prefix="askpass_")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            # git calls this once per prompt with the prompt text as argv[1],
            # so it has to distinguish Username from Password.
            fh.write(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "prompt = sys.argv[1].lower() if len(sys.argv) > 1 else ''\n"
                f"print({ASKPASS_USERNAME!r} if 'username' in prompt else {token!r})\n"
            )
        os.chmod(helper, 0o600)

        # GIT_ASKPASS must be executable; a .py is not on Windows, so it is
        # invoked through a one-line launcher.
        lfd, launcher = tempfile.mkstemp(suffix=".bat", prefix="askpass_")
        with os.fdopen(lfd, "w", encoding="utf-8") as fh:
            fh.write(f'@echo off\r\n"{sys.executable}" "{helper}" %*\r\n')

        env = os.environ.copy()
        env["GIT_ASKPASS"] = launcher
        # Never fall back to an interactive prompt: a hang is worse than a clean
        # error when this runs unattended.
        env["GIT_TERMINAL_PROMPT"] = "0"
        yield env
    finally:
        for p in (helper, launcher):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
