"""Tests for scripts/core/evolve.py — memory → capability promotion.

The parser bug these pin is real and shipped in the first draft: it split on the
literal "[V]" anywhere in a line and captured the text AFTER it. PATTERNS.md
marks entries as `### [V] Title (date)` headings, so that yielded the trailing
date on a heading and a mid-sentence fragment on a prose line. Every candidate
it produced was garbage — a tool that runs, exits 0, and reports nonsense.

No network, no writes: promote() is exercised in dry-run only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "core"))

import evolve  # noqa: E402


# ── heading parser ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("line,marker,title", [
    ("### [V] MCP Config Audit Discipline", "V", "MCP Config Audit Discipline"),
    ("### [P] Currency Audit — Semantic Staleness (2026-07-19)", "P",
     "Currency Audit — Semantic Staleness"),
    ("## [V] Anti-Bloat — Update existing files.", "V",
     "Anti-Bloat — Update existing files."),
    ("#### [V] Zernio Posting (2026-05-02)", "V", "Zernio Posting"),
])
def test_heading_parse(line, marker, title):
    m = evolve.PATTERN_HEADING_RE.match(line.strip())
    assert m, f"failed to parse: {line}"
    assert m.group("marker") == marker
    assert m.group("title").strip() == title


@pytest.mark.parametrize("line", [
    "> `[V]` = validated 3+. `[P]` = probationary.",     # the legend, not an entry
    "Some prose that mentions [V] mid-sentence and continues.",
    "### A heading with no marker at all",
    "- [ ] a checklist item",
])
def test_non_entries_are_not_parsed_as_patterns(line):
    assert evolve.PATTERN_HEADING_RE.match(line.strip()) is None


def test_validated_only_by_default(tmp_path, monkeypatch):
    md = tmp_path / "PATTERNS.md"
    md.write_text(
        "### [V] Validated Thing (2026-01-01)\nBody of the validated thing here.\n\n"
        "### [P] Probationary Thing (2026-01-02)\nBody of the probationary thing.\n",
        encoding="utf-8")
    monkeypatch.setattr(evolve, "PATTERNS", md)

    got = evolve.validated_patterns()
    assert [p["title"] for p in got] == ["Validated Thing"]

    both = evolve.validated_patterns(include_probationary=True)
    assert {p["marker"] for p in both} == {"V", "P"}


def test_body_is_attached_to_the_title():
    """Title alone is too short to match a skill's vocabulary — the body is what
    makes the coverage score meaningful."""
    import textwrap
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        md = Path(td) / "PATTERNS.md"
        md.write_text(textwrap.dedent("""\
            ### [V] Short Title (2026-01-01)
            A body paragraph with distinctive vocabulary like supabase migration idempotency.

            ### [V] Next One (2026-01-02)
            Different body.
            """), encoding="utf-8")
        orig = evolve.PATTERNS
        try:
            evolve.PATTERNS = md
            got = evolve.validated_patterns()
        finally:
            evolve.PATTERNS = orig
    assert "supabase migration idempotency" in got[0]["text"]
    # and the body of the NEXT entry must not bleed into this one
    assert "Different body" not in got[0]["text"]


# ── tokenisation ─────────────────────────────────────────────────────────────

def test_stopwords_are_dropped():
    """Without this, generic words match half the catalogue and every pattern
    looks already-covered — a false negative that makes the tool useless."""
    tk = evolve.tokens("The agent should always check that the code is fixed")
    assert not (tk & {"the", "agent", "code", "check", "fix", "always"})


def test_short_tokens_are_dropped():
    assert all(len(t) >= evolve.MIN_TOKEN_LEN for t in evolve.tokens("a bc def ghij klmno"))


# ── coverage scoring ─────────────────────────────────────────────────────────

def test_identical_vocabulary_scores_as_covered():
    pat = evolve.tokens("supabase migration idempotency ledger dedup")
    cov = [{"kind": "skill", "name": "x", "tokens": pat}]
    score, owner = evolve.best_owner(pat, cov)
    assert score == 1.0 and owner["name"] == "x"
    assert score >= evolve.COVERED_THRESHOLD


def test_unrelated_vocabulary_is_a_candidate():
    pat = evolve.tokens("supabase migration idempotency ledger dedup")
    cov = [{"kind": "skill", "name": "y",
            "tokens": evolve.tokens("typography palette gradient responsive layout")}]
    score, _ = evolve.best_owner(pat, cov)
    assert score < evolve.COVERED_THRESHOLD


def test_no_owners_does_not_crash():
    assert evolve.best_owner(evolve.tokens("anything at all"), []) == (0.0, None)


# ── promotion ────────────────────────────────────────────────────────────────

def test_promote_is_dry_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "SKILLS_DIR", tmp_path / "skills")
    r = evolve.promote("Wire The Router Before Rewriting Personas", "skill", apply=False)
    assert r["applied"] is False
    assert not (tmp_path / "skills").exists(), "dry run must not touch disk"


def test_slug_comes_from_the_title_not_the_body():
    """text is "Title — body"; slugging the whole paragraph produced unusable
    directory names."""
    slug = evolve.slugify("MCP Config Audit Discipline — a long body paragraph "
                          "about auditing every config path for plaintext keys")
    assert slug.startswith("mcp-config-audit-discipline")
    assert "long-body" not in slug


def test_scaffold_carries_provenance_and_refuses_to_pretend_it_is_finished(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "SKILLS_DIR", tmp_path / "skills")
    r = evolve.promote("Some Validated Pattern — with a body", "skill", apply=True)
    assert r["applied"] is True
    body = (tmp_path / "skills" / r["slug"] / "SKILL.md").read_text(encoding="utf-8")
    assert "PROMOTED FROM MEMORY" in body      # provenance
    assert "TODO" in body                       # not presented as complete
    assert "triggers: []" in body               # must not claim routes it hasn't earned


def test_promote_does_not_clobber_an_existing_skill(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "SKILLS_DIR", tmp_path / "skills")
    evolve.promote("Dup Pattern", "skill", apply=True)
    again = evolve.promote("Dup Pattern", "skill", apply=True)
    assert again["applied"] is False
    assert again.get("skipped") == "already exists"


def test_scan_runs_against_the_real_repo():
    """Smoke test on live data — the shape must hold, not a specific count."""
    r = evolve.scan()
    for key in ("validated_total", "owners_scanned", "covered", "candidates"):
        assert key in r
    assert r["owners_scanned"] > 50, "should see the real skill catalogue"
    assert r["covered"] + len(r["candidates"]) == r["validated_total"]
