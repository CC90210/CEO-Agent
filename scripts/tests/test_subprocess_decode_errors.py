"""One undecodable byte must not delete a child's entire output.

WHY THIS EXISTS
---------------
state/logs/daemon-bravo-scheduler.log carried this, repeatedly:

    File "...threading.py", line 1012, in run
      self._target(*self._args, **self._kwargs)
    File "...subprocess.py", line 1599, in _readerthread
      buffer.append(fh.read())
    File "<frozen codecs>", line 322, in decode
    UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb7 in position 45

0xb7 is the cp1252 middle dot — what a Windows console emits for a bulleted
line. scheduler.py decoded children as STRICT utf-8, so one such byte raised
inside subprocess's reader THREAD. The thread died, communicate() returned None
for that stream, and the job's whole stdout vanished. The job was then recorded
as a success, because "said nothing" and "fine" are the same shape.

Losing a run's output to a punctuation mark is not a decoding policy. It is
silent data loss in the component whose entire purpose is reporting what ran.

The fix lives in the shared helper, not at the four call sites: the fault is a
property of "decoding output from a Windows child", and 37 files spawn through
these helpers. scheduler.py's own raw subprocess.run sites are patched too,
because they do not go through the helper.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from lib.subprocess_helpers import (  # noqa: E402
    _default_decode_errors,
    safe_run,
)

# A child that prints a bulleted line the way a cp1252 console does: real text,
# then the raw 0xb7 byte, then more real text. Written to the buffer directly so
# no encoder gets a chance to sanitise it.
EMIT_BAD_BYTE = (
    "import sys; "
    "sys.stdout.buffer.write(b'checked 3 jobs\\xb7 all clean'); "
    "sys.stdout.buffer.flush()"
)


# ── the real thing: run a child that emits the byte ────────────────────────

def test_output_survives_an_undecodable_byte():
    r = safe_run([sys.executable, "-c", EMIT_BAD_BYTE],
                 capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.stdout is not None, "the reader thread died and took the output with it"
    assert "checked 3 jobs" in r.stdout, "text BEFORE the bad byte must survive"
    assert "all clean" in r.stdout, "text AFTER the bad byte must survive"


def test_strict_decoding_is_what_used_to_lose_it():
    """The premise, proven rather than asserted.

    Decoded directly rather than through a subprocess ON PURPOSE. Running the
    strict version for real reproduces the incident faithfully — including
    killing subprocess's reader thread — and pytest reports an unhandled THREAD
    exception against whichever test happens to run next, which is a test that
    breaks its neighbours to prove a point about itself.
    """
    payload = b"checked 3 jobs\xb7 all clean"
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        assert exc.object[exc.start] == 0xB7
    else:
        raise AssertionError(
            "0xb7 decoded cleanly as utf-8 — the premise no longer holds and "
            "the test above would pass for the wrong reason")
    # And the replacing decode, which is what the helper now installs, keeps
    # everything on both sides of the bad byte.
    replaced = payload.decode("utf-8", errors="replace")
    assert replaced.startswith("checked 3 jobs")
    assert replaced.endswith("all clean")


# ── the rule itself ────────────────────────────────────────────────────────

def test_it_applies_only_when_the_caller_asked_for_text():
    """errors= is meaningless on a bytes pipe and subprocess raises on it."""
    assert _default_decode_errors({"capture_output": True}) == {"capture_output": True}
    assert "errors" not in _default_decode_errors({})


def test_text_universal_newlines_and_encoding_all_count_as_text():
    for kw in ({"text": True}, {"universal_newlines": True}, {"encoding": "utf-8"}):
        assert _default_decode_errors(dict(kw))["errors"] == "replace", kw


def test_an_explicit_errors_always_wins():
    out = _default_decode_errors({"text": True, "errors": "strict"})
    assert out["errors"] == "strict", "the helper must never override a caller"


def test_the_caller_dict_is_not_mutated():
    original = {"text": True}
    _default_decode_errors(original)
    assert original == {"text": True}


# ── wiring: a rule nothing calls is a decoration ───────────────────────────

def test_every_helper_applies_it():
    src = (REPO / "scripts" / "lib" / "subprocess_helpers.py").read_text(encoding="utf-8")
    for fn in ("def safe_run(", "def safe_popen(", "def safe_daemon_popen("):
        body = src[src.index(fn):]
        body = body[: body.index("\ndef ", 1)]
        assert "_default_decode_errors(kwargs)" in body, f"{fn} does not apply it"


def test_the_schedulers_own_raw_spawns_are_patched_too():
    """scheduler.py calls subprocess.run directly, so the helper cannot cover
    it. All four sites decode as utf-8 and every one needs errors=replace."""
    src = (REPO / "scripts" / "scheduler.py").read_text(encoding="utf-8")
    utf8_sites = src.count('encoding="utf-8"')
    replace_sites = src.count('errors="replace"')
    assert utf8_sites >= 4, "expected at least the four known spawn sites"
    assert replace_sites >= utf8_sites, (
        f"{utf8_sites} sites decode utf-8 but only {replace_sites} tolerate a bad byte")


def test_the_unguarded_stdout_dereference_is_gone():
    """`result.stdout.strip()` raised AttributeError: 'NoneType' when the
    reader thread had died — reported to the operator as the job's error."""
    src = (REPO / "scripts" / "scheduler.py").read_text(encoding="utf-8")
    assert "result.stdout.strip()" not in src, (
        "a poisoned stream makes stdout None; deref it and the real cause is "
        "replaced by a NoneType AttributeError")
