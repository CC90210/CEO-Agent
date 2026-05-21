"""Tests for scripts/lib/structured_log.py — JSON logging framework."""

from __future__ import annotations

import io
import json
import logging
import os
import re
from pathlib import Path

import pytest

from lib import structured_log
from lib.structured_log import StructuredLogger, get_logger, reset_loggers


@pytest.fixture(autouse=True)
def _reset_logger_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(structured_log, "LOG_DIR", tmp_path / "logs")
    reset_loggers()
    monkeypatch.delenv("EMPIRE_LOG_LEVEL", raising=False)
    monkeypatch.delenv("EMPIRE_LOG_FORMAT", raising=False)
    yield
    reset_loggers()


def _capture(logger: StructuredLogger) -> io.StringIO:
    """Swap the StreamHandler's stream with a StringIO so we can assert content."""
    stream = io.StringIO()
    for h in logger._logger.handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.stream = stream
    return stream


def test_json_output_format_is_valid():
    log = get_logger("t_json")
    stream = _capture(log)
    log.info("Email sent", to="user@example.com", interaction_id="abc")
    payload = json.loads(stream.getvalue().strip())
    assert payload["level"] == "INFO"
    assert payload["module"] == "t_json"
    assert payload["message"] == "Email sent"
    assert payload["context"] == {"to": "user@example.com", "interaction_id": "abc"}


def test_log_levels_filter_correctly(monkeypatch):
    monkeypatch.setenv("EMPIRE_LOG_LEVEL", "WARNING")
    reset_loggers()
    log = get_logger("t_level")
    stream = _capture(log)
    log.debug("debug-msg")
    log.info("info-msg")
    log.warn("warn-msg")
    log.error("error-msg")
    output = stream.getvalue()
    assert "debug-msg" not in output
    assert "info-msg" not in output
    assert "warn-msg" in output
    assert "error-msg" in output


def test_context_key_value_pairs_included():
    log = get_logger("t_ctx")
    stream = _capture(log)
    log.info("Op", a=1, b="two", c=True, d=None)
    payload = json.loads(stream.getvalue().strip())
    assert payload["context"]["a"] == 1
    assert payload["context"]["b"] == "two"
    assert payload["context"]["c"] is True
    assert payload["context"]["d"] is None


def test_log_rotation_triggers_when_file_grows(monkeypatch, tmp_path):
    monkeypatch.setattr(structured_log, "_MAX_BYTES", 256)
    reset_loggers()
    log = get_logger("t_rotate")
    for i in range(200):
        log.info("padding", iter=i, blob="x" * 40)
    files = sorted((tmp_path / "logs").glob("t_rotate.log*"))
    # At minimum: active log + at least one rotated (gzipped) backup
    assert any(p.suffix == ".gz" or p.name.endswith(".1") for p in files), \
        f"expected rotated backup, got {[p.name for p in files]}"


def test_console_output_switches_to_text(monkeypatch):
    monkeypatch.setenv("EMPIRE_LOG_FORMAT", "text")
    reset_loggers()
    log = get_logger("t_text")
    stream = _capture(log)
    log.info("Hello", who="world")
    line = stream.getvalue().strip()
    assert line.startswith(re.search(r"^\d{4}-\d{2}-\d{2}", line)[0])
    assert "INFO" in line
    assert "[t_text]" in line
    assert "Hello" in line
    assert "who=world" in line


def test_multiple_modules_write_to_separate_files(tmp_path):
    log_a = get_logger("module_a")
    log_b = get_logger("module_b")
    log_a.info("from-a")
    log_b.info("from-b")
    for h in log_a._logger.handlers + log_b._logger.handlers:
        h.flush()
    file_a = (tmp_path / "logs" / "module_a.log").read_text()
    file_b = (tmp_path / "logs" / "module_b.log").read_text()
    assert "from-a" in file_a and "from-a" not in file_b
    assert "from-b" in file_b and "from-b" not in file_a


def test_timestamp_is_iso_8601():
    log = get_logger("t_ts")
    stream = _capture(log)
    log.info("when")
    payload = json.loads(stream.getvalue().strip())
    # ISO-8601 UTC: YYYY-MM-DDTHH:MM:SS.sssZ
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", payload["timestamp"])


def test_error_log_includes_stack_trace():
    log = get_logger("t_exc")
    stream = _capture(log)
    try:
        raise ValueError("intentional")
    except ValueError:
        log.exception("caught", route="/api/x")
    payload = json.loads(stream.getvalue().strip())
    assert payload["level"] == "ERROR"
    assert "stack_trace" in payload
    assert "ValueError: intentional" in payload["stack_trace"]
    assert payload["context"]["route"] == "/api/x"


def test_get_logger_returns_cached_instance():
    a = get_logger("t_cache")
    b = get_logger("t_cache")
    assert a is b
