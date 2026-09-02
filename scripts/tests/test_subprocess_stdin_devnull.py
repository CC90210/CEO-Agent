"""Every windowless spawn hands its child a valid stdin.

WHY THIS EXISTS
---------------
Daemons on this box run under pythonw.exe, which has NO CONSOLE. subprocess
redirects stdout and stderr when asked and leaves stdin INHERITED, so every
child of a windowless parent inherited a console handle that does not exist and
intermittently died at interpreter startup with exit 3221225480 — 0xC0000008
STATUS_INVALID_HANDLE. Roughly 1 run in 100; 23 failure dumps between
2026-08-15 and 2026-09-02, every one with BOTH output streams empty, which is
what an OS kill looks like and what a Python exception never does.

It was recorded as 0xC0000005 "an access violation" (that is 3221225477) and
chased in email_engine for two and a half weeks. The evidence it was neither:
email_engine's own per-stage breadcrumb log shows the crashed run writing
NOTHING, not even its first statement, while the run five minutes earlier
logged all eight stages and finished — and capability_probe.py:270 recorded the
identical code on a probe that spawns no subprocess at all.

The fix lives in the shared helpers rather than in any caller, because 37 files
spawn through them and "spawned by a windowless parent" is the actual shared
property. These tests pin the three ways that fix could silently regress:
someone removing it, someone letting it clobber an explicit stdin, or someone
letting it collide with input= (which makes subprocess raise outright, and
self_audit.py:447 passes input=).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.subprocess_helpers import _default_stdin_devnull  # noqa: E402

WINDOWS_ONLY = pytest.mark.skipif(
    os.name != "nt", reason="console-handle inheritance is a Windows fault"
)


def test_a_bare_spawn_gets_devnull():
    assert _default_stdin_devnull({})["stdin"] is subprocess.DEVNULL


def test_an_explicit_stdin_is_never_clobbered():
    """A caller that wants a pipe must keep it — this helper is a default, not
    a policy."""
    out = _default_stdin_devnull({"stdin": subprocess.PIPE})
    assert out["stdin"] is subprocess.PIPE


def test_input_is_left_alone():
    """subprocess raises ValueError('stdin and input arguments may not both be
    used') if both are set. self_audit.py:447 passes input=, so setting stdin
    here would turn a working audit into a hard crash."""
    out = _default_stdin_devnull({"input": b"payload"})
    assert "stdin" not in out


def test_the_callers_kwargs_are_not_mutated():
    """Callers reuse kwargs dicts; mutating one in place leaks stdin into the
    next spawn."""
    original = {"timeout": 5}
    _default_stdin_devnull(original)
    assert original == {"timeout": 5}


@WINDOWS_ONLY
def test_safe_run_actually_closes_the_childs_stdin():
    """The end-to-end claim, executed rather than asserted about.

    A child that reads stdin must see EOF immediately instead of blocking on or
    inheriting the parent's handle.
    """
    from lib.subprocess_helpers import safe_run  # noqa: PLC0415

    proc = safe_run(
        [sys.executable, "-c", "import sys; sys.stdout.write(repr(sys.stdin.read()))"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "''", f"child did not see EOF on stdin: {proc.stdout!r}"


@WINDOWS_ONLY
def test_safe_run_still_honours_input():
    """The guard must not have broken the one caller that feeds stdin."""
    from lib.subprocess_helpers import safe_run  # noqa: PLC0415

    proc = safe_run(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
        input="fed", capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "fed"


# --------------------------------------------------------------------------- #
# The copies
# --------------------------------------------------------------------------- #

REPO = Path(__file__).resolve().parent.parent.parent

# bravo_cli keeps a deliberate COPY of these helpers rather than importing them
# (its module docstring gives the reasons: it is a pip-installable package, and
# the bridge needs an extra helper). A copy is a place a fix can fail to land —
# and it did: the scheduler was fixed first and the bridge, which runs under the
# same console-less pythonw, kept the fault. scripts/_subprocess_helpers.py is a
# re-export shim and inherits automatically, so it is not listed here.
SPAWN_HELPER_COPIES = [
    REPO / "scripts" / "lib" / "subprocess_helpers.py",
    REPO / "bravo_cli" / "_subprocess_helpers.py",
]


@pytest.mark.parametrize("path", SPAWN_HELPER_COPIES, ids=lambda p: p.parent.name)
def test_every_copy_of_the_helper_defaults_stdin(path):
    """Both copies must carry the guard, and every windowless spawn entry point
    in them must call it. Grepping for the definition alone would pass on a file
    that defines it and never uses it."""
    src = path.read_text(encoding="utf-8")
    assert "_default_stdin_devnull" in src, f"{path} has no stdin guard at all"
    # One call for the definition, plus one per spawn wrapper.
    assert src.count("_default_stdin_devnull(") >= 4, (
        f"{path} defines the guard but does not call it from every spawn "
        f"wrapper (found {src.count('_default_stdin_devnull(')} references; "
        "expected the def plus safe_run, safe_popen and safe_daemon_popen)"
    )


def test_the_watchdog_hands_its_daemons_a_stdin():
    """fleet_watchdog spawns the whole fleet with a raw Popen rather than these
    helpers, so it does not inherit the fix. Its children are long-lived, which
    makes this fault look like a crash loop instead of a bad spawn."""
    src = (REPO / "scripts" / "ops" / "fleet_watchdog.py").read_text(encoding="utf-8")
    launch = src[src.index("subprocess.Popen("):]
    assert "stdin=subprocess.DEVNULL" in launch[:400], (
        "fleet_watchdog.start() spawns daemons without stdin=DEVNULL"
    )
