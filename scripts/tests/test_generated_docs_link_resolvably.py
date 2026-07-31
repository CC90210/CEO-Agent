"""Generated routing docs must link their targets, and every link must resolve.

TWO FAILURE MODES, both real, both on 2026-07-30.

1. NOT LINKING AT ALL. build_capability_graph emitted plain `## name` headings.
   The link analyzer sees only [[wikilinks]] and [markdown](links), and
   `_strip_code()` removes code spans before analysis — so a backticked path is
   invisible too. Every one of 155 skills therefore had zero inbound links from
   WHEN_TO_USE_SKILLS.md; most survived on secondary references elsewhere, and
   the two with none surfaced as orphans. Fixing the instances would have left
   the next new skill born an orphan; fixing the emitter fixes the class.

2. LINKING SOMETHING THAT CANNOT RESOLVE. Applying the same fix to the agents
   emitter immediately produced six permanently broken edges: Obsidian skips
   dot-directories, so `.claude/agents/*.md` are not notes. A link that can
   never resolve is worse than no link — it fails the graph check forever and
   teaches everyone to ignore it.

The rule these encode: link every target you CAN, never emit a link you cannot
resolve, and let a test decide which is which rather than the author's memory.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Docs whose headings name a capability and must therefore link to it.
ROUTING_DOCS = [
    ("brain/WHEN_TO_USE_SKILLS.md", "skill"),
    ("brain/WHEN_TO_USE_AGENTS.md", "agent"),
]

WIKILINK_HEADING = re.compile(r"^##\s+\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", re.MULTILINE)
ANY_H2 = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def _read(rel: str) -> str:
    return (PROJECT_ROOT / rel).read_text(encoding="utf-8")


def _is_in_vault(rel_path: str) -> bool:
    """Obsidian — and obsidian_graph_doctor, which mirrors it — skip
    dot-directories. A note under .claude/ is not a note."""
    return not any(part.startswith(".") for part in Path(rel_path).parts[:-1])


@pytest.mark.parametrize("doc,kind", ROUTING_DOCS)
def test_routing_doc_links_the_capabilities_it_lists(doc, kind):
    """Regression on the orphan class. A routing doc that only NAMES its targets
    contributes nothing to the knowledge graph, so a capability referenced
    nowhere else is invisible."""
    text = _read(doc)
    headings = ANY_H2.findall(text)
    linked = WIKILINK_HEADING.findall(text)
    assert headings, f"{doc} has no H2 entries — the emitter or this test is wrong"
    assert linked, (
        f"{doc} lists {len(headings)} {kind}s and links NONE of them. Plain and "
        f"backticked headings are invisible to the link analyzer — that is how "
        f"155 skills ended up with zero inbound links.")


@pytest.mark.parametrize("doc,kind", ROUTING_DOCS)
def test_every_emitted_wikilink_actually_resolves(doc, kind):
    """The other half. Six `.claude/agents/...` links were emitted on the first
    pass and every one was permanently broken."""
    broken = []
    for target in WIKILINK_HEADING.findall(_read(doc)):
        if not (PROJECT_ROOT / f"{target}.md").exists():
            broken.append(f"{target} (file does not exist)")
        elif not _is_in_vault(target):
            broken.append(f"{target} (outside the vault — dot-directory)")
    assert not broken, f"{doc} emits unresolvable wikilinks: {broken}"


def test_out_of_vault_capabilities_are_listed_but_not_linked():
    """The deliberate compromise, pinned so nobody 'fixes' it back into red.

    Agents under .claude/ still appear in the doc — they are real and CC needs
    to see them — they just carry no wikilink, because one would never resolve.
    """
    text = _read("brain/WHEN_TO_USE_AGENTS.md")
    headings = ANY_H2.findall(text)
    plain = [h for h in headings if not h.startswith("[[")]
    assert plain, (
        "expected the .claude/ agents to be listed as plain headings; if that "
        "changed, confirm they are not being wikilinked into broken edges")
    for name in plain:
        assert "[[" not in name and "](" not in name, name


def test_the_detector_would_catch_a_regression():
    """Guard the guard — a regex that matches nothing passes vacuously."""
    sample = "## [[skills/x/SKILL|x]]\n## plain-one\n"
    assert WIKILINK_HEADING.findall(sample) == ["skills/x/SKILL"]
    assert len(ANY_H2.findall(sample)) == 2
    assert _is_in_vault("skills/x/SKILL") is True
    assert _is_in_vault(".claude/agents/architect") is False
