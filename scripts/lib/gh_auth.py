"""gh_auth.py — one-call GitHub CLI auth for every tool that shells out to `gh`.

Sibling of lib/claude_auth.py (which does the same job for the `claude` CLI).

THE PROBLEM THIS EXISTS FOR (measured 2026-08-13):

`gh` was being spawned with a bare inherited environment while this box's
stored gh login had gone bad — `gh auth status` reports
"X Failed to log in to github.com account CC90210 (default)". Every call
therefore ran ANONYMOUS:

    core     limit=60    remaining=60      <- unauthenticated ceiling
    graphql  limit=0     remaining=0       <- GraphQL refuses anon outright

`graphql = 0` is why the symptom always read "graphql failed: gh: API rate
limit exceeded", and why review_loop gave up on oasis-command-center#172 and
#174 after 10 failed harvests each. With the token injected:

    core     limit=5000
    graphql  limit=5000

THE NAME TRAP: the empire stores the credential as
GITHUB_PERSONAL_ACCESS_TOKEN. `gh` reads only GH_TOKEN / GITHUB_TOKEN, so
`capability_probe check github` reports AVAILABLE (the key IS there) while
every gh subprocess still runs anonymous. Presence of a credential is not the
same as the tool being able to see it.

CANONICAL PATTERN for any script that shells out to gh:

    from lib.gh_auth import gh_exe, gh_env
    subprocess.run([gh_exe(), "api", path], env=gh_env(), ...)

Never logs or returns the token. Degrades to the plain inherited environment
when nothing is configured, so adopting this can only improve on a bare spawn.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# gh's own env var names, in the order gh itself resolves them.
_GH_VARS = ("GH_TOKEN", "GITHUB_TOKEN")
# Where the empire actually stores it, most-specific first.
_EMPIRE_VARS = ("GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")

_ENV_CACHE: dict[str, str] | None = None
_EXE_CACHE: str | None = None


def gh_exe() -> str:
    """Locate the gh binary.

    PATH first, then the Windows install dir a daemon's slim PATH misses —
    PM2 / pythonw schedulers do not inherit an interactive shell's PATH, which
    is how a working gh turns into rc=127 "not found" only in production.
    """
    global _EXE_CACHE
    if _EXE_CACHE is not None:
        return _EXE_CACHE
    found = shutil.which("gh")
    if not found:
        for cand in (r"C:\Program Files\GitHub CLI\gh.exe",
                     r"C:\Program Files (x86)\GitHub CLI\gh.exe",
                     "/opt/homebrew/bin/gh", "/usr/local/bin/gh", "/usr/bin/gh"):
            if os.path.exists(cand):
                found = cand
                break
    _EXE_CACHE = found or "gh"   # fall back to the bare name; caller sees rc=127
    return _EXE_CACHE


def gh_env(extras: dict[str, str] | None = None) -> dict[str, str]:
    """Child environment for a gh subprocess, with GH_TOKEN injected.

    Reads through lib.secret_loader (RULE 3 — wrappers load secrets internally
    and never echo them). Cached: the token does not change within a process
    and re-reading it per call multiplies secret-access log noise.
    """
    global _ENV_CACHE
    if _ENV_CACHE is None:
        env = dict(os.environ)
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
            from lib.secret_loader import get as _secret  # noqa: E402

            token = None
            for var in _EMPIRE_VARS:
                token = _secret(var)
                if token:
                    break
            if token:
                env["GH_TOKEN"] = token
                # Single source: a stale GITHUB_TOKEN in the ambient env is a
                # second candidate gh may prefer over the one we just resolved.
                env.pop("GITHUB_TOKEN", None)
        except Exception as exc:  # noqa: BLE001 — auth help must never crash a caller
            print(f"[gh_auth] WARNING: could not load a GitHub token "
                  f"({type(exc).__name__}: {exc}); gh will run with whatever auth it "
                  f"already has (likely anonymous: 60 core/hr, 0 graphql).",
                  file=sys.stderr)
        _ENV_CACHE = env
    if extras:
        merged = dict(_ENV_CACHE)
        merged.update(extras)
        return merged
    return _ENV_CACHE


def has_token() -> bool:
    """True if a GitHub token was resolvable. Never reveals its value."""
    return bool(gh_env().get(_GH_VARS[0]))


def status_is_authenticated(rc: int, output: str) -> bool:
    """Interpret `gh auth status` honestly.

    gh exits 1 if ANY stored account is unhealthy, even when a working one is
    active — this box holds a dead keyring entry next to a good injected token,
    and a bare `rc != 0` check aborted every harvest despite full API access.
    "Logged in to" appears only in success lines (the failure wording is
    "Failed to log in"), so this cannot be satisfied by a broken account.
    """
    return rc == 0 or "Logged in to" in (output or "")
