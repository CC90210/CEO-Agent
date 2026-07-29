"""The Anti-Slop Matrix exists on five surfaces. Keep them from drifting.

Codifying the matrix (2026-07-29) created a consistency hazard: the same seven
rows now appear in

  1. PERSONAL.md                        LOCKSTEP `anti_patterns`  — the seed
  2. the six runtime entry points       stamped from the seed
  3. brain/EXECUTION_RULES.md § 19      the rationale table (incident per row)
  4. docs/sop/ADON_AGENT_PROTOCOL_SOP.md  copy for EXTERNAL agents (APEX/Adon)
  5. oasis-command-center prompts-library  as output constraints (other repo)

Surfaces 1-2 are mechanically safe — genome_sync stamps them and
test_entrypoint_parity enforces byte-identity. Surfaces 3-4 are hand-maintained
in this repo and will rot the first time someone edits the seed and stops there:
the seed grows an eighth row, the SOP shipped to Adon still teaches seven, and
nothing notices.

These tests assert every in-repo surface covers all seven SUBJECTS. They check
coverage, not wording — surface 4 deliberately rephrases for an audience that
cannot read our source tree, and forcing byte-identity there would be wrong.

Surface 5 lives in another repo and cannot be imported; it is listed in the
docstring above so a future reader knows to update it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent

SEED = REPO / "PERSONAL.md"
RULES = REPO / "brain" / "EXECUTION_RULES.md"
ADON_SOP = REPO / "docs" / "sop" / "ADON_AGENT_PROTOCOL_SOP.md"
CLI_WORKFLOW = REPO / ".agents" / "workflows" / "cli-anything.md"

# One entry per row. `probe` is a set of alternatives — any ONE is enough, so a
# surface may rephrase for its audience without failing.
ROW_SUBJECTS: dict[str, tuple[str, ...]] = {
    "1-credential-claims": ("capability_probe", "probe first", "probe, never assume"),
    "2-silent-errors":     ("swallow", "silent error", "traceback"),
    "3-mock-data":         ("mock data", "live hydration", "fail closed", "hard fail"),
    "4-ui-slop":           ("ui slop", "gradient", "generic ui"),
    "5-drive-by":          ("drive-by", "surgical"),
    "6-unverified":        ("empirical", "unverified", "without running", "claim done",
                            "actual command output"),
    "7-guessing":          ("guess", "read the source", "authoritative inspection"),
}

LOCKSTEP_RE = re.compile(
    r"<!--\s*LOCKSTEP:anti_patterns\s*-->(.*?)<!--\s*/LOCKSTEP:anti_patterns\s*-->",
    re.DOTALL)


def _covers(text: str, probes: tuple[str, ...]) -> bool:
    """Whole-document substring check. Deliberately WEAK — see _row_covers."""
    low = text.lower()
    return any(p.lower() in low for p in probes)


def _matrix_region(text: str, anchor: str | None) -> str:
    """Slice to the matrix's own table before looking for row lines.

    These documents contain OTHER tables — the SOP alone has 35 table lines
    across credential rules, vault constants and coordination. Searching the
    whole document made `_row_line` return the first line that merely started
    with the right digit, from an unrelated table, so every SOP row read as
    missing. Scope first, then probe.
    """
    if not anchor:
        return text
    idx = text.find(anchor)
    if idx == -1:
        return ""
    rest = text[idx + len(anchor):]
    # Stop at the next section break so a later table cannot bleed in.
    end = min((p for p in (rest.find("\n---"), rest.find("\n## ")) if p != -1),
              default=len(rest))
    return rest[:end]


def _row_line(text: str, row_no: int, anchor: str | None = None) -> str | None:
    """The single table line for `row_no`, in either notation used here:
    `| 3 | … |` (seed, § 19, SOP) or `| **#3 …** | … |` (cli-anything subset)."""
    for line in _matrix_region(text, anchor).splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if re.match(rf"^\|\s*\*{{0,2}}#?{row_no}\b", s):
            return s
    return None


def _row_covers(text: str, row_no: int, probes: tuple[str, ...],
                anchor: str | None = None) -> bool:
    """Probe WITHIN the row's own line, not anywhere in the document.

    The document-wide version was useless and this test proved it: gutting row 3
    of the SOP still passed, because the words "hard fail" happened to survive
    elsewhere on the page. A surface can lose an entire row while every probe
    still matches something incidental. Scoping to the row line is the whole
    point — the guard has to fail when the row is gone.
    """
    line = _row_line(text, row_no, anchor)
    if line is None:
        return False
    low = line.lower()
    return any(p.lower() in low for p in probes)


# ── the seed is the source of truth ──────────────────────────────────────────

def test_seed_block_exists():
    m = LOCKSTEP_RE.search(SEED.read_text(encoding="utf-8"))
    assert m, "PERSONAL.md lost the anti_patterns LOCKSTEP block"
    assert len(m.group(1).strip()) > 500, "block present but suspiciously thin"


def test_seed_has_exactly_seven_rows():
    """A markdown table row per defect. If this count changes, every surface
    below needs the new row — which is precisely what the coverage tests catch."""
    body = LOCKSTEP_RE.search(SEED.read_text(encoding="utf-8")).group(1)
    rows = re.findall(r"^\|\s*(\d+)\s*\|", body, re.MULTILINE)
    assert [int(r) for r in rows] == [1, 2, 3, 4, 5, 6, 7], f"rows found: {rows}"


@pytest.mark.parametrize("subject,probes", ROW_SUBJECTS.items())
def test_seed_covers_every_subject(subject, probes):
    body = LOCKSTEP_RE.search(SEED.read_text(encoding="utf-8")).group(1)
    n = int(subject.split("-", 1)[0])
    assert _row_covers(body, n, probes), f"seed row {subject} missing or gutted"


# ── hand-maintained surfaces must not fall behind ────────────────────────────

@pytest.mark.parametrize("subject,probes", ROW_SUBJECTS.items())
def test_execution_rules_rationale_covers_every_subject(subject, probes):
    """§ 19 carries one real incident per row. A row added to the seed with no
    incident recorded here is a rule nobody will believe under pressure."""
    text = RULES.read_text(encoding="utf-8")
    section = text.split("## 19.", 1)
    assert len(section) == 2, "EXECUTION_RULES lost § 19"
    body = section[1].split("\n## ", 1)[0]
    n = int(subject.split("-", 1)[0])
    assert _row_covers(body, n, probes), f"EXECUTION_RULES § 19 row {subject} missing or gutted"


@pytest.mark.parametrize("subject,probes", ROW_SUBJECTS.items())
def test_adon_sop_covers_every_subject(subject, probes):
    """This is what APEX/Adon read as a system message. They cannot see our
    source tree, so a row missing here is a row that agent never learns."""
    n = int(subject.split("-", 1)[0])
    assert _row_covers(ADON_SOP.read_text(encoding="utf-8"), n, probes,
                       anchor="Anti-Slop Matrix"), \
        f"ADON SOP row {subject} missing or gutted"


def test_cli_workflow_carries_its_declared_subset():
    """cli-anything intentionally carries only the four rows that bite on a CLI
    build. Pinned so the subset is a decision, not an accident of editing."""
    text = CLI_WORKFLOW.read_text(encoding="utf-8")
    assert "Anti-Slop gates" in text
    for subject in ("1-credential-claims", "2-silent-errors", "3-mock-data", "6-unverified"):
        n = int(subject.split("-", 1)[0])
        assert _row_covers(text, n, ROW_SUBJECTS[subject], anchor="Anti-Slop gates"), \
            f"cli-anything row {subject} missing or gutted"


# ── the seed must never be edited in an expression ───────────────────────────

def test_entry_points_carry_the_block_and_point_at_the_seed():
    """genome_sync stamps these; test_entrypoint_parity proves byte-identity.
    This asserts the weaker but separate property: the marker pair exists at all,
    so a future sync cannot silently skip a chassis (a missing pair is an error
    by design, not an implicit insert)."""
    for name in ("CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md",
                 "AGENTS.md", "OPENCODE.md", "ZCODE.md"):
        text = (REPO / name).read_text(encoding="utf-8")
        assert LOCKSTEP_RE.search(text), f"{name} has no anti_patterns block"


def test_matrix_names_the_probe_and_never_tells_an_agent_to_read_the_env_file():
    """Row 1 mandates capability_probe. Instructing an agent to read the env file
    directly would send every chassis at a path secret_guard blocks and logs —
    the deviation from the V8.0 spec as written, recorded so it is not undone."""
    body = LOCKSTEP_RE.search(SEED.read_text(encoding="utf-8")).group(1)
    assert "capability_probe.py" in body
    assert re.search(r"never.{0,40}read.{0,20}`?\.env", body, re.IGNORECASE | re.DOTALL), \
        "row 1 must state explicitly that reading the env file is not the path"
