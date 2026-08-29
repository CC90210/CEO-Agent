"""harness_eval.check_fleet_compiles — the fleet-wide syntax + unbound-name gate.

This gate is why the inbound classifier's NameError would be caught today
instead of running the keyword fallback silently for two days. It is also the
check that flapped hardest once it shipped.

THE FLAP, measured over 44 runs on 2026-08-28: it failed in bursts of 4-8 and
then went green, and every burst lined up with an editing window — the
17:09-17:47 UTC burst matched commits at 13:09-13:47 local, to the minute. It
was reading files mid-write. A partially written file is a SyntaxError; a file
saved between its call site and its import is an undefined name. Neither is a
defect in the fleet, and between them they cost ~3 percentage points of the
weekly harness score.

That matters beyond the number: a gate that cries wolf during every save is one
an operator learns to scroll past, which is exactly how the two-day classifier
outage stayed invisible behind a green harness.

So a failure is CONFIRMED by a second read. These tests pin both halves — a real
defect must still fail, and a mid-write must not.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import harness_eval as he  # noqa: E402


BROKEN_NAME = "def f():\n    return undefined_thing_xyz()\n"
BROKEN_SYNTAX = "def f(:\n"
CLEAN = "def f():\n    return 1\n"
# Two definitions of one name. The later wins and the first is dead — the
# scheduler.py `_clip` collision and the structured_log.py `doRollover`
# collision, both found 2026-08-29. pyflakes reports this as
# RedefinedWhileUnused; the gate simply was not collecting that message type,
# only UndefinedName. The defect was in the gate's coverage, not in the linter.
SHADOWED = "def f(a):\n    return a\n\n\ndef g():\n    return f(1)\n\n\ndef f(a, b):\n    return a + b\n"
# The legitimate shapes that must NOT be flagged: an alternate definition is
# always inside a conditional or a handler, never at unconditional top level.
CONDITIONAL_ALT = (
    "import sys\n\nif sys.platform == 'win32':\n    def f():\n        return 1\n"
    "else:\n    def f():\n        return 2\n\n"
    "try:\n    from os import getcwd as g\nexcept ImportError:\n    def g():\n        return '.'\n"
)


class _Scan:
    """Drive check_fleet_compiles over ONE synthetic file.

    Patches the file walk so the gate sees a single controlled path, and patches
    read_text so we can hand it different content on the first and second read —
    which is precisely what a save completing mid-scan looks like.
    """

    def __init__(self, monkeypatch, tmp_path, reads: list[str]):
        self.reads = list(reads)
        self.count = 0
        target = tmp_path / "subject.py"
        target.write_text(reads[-1], encoding="utf-8")

        monkeypatch.setattr(he.Path, "rglob", lambda self, pat: iter([target]))
        monkeypatch.setattr(
            he.Path, "relative_to",
            lambda self, other: Path("scripts/subject.py"), raising=False)

        real_read = Path.read_text

        def fake_read(p, *a, **k):
            if Path(p) == target:
                text = self.reads[min(self.count, len(self.reads) - 1)]
                self.count += 1
                return text
            return real_read(p, *a, **k)

        monkeypatch.setattr(he.Path, "read_text", fake_read)

    def run(self):
        return he.check_fleet_compiles()


# --- real defects must still fail --------------------------------------------

def test_a_stable_undefined_name_fails(monkeypatch, tmp_path):
    """The a71826a7 class: valid syntax, NameError at runtime."""
    ok, msg = _Scan(monkeypatch, tmp_path, [BROKEN_NAME, BROKEN_NAME]).run()
    assert ok is False
    assert "undefined name" in msg


def test_a_stable_syntax_error_fails(monkeypatch, tmp_path):
    """The 2026-08-11 class: a session cut off mid-batch-edit."""
    ok, msg = _Scan(monkeypatch, tmp_path, [BROKEN_SYNTAX, BROKEN_SYNTAX]).run()
    assert ok is False
    assert "syntax error" in msg.lower()


def test_a_dead_redefinition_fails(monkeypatch, tmp_path):
    """Two live examples on the day this landed: scheduler.py's second `_clip`
    silently rebound five call sites to a different signature, and
    structured_log.py's second `doRollover` made the sharing-violation fallback
    the class exists for unreachable — while a 190 MB log went unrotated."""
    ok, msg = _Scan(monkeypatch, tmp_path, [SHADOWED, SHADOWED]).run()
    assert not ok
    assert "redefined" in msg, msg
    assert "'f'" in msg, msg


def test_conditional_alternate_definitions_are_not_flagged(monkeypatch, tmp_path):
    """Fail-loud must not become fail-noisy. A platform branch and a
    try/except-ImportError fallback both define one name twice on purpose;
    flagging them would make the gate something operators mute."""
    ok, msg = _Scan(monkeypatch, tmp_path, [CONDITIONAL_ALT]).run()
    assert ok, msg


def test_the_allowlist_only_holds_entries_that_still_fire():
    """An allowlist is a mute button, so it has to decay. Every entry must
    correspond to a redefinition pyflakes ACTUALLY reports today; once the
    underlying code is cleaned up the entry has to go, or the next real defect
    in that file and name is muted by a stale exemption."""
    import ast

    from pyflakes.checker import Checker
    from pyflakes.messages import RedefinedWhileUnused

    root = Path(__file__).resolve().parents[2]
    live = set()
    for rel, _name in he._REDEFINITION_ALLOWLIST:
        path = root / rel
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for m in Checker(tree, filename=str(path)).messages:
            if isinstance(m, RedefinedWhileUnused) and m.message_args:
                live.add((rel, m.message_args[0]))
    stale = sorted(he._REDEFINITION_ALLOWLIST - live)
    assert not stale, f"allowlist entries no longer needed — remove them: {stale}"


def test_a_clean_file_passes(monkeypatch, tmp_path):
    ok, msg = _Scan(monkeypatch, tmp_path, [CLEAN]).run()
    assert ok is True
    assert "parse clean" in msg


# --- mid-write must NOT fail --------------------------------------------------

def test_a_file_that_reads_clean_on_confirm_is_transient(monkeypatch, tmp_path):
    """A save completing between the two reads. THE flap."""
    ok, msg = _Scan(monkeypatch, tmp_path, [BROKEN_NAME, CLEAN]).run()
    assert ok is True, "a mid-write snapshot must not fail the gate"
    assert "transient" in msg


def test_a_partial_syntax_write_is_transient(monkeypatch, tmp_path):
    ok, msg = _Scan(monkeypatch, tmp_path, [BROKEN_SYNTAX, CLEAN]).run()
    assert ok is True
    assert "transient" in msg


def test_content_still_moving_is_transient_not_a_failure(monkeypatch, tmp_path):
    """Broken both times but DIFFERENT both times — the file is actively being
    written, so we cannot judge it either way this run. Reporting it would be
    guessing; the next run will see the settled file."""
    ok, msg = _Scan(monkeypatch, tmp_path,
                    [BROKEN_NAME, BROKEN_NAME + "# still writing\n"]).run()
    assert ok is True
    assert "transient" in msg


def test_transient_count_is_reported_not_hidden(monkeypatch, tmp_path):
    """Suppression that says nothing is indistinguishable from a gate that
    stopped working. If mid-write skips ever become common, the message says so."""
    _, msg = _Scan(monkeypatch, tmp_path, [BROKEN_NAME, CLEAN]).run()
    assert "1 transient" in msg


# --- the confirm read must be cheap ------------------------------------------

def test_clean_files_are_read_exactly_once(monkeypatch, tmp_path):
    """The confirm pass must only cost on failures. Re-reading all 350 files
    every run would double the gate's IO on a box where process IO is already
    the bottleneck."""
    scan = _Scan(monkeypatch, tmp_path, [CLEAN])
    scan.run()
    assert scan.count == 1, f"clean file read {scan.count} times, expected 1"


def test_failing_files_are_read_twice(monkeypatch, tmp_path):
    scan = _Scan(monkeypatch, tmp_path, [BROKEN_NAME, BROKEN_NAME])
    scan.run()
    assert scan.count == 2
