"""CEO-Agent ↔ empire-harness canonical drift test (Fleet V2 P3 dogfood; V3 multi-block).

CEO-Agent consumes the fleet harness. This makes "a CEO LOCKSTEP block drifted from the
empire-harness canonical" a build failure. Canonical blocks are vendored under
brain/_canonical/LOCKSTEP_<name>.md (synced from CC90210/empire-harness, pinned in
harness.lock), and every entry point's copy of each block must match byte-for-byte.

GENERALIZED (V3): checks EVERY vendored canonical block, not just tool_discipline — so a
second security block (e.g. untrusted_content) is held to the same standard automatically.
"""
from __future__ import annotations
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINTS = ["CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md", "AGENTS.md", "OPENCODE.md"]
CANON_DIR = ROOT / "brain" / "_canonical"
LOCK = ROOT / "harness.lock"


def _canonical_files():
    return sorted(CANON_DIR.glob("LOCKSTEP_*.md")) if CANON_DIR.is_dir() else []


def _block_name(p: Path) -> str:
    # LOCKSTEP_tool_discipline.md -> tool_discipline
    return p.stem.replace("LOCKSTEP_", "", 1)


def _block_re(name: str) -> re.Pattern:
    return re.compile(rf"<!-- LOCKSTEP:{re.escape(name)} -->.*?<!-- /LOCKSTEP:{re.escape(name)} -->", re.DOTALL)


class TestHarnessCanonical(unittest.TestCase):
    def test_at_least_tool_discipline_vendored(self):
        names = [_block_name(p) for p in _canonical_files()]
        self.assertIn("tool_discipline", names, "tool_discipline canonical missing from brain/_canonical/")

    def test_harness_lock_pins_every_canonical(self):
        self.assertTrue(LOCK.is_file(), "harness.lock missing — repo hasn't pinned empire-harness")
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        for cf in _canonical_files():
            rel = str(cf.relative_to(ROOT)).replace("\\", "/")
            self.assertIn(rel, lock.get("files", {}), f"harness.lock does not pin {rel}")
            actual = hashlib.sha256(cf.read_bytes()).hexdigest()
            self.assertEqual(actual, lock["files"][rel],
                             f"{rel} vendored block was edited — re-sync from empire-harness, don't hand-edit")

    def test_entry_points_match_every_canonical(self):
        for cf in _canonical_files():
            name = _block_name(cf)
            rx = _block_re(name)
            m = rx.search(cf.read_text(encoding="utf-8"))
            self.assertIsNotNone(m, f"vendored {cf.name} is malformed (no LOCKSTEP:{name} block)")
            canon = m.group(0)
            for ep in ENTRY_POINTS:
                em = rx.search((ROOT / ep).read_text(encoding="utf-8"))
                self.assertIsNotNone(em, f"{ep} missing the LOCKSTEP:{name} block")
                self.assertEqual(em.group(0), canon,
                                 f"{ep} LOCKSTEP:{name} block drifted from the empire-harness canonical")


if __name__ == "__main__":
    unittest.main()
