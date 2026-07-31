"""Entry-point parity + version single-sourcing test (audit Phase 5).

The six entry points (CLAUDE/GEMINI/ANTIGRAVITY/AGENTS/OPENCODE/ZCODE.md) wake
every agent — regardless of model — into the same identity, state, and mission.
This test makes drift between them a build failure:

  1. All entry points exist.
  2. The architecture version is single-sourced in brain/STATE.md
     (`architecture_version`) — so a bump is a one-line edit there, and the
     entry points stay version-agnostic (no hardcoded "Vx.y" in their H1).
  3. Each references CONTEXT.md (boot item #5 — the shared vocabulary).
  4. Every `<!-- LOCKSTEP:<name> --> ... <!-- /LOCKSTEP:<name> -->` block is
     byte-identical across all five (passes cleanly with zero blocks present;
     Phase 8 adds the first one).

Run:
  python -m pytest scripts/tests/test_entrypoint_parity.py -q
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINTS = ["CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md", "AGENTS.md", "OPENCODE.md", "ZCODE.md"]
STATE = ROOT / "brain" / "STATE.md"

LOCKSTEP_RE = re.compile(
    r"<!--\s*LOCKSTEP:([A-Za-z0-9_-]+)\s*-->(.*?)<!--\s*/LOCKSTEP:\1\s*-->",
    re.DOTALL,
)
# A version token in a heading, e.g. "V6.0", "V6.8.3", "v7" — what we forbid in H1.
VERSION_IN_HEADING = re.compile(r"\bV\d+(?:\.\d+)*\b", re.IGNORECASE)


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="replace")


class TestEntrypointParity(unittest.TestCase):

    def test_all_entry_points_exist(self):
        for name in ENTRY_POINTS:
            self.assertTrue((ROOT / name).is_file(), f"missing entry point: {name}")

    def test_architecture_version_single_sourced_in_state(self):
        self.assertTrue(STATE.is_file(), "brain/STATE.md missing")
        text = STATE.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(?m)^\s*architecture_version\s*:\s*(\S+)", text)
        self.assertIsNotNone(m, "brain/STATE.md must define `architecture_version` (single source of truth)")
        self.assertTrue(m.group(1).strip(), "architecture_version must be non-empty")

    def test_entry_points_are_version_agnostic(self):
        """No entry point may hardcode the CURRENT architecture version.

        Checks EVERY heading level, not just H1. Until 2026-07-28 this only
        looked at H1, so `## Architecture (V6.0 → V7.3.3)` drifted silently in
        all six files while brain/STATE.md said V7.4.0 — the gate passed and the
        docs lied. A stale version in a doc six runtimes boot from is worse than
        no version at all.

        Two things stay legal, because neither claims to be the current version:
          * historical citations — "V7.2.0 agency imports"
          * proper nouns — "RULE 10: V6 Coherence Gate"
        So the heading check is scoped to headings that are ABOUT the
        architecture, which is where the drift actually happens.
        """
        banned_phrases = ("current running version", "current version is")
        for name in ENTRY_POINTS:
            text = _read(name)
            for ln in text.splitlines():
                stripped = ln.lstrip()
                if not stripped.startswith("#"):
                    continue
                if "architecture" not in stripped.lower():
                    continue
                self.assertIsNone(
                    VERSION_IN_HEADING.search(stripped),
                    f"{name} architecture heading hardcodes a version ({stripped.strip()!r}) — "
                    "the version is single-sourced in brain/STATE.md",
                )
            lowered = text.lower()
            for phrase in banned_phrases:
                idx = lowered.find(phrase)
                if idx == -1:
                    continue
                window = text[idx: idx + 160]
                self.assertIsNone(
                    VERSION_IN_HEADING.search(window),
                    f"{name} states a current version inline ({window.strip()!r:.90}) — "
                    "point at brain/STATE.md `architecture_version` instead",
                )

    def test_each_references_context_md(self):
        for name in ENTRY_POINTS:
            self.assertIn("CONTEXT.md", _read(name),
                          f"{name} must reference CONTEXT.md (shared vocabulary, boot item #5)")

    def test_lockstep_blocks_byte_identical(self):
        per_file: dict[str, dict[str, str]] = {}
        for name in ENTRY_POINTS:
            per_file[name] = {m.group(1): m.group(2) for m in LOCKSTEP_RE.finditer(_read(name))}
        all_block_names = set().union(*(d.keys() for d in per_file.values())) if per_file else set()
        for block in sorted(all_block_names):
            present = {n: per_file[n].get(block) for n in ENTRY_POINTS}
            missing = [n for n, v in present.items() if v is None]
            self.assertFalse(missing, f"LOCKSTEP:{block} present in some files but missing from {missing}")
            contents = set(present.values())
            self.assertEqual(len(contents), 1,
                             f"LOCKSTEP:{block} differs across entry points — must be byte-identical")


if __name__ == "__main__":
    unittest.main(verbosity=2)
