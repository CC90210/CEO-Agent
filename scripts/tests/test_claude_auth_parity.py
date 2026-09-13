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


# ---------------------------------------------------------------------------
# Claude Spillover (fixture v3, 2026-09-12; scripts/spillover/CONTRACT.md §13).
# Two new lists ride in the same fixture: `lane_env_strip` (env vars no child
# claude may inherit, because they route it into the local spillover proxy or
# a model lane) and the narrow, verb-anchored `subscription_limit_signals`.
# Same rule as above: every port loads them and this file proves the ports
# agree, including when the fixture cannot be read and the inline copies take
# over. A lane var the fallback forgets is a routing leak on a partial deploy.

LANE_VARS: list[str] = FIXTURE["lane_env_strip"]
SUB_MATCH: list[str] = FIXTURE["subscription_limit_must_match"]
SUB_NOT_MATCH: list[str] = FIXTURE["subscription_limit_must_not_match"]

# Every lane var inherited, one in the mixed case a Windows parent can hand
# down, plus what must survive.
LANE_BASE = {
    **{name: "inherited" for name in LANE_VARS},
    "Anthropic_Base_Url": "http://127.0.0.1:20131",
    "ANTHROPIC_API_KEY": "test-api-key-not-real",
    "PATH": "/usr/bin",
    "UNRELATED": "kept",
}
# A deliberate extra survives: the strip runs BEFORE extras are applied.
LANE_EXTRAS = {"ANTHROPIC_CUSTOM_HEADERS": "X-Bravo-Lane: automation", "CI": "true"}
LANE_EXPECTED = {"PATH": "/usr/bin", "UNRELATED": "kept", "CI": "true",
                 "ANTHROPIC_CUSTOM_HEADERS": "X-Bravo-Lane: automation"}

_NODE_LANE_DRIVER = (
    "const m = require(process.argv[1]);"
    "const c = JSON.parse(process.argv[2]);"
    "console.log(JSON.stringify({"
    " env: m.buildClaudeSpawnEnv({ base: c.base, extras: c.extras }),"
    " lane: m.LANE_ENV_VARS,"
    " limit: c.samples.map((s) => m.isSubscriptionLimit(s)),"
    "}));"
)


def _node_lane_run(module_path: Path) -> subprocess.CompletedProcess:
    payload = {"base": LANE_BASE, "extras": LANE_EXTRAS, "samples": SUB_MATCH + SUB_NOT_MATCH}
    return subprocess.run(
        ["node", "-e", _NODE_LANE_DRIVER, str(module_path), json.dumps(payload)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, cwd=str(REPO),
    )


def _py_ports():
    """(label, module) for each Python port of build_claude_spawn_env."""
    from lib import claude_auth as scripts_port

    sys.path.insert(0, str(REPO))
    from bravo_cli import _claude_auth as cli_port  # type: ignore

    return [("scripts/lib/claude_auth.py", scripts_port), ("bravo_cli/_claude_auth.py", cli_port)]


def test_every_python_port_loads_the_full_lane_list():
    for label, port in _py_ports():
        assert set(port.LANE_ENV_VARS) == set(LANE_VARS), f"{label} lane list != fixture"


@pytest.mark.parametrize("force_api_key", [False, True])
def test_python_ports_strip_the_lane_vars_before_extras(force_api_key):
    base_before = dict(LANE_BASE)
    expected = dict(LANE_EXPECTED)
    if force_api_key:
        expected["ANTHROPIC_API_KEY"] = LANE_BASE["ANTHROPIC_API_KEY"]
    for label, port in _py_ports():
        env = port.build_claude_spawn_env(force_api_key=force_api_key, base=LANE_BASE,
                                          extras=LANE_EXTRAS)
        assert env == expected, (
            f"{label} let an inherited lane var through (or dropped a deliberate "
            f"extra): {sorted(set(env) ^ set(expected))}")
        assert LANE_BASE == base_before, f"{label} mutated the caller's base env"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_node_port_strips_exactly_what_python_strips():
    from lib.claude_auth import build_claude_spawn_env, is_subscription_limit

    proc = _node_lane_run(REPO / "scripts" / "c_suite_context.js")
    assert proc.returncode == 0, f"node driver failed: {proc.stderr[-800:]}"
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert got["env"] == build_claude_spawn_env(base=LANE_BASE, extras=LANE_EXTRAS) == LANE_EXPECTED
    assert set(got["lane"]) == set(LANE_VARS)
    assert got["limit"] == [is_subscription_limit(s) for s in SUB_MATCH + SUB_NOT_MATCH], (
        "Node and Python disagree on what a subscription usage limit looks like")


@pytest.mark.parametrize("sample", SUB_MATCH)
def test_every_python_port_recognises_a_real_subscription_limit(sample):
    for label, port in _py_ports():
        assert port.is_subscription_limit(sample) is True, (
            f"{label} missed a real usage-limit stop: {sample!r}")


@pytest.mark.parametrize("sample", SUB_NOT_MATCH)
def test_no_python_port_mistakes_a_warning_or_transient_limit(sample):
    for label, port in _py_ports():
        assert port.is_subscription_limit(sample) is False, (
            f"{label} called {sample!r} a subscription limit — that would park every "
            "automation on fallback models for the breaker's cooldown")


def _isolated_copy(port: str, tmp_path: Path, fixture_state: str) -> Path:
    """Copy one port into a fake repo root whose fixture is missing, corrupt, or
    v2-shaped (the realistic partial deploy: new code, old config)."""
    dest = tmp_path / port
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / port, dest)
    if fixture_state != "missing":
        config = tmp_path / "config" / "claude_auth_signals.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("{ not json" if fixture_state == "corrupt"
                          else json.dumps({"version": 2, "signals": ["usage limit"]}),
                          encoding="utf-8")
    return dest


@pytest.mark.parametrize("fixture_state", ["missing", "corrupt", "v2"])
@pytest.mark.parametrize("port", ["scripts/lib/claude_auth.py", "bravo_cli/_claude_auth.py"])
def test_python_port_still_strips_when_the_fixture_is_unreadable(
        port, fixture_state, tmp_path, monkeypatch, capsys):
    import importlib.util

    # Otherwise bravo_cli borrows the real list from lib.claude_auth and its own
    # fallback never runs.
    monkeypatch.setitem(sys.modules, "lib.claude_auth", None)
    dest = _isolated_copy(port, tmp_path, fixture_state)
    spec = importlib.util.spec_from_file_location(f"_isolated_{dest.stem}_{fixture_state}", dest)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "using the inline fallback" in capsys.readouterr().err, (
        f"{port} degraded silently — a daemon on a partial deploy would never say so")
    assert module.build_claude_spawn_env(base=LANE_BASE, extras=LANE_EXTRAS) == LANE_EXPECTED, (
        f"{port}'s inline lane list is incomplete: with the fixture {fixture_state}, "
        "a lane var reaches the child")
    assert all(module.is_subscription_limit(s) for s in SUB_MATCH)
    assert not any(module.is_subscription_limit(s) for s in SUB_NOT_MATCH)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_node_port_still_strips_when_the_fixture_is_unreadable(tmp_path):
    proc = _node_lane_run(_isolated_copy("scripts/c_suite_context.js", tmp_path, "missing"))
    assert proc.returncode == 0, f"node driver failed: {proc.stderr[-800:]}"
    assert "using the inline fallback" in proc.stderr, "the Node port degraded silently"
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert got["env"] == LANE_EXPECTED, "the Node inline lane list is incomplete"
    assert got["limit"] == [True] * len(SUB_MATCH) + [False] * len(SUB_NOT_MATCH)


def test_the_loader_rereads_a_monkeypatched_signals_path(monkeypatch, tmp_path, capsys):
    """SIGNALS_PATH pointed at nothing: the lane list falls back to the full
    inline copy, and says so."""
    from lib import claude_auth as ca

    missing = tmp_path / "gone" / "claude_auth_signals.json"
    monkeypatch.setattr(ca, "SIGNALS_PATH", missing)
    lane = ca._load_fixture_list("lane_env_strip", ca._FALLBACK_LANE_ENV_STRIP)
    assert set(lane) == set(LANE_VARS)
    assert str(missing) in capsys.readouterr().err


def test_coordination_agent_fallback_strips_the_full_lane_list():
    """coordination_agent.js builds its own claude env only when
    c_suite_context.js failed to load, so its copy is the last line of defence."""
    text = (REPO / "coordination_agent.js").read_text(encoding="utf-8")
    m = re.search(r"const CLAUDE_LANE_ENV_FALLBACK = \[(.*?)\];", text, re.S)
    assert m, "CLAUDE_LANE_ENV_FALLBACK is gone from coordination_agent.js"
    assert set(re.findall(r"'([A-Z0-9_]+)'", m.group(1))) == set(LANE_VARS)
    assert re.search(r"CLAUDE_LANE_ENV_FALLBACK\.includes\(k\.toUpperCase\(\)\)", text), (
        "the fallback env no longer applies the lane list")


def test_skill_creator_eval_inline_lane_list_is_complete():
    """run_eval.py can run outside this repo, so it keeps its own copy."""
    import ast

    src = (REPO / "skills" / "skill-creator" / "scripts" / "run_eval.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "_LANE_ENV_FALLBACK" for t in node.targets):
            assert set(ast.literal_eval(node.value)) == set(LANE_VARS)
            return
    pytest.fail("run_eval.py no longer defines _LANE_ENV_FALLBACK")


def test_bridge_cold_spawn_uses_the_builder_not_a_hand_copied_env():
    """Separate from the 'suspects' test above on purpose: bridge_chat_server is
    a CALLER, not an implementation. Its cold spawn copied os.environ and popped
    only ANTHROPIC_API_KEY while the warm pool beside it used the builder, so it
    would have handed every inherited lane var to claude."""
    text = (REPO / "bravo_cli" / "bridge_chat_server.py").read_text(encoding="utf-8")
    assert not re.search(r"""env\.pop\(\s*["']ANTHROPIC_API_KEY["']""", text), (
        "bridge_chat_server hand-builds a claude env again; use _build_claude_spawn_env")
    assert "_build_claude_spawn_env(force_api_key=False)" in text
    assert text.count("build_claude_spawn_env as _build_claude_spawn_env") == 2, (
        "both import branches (package and script) must bind the builder")
