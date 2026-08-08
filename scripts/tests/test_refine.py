"""Tests for scripts/core/refine.py — the evidence-gated refinement boundary.

Two things here are security/correctness boundaries and must never silently
reopen, both found by attacking the first implementation on 2026-08-08:

1. **The auto-apply allowlist.** `fnmatch`'s `*` matches `/`, so the original
   path-glob allowlist classified `memory/../CLAUDE.md` as auto-appliable — four
   characters defeated the whole fail-closed claim. Classification now runs on
   the RESOLVED path with segment-exact rules.
2. **The gate.** The delta must be a real measured value. Comparing the digest
   (which folds in the exit code) meant an edit that BROKE the evidence command
   counted as a success, and an edit that only flipped the exit code counted as
   a change.

No network, no DB writes: these exercise the pure classification and evidence
paths only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "core"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import refine  # noqa: E402


# --------------------------------------------------------------------------
# 1. the allowlist
# --------------------------------------------------------------------------
# Every spelling that must NOT reach auto-apply. Traversal entries are the
# regression cases for the 2026-08-08 hole.
HELD = [
    "memory/../CLAUDE.md",
    "memory/../PERSONAL.md",
    "memory/../brain/STATE.md",
    "memory/../scripts/state/exec_guard.py",
    "skills/x/../../CLAUDE.md",
    "MEMORY/../CLAUDE.md",
    "memory\\..\\CLAUDE.md",
    "./memory/../CLAUDE.md",
    "../CLAUDE.md",
    # '*' must not cross a slash
    "memory/sub/deep.md",
    "memory/a/b/c.md",
    "skills/foo/bar/SKILL.md",
    # ordinary operator-gated targets
    "CLAUDE.md",
    "GEMINI.md",
    "PERSONAL.md",
    "brain/STATE.md",
    "scripts/state/exec_guard.py",
    "docs/adr/INDEX.md",
    # carve-outs inside the allowlist, any casing
    "memory/SESSION_LOG.md",
    "memory/session_log.md",
    "memory/PROPOSED_CHANGES.md",
    "memory/Proposed_Changes.md",
    "skills/_archive/old/SKILL.md",
    # right directory, wrong file
    "skills/foo/README.md",
    "skills/SKILL.md",
    "memory/notes.txt",
]

AUTO = [
    "memory/PATTERNS.md",
    "memory/MISTAKES.md",
    "skills/anti-drift/SKILL.md",
    "skills/harness-refinement/SKILL.md",
]


@pytest.mark.parametrize("path", HELD)
def test_these_paths_never_auto_apply(path):
    requires_operator, why = refine.classify_target(path)
    assert requires_operator is True, f"{path} leaked into auto-apply: {why}"


@pytest.mark.parametrize("path", AUTO)
def test_allowlisted_paths_still_auto_apply(path):
    requires_operator, why = refine.classify_target(path)
    assert requires_operator is False, f"{path} was over-blocked: {why}"


def test_traversal_is_reported_as_its_resolved_target():
    """The reason must name what the path actually points at, not what it said."""
    _, why = refine.classify_target("memory/../CLAUDE.md")
    assert "CLAUDE.md" in why
    assert "memory/../" not in why


def test_a_path_outside_the_repo_is_refused():
    requires_operator, why = refine.classify_target("../../../../Windows/System32/drivers/etc/hosts")
    assert requires_operator is True
    assert "does not resolve inside the repo" in why


def test_unknown_directories_default_to_held():
    """Fail-closed: a directory nobody has thought about yet is not auto-appliable."""
    requires_operator, _ = refine.classify_target("some_new_dir/file.md")
    assert requires_operator is True


def test_star_does_not_cross_a_slash_in_the_matcher():
    assert refine._segments_match(("memory", "a.md"), ("memory", "*")) is True
    assert refine._segments_match(("memory", "sub", "a.md"), ("memory", "*")) is False


# --------------------------------------------------------------------------
# 2. the evidence runner
# --------------------------------------------------------------------------
def test_evidence_captures_exit_code_and_value():
    r = refine.run_evidence('python -c "print(7)"', None)
    assert r["exit"] == 0
    assert r["value"].strip() == "7"
    assert r["digest"]


def test_evidence_reports_a_nonzero_exit_rather_than_hiding_it():
    r = refine.run_evidence('python -c "import sys; sys.exit(3)"', None)
    assert r["exit"] == 3


def test_unparseable_command_yields_no_digest():
    r = refine.run_evidence('python -c "print(1)', None)  # unbalanced quote
    assert r["digest"] is None


def test_missing_key_is_explicit_not_silently_none():
    r = refine.run_evidence('python -c "print(\'{}\')"', "nope.not.here")
    assert r["value"] == "<key-missing>"


def test_keyed_evidence_extracts_a_dotted_path():
    r = refine.run_evidence(
        'python -c "print(\'{\\"a\\": {\\"b\\": 5}}\')"', "a.b"
    )
    assert r["value"] == "5"


def test_output_is_capped_and_flagged_rather_than_buffered_unbounded():
    """A noisy evidence command must not be able to allocate without limit."""
    big = f'python -c "print(\'x\' * {refine.GATE_READ_CAP * 3})"'
    r = refine.run_evidence(big, None)
    assert r["truncated"] is True
    assert len(r["output"]) <= refine.GATE_OUTPUT_CAP
    # the digest input is bounded too, not just the stored output
    assert len(r["value"]) <= refine.GATE_OUTPUT_CAP


def test_digest_is_stable_for_an_identical_run():
    """The volatility pre-check depends on this being true for sane commands."""
    a = refine.run_evidence('python -c "print(1)"', None)
    b = refine.run_evidence('python -c "print(1)"', None)
    assert a["digest"] == b["digest"]


def test_harness_eval_is_volatile_unkeyed_and_stable_keyed():
    """The live case the volatility pre-check exists for.

    `harness_eval --json` stamps a fresh timestamp/run_id per run, so unkeyed it
    can never prove anything; narrowed to `score` it is stable. If this ever
    flips, the pre-check's error message is pointing operators at the wrong fix.
    """
    cmd = "python scripts/harness_eval.py --json"
    raw_a = refine.run_evidence(cmd, None)
    raw_b = refine.run_evidence(cmd, None)
    assert raw_a["digest"] != raw_b["digest"], "unkeyed harness_eval became stable"

    keyed_a = refine.run_evidence(cmd, "score")
    keyed_b = refine.run_evidence(cmd, "score")
    assert keyed_a["digest"] == keyed_b["digest"], "keyed harness_eval became unstable"


# --------------------------------------------------------------------------
# 3. the gate decision
# --------------------------------------------------------------------------
def _ev(exit_code, value):
    return {"exit": exit_code, "value": value}


# (label, before, after, key, expect_rejected)
GATE_CASES = [
    # The two Codex [high]/[medium] findings, as regressions.
    ("edit BROKE an unkeyed command: 0 -> 1, output identical",
     _ev(0, ""), _ev(1, ""), None, True),
    ("only the exit code moved; the keyed value sat still",
     _ev(1, '"9/10"'), _ev(0, '"9/10"'), "score", True),
    # Genuine improvements must still pass.
    ("keyed improvement 9/10 -> 10/10",
     _ev(1, '"9/10"'), _ev(0, '"10/10"'), "score", False),
    ("keyed red->green: exit stays 1, score moves 8 -> 9",
     _ev(1, '"8/10"'), _ev(1, '"9/10"'), "score", False),
    ("unkeyed, clean run, output changed",
     _ev(0, "a"), _ev(0, "b"), None, False),
    # No measurement happened.
    ("evidence key vanished after the edit",
     _ev(0, '"9/10"'), _ev(0, "<key-missing>"), "score", True),
    ("command could not execute (127)",
     _ev(0, "x"), _ev(127, "<could not execute>"), None, True),
    ("command timed out (124)",
     _ev(0, "x"), _ev(124, "<timeout>"), None, True),
    ("124 rejects even when keyed and the value looks fine",
     _ev(0, '"1"'), _ev(124, '"2"'), "score", True),
    # The base case.
    ("nothing changed at all", _ev(0, "same"), _ev(0, "same"), None, True),
]


@pytest.mark.parametrize(
    "label,before,after,key,expect_rejected",
    GATE_CASES,
    ids=[c[0] for c in GATE_CASES],
)
def test_gate_verdict(label, before, after, key, expect_rejected):
    verdict = refine.gate_verdict(before, after, key)
    if expect_rejected:
        assert verdict is not None, f"gate ACCEPTED what it must reject: {label}"
    else:
        assert verdict is None, f"gate REJECTED a genuine improvement: {label} ({verdict})"


def test_gate_rejection_reasons_are_distinguishable():
    """An operator has to be able to tell WHY it was rejected, not just that it was."""
    broke = refine.gate_verdict(_ev(0, ""), _ev(1, ""), None)
    static = refine.gate_verdict(_ev(0, "x"), _ev(0, "x"), None)
    missing = refine.gate_verdict(_ev(0, "x"), _ev(0, "<key-missing>"), "score")
    assert "broke" in broke
    assert "no measured effect" in static
    assert "vanished" in missing
    assert len({broke, static, missing}) == 3


def test_gate_is_pure():
    """It must not mutate its inputs — apply_refinement stores them afterwards."""
    before, after = _ev(0, "a"), _ev(0, "b")
    snapshot = (dict(before), dict(after))
    refine.gate_verdict(before, after, None)
    assert (before, after) == snapshot


# --------------------------------------------------------------------------
# 4. capability metadata contract
# --------------------------------------------------------------------------
def test_capability_meta_satisfies_the_contract():
    from lib.capability_metadata import validate_capability_meta

    assert validate_capability_meta(refine.CAPABILITY_META) == []


def test_mutating_subcommands_are_hidden_from_the_chat_bridge():
    """They take a free-text shell command; inbound content is untrusted."""
    subs = refine.CAPABILITY_META["bridge"]["subcommands"]
    for name in ("propose", "apply", "revert", "cancel"):
        assert subs[name]["visible"] is False, f"{name} must not be bridge-visible"
    for name in ("list", "show", "ledger"):
        assert subs[name]["visible"] is True
