"""Every implementation of "did Claude stop for a reason a retry can't fix?"
must agree — with the shared fixture and with each other.

WHY THIS TEST EXISTS. On 2026-09-03 a SunBiz rep dropped a merchant application
into the OASIS Command Center and got:

    cli_failed:You've hit your session limit - resets 8pm

The extraction daemon gates its free-model fallback on this predicate. The Node
copy of the regex matched that string. The Python copy — the one the daemon
actually loads — did not. So the daemon classified a quota stop as a code bug,
never tried the free tier, and the feature was simply down until the limit
reset. Four copies of one regex, each with a comment reading "keep in lockstep",
and no test comparing them.

A comment is not an enforcement mechanism. This is.

Run: python -m pytest scripts/tests/test_claude_auth_parity.py -q
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

SIGNALS_PATH = REPO / "config" / "claude_auth_signals.json"
FIXTURE = json.loads(SIGNALS_PATH.read_text(encoding="utf-8"))
MUST_MATCH: list[str] = FIXTURE["must_match"]
MUST_NOT_MATCH: list[str] = FIXTURE["must_not_match"]

# The literal string off CC's screenshot. Called out separately so a regression
# names the actual incident rather than "case 7 failed".
INCIDENT_STRING = "You've hit your session limit - resets 8pm"


def _py_impls():
    """(label, predicate) for each Python implementation in this repo."""
    from lib.claude_auth import is_claude_auth_or_quota_failure as scripts_impl

    impls = [("scripts/lib/claude_auth.py", scripts_impl)]
    try:
        sys.path.insert(0, str(REPO))
        from bravo_cli._claude_auth import (  # type: ignore
            is_claude_auth_or_quota_failure as cli_impl,
        )

        impls.append(("bravo_cli/_claude_auth.py", cli_impl))
    except Exception as e:  # pragma: no cover - import shape differs per checkout
        pytest.fail(f"bravo_cli/_claude_auth.py is not importable, so its drift is invisible: {e}")
    return impls


@pytest.mark.parametrize("label,impl", _py_impls(), ids=lambda v: v if isinstance(v, str) else "")
@pytest.mark.parametrize("sample", MUST_MATCH)
def test_python_matches_every_quota_signal(label, impl, sample):
    assert impl(sample, 1) is True, (
        f"{label} does NOT recognise a real Claude stop message: {sample!r}. "
        "A miss here means an automation keeps retrying a capped subscription "
        "instead of taking the free tier."
    )


@pytest.mark.parametrize("label,impl", _py_impls(), ids=lambda v: v if isinstance(v, str) else "")
@pytest.mark.parametrize("sample", MUST_NOT_MATCH)
def test_python_ignores_non_quota_output(label, impl, sample):
    assert impl(sample, 1) is False, (
        f"{label} false-positives on {sample!r}. Several of these are extracted "
        "MERCHANT data (street numbers, dollar amounts) that lands in the CLI's "
        "own output — matching them would misroute an ordinary bug to the "
        "fallback path and hide it."
    )


@pytest.mark.parametrize("label,impl", _py_impls(), ids=lambda v: v if isinstance(v, str) else "")
def test_python_short_circuits_on_success(label, impl):
    assert impl("usage limit", 0) is False, (
        f"{label} reports a quota failure on exit code 0. A successful run whose "
        "OUTPUT merely quotes an auth error is not a failure."
    )


@pytest.mark.parametrize("label,impl", _py_impls(), ids=lambda v: v if isinstance(v, str) else "")
def test_the_incident_string(label, impl):
    assert impl(INCIDENT_STRING, 1) is True, (
        f"{label} regressed on the 2026-09-03 SunBiz incident string."
    )


def test_python_impls_agree_with_each_other():
    """Not just 'both pass the fixture' — identical verdicts on every sample."""
    impls = _py_impls()
    for sample in MUST_MATCH + MUST_NOT_MATCH:
        verdicts = {label: impl(sample, 1) for label, impl in impls}
        assert len(set(verdicts.values())) == 1, f"Python implementations disagree on {sample!r}: {verdicts}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_node_port_agrees_with_python():
    """Shell out to the real Node module and compare verdicts case by case."""
    from lib.claude_auth import is_claude_auth_or_quota_failure as py_impl

    driver = (
        "const m = require(process.argv[1]);"
        "const cases = JSON.parse(process.argv[2]);"
        "console.log(JSON.stringify(cases.map(c => m.isClaudeAuthOrQuotaFailure(c, 1))));"
    )
    cases = MUST_MATCH + MUST_NOT_MATCH
    proc = subprocess.run(
        ["node", "-e", driver, str(REPO / "scripts" / "c_suite_context.js"), json.dumps(cases)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, f"node driver failed: {proc.stderr[-800:]}"
    node_verdicts = json.loads(proc.stdout.strip().splitlines()[-1])
    mismatches = [
        (c, py_impl(c, 1), n) for c, n in zip(cases, node_verdicts) if py_impl(c, 1) != n
    ]
    assert not mismatches, (
        "Node and Python disagree — this is exactly the drift that took the SunBiz "
        f"application reader down: {mismatches}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_node_port_short_circuits_on_success():
    driver = (
        "const m = require(process.argv[1]);"
        "console.log(JSON.stringify(m.isClaudeAuthOrQuotaFailure('usage limit', 0)));"
    )
    proc = subprocess.run(
        ["node", "-e", driver, str(REPO / "scripts" / "c_suite_context.js")],
        capture_output=True, text=True, timeout=60, cwd=str(REPO),
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    assert proc.stdout.strip().splitlines()[-1] == "false"


def test_no_implementation_hardcodes_its_own_alternation():
    """Catch the NEXT copy-paste before it drifts.

    A file that builds this predicate from its own inline alternation instead of
    the shared fixture is how we got here. The inline last-resort lists are
    allowed (they are keyed by the marker below); a fresh hand-rolled regex is
    not.
    """
    suspects = [
        REPO / "scripts" / "lib" / "claude_auth.py",
        REPO / "bravo_cli" / "_claude_auth.py",
        REPO / "scripts" / "c_suite_context.js",
    ]
    for path in suspects:
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "claude_auth_signals.json" in text, (
            f"{path.relative_to(REPO)} no longer reads the shared signal fixture — "
            "it has been forked back into a private regex. That is the 2026-09-03 bug."
        )
        # The old month-name hack is a tell that someone patched around a
        # missing phrase locally instead of adding it to the fixture.
        assert not re.search(r"resets\.\*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", text, re.I), (
            f"{path.relative_to(REPO)} contains the month-name workaround; add the real "
            "phrase to config/claude_auth_signals.json instead."
        )


def test_sibling_repo_copy_if_checked_out():
    """CFO-Agent keeps its own port (separate repo, cannot import ours).

    If it is on this machine, it must still agree. Skipped when absent rather
    than silently passing — an unchecked copy is how drift survives.
    """
    sibling = Path(
        os.environ.get("CFO_AGENT_ROOT", str(Path.home() / "APPS" / "CFO-Agent"))
    ) / "cfo" / "claude_auth.py"
    if not sibling.exists():
        pytest.skip(f"CFO-Agent not checked out at {sibling}")
    text = sibling.read_text(encoding="utf-8", errors="replace")
    missing = [
        phrase
        for phrase in ("hit your", "session limit", "credit balance")
        if phrase.lower() not in text.lower()
    ]
    assert not missing, (
        f"{sibling} has drifted from config/claude_auth_signals.json — missing {missing}. "
        "Atlas will keep hammering a capped subscription. Sync it (it is a separate "
        "repo, so this is a manual port) or point CFO_AGENT_ROOT elsewhere."
    )
