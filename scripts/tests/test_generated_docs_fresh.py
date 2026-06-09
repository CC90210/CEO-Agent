"""Generated-docs freshness test (audit Phase 6).

The routing docs (brain/WHEN_TO_USE_SKILLS.md, brain/INDEX.md, memory/INDEX.md,
memory/MEMORY_INDEX.md) are generated from brain/CAPABILITY_GRAPH.json by
`scripts/build_capability_graph.py --emit-docs`. Hand-written maps drift; this
test makes drift a build failure — if a skill or brain/memory file is added and
the docs aren't regenerated, this fails.

Fix on failure:
  python scripts/build_capability_graph.py --emit-docs && git add -A && git commit

Run:
  python -m pytest scripts/tests/test_generated_docs_fresh.py -q
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_capability_graph as bcg  # noqa: E402


class TestGeneratedDocsFresh(unittest.TestCase):
    def test_generated_docs_match_disk(self):
        graph = bcg.build()
        rendered = bcg.render_generated_docs(graph)
        self.assertTrue(rendered, "no generated docs registered")
        for rel, expected in rendered.items():
            with self.subTest(doc=rel):
                path = ROOT / rel
                self.assertTrue(path.is_file(), f"{rel} missing — run --emit-docs")
                actual = path.read_text(encoding="utf-8")
                self.assertEqual(
                    actual, expected,
                    f"{rel} is STALE. Run: python scripts/build_capability_graph.py --emit-docs",
                )

    def test_skill_count_is_complete(self):
        graph = bcg.build()
        n = sum(1 for node in graph["nodes"] if node["kind"] == "skill")
        # Guards against silent skill-discovery regressions.
        self.assertGreaterEqual(n, 149, f"expected >=149 active skills, graph found {n}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
