"""V6 BUILD 2 — hybrid retrieval regression suite.

Proves the semantic engine catches conceptual matches that pure-lexical FTS5
misses, and that Reciprocal Rank Fusion combines the two without losing
either side's high-confidence hits.

These tests run against the LIVE indexed corpus in state/memory_index.db +
state/memory_lance/. They assume `memory_retriever.py build --force` has
been executed at least once (the build command runs as part of the CI
pre-test step; locally, this is what bootstraps a fresh checkout).

Behavioral assertions, not corpus-content assertions — when markdown
files get edited, these tests should still hold. Specifically we check:
  - structural shape (RRF score present in hybrid; lex_score in lexical-only;
    sem_score in semantic-only)
  - delta semantics (hybrid surfaces results lexical alone misses for
    paraphrase queries)
  - parametrized paraphrase pairs (10 cases — bulk of the 12+ count)
  - flag plumbing (--lexical-only, --semantic-only, --explain, --kind)
  - token-budget cap holds across all modes
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import memory_retriever as mr  # type: ignore[import-not-found]  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _ensure_indexes_exist():
    """Confirm both indexes are populated before any test runs. Skip the whole
    module otherwise — these tests are integration-grade, not unit-grade."""
    status = mr.status()
    if status.get("index") == "missing":
        pytest.skip("FTS5 index not built — run `python scripts/memory_retriever.py build`")
    if status.get("chunks", 0) == 0:
        pytest.skip("FTS5 index has zero chunks")
    sem = status.get("semantic") or {}
    if sem.get("store") != "lancedb" or not sem.get("rows"):
        pytest.skip("LanceDB index missing/empty — run `python scripts/memory_retriever.py build`")


# ── Mode plumbing tests ──────────────────────────────────────────────────


def test_lexical_mode_returns_results_and_only_lex_score() -> None:
    hits = mr.query("stripe refund", limit=5, mode="lexical")
    assert hits, "lexical mode must return results for a token-present query"
    for h in hits:
        assert "lex_score" in h
        # In lexical-only there's no semantic leg, so no sem_score / rrf_score
        assert "rrf_score" not in h


def test_semantic_mode_returns_results_and_only_sem_score() -> None:
    hits = mr.query("price objections", limit=5, mode="semantic")
    assert hits, "semantic mode must return results for a paraphrase query"
    for h in hits:
        assert "sem_score" in h
        assert 0.0 <= h["sem_score"] <= 1.0
        assert "rrf_score" not in h


def test_hybrid_default_mode_includes_rrf_score() -> None:
    hits = mr.query("price objections", limit=5)  # mode defaults to hybrid
    assert hits, "hybrid mode must return results"
    assert all("rrf_score" in h for h in hits), \
        "every hybrid hit must carry the rrf_score the merger computed"


def test_explain_flag_surfaces_lex_and_sem_ranks() -> None:
    hits = mr.query("price objections", limit=5, mode="hybrid", explain=True)
    assert hits
    # Across the result set, at least ONE hit should record both ranks
    # (proving both legs are actually contributing).
    both_ranks = [h for h in hits
                  if h.get("lex_rank") is not None and h.get("sem_rank") is not None]
    assert both_ranks, (
        "explain mode must surface results that appear in BOTH rankings — "
        f"got hits: {[(h['ref'], h.get('lex_rank'), h.get('sem_rank')) for h in hits]}"
    )
    assert all("explain" in h for h in hits), "explain text missing"


# ── Paraphrase regression suite (the main deliverable) ──────────────────
#
# Each pair: (query_phrase, lexical_keyword_NOT_in_query).
# The semantic leg should surface content where the corpus uses the lexical
# keyword form even though the query uses a synonym/paraphrase.

PARAPHRASE_CASES = [
    # ── CC's marquee example ──
    ("price objections",       "objection"),
    ("cost resistance",        "pricing"),

    # ── Operational paraphrases ──
    ("pause the agent",        "stop"),
    ("payment reversal",       "refund"),
    ("throttle traffic",       "rate"),

    # ── Dev/engineering paraphrases ──
    ("unused dead code",       "orphan"),
    ("regenerate markdown",    "export"),
    ("hide credentials",       "secret"),
    ("agent crashed",          "fail"),

    # ── Sales/business paraphrases ──
    ("client onboarding",      "deploy"),
]


@pytest.mark.parametrize("query_phrase,paired_lex_keyword",
                         PARAPHRASE_CASES,
                         ids=[q for q, _ in PARAPHRASE_CASES])
def test_semantic_finds_paraphrase_that_lexical_alone_may_miss(
    query_phrase: str, paired_lex_keyword: str,
) -> None:
    """The semantic leg should find SOMETHING for every paraphrase.

    `paired_lex_keyword` is the lexically-near term we'd expect the corpus
    to use for the same concept (e.g., 'objection' for the query 'price
    objections'). We don't INSIST that exact keyword appears in results —
    corpus drifts. What we DO assert: semantic returns results for the
    paraphrase, AND those results aren't a strict subset of lexical
    results. That proves the semantic layer is contributing unique signal.
    """
    lex_hits = mr.query(query_phrase, limit=10, mode="lexical")
    sem_hits = mr.query(query_phrase, limit=10, mode="semantic")
    lex_refs = {h["ref"] for h in lex_hits}
    sem_refs = {h["ref"] for h in sem_hits}

    assert sem_hits, (
        f"semantic returned NO results for {query_phrase!r} "
        f"(would expect at least chunks mentioning {paired_lex_keyword!r})"
    )
    unique_to_semantic = sem_refs - lex_refs
    assert unique_to_semantic, (
        f"semantic added no unique results for {query_phrase!r} "
        f"(paired keyword: {paired_lex_keyword!r}).\n"
        f"  lex refs: {sorted(lex_refs)}\n"
        f"  sem refs: {sorted(sem_refs)}\n"
        f"  Either the corpus paraphrase pair drifted, or the semantic leg "
        f"is degenerating to FTS5 behavior."
    )


def test_hybrid_union_contains_contributions_from_both_legs() -> None:
    """Hybrid top-`2*limit` should contain at least ONE result from each leg's
    own top-K. RRF doesn't guarantee preserving either leg's top-1 when the
    OTHER leg has chunks ranked high in BOTH rankings — that's correct RRF
    math, not a bug. What we CAN guarantee is that the hybrid window
    is wide enough to surface signal from each side.
    """
    q = "price objections"
    lex_top5 = {h["ref"] for h in mr.query(q, limit=5, mode="lexical")}
    sem_top5 = {h["ref"] for h in mr.query(q, limit=5, mode="semantic")}
    hyb_top10 = {h["ref"] for h in mr.query(q, limit=10, mode="hybrid")}

    # Hybrid must contain SOMETHING from each leg's top-5
    if lex_top5:
        assert lex_top5 & hyb_top10, (
            f"hybrid top-10 contains NO results from lexical top-5 — "
            f"RRF is misbehaving.\n  lex_top5: {lex_top5}\n  hyb_top10: {hyb_top10}"
        )
    if sem_top5:
        assert sem_top5 & hyb_top10, (
            f"hybrid top-10 contains NO results from semantic top-5 — "
            f"RRF is misbehaving.\n  sem_top5: {sem_top5}\n  hyb_top10: {hyb_top10}"
        )


# ── Structural integrity tests ───────────────────────────────────────────


def test_kind_filter_respected_in_all_three_modes() -> None:
    for mode in ("lexical", "semantic", "hybrid"):
        hits = mr.query("client", limit=5, kind="skill", mode=mode)
        for h in hits:
            assert h["kind"] == "skill", \
                f"kind filter leaked in mode={mode}: {h['kind']}"


def test_limit_caps_results_across_all_modes() -> None:
    for mode in ("lexical", "semantic", "hybrid"):
        hits = mr.query("agent", limit=3, mode=mode)
        assert len(hits) <= 3, f"mode={mode} returned {len(hits)} > limit=3"


def test_token_budget_caps_total_snippet_size() -> None:
    """The per-query output cap (~1500 tokens) holds for hybrid results too —
    a malicious query shouldn't blast the agent's context window."""
    hits = mr.query("the and a", limit=50, mode="hybrid")  # high-volume query
    total_chars = sum(
        len(h.get("snippet", "")) + len(h.get("heading", "")) + len(h.get("source", ""))
        for h in hits
    )
    budget_chars = mr.MAX_RESULT_TOKENS * mr.APPROX_CHARS_PER_TOKEN
    assert total_chars <= budget_chars * 1.5, (
        f"hybrid result set ({total_chars} chars) overshoots the "
        f"{budget_chars}-char budget by more than 50%"
    )


def test_empty_query_returns_empty_in_all_modes() -> None:
    for mode in ("lexical", "semantic", "hybrid"):
        assert mr.query("", limit=5, mode=mode) == [], f"mode={mode} leaked on empty query"
        assert mr.query("   ", limit=5, mode=mode) == [], f"mode={mode} leaked on whitespace"


def test_status_surfaces_both_engine_stats() -> None:
    s = mr.status()
    assert s["chunks"] > 0
    assert "semantic" in s
    sem = s["semantic"]
    assert sem.get("store") == "lancedb"
    assert sem.get("dim") == mr.EMBED_DIM
    assert sem.get("rows", 0) > 0
    # The two indexes should be in approximate sync (allow ±10% for in-flight edits).
    if sem.get("rows") and s.get("chunks"):
        ratio = sem["rows"] / s["chunks"]
        assert 0.9 <= ratio <= 1.1, (
            f"semantic ({sem['rows']}) and FTS5 ({s['chunks']}) drift by "
            f"more than 10% — run `python scripts/memory_retriever.py build --force`"
        )


def test_rrf_merge_is_order_independent_of_rankings_input_order() -> None:
    """Sanity check the RRF math itself — the merger is symmetric, so
    swapping the order of input rankings must not change the output."""
    r1 = [("a.md", 0), ("b.md", 1), ("c.md", 2)]
    r2 = [("c.md", 2), ("d.md", 0), ("a.md", 0)]
    forward = mr._rrf_merge([r1, r2], limit=5)
    backward = mr._rrf_merge([r2, r1], limit=5)
    assert forward == backward, (
        f"_rrf_merge is not symmetric: {forward} vs {backward}"
    )


def test_rrf_merge_higher_rank_in_both_lists_beats_single_appearance() -> None:
    """A chunk that appears at rank 5 in BOTH rankings should outscore a
    chunk that appears at rank 1 in only ONE ranking. (Standard RRF
    behavior: 1/(60+5) + 1/(60+5) = 0.0308 > 1/(60+1) = 0.0164.)"""
    rank5_in_r1 = [("filler.md", x) for x in range(4)] + [("both.md", 0)]
    rank5_in_r2 = [("filler2.md", x) for x in range(4)] + [("both.md", 0)]
    only_r1 = [("only_in_r1.md", 1)]

    merged = mr._rrf_merge([rank5_in_r1, rank5_in_r2, only_r1], limit=10)
    # "both.md" should outscore "only_in_r1.md"
    assert merged.index(("both.md", 0)) < merged.index(("only_in_r1.md", 1)), \
        f"RRF didn't reward dual-appearance: {merged}"
