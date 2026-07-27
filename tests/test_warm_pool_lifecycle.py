"""Regression tests for the warm-pool orphan leak found 2026-07-26.

Symptom on the SunBiz VPS: 14 `/usr/bin/claude` processes aged 26 to 42 days
holding 1,980 MB of RSS, while the pool is designed for max 8 with a 15-minute
idle reaper. Roughly one leaked process every 3 days since prewarm() was
introduced (feb9589e, 2026-05-09).

Cause: prewarm() releases _POOL_LOCK to spawn (5-30s) and consume the init turn
(up to 120s), then reacquires it and did `_WARM_POOL[pool_key] = wp`
UNCONDITIONALLY. /prewarm and /chat build the same pool_key, so a real turn
landing inside that ~150s window got silently clobbered. The dropped handle was
then unreachable by the idle reaper, the evictor and kill_for_session, remained
a direct child of the daemon, and never exited (nothing ever closes its stdin,
so claude never sees EOF).

These tests spawn no real subprocess. They drive the real prewarm() code path
with a fake process class so the race is deterministic.
"""
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from bravo_cli import warm_claude_pool as wcp


class FakeWarm:
    """Stand-in for WarmClaudeProcess with the surface prewarm() touches."""

    def __init__(self, *args, on_send_turn=None, **kwargs):
        self.created_at = time.time()
        self.last_used_at = self.created_at
        self.busy = False
        self.killed_reason = None
        self._alive = True
        self._on_send_turn = on_send_turn

    def is_alive(self):
        return self._alive

    def kill(self, reason="", grace=5.0):
        self.killed_reason = reason
        self._alive = False

    def send_turn(self, *args, **kwargs):
        # The unlocked window. A racing /chat turn lands here.
        if self._on_send_turn:
            self._on_send_turn()
        return True


@pytest.fixture(autouse=True)
def clean_pool():
    with wcp._POOL_LOCK:
        wcp._WARM_POOL.clear()
    yield
    with wcp._POOL_LOCK:
        wcp._WARM_POOL.clear()


def test_prewarm_does_not_orphan_a_racing_incumbent(monkeypatch):
    """THE regression test. A /chat turn that populates the same pool_key
    while prewarm is spawning must NOT be silently dropped.

    Pre-fix this fails: _WARM_POOL[key] ends up as the prewarm process and the
    incumbent is orphaned with killed_reason None, alive forever.
    """
    key = "agentX:tab123:rolefp"
    incumbent = FakeWarm()

    def racing_chat_turn():
        # Simulates use_or_create() storing a live process for the same key
        # during prewarm's unlocked spawn window.
        with wcp._POOL_LOCK:
            wcp._WARM_POOL[key] = incumbent

    made = []

    def fake_ctor(*args, **kwargs):
        wp = FakeWarm(on_send_turn=racing_chat_turn)
        made.append(wp)
        return wp

    monkeypatch.setattr(wcp, "WarmClaudeProcess", fake_ctor)

    assert wcp.prewarm(key, "agentX", Path(".")) is True

    prewarmed = made[0]
    # The incumbent may be mid-turn for a real operator, so it must win.
    assert wcp._WARM_POOL.get(key) is incumbent, "incumbent was clobbered"
    assert incumbent.is_alive(), "incumbent must not be killed"
    # And critically: the loser must be TERMINATED, not merely dropped.
    assert prewarmed.killed_reason == "prewarm_lost_race", (
        "prewarm's process was dropped without being killed — this is the leak"
    )
    assert not prewarmed.is_alive()


def test_prewarm_replaces_a_dead_incumbent_and_reaps_it(monkeypatch):
    """A dead incumbent should be replaced AND killed, never just dropped."""
    key = "agentX:tab456:rolefp"
    dead = FakeWarm()
    dead._alive = False

    def racing_dead_entry():
        with wcp._POOL_LOCK:
            wcp._WARM_POOL[key] = dead

    made = []

    def fake_ctor(*args, **kwargs):
        wp = FakeWarm(on_send_turn=racing_dead_entry)
        made.append(wp)
        return wp

    monkeypatch.setattr(wcp, "WarmClaudeProcess", fake_ctor)
    assert wcp.prewarm(key, "agentX", Path(".")) is True

    assert wcp._WARM_POOL.get(key) is made[0], "live process should take the slot"
    assert dead.killed_reason == "prewarm_lost_race", "dead incumbent must be reaped"


def test_pool_never_holds_an_unreferenced_live_process(monkeypatch):
    """Whatever the race outcome, exactly one process may survive per key."""
    key = "agentX:tab789:rolefp"
    incumbent = FakeWarm()
    made = []

    def fake_ctor(*args, **kwargs):
        wp = FakeWarm(on_send_turn=lambda: wcp._WARM_POOL.__setitem__(key, incumbent))
        made.append(wp)
        return wp

    monkeypatch.setattr(wcp, "WarmClaudeProcess", fake_ctor)
    wcp.prewarm(key, "agentX", Path("."))

    survivors = [p for p in (incumbent, *made) if p.is_alive()]
    assert len(survivors) == 1, f"{len(survivors)} live processes for one key"
    assert survivors[0] is wcp._WARM_POOL.get(key)


# ── kill() hardening ────────────────────────────────────────────────────────

@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group semantics")
def test_kill_reaps_the_child_and_does_not_hang():
    """kill() must terminate AND wait(), so no zombie and no unbounded block.

    Pre-fix, kill() closed stdin first. Closing a buffered pipe flushes it, and
    a write into a full pipe whose reader stopped blocks forever (pipe(7),
    CPython #66629) — proc.kill() on the next line would never run. Since a
    block is not an exception, the bare `except Exception` could not save it.
    """
    child = subprocess.Popen(
        [sys.executable, "-c", "import time\nwhile True: time.sleep(1)"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, start_new_session=True,
    )
    holder = wcp.WarmClaudeProcess.__new__(wcp.WarmClaudeProcess)
    holder.proc = child

    done = threading.Event()

    def run_kill():
        wcp.WarmClaudeProcess.kill(holder, reason="test", grace=5.0)
        done.set()

    t = threading.Thread(target=run_kill, daemon=True)
    t.start()
    assert done.wait(timeout=20), "kill() hung — it must never block unbounded"

    assert child.poll() is not None, "child still alive after kill()"
    # poll() returning an int (not None) proves it was reaped, not a zombie.
    assert isinstance(child.returncode, int)


def test_process_is_reapable_after_construction():
    """busy=True was set in __init__ and cleared only in send_turn's finally.
    _reap_idle skips busy entries unconditionally — including its own dead
    check — so anything that never took a turn was immortal in the pool."""
    src = Path(wcp.__file__).read_text(encoding="utf-8")
    ctor_tail = src[src.index("self._stderr_thread.start()"):]
    assert "self.busy = False" in ctor_tail[:800], (
        "__init__ must clear busy once spawn completes, or the idle reaper "
        "can never collect a process that never took a turn"
    )
