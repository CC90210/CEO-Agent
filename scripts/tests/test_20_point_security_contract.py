"""The 20-Point Vibe-Security Matrix exists on two surfaces. Keep them honest.

Codifying the matrix (2026-08-15, ADR-0016) created the same consistency hazard
that `test_antislop_matrix_sync.py` was written for, with one deliberate
difference in the remedy.

The Anti-Slop Matrix is COPIED to five surfaces because each audience needs it
inline. The Vibe-Security Matrix is REFERENCED from everywhere inside this repo
and copied to exactly one place:

  1. skills/security-protocol/SKILL.md          the single in-repo source (20 rows)
  2. prompts/20_POINT_SECURITY_AUDITOR_SYSTEM_PROMPT.md
                                                the deliberate exception — its
                                                audience (Codex, Gemini, a sibling
                                                agent auditing another repo) cannot
                                                read our source tree, so a pointer
                                                would be an empty instruction
  3. brain/EXECUTION_RULES.md § 21              the RULE and the incident — must
                                                NOT restate the rows
  4. CONTEXT.md                                 the canonical terms

So the tests below assert three different properties, not one:

  * surfaces 1 and 2 both cover all twenty subjects (coverage, not byte-identity —
    surface 2 rephrases for an audience with no access to `scripts/`)
  * surface 3 does the opposite: it must NOT carry a twenty-row table, because a
    second in-repo copy is drift with a schedule attached
  * the defense->point mapping is a true partition of 1..20, so no point can be
    silently orphaned when someone edits one table and not the other

Plus two regression guards: the seven-row Anti-Slop Matrix must still be seven
rows (this change sat next to it and must not have disturbed it), and the
portable prompt must keep telling agents never to open credential files.

Probes are scoped to each row's OWN line, never the whole document. The
document-wide version is useless and `test_antislop_matrix_sync.py` proved it:
a surface can lose an entire row while every probe still matches something
incidental elsewhere on the page.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

SKILL = REPO / "skills" / "security-protocol" / "SKILL.md"
PROMPT = REPO / "prompts" / "20_POINT_SECURITY_AUDITOR_SYSTEM_PROMPT.md"
RULES = REPO / "brain" / "EXECUTION_RULES.md"
CONTEXT = REPO / "CONTEXT.md"
SEED = REPO / "PERSONAL.md"
TEMPLATE = REPO / "prompts" / "_TEMPLATE_SYSTEM_PROMPT.md"
VIBE_SKILL = REPO / "skills" / "vibe-to-execution" / "SKILL.md"

# The two surfaces that actually RUN a security review. A matrix nothing routes
# to is a document, not a control.
SEC_AGENT = REPO / ".claude" / "agents" / "security-reviewer.md"
REVIEW_SKILL = REPO / "skills" / "code-review" / "SKILL.md"

MATRIX_HEADING = "The 20-Point Vibe-Security Matrix"
# The bare name, for surfaces that mention the matrix inline (where it is bolded
# and preceded by a lowercase "the") rather than as a heading.
MATRIX_NAME = "20-Point Vibe-Security Matrix"

# One entry per point. Each value is a set of alternatives — any ONE is enough,
# so a surface may rephrase for its audience without failing. Every probe here
# was chosen to be present on BOTH surface 1 and surface 2.
POINT_SUBJECTS: dict[int, tuple[str, ...]] = {
    1:  ("git ls-files", "committed"),
    2:  ("next_public", "frontend"),
    3:  ("row level security",),
    4:  ("permission",),
    5:  ("rate limit",),
    6:  ("concatenation",),
    7:  ("input validation",),
    8:  ("raw html",),
    9:  ("plaintext",),
    10: ("localstorage",),
    11: ("admin surface",),
    12: ("cors",),
    13: ("email verification",),
    14: ("idor", "ownership check"),
    15: ("raw request body",),
    16: ("signature",),
    17: ("stack trace",),
    18: ("dependencies",),
    19: ("breach check", "password strength"),
    20: ("file upload",),
}

ROW_RE = re.compile(r"^\|\s*(\d{1,2})\s*\|")


def _section(text: str, heading: str, stop_at_subheading: bool = True) -> str:
    """Slice from `heading` to the next heading.

    Scoping matters: both documents contain OTHER tables (the defense mapping,
    the severity rubric, the three-matrices comparison). Searching the whole
    document would let an unrelated table satisfy a row probe — the exact bug
    `test_antislop_matrix_sync.py` documents.

    `stop_at_subheading=False` is for a `##` section that legitimately owns its
    own `###` subsections — EXECUTION_RULES § 21 is one, and stopping at the
    first `###` silently truncated it to the intro paragraph, which made the
    "does not restate the matrix" assertion pass for the wrong reason.
    """
    idx = text.find(heading)
    assert idx != -1, f"heading not found: {heading!r}"
    rest = text[idx + len(heading):]
    stops = [rest.find("\n## ")]
    if stop_at_subheading:
        stops.append(rest.find("\n### "))
    end = min((p for p in stops if p != -1), default=len(rest))
    return rest[:end]


def _row_line(section: str, n: int) -> str | None:
    for line in section.splitlines():
        m = ROW_RE.match(line.strip())
        if m and int(m.group(1)) == n:
            return line.strip()
    return None


def _row_numbers(section: str) -> list[int]:
    return [int(ROW_RE.match(l.strip()).group(1))
            for l in section.splitlines() if ROW_RE.match(l.strip())]


def _row_covers(section: str, n: int, probes: tuple[str, ...]) -> bool:
    line = _row_line(section, n)
    if line is None:
        return False
    low = line.lower()
    return any(p.lower() in low for p in probes)


# ── surface 1: the skill is the single in-repo source ────────────────────────

def test_skill_carries_the_matrix():
    assert MATRIX_HEADING in SKILL.read_text(encoding="utf-8"), \
        "security-protocol/SKILL.md lost the 20-point matrix"


def test_skill_has_exactly_twenty_rows_numbered_one_to_twenty():
    section = _section(SKILL.read_text(encoding="utf-8"), MATRIX_HEADING)
    assert _row_numbers(section) == list(range(1, 21))


@pytest.mark.parametrize("n,probes", sorted(POINT_SUBJECTS.items()))
def test_skill_covers_every_point(n, probes):
    section = _section(SKILL.read_text(encoding="utf-8"), MATRIX_HEADING)
    assert _row_covers(section, n, probes), f"skill row {n} missing or gutted"


def test_skill_is_routable_for_an_audit_request():
    """The matrix is worthless if `capability_query resolve` never reaches it.
    The router scores on frontmatter, so the audit vocabulary must live there."""
    fm = SKILL.read_text(encoding="utf-8").split("---", 2)[1].lower()
    for term in ("security audit", "vulnerabilit", "idor", "rls"):
        assert term in fm, f"frontmatter missing routing term: {term}"


# ── surface 2: the portable prompt, the deliberate copy ──────────────────────

def test_prompt_exists_and_carries_all_twenty_rows():
    section = _section(PROMPT.read_text(encoding="utf-8"), "## 3. THE TWENTY POINTS")
    assert _row_numbers(section) == list(range(1, 21))


@pytest.mark.parametrize("n,probes", sorted(POINT_SUBJECTS.items()))
def test_prompt_covers_every_point(n, probes):
    """This is what a fresh Codex/Gemini context reads. A row missing here is a
    class of bug that agent will never look for."""
    section = _section(PROMPT.read_text(encoding="utf-8"), "## 3. THE TWENTY POINTS")
    assert _row_covers(section, n, probes), f"portable prompt row {n} missing or gutted"


def test_prompt_forbids_opening_credential_files():
    """The audit sends an agent hunting for secrets. Without this line the
    obvious move is to open the credential file — which `secret_guard` blocks
    and logs, and which no point actually requires."""
    text = PROMPT.read_text(encoding="utf-8").lower()
    assert "never read credential files" in text
    assert re.search(r"do not open [`'\"]?\." + "env", text), \
        "prompt must name the credential-file pattern it forbids"


def test_prompt_is_read_only_by_contract():
    text = PROMPT.read_text(encoding="utf-8")
    assert "READ-ONLY AUDIT" in text
    assert "DO NOT FIX" in text


def test_prompt_requires_an_adversarial_refutation_pass():
    """The whole reason the matrix exists is that nine bugs survived two
    self-reviews. An audit that only confirms its own findings repeats that."""
    text = PROMPT.read_text(encoding="utf-8").lower()
    assert "refute" in text
    assert "default to dropping the finding" in text


# ── surface 3: the rule must NOT restate the rows ────────────────────────────

def test_execution_rules_has_section_21():
    assert "## 21." in RULES.read_text(encoding="utf-8"), "EXECUTION_RULES lost § 21"


def test_section_21_points_at_the_single_source_instead_of_copying_it():
    """A second in-repo twenty-row table is drift with a schedule attached.
    § 21 carries the rule and the incident; the rows live in the skill."""
    section = _section(RULES.read_text(encoding="utf-8"), "## 21.",
                       stop_at_subheading=False)
    assert "skills/security-protocol" in section, \
        "§ 21 must name the skill as the single source"
    rows = _row_numbers(section)
    assert len(rows) < 20, (
        f"§ 21 appears to restate the matrix ({len(rows)} numbered rows) — "
        "reference the skill, do not copy it")


def test_section_21_keeps_the_three_matrices_distinct():
    """Merging the 7 defenses, the 20 points and the 7 anti-slop rows into one
    list is the most likely future edit, and it destroys all three."""
    section = _section(RULES.read_text(encoding="utf-8"), "## 21.",
                       stop_at_subheading=False)
    low = section.lower()
    assert "build-time" in low and "audit-time" in low
    assert "anti-slop" in low


# ── the mapping must be a true partition of 1..20 ────────────────────────────

def _mapping_points() -> list[int]:
    section = _section(SKILL.read_text(encoding="utf-8"),
                       "### Mapping to the seven Production Defenses")
    found: list[int] = []
    for line in section.splitlines():
        s = line.strip()
        if not s.startswith("|") or set(s) <= set("|- "):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower().startswith("defense"):
            continue
        found.extend(int(x) for x in re.findall(r"\b(\d{1,2})\b", cells[1])
                     if 1 <= int(x) <= 20)
    return found


def test_every_point_is_mapped_exactly_once():
    """If a point is in no defense bucket it is silently unowned; if it is in
    two, marking one defense N/A quietly drops coverage the other still claims."""
    pts = _mapping_points()
    assert sorted(pts) == list(range(1, 21)), (
        f"mapping is not a partition of 1..20: got {sorted(pts)}")


def test_the_unowned_row_is_explicit():
    """Five points genuinely map to no defense. That gap is the reason the
    matrix is a superset — it must stay stated, not quietly absorbed."""
    section = _section(SKILL.read_text(encoding="utf-8"),
                       "### Mapping to the seven Production Defenses")
    assert "no single defense" in section.lower() or "unowned" in section.lower()


# ── both build-time surfaces must point at the audit-time expansion ──────────

@pytest.mark.parametrize("path", [TEMPLATE, VIBE_SKILL], ids=["template", "vibe-to-execution"])
def test_defense_surfaces_point_at_the_matrix(path):
    """The 7 defenses live on two hand-maintained surfaces with no byte-identity
    gate between them. Both must carry the pointer or an executor reading one of
    them believes seven is the whole contract."""
    text = path.read_text(encoding="utf-8")
    assert MATRIX_NAME in text, \
        f"{path.name} does not point at the audit-time expansion"
    assert "audit-time" in text.lower(), \
        f"{path.name} names the matrix but not the build-time/audit-time split"


# ── the consumers that actually run a review must route to it ───────────────

@pytest.mark.parametrize("path", [SEC_AGENT, REVIEW_SKILL],
                         ids=["security-reviewer-agent", "code-review-skill"])
def test_review_surfaces_route_to_the_matrix(path):
    """A checklist nobody routes to is a document, not a control. Both of these
    existed before the matrix and carried their own from-memory list of 'the
    usual suspects' — which is precisely how points 5, 12, 18 and 20 get skipped
    on every review."""
    text = path.read_text(encoding="utf-8")
    assert "security-protocol" in text, \
        f"{path.name} does not route to the matrix"
    assert MATRIX_NAME in text, \
        f"{path.name} references the skill but never names the matrix"


def test_security_reviewer_requires_refutation_and_forbids_credential_reads():
    """The agent is the thing that will actually produce findings. Both lessons
    from the validation run have to live in ITS prompt, not only in the portable
    one — 24% of raw findings were refutable and one cited fabricated evidence."""
    text = SEC_AGENT.read_text(encoding="utf-8").lower()
    assert "refute" in text, "security-reviewer must run a refutation pass"
    assert "secret_guard" in text or "never open" in text, \
        "security-reviewer must be told not to open credential files"


# ── canonical vocabulary ─────────────────────────────────────────────────────

@pytest.mark.parametrize("term", [
    "20-Point Vibe-Security Matrix",
    "Build-time defense vs audit-time point",
    "Two-layer public-route gate",
    "Server-side authorization boundary",
    "Pre-parse signature verification",
    "Decorative control",
])
def test_context_defines_the_canonical_terms(term):
    assert f"**{term}**" in CONTEXT.read_text(encoding="utf-8"), \
        f"CONTEXT.md missing canonical term: {term}"


# ── regression guards ────────────────────────────────────────────────────────

def test_anti_slop_matrix_still_has_exactly_seven_rows():
    """This change was authored next to the seven-row matrix and explicitly did
    not extend it. Pinned so a future 'unify the matrices' edit fails here first,
    where the reason is written down, rather than in a byte-identity test whose
    message explains nothing."""
    body = re.search(
        r"<!--\s*LOCKSTEP:anti_patterns\s*-->(.*?)<!--\s*/LOCKSTEP:anti_patterns\s*-->",
        SEED.read_text(encoding="utf-8"), re.DOTALL)
    assert body, "PERSONAL.md lost the anti_patterns LOCKSTEP block"
    rows = re.findall(r"^\|\s*(\d+)\s*\|", body.group(1), re.MULTILINE)
    assert [int(r) for r in rows] == [1, 2, 3, 4, 5, 6, 7]


def test_the_matrix_is_not_duplicated_into_a_third_in_repo_surface():
    """Guards the single-source property itself. `prompts/` is the sanctioned
    exception; anything else with twenty numbered rows under this heading is a
    copy that will rot."""
    carriers = []
    for md in list((REPO / "brain").glob("*.md")) + list((REPO / "skills").rglob("SKILL.md")):
        text = md.read_text(encoding="utf-8", errors="ignore")
        if MATRIX_HEADING not in text:
            continue
        if len(_row_numbers(_section(text, MATRIX_HEADING))) >= 20:
            carriers.append(md.relative_to(REPO).as_posix())
    assert carriers == ["skills/security-protocol/SKILL.md"], \
        f"matrix duplicated into: {carriers}"
