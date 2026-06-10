"""Routing-accuracy gate (V7) — the capability-vs-regression graduation pattern.

Two tiers, per Anthropic's agent-eval guidance + the golden-test pattern:

  • GOLDEN (regression, HARD gate): intents the lexical router MUST resolve correctly today.
    Fails CI if routing degrades — e.g. a future auto-generated `gws-*` CLI-ref leaks back in
    and outranks a real skill (the exact V6.8 pollution bug). This is the protection layer.

  • CAPABILITY FLOOR (soft): the evals/routing_nl hard natural-phrasing cases. Tracked as a
    floor (must not drop BELOW the current lexical pass count) rather than demanded at 100% —
    closing the remaining ones is the semantic-router improvement target (EMPIRE_ROUTER_SEMANTIC).

Pure, offline, deterministic (lexical default — no LanceDB dependency). Runs in the harness
pytest CI; gate on changes to skills/, brain/AGENT_ROUTER.md, brain/CAPABILITY_GRAPH.json.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from capability_query import Graph  # noqa: E402

# intent → required top-1 skill (the lexical default must satisfy every row)
GOLDEN = {
    "send an outreach email": "outreach-send",
    "send a cold email to a new lead": "outreach-send",
    "send a follow-up email": "outreach-send",
    "review the code before shipping": "code-review",
    "generate a CEO briefing": "ceo-briefing",
    "score a new lead": "score-b2b-lead-quality",
    "score this lead": "score-b2b-lead-quality",
}
CAPABILITY_FLOOR = 2  # current evals/routing_nl lexical pass count — must not regress below


def _top(g: Graph, intent: str):
    r = g.resolve_intent(intent, kind="skill", limit=1)
    return r[0]["name"] if r else None


class TestRoutingAccuracy(unittest.TestCase):
    def setUp(self):
        self.g = Graph.load()

    def test_golden_routing_regression(self):
        """Routing must not degrade on the golden intents (catches gws-*-pollution-style regressions)."""
        fails = [f"{intent!r} → {_top(self.g, intent)} (want {want})"
                 for intent, want in GOLDEN.items() if _top(self.g, intent) != want]
        self.assertFalse(fails, "routing regressed on golden intents:\n  " + "\n  ".join(fails))

    def test_capability_floor_holds(self):
        """The routing_nl hard-case pass count must not drop below the known floor."""
        nl = ROOT / "evals" / "routing_nl"
        if not nl.is_dir():
            self.skipTest("evals/routing_nl absent")
        passes = total = 0
        for cd in sorted(nl.iterdir()):
            ej, tm = cd / "expected.json", cd / "task.md"
            if not (ej.exists() and tm.exists()):
                continue
            total += 1
            want = json.loads(ej.read_text(encoding="utf-8")).get("expected")
            intent = tm.read_text(encoding="utf-8").strip()
            if _top(self.g, intent) == want:
                passes += 1
        self.assertGreaterEqual(
            passes, CAPABILITY_FLOOR,
            f"routing_nl capability regressed: {passes}/{total} passing < floor {CAPABILITY_FLOOR}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
