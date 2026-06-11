"""Repo ↔ empire-harness canonical drift test (auto-written by harness_sync).

DATA-DRIVEN: gates EVERY LOCKSTEP block pinned in harness.lock — tool_discipline,
untrusted_content, and any future block — against every entry-point file that EXISTS
(1 for a product, 5 for an agent). Adding a block to harness.lock auto-extends the gate;
no test edit needed. Path-agnostic (reads the vendored canonical paths from the lock, so it
works whether blocks live in .harness/ or brain/_canonical/).
"""
from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KNOWN = ["CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md", "AGENTS.md", "OPENCODE.md"]
LOCK = ROOT / "harness.lock"
_FILE_RE = re.compile(r"LOCKSTEP_([A-Za-z0-9_]+)\.md$")


def _norm(text: str) -> str:
    """Normalize line endings — the lock hash + canonical are LF; a CRLF checkout (git
    autocrlf on Windows / a fresh clone) must NOT break the gate. EOL-insensitive."""
    return text.replace("\r\n", "\n")


def _lf_sha(path: Path) -> str:
    return hashlib.sha256(_norm(path.read_text(encoding="utf-8")).encode("utf-8")).hexdigest()


def _pinned():
    """{block_name: (vendored_path, lock_hash)} for every LOCKSTEP_*.md pinned in harness.lock."""
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    out = {}
    for rel, h in lock.get("files", {}).items():
        m = _FILE_RE.search(rel.replace("\\", "/"))
        if m:
            out[m.group(1)] = (ROOT / rel, h)
    return out


def _present():
    return [n for n in KNOWN if (ROOT / n).is_file()]


class TestHarnessCanonical(unittest.TestCase):
    def test_lock_pins_a_block(self):
        self.assertTrue(LOCK.is_file(), "harness.lock missing — repo hasn't pinned empire-harness")
        self.assertTrue(_pinned(), "harness.lock pins no LOCKSTEP block")

    def test_vendored_blocks_match_lock(self):
        for name, (path, h) in _pinned().items():
            self.assertTrue(path.is_file(), f"vendored {name} block missing at {path}")
            self.assertEqual(_lf_sha(path), h,
                             f"vendored {name} block edited — re-run harness_sync, don't hand-edit")

    def test_entry_points_match_canonical(self):
        present = _present()
        self.assertTrue(present, "no entry-point file found (need at least CLAUDE.md)")
        for name, (path, _h) in _pinned().items():
            br = re.compile(
                r"<!-- LOCKSTEP:" + re.escape(name) + r" -->.*?<!-- /LOCKSTEP:" + re.escape(name) + r" -->",
                re.DOTALL)
            cm = br.search(path.read_text(encoding="utf-8"))
            self.assertIsNotNone(cm, f"canonical {name} block malformed at {path}")
            canon = cm.group(0)
            carriers = 0
            for ep in present:
                m = br.search((ROOT / ep).read_text(encoding="utf-8"))
                if m:
                    carriers += 1
                    self.assertEqual(_norm(m.group(0)), _norm(canon), f"{ep} {name} block drifted from canonical")
            self.assertTrue(carriers, f"no entry point carries the {name} block")


if __name__ == "__main__":
    unittest.main()
