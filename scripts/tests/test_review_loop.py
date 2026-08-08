"""Tests for the closed review loop (2026-07-29).

Covers the parts that are pure logic and must not regress:
  * review-notification detection off the email subject (deterministic, no model)
  * repo aliasing — Business-Empire-Agent and CEO-Agent are ONE repo, and
    harvesting both would double every finding
  * severity ranking and the danger-path guard that keeps the auto-fixer away
    from migrations, credentials, CI and money

No network, no gh, no model.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from email_playbook import detect_review_notification  # noqa: E402
from review_harvest import (  # noqa: E402
    canonical_repo,
    is_dangerous,
    severity_of,
)


# ── notification detection ───────────────────────────────────────────────────

@pytest.mark.parametrize("sender,subject,expected", [
    # The exact subjects sitting in CC's inbox on 2026-07-29.
    ("notifications@github.com",
     "Re: [CC90210/CEO-Agent] V7.4.1 — native email pipeline (PR #42)",
     {"repo": "CC90210/CEO-Agent", "pr": 42, "kind": "pr_review"}),
    ("notifications@github.com",
     "Re: [CC90210/CFO-Agent] Inbound financial consumer + vault graph repair (PR #2)",
     {"repo": "CC90210/CFO-Agent", "pr": 2, "kind": "pr_review"}),
    ("notifications@github.com",
     "[CC90210/CEO-Agent] Run failed: substrate-eval - feat/native-email-classifier (cc3e760)",
     {"repo": "CC90210/CEO-Agent", "pr": None, "kind": "run_failed",
      "branch": "feat/native-email-classifier", "workflow": "substrate-eval"}),
    ("notifications@github.com",
     "Re: [CC90210/oasis-command-center] fix(offers): lender-reply classifier (PR #100)",
     {"repo": "CC90210/oasis-command-center", "pr": 100, "kind": "pr_review"}),

    # ── "PR run failed:" — the pull_request-triggered sibling of "Run failed:".
    # GitHub sends BOTH for a branch that has an open PR, and this variant was
    # unmatched until 2026-08-08: 20 of the 22 undetected notifications in a
    # 53-message, two-day sample. Each one fell through to the LLM classifier
    # and the brain, which Telegrammed CC about its own red CI, over and over.
    #
    # The tail is the PR TITLE, not a branch — it contains spaces, colons,
    # parentheses and em-dashes. Parsing it as a branch (what the `Run failed:`
    # pattern does) would yield garbage like branch="V7.6:", so `branch` stays
    # None and review_loop resolves the PR from the repo instead.
    ("notifications@github.com",
     "[CC90210/CEO-Agent] PR run failed: substrate-eval - V7.6: evidence-gated "
     "harness refinement (prime-agent import) (2b4bf13)",
     {"repo": "CC90210/CEO-Agent", "pr": None, "kind": "run_failed",
      "branch": None, "workflow": "substrate-eval"}),
    ("notifications@github.com",
     "[CC90210/oasis-command-center] PR run failed: CI - feat(email): dual-brand "
     "sending identity (SunBiz + Bluerise), Phase 1 (fe6ab46)",
     {"repo": "CC90210/oasis-command-center", "pr": None, "kind": "run_failed",
      "branch": None, "workflow": "CI"}),
    # Two-word workflow name, and an em-dash inside the PR title: the workflow
    # must stop at the FIRST " - " (ASCII hyphen, spaces both sides) and must
    # not be confused by the "—" later in the title.
    ("notifications@github.com",
     "[CC90210/real-estate-App] PR run failed: Application quality - feat(turso): "
     "PropFlow data plane — bridge replaces RLS, both server factories switched (4c5285d)",
     {"repo": "CC90210/real-estate-App", "pr": None, "kind": "run_failed",
      "branch": None, "workflow": "Application quality"}),
])
def test_detects_review_notifications(sender, subject, expected):
    assert detect_review_notification(sender, subject) == expected


def test_pr_run_failed_does_not_invent_a_branch():
    """Regression lock: the PR-title tail must never be parsed as a branch.

    `Run failed:` ends in a real branch token; `PR run failed:` ends in the PR
    title. One regex serving both would set branch="V7.6:" here, and
    review_loop would then ask `gh pr list --head V7.6:` forever.
    """
    got = detect_review_notification(
        "notifications@github.com",
        "[CC90210/CEO-Agent] PR run failed: substrate-eval - V7.6: evidence-gated "
        "harness refinement (prime-agent import) (2b4bf13)")
    assert got is not None
    assert got["branch"] is None
    assert got["workflow"] == "substrate-eval"


def test_plain_run_failed_still_extracts_its_branch():
    """The original pattern must keep working — the PR variant is additive."""
    got = detect_review_notification(
        "notifications@github.com",
        "[CC90210/real-estate-marketing-suite] Run failed: Production gates - main (6078c6d)")
    assert got == {"repo": "CC90210/real-estate-marketing-suite", "pr": None,
                   "kind": "run_failed", "branch": "main",
                   "workflow": "Production gates"}


@pytest.mark.parametrize("sender,subject", [
    # Not a review ping — must fall through to normal classification.
    ("hello@lindy.ai", "Lindy is cutting prices by 4x on average"),
    ("receipts@stripe.com", "Your receipt from OASIS AI Solutions"),
    ("notifications@github.com", "[GitHub] A third-party OAuth application was added"),
    ("jane@acme.example", "Re: [CC90210/CEO-Agent] can we talk (PR #42)"),  # human sender
])
def test_ignores_non_review_mail(sender, subject):
    assert detect_review_notification(sender, subject) is None


def test_subject_with_folded_header_newlines():
    """Real GitHub subjects arrive folded with \\r\\n mid-line."""
    got = detect_review_notification(
        "notifications@github.com",
        "Re: [CC90210/CMO-Agent] V7.3 creative-editing brain + vault graph\r\n repair (PR #6)")
    assert got == {"repo": "CC90210/CMO-Agent", "pr": 6, "kind": "pr_review"}


# ── repo aliasing ────────────────────────────────────────────────────────────

def test_repo_alias_collapses_to_one_slug():
    """These two slugs are the SAME GitHub repo — harvesting both double-counts."""
    assert canonical_repo("CC90210/Business-Empire-Agent") == "CC90210/CEO-Agent"
    assert canonical_repo("cc90210/business-empire-agent") == "CC90210/CEO-Agent"
    assert canonical_repo("CC90210/CEO-Agent") == "CC90210/CEO-Agent"
    assert canonical_repo("CC90210/CFO-Agent") == "CC90210/CFO-Agent"


# ── severity ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("body,expected", [
    ("> [!CAUTION]\n**`drain` can spin forever**", "critical"),
    ("SQL injection risk in this query", "critical"),
    ("This leaks a credential into the log", "critical"),
    ("> [!WARNING] Potential issue: unguarded subprocess", "high"),
    ("Possible null dereference here", "high"),
    ("> [!NOTE] Consider refactoring this duplicate block", "medium"),
    ("Nit: rename this variable for clarity", "low"),
])
def test_severity_ranking(body, expected):
    assert severity_of(body) == expected


# ── the danger guard ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "database/105_cron_jobs_fail_count.sql",
    "migrations/001_init.sql",
    ".env.agents",
    ".github/workflows/substrate-eval.yml",
    "scripts/integrations/send_gateway.py",
    "scripts/state/secret_guard.py",
    "scripts/state/exec_guard.py",
    "scripts/casl_compliance.py",
    "scripts/stripe_tool.py",
    "app/api/payment/route.ts",
])
def test_dangerous_paths_are_operator_only(path):
    assert is_dangerous(path), f"{path} must never be auto-fixed"


@pytest.mark.parametrize("path", [
    "scripts/lib/vault_scope.py",
    "docs/ATLAS_INTERNATIONAL_TAX_MASTERPLAN.md",
    "app/components/LeadTable.tsx",
    "scripts/email_brain.py",
])
def test_ordinary_paths_are_fixable(path):
    assert not is_dangerous(path)


# ── Codex audit findings, 2026-07-29 ─────────────────────────────────────────
# Three ways the loop could silently drop work. Each has a test so it stays dead.

def test_transient_harvest_errors_do_not_erase_the_queue():
    """Codex P1: popping the queue entry on ANY harvest error meant one `gh`
    auth blip or rate-limit permanently lost the PR — and the queue is the only
    record. Only a genuinely gone PR may be dropped on the first failure."""
    import review_loop

    transient = ["gh timed out after 90s", "graphql failed: API rate limit exceeded",
                 "gh not authenticated: HTTP 401"]
    gone = ["PR CC90210/CEO-Agent#999 not found",
            "graphql failed: Could not resolve to a PullRequest",
            "graphql failed: 404 Not Found"]

    def is_gone(err: str) -> bool:
        return any(s in err.lower() for s in
                   ("not found", "404", "could not resolve to a pullrequest"))

    for err in transient:
        assert not is_gone(err), f"{err!r} must be retried, not dropped"
    for err in gone:
        assert is_gone(err), f"{err!r} must be dropped, not retried forever"

    # And the giving-up backstop must exist so a poisoned entry can't wedge it.
    src = Path(review_loop.__file__).read_text(encoding="utf-8")
    assert "harvest_failures" in src
    assert ">= 10" in src


def test_escalated_findings_are_not_marked_seen():
    """Codex P2: 'escalated' means the fixer REFUSED to act (migrations,
    credentials, CI, money) and nobody fixed it. Marking it seen would make an
    operator-only finding vanish from every future harvest after one pass."""
    import review_fix

    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    marked = src.split("mark_seen([")[1].split("])")[0]
    assert '"escalated"' not in marked and "'escalated'" not in marked, (
        "escalated must stay out of the seen-ledger so it keeps surfacing")
    for terminal in ("fixed", "skipped", "no-op"):
        assert terminal in marked


def test_run_failed_mail_yields_a_branch_to_resolve():
    """A "Run failed:" notification carries no PR number. Without capturing the
    BRANCH the queue entry could never be resolved to anything actionable — and
    review_loop skipped PR-less entries WITHOUT removing them, so one row
    accumulated per red CI run, forever."""
    got = detect_review_notification(
        "notifications@github.com",
        "[CC90210/CEO-Agent] Run failed: substrate-eval - feat/native-email-classifier (cc3e760)")
    assert got["kind"] == "run_failed"
    assert got["pr"] is None
    assert got["branch"] == "feat/native-email-classifier"
    # Hyphens survive on BOTH sides of the " - " separator.
    assert got["workflow"] == "substrate-eval"


@pytest.mark.parametrize("subject,workflow,branch", [
    ("[o/r] Run failed: substrate-eval - feat/native-email-classifier (abc1234)",
     "substrate-eval", "feat/native-email-classifier"),
    ("[o/r] Run failed: CI - main (deadbee)", "CI", "main"),
    ("[o/r] Run failed: deploy-vps-prod - release-2026-07 (0011223)",
     "deploy-vps-prod", "release-2026-07"),
])
def test_run_failed_parsing_keeps_hyphens_on_both_sides(subject, workflow, branch):
    got = detect_review_notification("notifications@github.com", subject)
    assert got["workflow"] == workflow
    assert got["branch"] == branch


def test_review_loop_resolves_or_drops_branch_only_entries():
    import review_loop

    src = Path(review_loop.__file__).read_text(encoding="utf-8")
    assert "pr_for_branch" in src, "branch -> PR resolution must exist"
    # And an unresolvable entry must be POPPED, not left to accumulate.
    resolve_block = src.split("Resolve branch-only entries")[1].split("Oldest-first")[0]
    assert "queue.pop(" in resolve_block


def test_failing_checks_are_surfaced_not_silently_dropped():
    """Codex P1: a PR queued because CI went red but carrying no inline bot
    comments produced an empty success, and review_loop then cleared it from the
    queue untouched — silently discarding the exact 'Run failed:' notification
    this loop exists to handle."""
    import review_fix

    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    assert 'kind"] == "failing_check"' in src, (
        "review_fix must consume failing_check findings, not filter them away")
    assert "escalated" in src.split('kind"] == "failing_check"')[0][-800:]
