"""Local HTTP chat server — `bravo bridge serve`.

Runs on the operator's machine at http://localhost:9100. The dashboard's
chat page connects directly to this when the bridge is online; the operator's
API key + brain files never leave the machine.

Endpoints
---------
GET  /health                — liveness probe (CORS-allowed)
GET  /agents                — list of agents resolvable on this machine
POST /chat                  — start a chat turn, streams SSE back
                                body: {agent, messages: [{role, content}]}

Architecture is deliberately small:
  1. Dashboard POSTs {agent, messages}.
  2. Server cd's to that agent's repo root.
  3. Reads its brain entry file (CLAUDE.md / AGENTS.md / brain/SOUL.md).
  4. Calls Anthropic with the entry as system prompt + one tool: read_file.
  5. While the model emits tool_use blocks, server reads the requested file
     (path-allowlisted to that agent's repo), feeds back, model continues.
  6. Streams text deltas back as SSE.

This is the same pattern Claude Code uses — entry file + on-demand reads —
but running on the operator's machine, paid by the operator's Anthropic key,
serving the operator's own dashboard.

Why localhost not Vercel: browsers allow `http://localhost` connections from
HTTPS pages by exemption. So no tunnel needed; the dashboard widget talks
directly to this server.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import urllib.request
import urllib.error

try:
    from .agent_roots import (
        resolve_root,
        resolve_entry_file,
        all_resolved,
        under_root,
    )
except ImportError:
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    from agent_roots import (  # type: ignore
        resolve_root,
        resolve_entry_file,
        all_resolved,
        under_root,
    )

PORT = int(os.environ.get("BRAVO_BRIDGE_PORT", "9100"))
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = os.environ.get("BRAVO_CHAT_MODEL", "claude-sonnet-4-6")
MAX_TURNS = 8                  # safety cap — read_file tool calls per chat turn
MAX_FILE_BYTES = 200_000       # don't blow context with megabyte files
ALLOWED_ORIGINS = [
    "https://agent-dashboard-cc90210.vercel.app",
    "http://localhost:3100",
]


def _read_anthropic_key() -> str:
    """Operator's Anthropic key. Same env-file scan the bridge already uses."""
    if "ANTHROPIC_API_KEY" in os.environ:
        return os.environ["ANTHROPIC_API_KEY"]
    home = Path.home()
    candidates = [
        Path.cwd() / ".env.agents",
        home / "Business-Empire-Agent" / ".env.agents",
        home / ".bravo" / ".env.agents",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "ANTHROPIC_API_KEY":
                    return v.strip().strip('"').strip("'")
        except Exception:
            continue
    return ""


READ_FILE_TOOL = {
    "name": "read_file",
    "description": (
        "Read a file from this agent's repository. Paths are relative to "
        "the agent's repo root. Use this whenever you need information "
        "you don't have in your initial brain entry — e.g. CAPABILITIES.md "
        "for tool routing, a SKILL.md body, ACTIVE_TASKS for current work, "
        "etc. Path-allowlisted: you can only read files inside this agent's "
        "repo, never outside."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to agent repo root (e.g. brain/CAPABILITIES.md)",
            }
        },
        "required": ["path"],
    },
}


def _system_prompt_for(agent: str, root: Path, entry: Path) -> str:
    """Compose the system prompt: brain entry + lazy-load instructions."""
    try:
        entry_text = entry.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        entry_text = f"(could not read entry file at {entry}: {e})"

    rel_entry = entry.relative_to(root)
    return f"""You are {agent.upper()}, running on the operator's local machine via the OASIS Agent Command Center.

Working directory: {root}
Brain entry: {rel_entry}

You have ONE tool: read_file(path). Use it to lazily load deeper files from your repo as the conversation needs them — CAPABILITIES.md for tool routing, brain/USER.md for operator profile, brain/STATE.md for current state, skills/<name>/SKILL.md for skill bodies, memory/* for recent state. Read on demand. Never speculate when you can read.

Boundaries:
- Path-allowlisted to this repo. read_file outside the repo will be rejected.
- Read-only: you cannot write or execute via this chat. Surface what you'd
  do; the operator runs the actual command.
- Up to {MAX_TURNS} read_file calls per turn — cap, not a target.

--- BEGIN {rel_entry} ---
{entry_text}
--- END {rel_entry} ---
"""


def _call_anthropic(api_key: str, system: str, messages: list[dict], stream: bool = True):
    """One call to Anthropic. Returns the raw urllib response (caller streams)."""
    body = {
        "model": DEFAULT_MODEL,
        "max_tokens": 4096,
        "system": system,
        "tools": [READ_FILE_TOOL],
        "messages": messages,
        "stream": stream,
    }
    req = urllib.request.Request(
        ANTHROPIC_API,
        method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "accept": "text/event-stream",
        },
    )
    return urllib.request.urlopen(req, timeout=120)


class _ChatHandler(BaseHTTPRequestHandler):
    # Quiet the default request logger
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _set_cors(self) -> None:
        origin = self.headers.get("origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("access-control-allow-origin", origin)
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "bravo-bridge-chat", "version": "0.1.0"})
            return
        if self.path == "/agents":
            self._json(200, {"ok": True, "agents": all_resolved()})
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/chat":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._json(400, {"ok": False, "error": "invalid_json"})
            return

        agent = str(payload.get("agent", "bravo")).lower()
        messages = payload.get("messages") or []
        if not isinstance(messages, list) or not messages:
            self._json(400, {"ok": False, "error": "no_messages"})
            return

        root = resolve_root(agent)
        if not root:
            self._json(412, {
                "ok": False,
                "error": "agent_not_paired_locally",
                "agent": agent,
                "hint": "This agent's repo is not present at any known path on this machine.",
            })
            return
        entry = resolve_entry_file(root)
        if not entry:
            self._json(412, {
                "ok": False,
                "error": "no_entry_brain",
                "agent": agent,
                "root": str(root),
                "hint": "No CLAUDE.md / AGENTS.md / brain/SOUL.md found in the agent's repo root.",
            })
            return

        api_key = _read_anthropic_key()
        if not api_key:
            self._json(412, {
                "ok": False,
                "error": "no_anthropic_key",
                "hint": "Set ANTHROPIC_API_KEY in the operator's local .env.agents.",
            })
            return

        # ---- Stream SSE back -----------------------------------------------
        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self._set_cors()
        self.end_headers()

        def emit(event: str, data: dict) -> None:
            self.wfile.write(
                f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
            )
            self.wfile.flush()

        try:
            self._run_chat(agent, root, entry, api_key, messages, emit)
        except Exception as e:
            try:
                emit("error", {"message": f"chat_loop_failed: {e}"})
                emit("done", {})
            except Exception:
                pass

    def _run_chat(
        self,
        agent: str,
        root: Path,
        entry: Path,
        api_key: str,
        messages: list[dict],
        emit,
    ) -> None:
        system = _system_prompt_for(agent, root, entry)
        # Anthropic message thread — converts client {role, content} to API shape
        thread: list[dict] = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("user", "assistant")
        ]
        emit("info", {"agent": agent, "root": str(root), "entry": str(entry.relative_to(root))})

        for turn in range(MAX_TURNS):
            resp = _call_anthropic(api_key, system, thread, stream=True)
            assistant_blocks: list[dict] = []   # reconstructed from stream
            current_block: dict | None = None
            current_input_buf = ""              # for tool_use partial JSON
            stop_reason: str | None = None

            for line in _iter_sse_lines(resp):
                if not line:
                    continue
                if line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data_raw = line[5:].strip()
                if not data_raw or data_raw == "[DONE]":
                    continue
                try:
                    data = json.loads(data_raw)
                except Exception:
                    continue
                t = data.get("type")
                if t == "content_block_start":
                    block = data.get("content_block", {})
                    current_block = {"type": block.get("type"), "text": ""}
                    if current_block["type"] == "tool_use":
                        current_block["id"] = block.get("id")
                        current_block["name"] = block.get("name")
                        current_input_buf = ""
                    assistant_blocks.append(current_block)
                elif t == "content_block_delta":
                    delta = data.get("delta", {})
                    if delta.get("type") == "text_delta" and current_block:
                        chunk = delta.get("text", "")
                        current_block["text"] += chunk
                        emit("delta", {"text": chunk})
                    elif delta.get("type") == "input_json_delta" and current_block:
                        current_input_buf += delta.get("partial_json", "")
                elif t == "content_block_stop":
                    if current_block and current_block["type"] == "tool_use":
                        try:
                            current_block["input"] = json.loads(current_input_buf or "{}")
                        except Exception:
                            current_block["input"] = {}
                    current_block = None
                elif t == "message_delta":
                    sr = data.get("delta", {}).get("stop_reason")
                    if sr:
                        stop_reason = sr
                elif t == "message_stop":
                    pass

            # If the model didn't request a tool, we're done with this chat turn.
            tool_uses = [b for b in assistant_blocks if b.get("type") == "tool_use"]
            if stop_reason != "tool_use" or not tool_uses:
                emit("done", {"stop_reason": stop_reason or "end_turn"})
                return

            # Append the assistant's tool-use turn to the thread (Anthropic-shape)
            thread.append({
                "role": "assistant",
                "content": [
                    (
                        {"type": "text", "text": b.get("text", "")}
                        if b.get("type") == "text"
                        else {
                            "type": "tool_use",
                            "id": b.get("id"),
                            "name": b.get("name"),
                            "input": b.get("input", {}),
                        }
                    )
                    for b in assistant_blocks
                ],
            })

            # Run each tool, append tool_result(s)
            tool_results: list[dict] = []
            for use in tool_uses:
                if use.get("name") != "read_file":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": use.get("id"),
                        "content": "unknown_tool",
                        "is_error": True,
                    })
                    continue
                rel_path = str(use.get("input", {}).get("path", "")).strip()
                emit("tool", {"name": "read_file", "path": rel_path})
                content, is_error = self._safe_read(root, rel_path)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": use.get("id"),
                    "content": content,
                    "is_error": is_error,
                })
            thread.append({"role": "user", "content": tool_results})
            # Loop continues — model gets the file body, decides next move.

        # Hit the cap
        emit("error", {"message": f"max_tool_turns_exceeded ({MAX_TURNS})"})
        emit("done", {"stop_reason": "max_turns"})

    def _safe_read(self, root: Path, rel_path: str) -> tuple[str, bool]:
        if not rel_path:
            return "empty path", True
        p = (root / rel_path).resolve()
        if not under_root(root, p):
            return f"path outside agent root: {rel_path}", True
        if not p.is_file():
            return f"not a file: {rel_path}", True
        try:
            data = p.read_bytes()
        except Exception as e:
            return f"read failed: {e}", True
        if len(data) > MAX_FILE_BYTES:
            return f"file too large ({len(data)} bytes; cap {MAX_FILE_BYTES})", True
        try:
            return data.decode("utf-8"), False
        except Exception:
            return data.decode("utf-8", errors="replace"), False

    def _json(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self._set_cors()
        self.end_headers()
        self.wfile.write(raw)


def _iter_sse_lines(resp):
    """Yield decoded text lines from a urllib SSE response. Anthropic uses
    LF-delimited frames; we just iterate readline() until EOF."""
    while True:
        line = resp.readline()
        if not line:
            return
        try:
            yield line.decode("utf-8", errors="replace").rstrip("\r\n")
        except Exception:
            return


def serve_forever() -> int:
    """Entry point for `bravo bridge serve`."""
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), _ChatHandler)
    print(f"oasis-bridge-chat listening on http://127.0.0.1:{PORT}")
    print(f"  agents resolvable: {sum(1 for v in all_resolved().values() if v['root'])}/5")
    print("  Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(serve_forever())
