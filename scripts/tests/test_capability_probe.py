"""Tests for capability_probe's codex/openai check.

WHY THIS FILE EXISTS
--------------------
capability_probe is the tool an agent is told to trust OVER its own memory
before saying "I don't have access to X". On 2026-08-29 it produced that exact
false negative about the one capability RULE 8 makes mandatory:

    $ python scripts/capability_probe.py check openai
    openai: NOT CONFIGURED
      keys missing : OPENAI_API_KEY

...while `codex login status` answered "Logged in using ChatGPT" in 2.9s. Codex
here authenticates by subscription; OPENAI_API_KEY is not how it logs in and is
not set. So the probe was telling agents the required independent audit was
impossible, and making the skip look justified.

These tests pin the three properties that failure needed:

  LIVE    — the verdict comes from the CLI's own auth state, not from an env var
            the CLI never reads.
  QUIET   — the reported reason never echoes the CLI's raw output. `codex login
            status` can describe an API-key login, and this tool's CONTRACT
            forbids any credential material reaching a model's context.
  HONEST  — a failure to VERIFY is worded as unverified, never as absent, and
            every failure path names the command that fixes it.

The subprocess is stubbed everywhere except the live test at the bottom, which
runs the real CLI and is the reported bug's direct repro.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import capability_probe as cp  # noqa: E402


class _Proc:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture()
def fake_codex(monkeypatch):
    """Pretend `codex` is installed; let each test choose what it says."""
    monkeypatch.setattr(cp.shutil, "which", lambda name: r"C:\fake\codex.CMD")

    def _set(proc=None, raises=None):
        def _run(*_a, **_k):
            if raises is not None:
                raise raises
            return proc
        monkeypatch.setattr(cp.subprocess, "run", _run)

    return _set


# ------------------------------------------------------------------- LIVE ----

def test_available_without_openai_api_key(fake_codex):
    """THE REGRESSION: subscription auth, no env key, must read AVAILABLE.

    `have` is deliberately empty — that is the real machine's state.
    """
    fake_codex(_Proc(0, stderr="Logged in using ChatGPT"))
    r = cp.probe("openai", set())
    assert r["available"] is True
    # Not merely available — OPENAI_API_KEY must not be listed as missing, or the
    # reader is sent to fix a key that was never the blocker.
    assert r["keys_missing"] == []
    assert "ChatGPT subscription" in r["auth"]


def test_verdict_read_from_stderr_not_just_stdout(fake_codex):
    """codex prints its auth mode to STDERR and leaves stdout empty (measured)."""
    fake_codex(_Proc(0, stdout="", stderr="Logged in using ChatGPT"))
    authed, detail = cp._codex_auth()
    assert authed is True
    assert "mode not recognised" not in detail


def test_unauthenticated_cli_is_not_available(fake_codex):
    """A logged-out CLI must NOT be laundered into AVAILABLE by the live probe."""
    fake_codex(_Proc(1, stderr="Not logged in"))
    r = cp.probe("openai", set())
    assert r["available"] is False
    assert r["keys_missing"] == ["OPENAI_API_KEY"]
    assert "codex login" in r["auth"]


def test_api_key_still_authorizes_when_cli_is_logged_out(fake_codex):
    """The env-key path is the minority path, not a removed one."""
    fake_codex(_Proc(1, stderr="Not logged in"))
    r = cp.probe("openai", {"OPENAI_API_KEY"})
    assert r["available"] is True


# ------------------------------------------------------------------ QUIET ----

def test_auth_detail_never_echoes_cli_output(fake_codex):
    """CONTRACT: no credential material in the output, on any path.

    An API-key login makes `codex login status` describe the key. This asserts
    the classifier reports the MODE and drops the text it read it from.
    """
    leak = "sk-proj-FAKETESTVALUE-not-a-real-key"
    fake_codex(_Proc(0, stderr="Logged in using an API key (" + leak + ")"))
    authed, detail = cp._codex_auth()
    assert authed is True
    assert leak not in detail
    assert "FAKETESTVALUE" not in detail
    assert detail == (
        "codex CLI logged in (API key) — OPENAI_API_KEY is not required for this path"
    )


def test_unrecognised_mode_is_named_not_echoed(fake_codex):
    """Unknown wording must degrade to a label, never to a passthrough."""
    secret_ish = "token=abcd1234wouldbealeak"
    fake_codex(_Proc(0, stderr="Authenticated " + secret_ish))
    authed, detail = cp._codex_auth()
    assert authed is True
    assert secret_ish not in detail
    assert "mode not recognised" in detail


# ----------------------------------------------------------------- HONEST ----

def test_timeout_is_reported_unverified_not_absent(fake_codex):
    """A stall must not harden into "I don't have access" — the original bug."""
    fake_codex(raises=subprocess.TimeoutExpired(cmd="codex", timeout=cp.CODEX_STATUS_TIMEOUT))
    authed, detail = cp._codex_auth()
    assert authed is False
    assert "UNVERIFIED" in detail
    assert "not logged in" not in detail


@pytest.mark.parametrize("rc", [3221225480, -11])
def test_abnormal_termination_is_unverified_not_logged_out(fake_codex, rc):
    """A crash is not a verdict.

    3221225480 is 0xC0000008 STATUS_INVALID_HANDLE, observed once in ~6 runs
    spawning the codex.CMD shim, with both streams empty. Reporting that as
    "not logged in" would be a confident false negative on a transient.
    """
    fake_codex(_Proc(rc, stdout="", stderr=""))
    authed, detail = cp._codex_auth()
    assert authed is False
    assert "UNVERIFIED" in detail
    assert "not logged in" not in detail


def test_clean_nonzero_exit_is_still_read_as_logged_out(fake_codex):
    """The crash carve-out must not swallow codex's real logged-out signal."""
    fake_codex(_Proc(1, stderr="Not logged in"))
    authed, detail = cp._codex_auth()
    assert authed is False
    assert "not logged in" in detail
    assert "UNVERIFIED" not in detail


def test_status_probe_never_inherits_caller_stdin(monkeypatch):
    """cmd.exe (the .CMD shim) will read stdin if handed one — it must not be."""
    monkeypatch.setattr(cp.shutil, "which", lambda name: r"C:\fake\codex.CMD")
    seen = {}

    def _run(*_a, **kw):
        seen.update(kw)
        return _Proc(0, stderr="Logged in using ChatGPT")

    monkeypatch.setattr(cp.subprocess, "run", _run)
    cp._codex_auth()
    assert seen["stdin"] is subprocess.DEVNULL


def test_missing_cli_names_the_install_command(monkeypatch):
    monkeypatch.setattr(cp.shutil, "which", lambda name: None)
    authed, detail = cp._codex_auth()
    assert authed is False
    assert "npm install -g @openai/codex" in detail


def test_os_error_names_its_cause(fake_codex):
    """No silent False: an unexecutable binary says so, and says why."""
    fake_codex(raises=PermissionError(13, "Permission denied"))
    authed, detail = cp._codex_auth()
    assert authed is False
    assert "PermissionError" in detail


# ------------------------------------------- the command it is obliged to name ----

def test_invoke_names_the_rule_8_wrapper_and_that_wrapper_exists():
    """Naming the command to run is this tool's whole contract.

    The existence assert matters too: an invoke string pointing at a moved script
    is the "AVAILABLE, then No such file" false positive the SERVICES table
    already warns about for the `late` entry.
    """
    _, invoke = cp.SERVICES["openai"]
    assert "scripts/core/codex_review.py review" in invoke
    assert "codex-companion.mjs" in invoke
    assert (REPO_ROOT / "scripts" / "core" / "codex_review.py").is_file()


def test_codex_alias_resolves_to_openai():
    """RULE 8 calls this capability "Codex"; that is what an agent will type."""
    assert cp.ALIASES["codex"] == "openai"
    assert all(target in cp.SERVICES for target in cp.ALIASES.values())


# -------------------------------------------------------------------- live ----

@pytest.mark.skipif(
    shutil.which("codex") is None, reason="codex CLI not installed on this machine"
)
def test_live_check_openai_exits_zero_and_names_the_command():
    """End-to-end against the REAL CLI — the reported bug's direct repro.

    Retries ONLY on abnormal termination, never on a real verdict. Process
    creation on this Windows box intermittently dies with 0xC0000008
    (STATUS_INVALID_HANDLE) and no output — measured 2026-08-29 at 1 of 15 runs
    of `check stripe`, a path that spawns no subprocess at all, so it is the
    environment, not this probe. Exit 1 is the actual regression and fails on
    the first sight of it; retrying that would be exactly the swallowed failure
    this suite is here to prevent.
    """
    attempts = []
    for _ in range(3):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "capability_probe.py"),
             "check", "openai"],
            capture_output=True,
            text=True,
            timeout=90,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        attempts.append(proc.returncode)
        if proc.returncode in (0, 1):
            break
    else:
        pytest.fail(
            "capability_probe never terminated normally in 3 attempts "
            f"(exit codes {attempts}) — this is the host's process-creation "
            "flake, NOT a NOT CONFIGURED verdict. Re-run."
        )

    assert proc.returncode == 0, (
        "probe still reports NOT CONFIGURED:\n" + proc.stdout + proc.stderr
    )
    assert "AVAILABLE" in proc.stdout
    assert "scripts/core/codex_review.py review" in proc.stdout
