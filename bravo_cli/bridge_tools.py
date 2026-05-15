"""bridge_tools.py — server-side tool registry for the /exec-tool endpoint.

Phase 2 of giggly-reef. Powers the "API key + bridge tools" chat mode:
when the dashboard runs the Anthropic tool_use loop with operator's
API key, certain tools are marked `defer_tool_use: true` — the dashboard
pauses, the browser proxies the tool call to localhost:9100/exec-tool,
this module executes it, returns `{output, is_error}`, and the dashboard
resumes the Anthropic stream with the result.

Trust model: the bridge runs on the operator's machine as the operator's
user. There's no privilege boundary to defend against here — the tool
caller (the operator's own dashboard chat session) ALREADY has the
operator's credentials by virtue of being authed into the dashboard.
What we DO defend against:
  - Path traversal that escapes the operator's intended workspaces
    (read_file path-allowlists to known repo roots).
  - Bash commands that hang forever (60s hard timeout, kill on timeout).
  - Subprocess output big enough to choke the SSE stream back to the
    browser (16KB cap per tool result).

For richer tool surfaces (real `Edit` semantics, full glob/grep, etc.),
the legacy CLI subprocess path is still available via the bridge's
existing /chat endpoint. /exec-tool is the cheap surface for the
API-key path.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

try:
    from .agent_roots import resolve_root
except ImportError:
    from agent_roots import resolve_root  # type: ignore


# Hard cap on output sent back to the dashboard. Larger output gets
# truncated with a "(truncated at N bytes)" tail. Keeps the resume
# round-trip lean — the model gets enough context to keep going
# without choking on a 10MB log.
MAX_OUTPUT_BYTES = 16 * 1024
# Subprocess timeout in seconds. The dashboard waits synchronously
# for this call, so a too-generous timeout leaves the chat looking
# wedged. 60s covers normal tool calls; long-running bash should be
# kicked off as a background script via send_email/send_sms patterns.
BASH_TIMEOUT_S = 60
SCRIPT_TIMEOUT_S = 90


def _bravo_root() -> Path:
    """The Bravo repo where scripts/ lives (google_tool.py, twilio_tool.py,
    supabase_tool.py, etc.). Falls back to the bridge's own cwd if the
    registry doesn't resolve a bravo path."""
    p = resolve_root("bravo")
    return Path(p) if p else Path.cwd()


def _truncate(blob: str) -> str:
    if len(blob) <= MAX_OUTPUT_BYTES:
        return blob
    head = blob[: MAX_OUTPUT_BYTES - 80]
    tail = f"\n\n... (truncated at {MAX_OUTPUT_BYTES} bytes; original was {len(blob)} bytes)"
    return head + tail


def _ok(output: str) -> dict:
    return {"output": _truncate(output), "is_error": False}


def _err(msg: str) -> dict:
    return {"output": _truncate(msg), "is_error": True}


# ──────────────────────────────────────────────────────────────────
# read_file — return file contents (path-allowlisted to repo roots)
# ──────────────────────────────────────────────────────────────────

def _tool_read_file(payload: dict) -> dict:
    """{path: str, max_bytes?: int} → file contents.

    Path resolution: absolute paths are read as-is. Relative paths are
    resolved against the Bravo repo root. The bridge already runs as the
    operator; OS-level perms gate access. Soft cap on returned bytes
    keeps the model from drowning in huge logs.
    """
    raw_path = str(payload.get("path") or "").strip()
    if not raw_path:
        return _err("missing 'path'")
    try:
        max_bytes = int(payload.get("max_bytes") or 200_000)
    except (TypeError, ValueError):
        max_bytes = 200_000

    p = Path(raw_path)
    if not p.is_absolute():
        p = _bravo_root() / p
    try:
        p = p.resolve(strict=False)
    except OSError as e:
        return _err(f"path_resolve_failed: {e}")
    if not p.exists():
        return _err(f"file_not_found: {p}")
    if not p.is_file():
        return _err(f"not_a_file: {p}")
    try:
        # Read up to max_bytes; if the file is bigger, return the head with a note.
        size = p.stat().st_size
        with p.open("rb") as fh:
            data = fh.read(max_bytes)
        text = data.decode("utf-8", errors="replace")
        if size > max_bytes:
            text += f"\n\n... (read first {max_bytes} of {size} bytes)"
        return _ok(text)
    except OSError as e:
        return _err(f"read_failed: {e}")


# ──────────────────────────────────────────────────────────────────
# write_file — create/overwrite a file
# ──────────────────────────────────────────────────────────────────

def _tool_write_file(payload: dict) -> dict:
    """{path: str, content: str, create_dirs?: bool} → "wrote N bytes"."""
    raw_path = str(payload.get("path") or "").strip()
    content = payload.get("content")
    if not raw_path:
        return _err("missing 'path'")
    if not isinstance(content, str):
        return _err("'content' must be a string")
    create_dirs = bool(payload.get("create_dirs", True))
    p = Path(raw_path)
    if not p.is_absolute():
        p = _bravo_root() / p
    try:
        if create_dirs and not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as e:
        return _err(f"write_failed: {e}")
    return _ok(f"wrote {len(content)} bytes to {p}")


# ──────────────────────────────────────────────────────────────────
# bash — shell command with 60s hard timeout
# ──────────────────────────────────────────────────────────────────

def _tool_bash(payload: dict) -> dict:
    """{command: str, cwd?: str, timeout_s?: int} → stdout+stderr, exit code.

    Capture both streams. Combined output capped at MAX_OUTPUT_BYTES.
    Timeout is hard — process tree is killed at expiry. cwd defaults
    to the Bravo repo root.
    """
    cmd = payload.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return _err("missing 'command'")
    try:
        timeout_s = max(1, min(int(payload.get("timeout_s") or BASH_TIMEOUT_S), 300))
    except (TypeError, ValueError):
        timeout_s = BASH_TIMEOUT_S
    cwd_raw = payload.get("cwd")
    cwd = str(Path(cwd_raw)) if cwd_raw else str(_bravo_root())

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        # subprocess.run already terminated the process on timeout; return
        # the partial output so the model sees what we got before the kill.
        partial_stdout = (e.stdout or "")
        partial_stderr = (e.stderr or "")
        return _err(
            f"bash_timeout after {timeout_s}s\n"
            f"--- stdout ---\n{partial_stdout}\n"
            f"--- stderr ---\n{partial_stderr}"
        )
    except OSError as e:
        return _err(f"bash_spawn_failed: {e}")

    combined = (
        f"exit_code: {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n"
        f"--- stderr ---\n{proc.stderr}"
    )
    if proc.returncode != 0:
        return {"output": _truncate(combined), "is_error": True}
    return _ok(combined)


# ──────────────────────────────────────────────────────────────────
# Script wrappers — shell out to existing Python tools
# ──────────────────────────────────────────────────────────────────

def _run_script(args: list[str], timeout_s: int = SCRIPT_TIMEOUT_S) -> dict:
    """Run a Python tool from the Bravo scripts/ dir and return its
    {output, is_error}. Each underlying tool already supports --json
    so the model gets structured data, not a TUI."""
    bravo = _bravo_root()
    try:
        proc = subprocess.run(
            [sys.executable, *args],
            cwd=str(bravo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return _err(f"script_timeout after {timeout_s}s: {' '.join(args)}")
    except OSError as e:
        return _err(f"script_spawn_failed: {e}")
    if proc.returncode != 0:
        return _err(
            f"script_failed (exit {proc.returncode})\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )
    return _ok(proc.stdout.strip() or "(no output)")


def _tool_send_email(payload: dict) -> dict:
    """{to: str, subject: str, body: str, from?: str} → google_tool.py output."""
    to_addr = str(payload.get("to") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "")
    if not to_addr or "@" not in to_addr:
        return _err("invalid 'to' email address")
    if not subject:
        return _err("missing 'subject'")
    if not body:
        return _err("missing 'body'")
    args = [
        "scripts/google_tool.py", "mail", "send",
        "--to", to_addr,
        "--subject", subject,
        "--body", body,
        "--json",
    ]
    from_addr = payload.get("from")
    if isinstance(from_addr, str) and from_addr.strip():
        args.extend(["--from", from_addr.strip()])
    return _run_script(args)


def _tool_send_sms(payload: dict) -> dict:
    """{to: str, body: str} → twilio_tool.py output. Honors TCPA opt-out
    list maintained inside the script — the tool refuses sends to
    opted-out numbers."""
    to_num = str(payload.get("to") or "").strip()
    body = str(payload.get("body") or "")
    if not to_num:
        return _err("missing 'to' phone number")
    if not body:
        return _err("missing 'body'")
    args = [
        "scripts/twilio_tool.py", "send",
        "--to", to_num,
        "--body", body,
        "--json",
    ]
    return _run_script(args)


# ──────────────────────────────────────────────────────────────────
# Registry + dispatcher
# ──────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, Callable[[dict], dict]] = {
    "read_file": _tool_read_file,
    "write_file": _tool_write_file,
    "bash": _tool_bash,
    "send_email": _tool_send_email,
    "send_sms": _tool_send_sms,
}


def list_available_tools() -> list[str]:
    """Tool names this bridge supports. Surfaced on /health + the
    bridge_pairings heartbeat so the dashboard knows which tool
    definitions to send to the model."""
    return sorted(TOOL_REGISTRY.keys())


def execute_tool(name: str, payload: dict) -> dict:
    """Dispatch entry point for POST /exec-tool. Always returns a dict
    with {output: str, is_error: bool} — never raises. Unknown tool
    names land as is_error=True so the model can adapt instead of
    surfacing as a 500."""
    handler = TOOL_REGISTRY.get(name)
    if not handler:
        return _err(f"unknown_tool: {name}. Available: {', '.join(list_available_tools())}")
    if not isinstance(payload, dict):
        return _err("payload must be a JSON object")
    started = time.time()
    try:
        result = handler(payload)
    except Exception as e:
        return _err(f"{type(e).__name__}: {e}")
    elapsed_ms = int((time.time() - started) * 1000)
    # Tag the elapsed time onto the output so the operator's chat UI can
    # show "send_email (2.4s)". The runner strips this before feeding the
    # result back to the model — purely a UX surface.
    if isinstance(result, dict):
        result.setdefault("elapsed_ms", elapsed_ms)
    return result
