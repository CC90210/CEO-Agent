"""Tests for scripts/core/error_knowledge_pipeline.py."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core import error_knowledge_pipeline as ekp


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    logs_dir = state / "logs"
    logs_dir.mkdir()
    monkeypatch.setattr(ekp, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ekp, "STATE_DIR", state)
    monkeypatch.setattr(ekp, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(ekp, "MISTAKES_PATH", tmp_path / "memory" / "MISTAKES.md")
    monkeypatch.setattr(ekp, "DEFAULT_LOG_FILES", [state / "exec_guard.log"])
    return tmp_path


def _recent_ts(minutes_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


# ── Parsing ────────────────────────────────────────────────────────────

def test_parse_logs_groups_by_module_and_error_type(sandbox):
    _write_jsonl(sandbox / "state" / "exec_guard.log", [
        {"level": "ERROR", "module": "send_gateway", "error_type": "SMTPAuthError",
         "message": "auth failed", "timestamp": _recent_ts(10)},
        {"level": "ERROR", "module": "send_gateway", "error_type": "SMTPAuthError",
         "message": "auth failed again", "timestamp": _recent_ts(5)},
        {"level": "ERROR", "module": "n8n_inbound", "error_type": "Timeout",
         "timestamp": _recent_ts(2)},
    ])
    groups = ekp.parse_logs()
    by_key = {g.key: g for g in groups}
    assert "send_gateway::SMTPAuthError" in by_key
    assert by_key["send_gateway::SMTPAuthError"].count == 2
    assert "n8n_inbound::Timeout" in by_key


def test_non_error_events_are_ignored(sandbox):
    _write_jsonl(sandbox / "state" / "exec_guard.log", [
        {"level": "INFO", "module": "x", "message": "ok"},
        {"level": "DEBUG", "module": "x", "message": "trace"},
    ])
    groups = ekp.parse_logs()
    assert len(groups) == 0


def test_malformed_lines_are_skipped(sandbox):
    log = sandbox / "state" / "exec_guard.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        '{"level":"ERROR","module":"x","error_type":"E"}\n'
        'this is not json\n'
        '{"level":"ERROR","module":"y","error_type":"F"}\n',
        encoding="utf-8",
    )
    groups = ekp.parse_logs()
    assert len(groups) == 2


# ── Threshold filtering ────────────────────────────────────────────────

def test_filter_recurring_respects_threshold(sandbox):
    base_ts = _recent_ts(1)
    _write_jsonl(sandbox / "state" / "exec_guard.log", [
        {"level": "ERROR", "module": "mod", "error_type": "Quiet", "timestamp": base_ts},
        {"level": "ERROR", "module": "mod", "error_type": "Quiet", "timestamp": base_ts},
        # 5 occurrences of "Noisy" — above threshold (>3)
        *[{"level": "ERROR", "module": "mod", "error_type": "Noisy",
           "message": "f", "timestamp": base_ts} for _ in range(5)],
    ])
    groups = ekp.parse_logs()
    recurring = ekp.filter_recurring(groups, threshold=3)
    keys = {g.key for g in recurring}
    assert "mod::Noisy" in keys
    assert "mod::Quiet" not in keys


def test_filter_recurring_respects_window(sandbox):
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    _write_jsonl(sandbox / "state" / "exec_guard.log", [
        # 10 errors but 48h old → excluded by 24h window
        *[{"level": "ERROR", "module": "stale", "error_type": "OldError",
           "timestamp": old_ts} for _ in range(10)],
    ])
    groups = ekp.parse_logs()
    recurring = ekp.filter_recurring(groups, threshold=3, window_hours=24)
    assert "stale::OldError" not in {g.key for g in recurring}


# ── Dedup ──────────────────────────────────────────────────────────────

def test_existing_mistake_keys_parsed(sandbox):
    mistakes = sandbox / "memory" / "MISTAKES.md"
    mistakes.parent.mkdir(parents=True, exist_ok=True)
    mistakes.write_text(
        "## [SMTPAuthError] in send_gateway — 2026-05-21\n"
        "<!-- key: send_gateway::SMTPAuthError -->\n"
        "- Root cause: rotated creds\n",
        encoding="utf-8",
    )
    keys = ekp.existing_mistake_keys()
    assert keys == {"send_gateway::SMTPAuthError"}


# ── Suggestion rendering ───────────────────────────────────────────────

def test_render_suggestion_includes_dedup_key():
    g = ekp.ErrorGroup(module="x", error_type="E", count=5,
                       first_seen="2026-05-21T00:00:00Z",
                       last_seen="2026-05-21T12:00:00Z",
                       sample_message="failed")
    out = ekp.render_suggestion(g)
    assert "<!-- key: x::E -->" in out
    assert "5 occurrences" in out
    assert "[PROBATIONARY]" in out


# ── CLI ────────────────────────────────────────────────────────────────

def test_suggest_skips_known_keys(sandbox, capsys):
    base_ts = _recent_ts(1)
    _write_jsonl(sandbox / "state" / "exec_guard.log", [
        *[{"level": "ERROR", "module": "send_gateway", "error_type": "SMTPAuthError",
           "timestamp": base_ts} for _ in range(5)],
    ])
    mistakes = sandbox / "memory" / "MISTAKES.md"
    mistakes.parent.mkdir(parents=True, exist_ok=True)
    mistakes.write_text("<!-- key: send_gateway::SMTPAuthError -->\n", encoding="utf-8")

    rc = ekp.main(["suggest"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no new patterns" in out


def test_apply_writes_to_mistakes_md(sandbox, capsys):
    base_ts = _recent_ts(1)
    _write_jsonl(sandbox / "state" / "exec_guard.log", [
        *[{"level": "ERROR", "module": "x", "error_type": "Boom",
           "message": "kaboom", "timestamp": base_ts} for _ in range(5)],
    ])
    rc = ekp.main(["apply", "--yes"])
    assert rc == 0
    text = (sandbox / "memory" / "MISTAKES.md").read_text(encoding="utf-8")
    assert "<!-- key: x::Boom -->" in text
    assert "kaboom" in text


def test_apply_dry_run_does_not_modify(sandbox, capsys):
    base_ts = _recent_ts(1)
    _write_jsonl(sandbox / "state" / "exec_guard.log", [
        *[{"level": "ERROR", "module": "x", "error_type": "Boom",
           "timestamp": base_ts} for _ in range(5)],
    ])
    rc = ekp.main(["apply"])  # no --yes
    assert rc == 0
    assert not (sandbox / "memory" / "MISTAKES.md").exists()
