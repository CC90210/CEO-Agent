"""CEO-Agent ↔ empire-harness canonical drift test (Fleet V2 Phase 3 — dogfood).

CEO-Agent now consumes the fleet harness. This makes "CEO's LOCKSTEP block drifted
from the empire-harness canonical" a build failure: the canonical block is vendored
at brain/_canonical/LOCKSTEP_tool_discipline.md (synced from CC90210/empire-harness,
pinned in harness.lock), and every entry point's block must match it byte-for-byte.

Upgrade path: bump empire-harness VERSION → re-vendor the block + bump harness.lock →
this test proves all five entry points are back in lockstep with the fleet.
"""
from __future__ import annotations
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINTS = ["CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md", "AGENTS.md", "OPENCODE.md"]
CANONICAL = ROOT / "brain" / "_canonical" / "LOCKSTEP_tool_discipline.md"
LOCK = ROOT / "harness.lock"
BLOCK_RE = re.compile(r"<!-- LOCKSTEP:tool_discipline -->.*?<!-- /LOCKSTEP:tool_discipline -->", re.DOTALL)


class TestHarnessCanonical(unittest.TestCase):
    def test_canonical_block_present(self):
        self.assertTrue(CANONICAL.is_file(), "vendored canonical LOCKSTEP block missing")

    def test_harness_lock_pins_canonical(self):
        self.assertTrue(LOCK.is_file(), "harness.lock missing — repo hasn't pinned empire-harness")
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        rel = "brain/_canonical/LOCKSTEP_tool_discipline.md"
        self.assertIn(rel, lock.get("files", {}))
        actual = hashlib.sha256(CANONICAL.read_bytes()).hexdigest()
        self.assertEqual(actual, lock["files"][rel],
                         "vendored canonical block was edited — re-sync from empire-harness, don't hand-edit")

    def test_entry_points_match_canonical(self):
        canon = BLOCK_RE.search(CANONICAL.read_text(encoding="utf-8")).group(0)
        for name in ENTRY_POINTS:
            m = BLOCK_RE.search((ROOT / name).read_text(encoding="utf-8"))
            self.assertIsNotNone(m, f"{name} missing the LOCKSTEP block")
            self.assertEqual(m.group(0), canon,
                             f"{name} LOCKSTEP block drifted from the empire-harness canonical")


if __name__ == "__main__":
    unittest.main()
