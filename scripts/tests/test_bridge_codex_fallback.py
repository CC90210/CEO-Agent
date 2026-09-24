"""Command Center Claude -> Codex recovery contracts."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from bravo_cli import bridge_chat_server as bridge


QUOTA_ERROR = "You've hit your weekly limit; resets tomorrow"


class _FakeProcess:
    def __init__(self, *, stdout_lines: list[str] | None = None, returncode: int = 1):
        self.stdout = io.StringIO("".join(stdout_lines or []))
        self.stderr = io.StringIO(QUOTA_ERROR + "\n")
        self.pid = 12345
        self._returncode = returncode
        self.killed = False

    def wait(self, timeout=None):  # noqa: ARG002 - subprocess-compatible stub
        return self._returncode

    def poll(self):
        return self._returncode

    def kill(self):
        self.killed = True


class _FakeWarmProcess:
    def __init__(
        self,
        event: dict | None = None,
        *,
        events: list[dict] | None = None,
        ok: bool = False,
    ):
        self.proc = _FakeProcess()
        self._events = list(events or ([] if event is None else [event]))
        self._ok = ok
        self.killed = False

    def is_alive(self):
        return True

    def send_turn(self, _prompt, on_event, max_seconds):  # noqa: ARG002
        for event in self._events:
            on_event(event)
        return self._ok

    def recent_stderr(self):
        return QUOTA_ERROR

    def kill(self, reason):  # noqa: ARG002
        self.killed = True


def _handler(monkeypatch):
    handler = object.__new__(bridge._ChatHandler)
    monkeypatch.setattr(handler, "_which_cli", lambda _name: "claude")
    monkeypatch.setattr(handler, "_enriched_path", lambda _binary: "test-path")
    monkeypatch.setattr(bridge, "claude_identity_overlay", lambda *_a: ("", "project,local"))
    monkeypatch.setattr(bridge, "_warm_chat_lean_args", lambda: [])
    return handler


def _events():
    emitted: list[tuple[str, dict]] = []
    return emitted, lambda event, data: emitted.append((event, data))


@pytest.mark.parametrize(
    ("bearer", "role", "denied", "expected"),
    [
        (False, "", [], True),
        (True, "owner", [], True),
        (True, "admin", [], True),
        (True, "member", [], False),
        (True, "owner", ["Bash"], False),
    ],
)
def test_operator_trust_is_explicit_and_role_scoped(bearer, role, denied, expected):
    assert bridge._is_trusted_operator_session(
        bridge_bearer_present=bearer,
        team_role=role,
        disallowed_tools=denied,
    ) is expected


def test_warm_prework_quota_failure_uses_codex_for_trusted_operator(monkeypatch, tmp_path):
    handler = _handler(monkeypatch)
    warm = _FakeWarmProcess()
    monkeypatch.setattr(bridge, "_warm_use_or_create", lambda **_kwargs: warm)
    monkeypatch.setattr(bridge, "_codex_fallback_text", lambda *_a, **_kw: "Recovered")
    emitted, emit = _events()

    handled = handler._run_chat_via_warm_pool(
        "bravo", tmp_path, [{"role": "user", "content": "hello"}], emit,
        None, "tab-1", operator_trusted=True,
    )

    assert handled is True
    assert ("delta", {"text": "Recovered"}) in emitted
    assert any(event == "done" and data.get("fallback") == "codex" for event, data in emitted)
    assert sum(event == "done" for event, _data in emitted) == 1


def test_cold_first_turn_quota_failure_uses_codex_for_trusted_operator(monkeypatch, tmp_path):
    handler = _handler(monkeypatch)
    monkeypatch.setattr(bridge, "_safe_popen", lambda *_a, **_kw: _FakeProcess())
    monkeypatch.setattr(bridge.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(bridge, "_codex_fallback_text", lambda *_a, **_kw: "Recovered cold")
    emitted, emit = _events()

    handler._run_chat_via_claude(
        "bravo", tmp_path, [{"role": "user", "content": "hello"}], emit,
        operator_trusted=True,
    )

    assert ("delta", {"text": "Recovered cold"}) in emitted
    assert any(event == "done" and data.get("fallback") == "codex" for event, data in emitted)
    assert sum(event == "done" for event, _data in emitted) == 1
    assert not any(event == "error" for event, _data in emitted)


def test_warm_exit_zero_quota_delta_is_buffered_then_uses_codex(monkeypatch, tmp_path):
    """Live Claude emits the weekly limit as assistant text + rc=0."""
    handler = _handler(monkeypatch)
    warm = _FakeWarmProcess(
        events=[
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": QUOTA_ERROR}]},
            },
            {
                "type": "result",
                "stop_reason": "stop_sequence",
                "usage": {"output_tokens": 0},
                "result": QUOTA_ERROR,
            },
        ],
        ok=True,
    )
    monkeypatch.setattr(bridge, "_warm_use_or_create", lambda **_kwargs: warm)
    monkeypatch.setattr(bridge, "_codex_fallback_text", lambda *_a, **_kw: "Recovered live shape")
    emitted, emit = _events()

    handled = handler._run_chat_via_warm_pool(
        "bravo", tmp_path, [{"role": "user", "content": "hello"}], emit,
        None, "tab-live", operator_trusted=True,
    )

    deltas = [data["text"] for event, data in emitted if event == "delta"]
    assert handled is True
    assert deltas == ["Recovered live shape"]
    assert warm.killed is True
    assert sum(event == "done" for event, _data in emitted) == 1
    assert any(event == "done" and data.get("fallback") == "codex" for event, data in emitted)


def test_cold_exit_zero_quota_delta_is_buffered_then_uses_codex(monkeypatch, tmp_path):
    handler = _handler(monkeypatch)
    stdout_lines = [
        json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": QUOTA_ERROR}]},
        }) + "\n",
        json.dumps({
            "type": "result",
            "stop_reason": "stop_sequence",
            "usage": {"output_tokens": 0},
            "result": QUOTA_ERROR,
        }) + "\n",
    ]
    monkeypatch.setattr(
        bridge,
        "_safe_popen",
        lambda *_a, **_kw: _FakeProcess(stdout_lines=stdout_lines, returncode=0),
    )
    monkeypatch.setattr(bridge.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(bridge, "_codex_fallback_text", lambda *_a, **_kw: "Recovered cold live shape")
    emitted, emit = _events()

    handler._run_chat_via_claude(
        "bravo", tmp_path, [{"role": "user", "content": "hello"}], emit,
        operator_trusted=True,
    )

    deltas = [data["text"] for event, data in emitted if event == "delta"]
    assert deltas == ["Recovered cold live shape"]
    assert sum(event == "done" for event, _data in emitted) == 1
    assert any(event == "done" and data.get("fallback") == "codex" for event, data in emitted)


def test_quota_words_from_a_real_model_answer_are_not_replayed(monkeypatch, tmp_path):
    handler = _handler(monkeypatch)
    warm = _FakeWarmProcess(
        events=[
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "A weekly limit is a rolling cap."}]},
            },
            {
                "type": "result",
                "stop_reason": "end_turn",
                "usage": {"output_tokens": 8},
                "result": "A weekly limit is a rolling cap.",
            },
        ],
        ok=True,
    )
    monkeypatch.setattr(bridge, "_warm_use_or_create", lambda **_kwargs: warm)

    def forbidden_fallback(*_args, **_kwargs):
        raise AssertionError("genuine assistant text was replayed through Codex")

    monkeypatch.setattr(bridge, "_codex_fallback_text", forbidden_fallback)
    emitted, emit = _events()

    handled = handler._run_chat_via_warm_pool(
        "bravo", tmp_path, [{"role": "user", "content": "what is a weekly limit?"}], emit,
        None, "tab-explain", operator_trusted=True,
    )

    assert handled is True
    assert ("delta", {"text": "A weekly limit is a rolling cap."}) in emitted
    assert sum(event == "done" for event, _data in emitted) == 1


def test_warm_quota_failure_does_not_replay_after_tool_event(monkeypatch, tmp_path):
    handler = _handler(monkeypatch)
    warm = _FakeWarmProcess({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use",
            "name": "Bash",
            "id": "t1",
            "input": {"command": "echo ok"},
        }]},
    })
    monkeypatch.setattr(bridge, "_warm_use_or_create", lambda **_kwargs: warm)

    def forbidden_fallback(*_args, **_kwargs):
        raise AssertionError("Codex replayed a warm turn after a tool event")

    monkeypatch.setattr(bridge, "_codex_fallback_text", forbidden_fallback)
    emitted, emit = _events()

    handled = handler._run_chat_via_warm_pool(
        "bravo", tmp_path, [{"role": "user", "content": "hello"}], emit,
        None, "tab-1", operator_trusted=True,
    )

    assert handled is True
    assert any(event == "tool" for event, _data in emitted)
    assert any(event == "error" for event, _data in emitted)
    assert sum(event == "done" for event, _data in emitted) == 1


def test_cold_quota_failure_does_not_replay_after_tool_event(monkeypatch, tmp_path):
    handler = _handler(monkeypatch)
    tool_event = json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Bash", "id": "t1", "input": {"command": "echo ok"}}]},
    }) + "\n"
    monkeypatch.setattr(
        bridge, "_safe_popen", lambda *_a, **_kw: _FakeProcess(stdout_lines=[tool_event])
    )
    monkeypatch.setattr(bridge.Path, "home", staticmethod(lambda: tmp_path))

    def forbidden_fallback(*_args, **_kwargs):
        raise AssertionError("Codex replayed a turn after a tool event")

    monkeypatch.setattr(bridge, "_codex_fallback_text", forbidden_fallback)
    emitted, emit = _events()

    handler._run_chat_via_claude(
        "bravo", tmp_path, [{"role": "user", "content": "hello"}], emit,
        operator_trusted=True,
    )

    assert any(event == "tool" for event, _data in emitted)
    assert any(event == "error" for event, _data in emitted)


def test_cold_quota_failure_never_uses_codex_for_untrusted_session(monkeypatch, tmp_path):
    handler = _handler(monkeypatch)
    monkeypatch.setattr(bridge, "_safe_popen", lambda *_a, **_kw: _FakeProcess())
    monkeypatch.setattr(bridge.Path, "home", staticmethod(lambda: tmp_path))

    def forbidden_fallback(*_args, **_kwargs):
        raise AssertionError("untrusted Command Center text reached Codex")

    monkeypatch.setattr(bridge, "_codex_fallback_text", forbidden_fallback)
    emitted, emit = _events()

    handler._run_chat_via_claude(
        "bravo", tmp_path, [{"role": "user", "content": "untrusted"}], emit,
        operator_trusted=False,
    )

    assert not any(event == "delta" for event, _data in emitted)
    assert any(event == "error" for event, _data in emitted)
