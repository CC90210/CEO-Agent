"""The age bound limits what we EDIT. It must not limit what we KNOW.

WHY THIS EXISTS
---------------
review_loop seeds its queue from open PRs, then refuses any PR not updated in
14 days. That refusal is correct and must stay: review_fix EDITS AND PUSHES to
the PR branch, and pushing to a peer's six-week-dead branch is an unwelcome
surprise, not thoroughness.

But the skip happens BEFORE the harvest, so all it produced was a count. On
2026-09-06 that count was 29, and the loop's own result line read
`remaining=6 fixed=0` — a shrinking queue that looked like progress while 29
open PRs sat entirely outside the view. Harvesting them read-only found 40
unresolved findings across 15 of them, including PR #236, titled "Security:
close two lead-data leaks", carrying seven.

So: keep the bound on auto-editing, remove the bound on knowing.
`stale_report()` harvests the skipped set WITHOUT queueing and WITHOUT calling
review_fix, so it cannot push to anything. These tests pin both halves — that it
reports, and that it stays read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import review_loop  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent


class _FakeHarvest:
    """Stands in for the review_harvest module."""

    TRACKED_REPOS = ["acme/widgets"]

    def __init__(self, prs, findings):
        self._prs = prs
        self._findings = findings
        self.harvested: list[tuple[str, int]] = []

    def open_prs_detailed(self, repo):
        return list(self._prs)

    def harvest_pr(self, repo, number):
        self.harvested.append((repo, number))
        return self._findings.get(number)


def _install(monkeypatch, fake, queue=None):
    monkeypatch.setitem(sys.modules, "review_harvest", fake)
    monkeypatch.setattr(review_loop, "load_queue", lambda: dict(queue or {}))
    saved: list = []
    monkeypatch.setattr(review_loop, "save_queue", lambda q: saved.append(q))
    return saved


FRESH = "2099-01-01T00:00:00Z"      # always inside any window
ANCIENT = "2020-01-01T00:00:00Z"    # always outside it


# ── 1. the skipped set is remembered, not merely counted ───────────────────

def test_seed_records_which_prs_it_skipped(monkeypatch):
    fake = _FakeHarvest(
        prs=[{"number": 1, "updatedAt": ANCIENT, "headRefName": "old"},
             {"number": 2, "updatedAt": ANCIENT, "headRefName": "older"}],
        findings={},
    )
    _install(monkeypatch, fake)
    stats: dict = {}
    added = review_loop.seed_from_open_prs(stats=stats)
    assert added == 0
    assert stats["skipped_stale"] == 2
    assert stats["stale_keys"] == ["acme/widgets#1", "acme/widgets#2"], (
        "a count cannot tell 29 clean PRs from 29 carrying security findings"
    )


def test_a_stale_pr_is_never_harvested_during_seeding(monkeypatch):
    """Seeding stays cheap: the skip is before the network call."""
    fake = _FakeHarvest(
        prs=[{"number": 1, "updatedAt": ANCIENT, "headRefName": "old"}],
        findings={1: {"findings": [{"kind": "review_thread"}]}},
    )
    _install(monkeypatch, fake)
    review_loop.seed_from_open_prs(stats={})
    assert fake.harvested == [], "the 15-minute loop must not pay a round trip per stale PR"


# ── 2. the out-parameter did not break the existing contract ───────────────

def test_seed_still_returns_an_int_without_stats(monkeypatch):
    """The old callers, and two existing tests, pass no stats and read an int."""
    fake = _FakeHarvest(
        prs=[{"number": 9, "updatedAt": FRESH, "headRefName": "live"}],
        findings={9: {"findings": [{"kind": "review_thread"}]}},
    )
    _install(monkeypatch, fake)
    assert review_loop.seed_from_open_prs() == 1


# ── 3. the report sees what the loop cannot ────────────────────────────────

def test_stale_report_finds_the_findings_the_window_hides(monkeypatch):
    fake = _FakeHarvest(
        prs=[
            {"number": 236, "updatedAt": ANCIENT, "headRefName": "sec"},
            {"number": 51, "updatedAt": ANCIENT, "headRefName": "bump"},
            {"number": 99, "updatedAt": ANCIENT, "headRefName": "clean"},
            {"number": 7, "updatedAt": FRESH, "headRefName": "live"},
        ],
        findings={
            236: {"title": "Security: close two lead-data leaks",
                  "findings": [{"kind": "review_thread"}] * 7},
            51: {"title": "bump js-yaml", "findings": [{"kind": "failing_check"}] * 3},
            99: {"title": "nothing wrong", "findings": []},
            7: {"title": "live one", "findings": [{"kind": "review_thread"}]},
        },
    )
    _install(monkeypatch, fake)
    rep = review_loop.stale_report()

    assert rep["stale_prs"] == 3, "the fresh PR is not stale"
    assert rep["stale_with_findings"] == 2, "the clean stale PR must not be reported"
    assert rep["findings_total"] == 10
    assert [i["key"] for i in rep["items"]] == ["acme/widgets#236", "acme/widgets#51"], (
        "worst first — the security PR must not be buried under dependency bumps"
    )
    assert rep["items"][0]["count"] == 7
    assert rep["items"][0]["kinds"] == ["review_thread"]
    assert "Security" in rep["items"][0]["title"]
    assert (
        "acme/widgets#7" not in [i["key"] for i in rep["items"]]
    ), "a PR inside the window belongs to the fixer, not to this report"


# ── 4. read-only by construction ───────────────────────────────────────────

def test_stale_report_queues_nothing(monkeypatch):
    fake = _FakeHarvest(
        prs=[{"number": 236, "updatedAt": ANCIENT, "headRefName": "sec"}],
        findings={236: {"title": "x", "findings": [{"kind": "review_thread"}]}},
    )
    saved = _install(monkeypatch, fake)
    review_loop.stale_report()
    assert saved == [], (
        "the report must never write the queue — queueing is what leads to a push"
    )


def test_stale_report_never_invokes_the_fixer():
    """The bound exists because review_fix PUSHES. Prove this path cannot.

    Parsed, not grepped. The first version of this test read the function's
    source as text and tripped on its own docstring, which names review_fix
    precisely to say it is not called — a guard failing on the sentence that
    explains the guard. The AST sees identifiers, not prose.
    """
    import ast

    src = (REPO / "scripts" / "review_loop.py").read_text(encoding="utf-8")
    fn = next(
        node for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.FunctionDef) and node.name == "stale_report"
    )
    names = {
        n.id for n in ast.walk(fn) if isinstance(n, ast.Name)
    } | {
        n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)
    } | {
        alias.name.split(".")[0]
        for n in ast.walk(fn) if isinstance(n, ast.Import)
        for alias in n.names
    }
    for forbidden in ("run_review_fix", "review_fix", "save_queue", "subprocess", "push"):
        assert forbidden not in names, (
            f"stale_report must not reference {forbidden!r} — it reports, it does not act"
        )
    # ...and it must actually harvest, or it is a report of nothing.
    assert "harvest_pr" in names


def test_the_loop_surfaces_the_skipped_count_in_its_json():
    """last_result said `remaining=6` while 29 PRs sat outside the window."""
    src = (REPO / "scripts" / "review_loop.py").read_text(encoding="utf-8")
    assert '"stale_skipped": seed_stats.get("skipped_stale", 0),' in src, (
        "a shrinking queue looks like progress unless the dropped count rides with it"
    )
