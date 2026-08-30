"""capability_query.resolve_intent — the lexical skill router's scoring.

This is the function that decides which skill an intent routes to, and it is the
offline-DETERMINISTIC path the evals and CI depend on. Three scoring bugs were
found on 2026-08-28 by asking why the routing suite sat at 77.8% and routing_nl
at 33.3% (the latter documented as "deliberately red" — it was not, it was
these bugs). Fixing all three took both suites to 100%.

Each test below pins one of them with the case that exposed it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from capability_query import Graph, _stem, _stems  # noqa: E402


@pytest.fixture(scope="module")
def graph():
    return Graph.load()


def top(graph, intent: str, n: int = 1):
    return [r.get("name") for r in graph.resolve_intent(intent, kind="skill", limit=n)]


# --- bug 1: stopwords were deciding matches -----------------------------------

def test_function_words_are_not_scored():
    """On "write an implementation plan for a feature", harness-refinement
    scored 13.0 and beat writing-plans — and 12.0 of those points came from
    triggers matching "a", "an" and "for". The router was ranking skills by how
    much English grammar their triggers contained."""
    for w in ("a", "an", "the", "for", "to", "of", "with", "is", "my"):
        assert _stems(w) == set(), f"{w!r} still scores"


def test_stopword_removal_keeps_domain_words():
    """Conservative on purpose: small words that MEAN something here must stay."""
    for w in ("state", "log", "run", "job", "lead", "send", "test"):
        assert _stems(w), f"{w!r} was wrongly dropped as a stopword"


# --- bug 2: no stemming, so a skill's own name did not match ------------------

@pytest.mark.parametrize("a,b", [
    ("write", "writing"), ("plan", "plans"), ("skill", "skills"),
    ("deploy", "deployed"), ("review", "reviews"), ("test", "testing"),
    # -ies/-y needs an EXPLICIT rule. A first draft's comment claimed these
    # "fall through" to the generic suffix strip; they did not. policies
    # stemmed to "polic" while policy stemmed to "policy", so the pair never
    # matched, and the comment asserting otherwise is the exact stale-comment
    # class already logged in memory/MISTAKES.md.
    ("policy", "policies"), ("strategy", "strategies"),
    ("query", "queries"), ("copy", "copies"),
])
def test_inflections_collapse_to_one_stem(a, b):
    """`writing-plans` scored ZERO from its own name for "write ... plan",
    because {writing, plans} & {write, plan} is empty."""
    assert _stem(a) == _stem(b)


def test_the_skill_named_for_the_task_wins(graph):
    assert top(graph, "write an implementation plan for a feature") == ["writing-plans"]


# --- bug 3: trigger COUNT beat match QUALITY ----------------------------------

def test_a_fully_matched_trigger_beats_many_partial_ones(graph):
    """On "debug a failing test with a stack trace", systematic-debugging
    matched the trigger "stack trace" ENTIRELY and scored 6.0, while
    webapp-testing scored 10.0 from five triggers ("webapp test", "local app
    test", "frontend test", ...) each matching only the generic word "test".
    Trigger score is summed across all triggers, so more chances to match one
    word beat one exact phrase match. Coverage weighting fixes that."""
    assert top(graph, "debug a failing test with a stack trace", 3)[0] != "webapp-testing"


def test_coverage_weighting_is_actually_applied(graph):
    """A one-word trigger fully matched must outscore a long trigger sharing one
    generic word. Asserted through the public API rather than the formula, so a
    reimplementation still has to satisfy it."""
    res = graph.resolve_intent("stack trace", kind="skill", limit=3)
    assert res and "systematic-debugging" in [r.get("name") for r in res]


# --- the routing behaviour operators depend on --------------------------------

@pytest.mark.parametrize("intent,expected", [
    ("security protocol for credentials", "security-protocol"),
    ("send a cold outreach email to a lead", "outreach-send"),
    ("scrape a site that is behind cloudflare", "cloak-browser"),
    ("coordinate with APEX before editing a shared file", "cross-agent-coordination"),
    ("check which free tier services we can use", "resource-radar"),
])
def test_canonical_intents_route_correctly(graph, intent, expected):
    assert top(graph, intent) == [expected]


def test_resolution_is_deterministic(graph):
    """CI and the evals depend on this path being stable run to run — no
    dict-ordering or set-iteration leakage into the ranking."""
    q = "write an implementation plan for a feature"
    runs = [tuple(top(graph, q, 5)) for _ in range(5)]
    assert len(set(runs)) == 1


def test_empty_and_stopword_only_intents_return_nothing(graph):
    """"the a of" must not rank every skill that happens to contain articles —
    which, before the stopword fix, it would have."""
    assert graph.resolve_intent("", kind="skill") == []
    assert graph.resolve_intent("the a of for", kind="skill") == []
