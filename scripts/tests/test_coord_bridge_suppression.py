"""The coordination bridge's loop-prevention rules, tested permanently.

WHY THIS FILE EXISTS
--------------------
`coordination_agent.js` decides whether a peer's row deserves an automated
reply. Three suppressors keep that from becoming a ping-pong between two agents
that never sleep:

  * `Re:` rows are the peer ACKNOWLEDGING us — replying to an acknowledgement
    IS the loop
  * `[FINAL]` closes a thread and beats even `blocked` — a wrap-up must not read
    as a new question
  * a chain-depth cap stops two agents talking past each other while both stay
    under the hourly rate cap, which is a loop that looks polite

All three are CONTRACT terms: APEX implements the same rules on its side, so a
change here silently desynchronises the two harnesses.

They were verified once, in a throwaway script, which was then deleted — so the
only enforcement of a contract both agents depend on was a transcript. This is
the permanent version, following the same pattern as
test_notify_agent_routing.py: a Python test that drives the real JS, because
this repo has no JS runner and a second implementation in Python would be the
duplicate-definition class again.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE = REPO_ROOT / "coordination_agent.js"

# (row, should_get_an_automated_reply, why)
CASES = [
    # --- real APEX traffic that was wrongly SILENT before the widening ---
    ({"status": "done", "task": "HANDOVER PR #341 - v3 loop closed"}, True,
     "a substantive handover deserves an answer"),
    ({"status": "done", "task": "HARNESS ALIGNMENT handoff - full estate map"}, True,
     "a handoff deserves an answer"),
    ({"status": "done", "task": "Merged PR #350 into main"}, True,
     "a completion worth acknowledging"),
    ({"status": "blocked", "task": "ACTION BRAVO: your tie-break rule is unsound"}, True,
     "blocked always answers"),

    # --- the ping-pong shape: never reply to an acknowledgement ---
    ({"status": "working", "task": "Re: Review of oasis-command-center#311"}, False,
     "Re: is the peer acking us; replying is the loop"),
    ({"status": "done", "task": "Re: ACTION APEX - recheck IMPLEMENTED"}, False,
     "Re: even on a substantive done"),

    # --- the terminal marker, which must beat everything ---
    ({"status": "done", "task": "Contract v3 fully aligned [FINAL]"}, False,
     "[FINAL] closes the thread"),
    ({"status": "blocked", "task": "Something urgent [FINAL]"}, False,
     "[FINAL] beats blocked - a wrap-up is not a new question"),
    ({"status": "done", "task": "Everything is turnkey", "detail": "no reply needed"}, False,
     "explicit close phrase"),

    # --- awareness-only traffic stays quiet ---
    ({"status": "working", "task": "Routine progress on leadgen scraper"}, False,
     "a plain status is awareness, not a question"),
    ({"status": "done", "task": "Refactored some helpers"}, False,
     "done without substance markers stays quiet"),
]


def _eval_in_node(rows: list[dict]) -> list[bool]:
    """Run the REAL predicate out of coordination_agent.js.

    Extracts the suppressor block rather than importing the module, because the
    module connects to Telegram at load. Testing a copy would defeat the point —
    the value here is that the SHIPPED code is exercised.
    """
    src = BRIDGE.read_text(encoding="utf-8")
    start = src.index("const isReplyRow")
    end = src.index("const pollTable")
    block = src[start:end]
    script = (
        "const process={env:{}};\n"
        + block
        + "\nconst rows=" + json.dumps(rows) + ";\n"
        "console.log(JSON.stringify(rows.map(r=>isActionableRow(r))));\n"
    )
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        pytest.fail(f"node failed evaluating the bridge predicate: {r.stderr[:400]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_bridge_suppression_matrix():
    """One node call for the whole matrix — process spawns are slow on this box."""
    got = _eval_in_node([c[0] for c in CASES])
    wrong = [(c[0]["task"], c[1], g, c[2]) for c, g in zip(CASES, got) if g != c[1]]
    assert not wrong, "bridge reply logic diverged:\n" + "\n".join(
        f"  {t!r}: expected {w}, got {g} — {why}" for t, w, g, why in wrong)


def test_final_marker_beats_blocked():
    """Pinned separately because the precedence is the subtle part: [FINAL] is
    checked BEFORE status, so a wrap-up cannot be re-opened by carrying an
    urgent-sounding status."""
    got = _eval_in_node([
        {"status": "blocked", "task": "urgent thing"},
        {"status": "blocked", "task": "urgent thing [FINAL]"},
    ])
    assert got == [True, False]


def test_suppressors_are_checked_before_the_trigger():
    """A loop is worse than a miss: a missed row costs one late reply, a loop
    costs both agents' credits and floods the operators' only visibility
    surface. So the suppressors must run FIRST — asserted on the shipped source,
    because ordering is not observable from behaviour alone once both paths
    agree."""
    src = BRIDGE.read_text(encoding="utf-8")
    fn = src[src.index("const isActionableRow"):src.index("const pollTable")]
    i_final = fn.index("isFinalRow(row)")
    i_reply = fn.index("isReplyRow(row)")
    i_blocked = fn.index("row.status === 'blocked'")
    assert i_final < i_blocked and i_reply < i_blocked, (
        "suppressors must precede the trigger, or [FINAL] and Re: lose to status")


def test_chain_depth_cap_exists_and_resets_on_a_human():
    """The rate caps bound HOW OFTEN; this bounds HOW DEEP. Two agents can stay
    under the hourly cap and still talk past each other indefinitely. A human
    speaking is the only thing that resets it — that is the entire point."""
    src = BRIDGE.read_text(encoding="utf-8")
    assert "CHAIN_DEPTH_CAP" in src
    assert "chainDepth += 1" in src, "depth must actually increment on an auto-reply"
    assert "resetChainDepth()" in src
    # the reset must be wired to a HUMAN speaking, not to any message
    reset_ctx = src[max(0, src.index("resetChainDepth();") - 400):src.index("resetChainDepth();")]
    assert "speaker" in reset_ctx, "depth must reset on a human speaker, not on any event"
