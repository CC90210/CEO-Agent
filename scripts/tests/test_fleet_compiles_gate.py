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
