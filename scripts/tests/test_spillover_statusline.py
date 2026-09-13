"""Tests for scripts/spillover/statusline.py (CONTRACT.md section 12).

Claude Code pipes a statusLine JSON payload to stdin on every refresh, so the
two hard requirements are: this must never raise (a bad payload can only make
the line shorter/blanker, never crash the status bar) and it must stay fast
(well under the refresh budget). Most cases drive render()/read_state()
directly for state-shape coverage; a handful of real subprocess runs cover
the stdin-garbage and exit-code contract end to end.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STATUSLINE = REPO_ROOT / "scripts" / "spillover" / "statusline.py"
PYTHON = sys.executable

# The REAL install (never touched by this suite - see the isolation guard below).
_REAL_LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
_REAL_BRAVO_SPILLOVER_HOME = _REAL_LOCALAPPDATA / "bravo-spillover"
# Only the subpaths this feature's own tools ever write to (CONTRACT.md
# section 2). NEVER walk the whole HOME_DIR - omniroute-src/ and
# omniroute-npm/ are a full git checkout + a built Next.js app + node_modules
# (hundreds of thousands of files, another agent's live build in this same
# session); an unscoped recursive walk over the whole tree hung for minutes
# in test_spillover_ensure.py before this was scoped down, and would have
# raced that build for no reason - statusline.py only ever READS
# state/state.json, never writes anything at all.
_WATCHED_SUBPATHS = ("secrets", "state", "bin", "app", "config.json")


def _snapshot(root: Path):
    if not root.exists():
        return None
    paths: list[str] = []
    for name in _WATCHED_SUBPATHS:
        sub = root / name
        if sub.is_file():
            paths.append(name)
        elif sub.is_dir():
            paths.extend(str(p.relative_to(root)) for p in sub.rglob("*"))
    return sorted(paths)


@pytest.fixture(autouse=True)
def _isolated_spillover_home(tmp_path, monkeypatch):
    """home_dir() resolves HOME_DIR at CALL time from BRAVO_SPILLOVER_HOME
    (verified by reading statusline.py). This makes every test in this file
    set both BRAVO_SPILLOVER_HOME and LOCALAPPDATA to a fresh tmp_path before
    it runs, so a test that forgets to pass an explicit path still can't
    reach the real install."""
    home = tmp_path / "bravo-spillover"
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData-Local"))
    return home


@pytest.fixture(scope="session", autouse=True)
def _guard_real_bravo_spillover_untouched():
    """Session-wide proof the REAL %LOCALAPPDATA%/bravo-spillover is
    byte-for-byte the same (within the watched subpaths) before and after
    this file's tests run."""
    before = _snapshot(_REAL_BRAVO_SPILLOVER_HOME)
    yield
    after = _snapshot(_REAL_BRAVO_SPILLOVER_HOME)
    assert after == before, (
        f"a test touched the REAL {_REAL_BRAVO_SPILLOVER_HOME} "
        f"(before={before!r}, after={after!r})"
    )


NOW = 1_800_000_000.0  # fixed epoch so every test is deterministic


def _at(offset_seconds: float, now: float = NOW) -> float:
    return now + offset_seconds


def _load_module():
    spec = importlib.util.spec_from_file_location("statusline_probe", STATUSLINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sl():
    return _load_module()


# --------------------------------------------------------------- model name ---

def test_prefers_display_name_over_id(sl):
    line = sl.render({"model": {"display_name": "Opus 5", "id": "claude-opus-5"}}, None, NOW)
    assert line.startswith("Opus 5")


def test_falls_back_to_id_when_no_display_name(sl):
    line = sl.render({"model": {"id": "claude-sonnet-5"}}, None, NOW)
    assert line.startswith("claude-sonnet-5")


def test_defaults_to_claude_when_no_model_info_at_all(sl):
    assert sl.render({}, None, NOW) == "Claude"


def test_model_name_is_truncated_to_40_chars(sl):
    line = sl.render({"model": {"display_name": "X" * 200}}, None, NOW)
    assert line == "X" * 40


# ----------------------------------------------------------------- rate limits ---

def test_five_hour_and_seven_day_percentages_render(sl):
    payload = {
        "model": {"display_name": "Opus 5"},
        "rate_limits": {
            "five_hour": {"used_percentage": 72.4, "resets_at": _at(3600)},
            "seven_day": {"used_percentage": 41},
        },
    }
    state = {"mode": "direct", "config_mode": "spill"}
    line = sl.render(payload, state, NOW)
    assert line == "Opus 5 | 5h 72% reset " + sl._clock(_at(3600), NOW) + " | 7d 41% | direct"


def test_missing_rate_limits_omits_those_segments(sl):
    line = sl.render({"model": {"display_name": "Opus 5"}}, {"mode": "direct", "config_mode": "spill"}, NOW)
    assert line == "Opus 5 | direct"


def test_percentage_is_rounded(sl):
    payload = {"rate_limits": {"five_hour": {"used_percentage": 133.6}}}
    line = sl.render(payload, None, NOW)
    assert "5h 134%" in line


def test_percentage_over_999_is_clamped(sl):
    payload = {"rate_limits": {"five_hour": {"used_percentage": 5000}}}
    line = sl.render(payload, None, NOW)
    assert "5h 999%" in line


def test_negative_percentage_clamps_to_zero_rather_than_dropping(sl):
    payload = {"rate_limits": {"five_hour": {"used_percentage": -5}}}
    line = sl.render(payload, None, NOW)
    assert "5h 0%" in line


def test_nan_percentage_is_dropped_entirely(sl):
    payload = {"rate_limits": {"five_hour": {"used_percentage": float("nan")}}}
    line = sl.render(payload, None, NOW)
    assert "5h" not in line


def test_boolean_percentage_is_not_treated_as_a_number(sl):
    payload = {"rate_limits": {"five_hour": {"used_percentage": True}}}
    line = sl.render(payload, None, NOW)
    assert "5h" not in line


def test_non_numeric_percentage_is_dropped(sl):
    payload = {"rate_limits": {"five_hour": {"used_percentage": "not-a-number"}}}
    line = sl.render(payload, None, NOW)
    assert "5h" not in line


def test_reset_epoch_accepts_iso8601(sl):
    iso = datetime.fromtimestamp(_at(3600), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {"rate_limits": {"five_hour": {"used_percentage": 10, "resets_at": iso}}}
    line = sl.render(payload, None, NOW)
    assert "reset " in line


def test_reset_epoch_accepts_milliseconds(sl):
    payload = {"rate_limits": {"five_hour": {"used_percentage": 10, "resets_at": _at(3600) * 1000}}}
    line = sl.render(payload, None, NOW)
    assert "reset " in line


def test_reset_in_the_past_is_not_shown(sl):
    payload = {"rate_limits": {"five_hour": {"used_percentage": 10, "resets_at": NOW - 3600}}}
    line = sl.render(payload, None, NOW)
    assert "reset" not in line


# ---------------------------------------------------------------------- state ---

def test_no_state_file_shows_no_proxy_suffix(sl):
    assert sl.render({"model": {"display_name": "Opus 5"}}, None, NOW) == "Opus 5"


def test_unreadable_state_shows_proxy_unknown(sl):
    assert sl.render({"model": {"display_name": "Opus 5"}}, {}, NOW) == "Opus 5 | proxy ?"


@pytest.mark.parametrize("cfg,expected", [
    ("passthrough", "passthrough"),
    ("observe", "direct (observe)"),
    ("spill", "direct"),
    (None, "direct"),
    ("bogus-future-mode", "direct"),
])
def test_config_mode_suffix(sl, cfg, expected):
    state = {"mode": "direct", "config_mode": cfg}
    line = sl.render({"model": {"display_name": "Opus 5"}}, state, NOW)
    assert line == f"Opus 5 | {expected}"


def test_spilling_with_healthy_fallback_and_future_reset(sl):
    state = {"mode": "spilling", "limit": {"reset_at": _at(1800)}, "fallback": {"healthy": True}}
    line = sl.render({}, state, NOW)
    assert line == f"FALLBACK (GPT) until {sl._clock(_at(1800), NOW)}"


def test_spilling_with_down_fallback(sl):
    state = {"mode": "spilling", "limit": {"reset_at": _at(1800)}, "fallback": {"healthy": False}}
    line = sl.render({}, state, NOW)
    assert line == f"limit hit - fallback DOWN until {sl._clock(_at(1800), NOW)}"


def test_spilling_with_no_fallback_key_defaults_to_up(sl):
    state = {"mode": "spilling", "limit": {"reset_at": _at(1800)}}
    line = sl.render({}, state, NOW)
    assert line == f"FALLBACK (GPT) until {sl._clock(_at(1800), NOW)}"


def test_spilling_with_no_reset_at_all(sl):
    state = {"mode": "spilling", "fallback": {"healthy": True}}
    assert sl.render({}, state, NOW) == "FALLBACK (GPT)"


def test_spilling_but_reset_already_passed_falls_through_to_normal_line(sl):
    """Once reset <= now this must not keep showing a stale FALLBACK line even
    if the state file has not yet caught up to mode=direct."""
    state = {"mode": "spilling", "limit": {"reset_at": NOW - 10}, "fallback": {"healthy": True},
             "config_mode": "spill"}
    line = sl.render({"model": {"display_name": "Opus 5"}}, state, NOW)
    assert line == "Opus 5 | direct"


def test_limit_reset_as_iso_string(sl):
    iso = datetime.fromtimestamp(_at(1800), tz=timezone.utc).isoformat()
    state = {"mode": "spilling", "limit": {"reset_at": iso}}
    assert sl.render({}, state, NOW).startswith("FALLBACK (GPT) until ")


def test_malformed_limit_that_is_not_a_dict_is_tolerated(sl):
    state = {"mode": "spilling", "limit": "not-a-dict"}
    assert sl.render({}, state, NOW) == "FALLBACK (GPT)"


def test_malformed_fallback_that_is_not_a_dict_is_tolerated(sl):
    state = {"mode": "spilling", "fallback": "nope"}
    assert sl.render({}, state, NOW) == "FALLBACK (GPT)"


def test_mode_missing_entirely_is_treated_as_not_spilling(sl):
    state = {"config_mode": "spill"}
    line = sl.render({"model": {"display_name": "Opus 5"}}, state, NOW)
    assert line == "Opus 5 | direct"


# --------------------------------------------------------------- read_state() ---

def test_read_state_missing_file_returns_none(sl, tmp_path):
    assert sl.read_state(str(tmp_path / "nope.json")) is None


def test_read_state_malformed_json_returns_empty_dict(sl, tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{not json", encoding="utf-8")
    assert sl.read_state(str(p)) == {}


def test_read_state_non_dict_json_returns_empty_dict(sl, tmp_path):
    p = tmp_path / "state.json"
    p.write_text("[1,2,3]", encoding="utf-8")
    assert sl.read_state(str(p)) == {}


def test_read_state_valid_json_round_trips(sl, tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"mode": "direct"}), encoding="utf-8")
    assert sl.read_state(str(p)) == {"mode": "direct"}


def test_read_state_respects_home_dir_env(sl, tmp_path, monkeypatch):
    home = tmp_path / "bravo-spillover"
    (home / "state").mkdir(parents=True)
    (home / "state" / "state.json").write_text(json.dumps({"mode": "direct"}), encoding="utf-8")
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))
    assert sl.home_dir() == str(home)
    assert sl.read_state() == {"mode": "direct"}


# ------------------------------------------------------------- garbage stdin ---

def _run_statusline(stdin_bytes: bytes, home: Path, timeout: int = 10) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["BRAVO_SPILLOVER_HOME"] = str(home)
    return subprocess.run([PYTHON, "-S", str(STATUSLINE)], input=stdin_bytes,
                          env=env, capture_output=True, timeout=timeout)


def test_empty_stdin_exits_0_with_a_line(tmp_path):
    r = _run_statusline(b"", home=tmp_path / "nope")
    assert r.returncode == 0
    assert r.stdout.decode("ascii").strip() == "Claude"
    assert r.stderr == b""


def test_garbage_bytes_stdin_never_raises(tmp_path):
    r = _run_statusline(b"\xff\xfe\x00garbage{{{not json at all", home=tmp_path / "nope")
    assert r.returncode == 0
    assert r.stdout.decode("ascii").strip() == "Claude"
    assert r.stderr == b""


def test_json_array_stdin_is_tolerated(tmp_path):
    r = _run_statusline(b"[1,2,3]", home=tmp_path / "nope")
    assert r.returncode == 0
    assert r.stdout.decode("ascii").strip() == "Claude"


def test_json_scalar_stdin_is_tolerated(tmp_path):
    r = _run_statusline(b'"just a string"', home=tmp_path / "nope")
    assert r.returncode == 0
    assert r.stdout.decode("ascii").strip() == "Claude"


def test_deeply_wrong_types_never_raise(tmp_path):
    payload = json.dumps({"model": 12345, "rate_limits": "nope"}).encode("utf-8")
    r = _run_statusline(payload, home=tmp_path / "nope")
    assert r.returncode == 0
    assert r.stdout.decode("ascii").strip() == "Claude"
    assert r.stderr == b""


def test_output_is_pure_ascii_even_with_unicode_model_name(tmp_path):
    payload = json.dumps({"model": {"display_name": "Claude 5 — Opus"}}).encode("utf-8")
    r = _run_statusline(payload, home=tmp_path / "nope")
    assert r.returncode == 0
    r.stdout.decode("ascii")  # raises if not pure ASCII


def test_real_state_file_end_to_end(tmp_path):
    home = tmp_path / "bravo-spillover"
    (home / "state").mkdir(parents=True)
    (home / "state" / "state.json").write_text(
        json.dumps({"mode": "direct", "config_mode": "spill"}), encoding="utf-8")
    payload = json.dumps({"model": {"display_name": "Opus 5"}}).encode("utf-8")
    r = _run_statusline(payload, home=home)
    assert r.returncode == 0
    assert r.stdout.decode("ascii").strip() == "Opus 5 | direct"


def test_oversized_stdin_does_not_hang_or_crash(tmp_path):
    """MAX_INPUT_BYTES caps the read; feed a couple KB of noise (not the full
    1MB, to keep this test's process cheap) and confirm it still exits clean."""
    payload = b'{"model":{"display_name":"' + b"A" * 4000 + b'"}}'
    r = _run_statusline(payload, home=tmp_path / "nope")
    assert r.returncode == 0
    assert r.stdout.strip()


# ------------------------------------------------------------------- timing ---

def test_render_and_read_state_are_fast(sl, tmp_path):
    """Under 80ms (CONTRACT: statusline must stay well under Claude Code's
    refresh budget). Measured IN-PROCESS to isolate the primitive from
    interpreter startup, which dominates any subprocess timing and would
    measure Python's boot time instead of this script's own logic."""
    home = tmp_path / "bravo-spillover"
    (home / "state").mkdir(parents=True)
    state_path = home / "state" / "state.json"
    state_path.write_text(json.dumps({"mode": "direct", "config_mode": "spill"}), encoding="utf-8")
    payload = {"model": {"display_name": "Opus 5"},
               "rate_limits": {"five_hour": {"used_percentage": 50, "resets_at": _at(100)},
                               "seven_day": {"used_percentage": 10}}}
    start = time.perf_counter()
    for _ in range(50):
        state = sl.read_state(str(state_path))
        sl.render(payload, state, time.time())
    elapsed = time.perf_counter() - start
    per_call = elapsed / 50
    assert per_call < 0.08, f"average render+read_state took {per_call * 1000:.2f}ms (budget 80ms)"


def test_subprocess_end_to_end_does_not_hang(tmp_path):
    """A loose ceiling on the WHOLE process including interpreter startup —
    not the 80ms budget (that's the in-process test above), just a guard
    against something pathological (e.g. an accidental network/DNS call)."""
    start = time.perf_counter()
    r = _run_statusline(b"{}", home=tmp_path / "nope", timeout=5)
    elapsed = time.perf_counter() - start
    assert r.returncode == 0
    assert elapsed < 5.0, f"statusline.py subprocess took {elapsed:.2f}s"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
