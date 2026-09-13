"""Live proof that the automation pin beats a user-settings base URL.

claude_cli.run_claude_cli passes `--settings config/spillover/automation_pin.json`
so an automation reaches api.anthropic.com even after ~/.claude/settings.json
points ANTHROPIC_BASE_URL at the spillover proxy. That holds only if Claude Code
ranks command-line settings above user settings. This asks the real binary,
with zero quota spent:

  * two fake HTTP servers, A and B, on ephemeral loopback ports;
  * a temp CLAUDE_CONFIG_DIR whose settings.json sets ANTHROPIC_BASE_URL=A;
  * ANTHROPIC_AUTH_TOKEN=test in the child env, so no real credential is read
    or sent (the temp config dir holds none either);
  * `claude -p hi --setting-sources user --settings <temp pin to B>`.

B must receive the POST and A must receive nothing at all.

Skipped unless BRAVO_LIVE_CLI=1, because it needs the real claude binary.
Run: BRAVO_LIVE_CLI=1 python -m pytest scripts/tests/test_spillover_pin_live.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

pytestmark = pytest.mark.skipif(
    os.environ.get("BRAVO_LIVE_CLI") != "1",
    reason="needs the real claude binary; set BRAVO_LIVE_CLI=1 to run")

_MESSAGE = {"id": "msg_fake", "type": "message", "role": "assistant", "model": "fake-model",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1}}
_STREAM = [
    {"type": "message_start", "message": _MESSAGE},
    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "ok"}},
    {"type": "content_block_stop", "index": 0},
    {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
     "usage": {"output_tokens": 1}},
    {"type": "message_stop"},
]
_REPLY = {**_MESSAGE, "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}


class _Handler(BaseHTTPRequestHandler):
    """A minimal Messages API: enough for `claude -p` to finish cleanly."""

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep pytest output clean
        return

    def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler's naming
        self.server.seen.append(("POST", self.path))
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else b""
        path = self.path.split("?", 1)[0]
        if path == "/v1/messages/count_tokens":
            return self._send(200, b'{"input_tokens": 1}')
        if path != "/v1/messages":
            return self._send(404, b'{"type":"error","error":{"type":"not_found_error","message":"fake"}}')
        try:
            stream = bool(json.loads(body or b"{}").get("stream"))
        except ValueError:
            stream = False
        if stream:
            sse = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in _STREAM)
            return self._send(200, sse.encode("utf-8"), "text/event-stream")
        return self._send(200, json.dumps(_REPLY).encode("utf-8"))

    def do_GET(self):  # noqa: N802
        self.server.seen.append(("GET", self.path))
        self._send(404, b"{}")

    def do_HEAD(self):  # noqa: N802
        self.server.seen.append(("HEAD", self.path))
        self.send_response(200)
        self.send_header("content-length", "0")
        self.end_headers()


class _FakeUpstream(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.seen: list[tuple[str, str]] = []
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=5)


def test_the_settings_pin_beats_a_user_settings_base_url(tmp_path):
    from _subprocess_helpers import WINDOWLESS_FLAGS  # type: ignore
    from lib.claude_auth import build_claude_spawn_env
    from lib.claude_cli import resolve_claude_bin

    claude_bin = resolve_claude_bin()
    if not claude_bin:
        pytest.fail("BRAVO_LIVE_CLI=1 but no claude binary was found")

    server_a, server_b = _FakeUpstream(), _FakeUpstream()
    try:
        config_dir = tmp_path / "claude-config"
        config_dir.mkdir()
        (config_dir / "settings.json").write_text(
            json.dumps({"env": {"ANTHROPIC_BASE_URL": server_a.url}}), encoding="utf-8")
        pin = tmp_path / "automation_pin.json"
        pin.write_text(json.dumps({"env": {"ANTHROPIC_BASE_URL": server_b.url}}), encoding="utf-8")
        workdir = tmp_path / "work"
        workdir.mkdir()
        # The builder strips every inherited lane var (including a real
        # ANTHROPIC_BASE_URL or token in this shell) BEFORE these extras apply.
        env = build_claude_spawn_env(extras={
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "ANTHROPIC_AUTH_TOKEN": "test",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_AUTOUPDATER": "1",
            "CI": "true",
            "NO_COLOR": "1",
        })
        proc = subprocess.run(
            [claude_bin, "-p", "hi", "--setting-sources", "user", "--settings", str(pin),
             "--strict-mcp-config", "--no-session-persistence"],
            cwd=str(workdir), env=env, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=180,
            creationflags=WINDOWLESS_FLAGS,
        )
    finally:
        server_a.stop()
        server_b.stop()

    detail = (f"exit {proc.returncode}; stderr tail {proc.stderr[-400:]!r}; "
              f"A saw {server_a.seen}; B saw {server_b.seen}")
    assert not server_a.seen, f"the user-settings base URL got traffic, so the pin lost. {detail}"
    assert any(method == "POST" and path.startswith("/v1/messages")
               for method, path in server_b.seen), f"the pinned base URL never got the POST. {detail}"
