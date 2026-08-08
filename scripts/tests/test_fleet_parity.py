"""Fleet parity — the shared substrate must not drift between agent repos.

`scripts/core/refine.py` is deployed into Maven and Atlas verbatim, and
`architecture_version` is meant to be ONE number across the fleet. Both claims decay
silently: a bug fixed in one repo, a version bumped in another, and six months later
nobody knows which copy is authoritative. That is exactly how four parallel version
lines appeared in the first place (see brain/STATE.md's canonical-version comment).

This test makes the claim checkable. It skips cleanly when a sibling repo is not
present on this machine, so it is safe in CI and on a fresh clone.

Run: python -m pytest scripts/tests/test_fleet_parity.py -v
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

import pytest

BRAVO = Path(__file__).resolve().parents[2]
SIBLINGS = {
    "maven": BRAVO.parent / "CMO-Agent",
    "atlas": BRAVO.parent / "APPS" / "CFO-Agent",
}

# The ONLY lines allowed to differ: the owner field, and the docstring paragraph that
# names which agent this copy belongs to. Anything else is drift.
ALLOWED_DIFF_MARKERS = (
    '"owner":',
    "FLEET-PORTABLE.",
    "Atlas (`~/APPS/CFO-Agent`)",
    "deployed here verbatim",
)
MAX_ALLOWED_DIFF_LINES = 8


def _present(name: str) -> Path:
    p = SIBLINGS[name]
    if not (p / "scripts" / "core" / "refine.py").exists():
        pytest.skip(f"{name} not deployed on this machine ({p})")
    return p


def _version(repo: Path) -> str | None:
    state = repo / "brain" / "STATE.md"
    if not state.exists():
        return None
    m = re.search(r"^architecture_version:\s*(\S+)", state.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


@pytest.mark.parametrize("name", sorted(SIBLINGS))
def test_refine_py_differs_only_in_owner(name):
    repo = _present(name)
    base = (BRAVO / "scripts" / "core" / "refine.py").read_text(encoding="utf-8").split("\n")
    other = (repo / "scripts" / "core" / "refine.py").read_text(encoding="utf-8").split("\n")

    diff = [
        l for l in difflib.unified_diff(base, other, lineterm="", n=0)
        if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))
    ]
    unexpected = [l for l in diff if not any(m in l for m in ALLOWED_DIFF_MARKERS)]
    assert not unexpected, (
        f"{name}'s refine.py has drifted from Bravo's beyond the owner field:\n"
        + "\n".join(unexpected[:20])
        + "\n\nFix the bug in Bravo and redeploy; do not fork the sibling copy."
    )
    assert len(diff) <= MAX_ALLOWED_DIFF_LINES, f"{name}: {len(diff)} differing lines, expected <= {MAX_ALLOWED_DIFF_LINES}"


@pytest.mark.parametrize("name", sorted(SIBLINGS))
def test_owner_is_actually_the_sibling(name):
    """A copy that still says owner=bravo would mislabel that agent's refinements."""
    repo = _present(name)
    src = (repo / "scripts" / "core" / "refine.py").read_text(encoding="utf-8")
    assert f'"owner": "{name}"' in src, f"{name}'s copy does not declare owner={name!r}"


@pytest.mark.parametrize("name", sorted(SIBLINGS))
def test_architecture_version_is_one_line_fleet_wide(name):
    repo = _present(name)
    mine, theirs = _version(BRAVO), _version(repo)
    assert mine, "Bravo has no architecture_version — brain/STATE.md frontmatter"
    assert theirs, f"{name} has no architecture_version — it must carry the fleet number"
    assert mine == theirs, (
        f"version drift: Bravo={mine} but {name}={theirs}. "
        "One line, fleet-wide — bump all three or none."
    )


@pytest.mark.parametrize("name", sorted(SIBLINGS))
def test_graph_node_matches_the_skill_file(name):
    """Atlas's node was hand-injected — it has no graph builder — so pin it to the file.

    A hand-maintained graph entry is a lie waiting to happen: edit the SKILL.md triggers
    and the resolver keeps routing on the old ones. This asserts the two agree, for
    whichever sibling has both.
    """
    import json

    repo = _present(name)
    graph_path = repo / "brain" / "CAPABILITY_GRAPH.json"
    skill_path = repo / "skills" / "harness-refinement" / "SKILL.md"
    if not (graph_path.exists() and skill_path.exists()):
        pytest.skip(f"{name} lacks a graph or the skill")

    nodes = json.loads(graph_path.read_text(encoding="utf-8")).get("nodes", [])
    node = next((n for n in nodes if n.get("id") == "skill:harness-refinement"), None)
    if node is None:
        pytest.skip(f"{name}'s graph has no harness-refinement node (builder may not index it)")

    fm = re.search(r"^---\n(.*?)\n---", skill_path.read_text(encoding="utf-8"), re.S)
    assert fm, f"{name}'s SKILL.md has no frontmatter"
    body = fm.group(1)

    def field(key):
        m = re.search(rf"^{key}:\s*(.*)$", body, re.M)
        return m.group(1).strip() if m else None

    assert node.get("owner") == field("owner"), (
        f"{name}: graph owner={node.get('owner')!r} but SKILL.md says {field('owner')!r}"
    )
    file_triggers = json.loads(field("triggers"))
    assert sorted(node.get("triggers") or []) == sorted(file_triggers), (
        f"{name}: graph triggers drifted from SKILL.md — the resolver is routing on stale "
        "triggers. Re-inject the node or regenerate the graph."
    )


@pytest.mark.parametrize("name", sorted(SIBLINGS))
def test_sibling_documents_its_own_evidence_commands(name):
    """The one thing that must NOT be copied: Bravo's evidence commands.

    harness_eval.py and task_outcomes.py exist only in Bravo. A sibling skill citing
    them would document commands that cannot run there.
    """
    repo = _present(name)
    skill = repo / "skills" / "harness-refinement" / "SKILL.md"
    if not skill.exists():
        pytest.skip(f"{name} has no harness-refinement skill")
    text = skill.read_text(encoding="utf-8")
    # Negations that make a mention legitimate. Checked over a window, not a single
    # line: the sentence that disclaims the command usually wraps.
    NEGATION = re.compile(
        r"has no|have no|no `|do(es)? not exist|DO NOT EXIST|not installed|"
        r"are Bravo's|is Bravo's|those are Bravo",
        re.I,
    )
    for bravo_only in ("harness_eval.py", "task_outcomes.py"):
        if (repo / "scripts" / bravo_only).exists() or (repo / "scripts" / "core" / bravo_only).exists():
            continue  # it really does exist there; citing it is fine
        for m in re.finditer(re.escape(bravo_only), text):
            window = text[max(0, m.start() - 220): m.end() + 220]
            assert NEGATION.search(window), (
                f"{name}'s skill cites {bravo_only}, which is not installed there, "
                f"without saying so nearby:\n  ...{window[:200].strip()}..."
            )
    assert "capability_query.py resolve" in text, (
        f"{name}'s skill must document capability_query.py resolve — "
        "the one evidence command every agent has"
    )
