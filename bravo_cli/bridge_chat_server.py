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
import shlex
import subprocess
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
# OpenRouter exposes an Anthropic-compatible /v1/messages endpoint — same
# wire format (content_block_delta, tool_use blocks, etc.). Using that means
# one streaming loop covers both providers; only the URL + auth header swap.
OPENROUTER_MESSAGES_API = "https://openrouter.ai/api/v1/messages"
DEFAULT_ANTHROPIC_MODEL = os.environ.get("BRAVO_CHAT_MODEL", "claude-sonnet-4-6")
DEFAULT_OPENROUTER_MODEL = os.environ.get(
    "BRAVO_CHAT_OPENROUTER_MODEL", "anthropic/claude-sonnet-4"
)
MAX_TURNS = 8                  # safety cap — read_file tool calls per chat turn
MAX_FILE_BYTES = 200_000       # don't blow context with megabyte files
ALLOWED_ORIGINS = [
    "https://agent-dashboard-cc90210.vercel.app",
    "http://localhost:3100",
]


def _read_env_value(name: str) -> str:
    """Look up a single env var name, then fall back to scanning the
    operator's local secrets file. Never returns the value to a caller other
    than the chat path (which uses it solely for outbound API auth).
    """
    if name in os.environ:
        return os.environ[name]
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
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
        except Exception:
            continue
    return ""


def _resolve_provider() -> tuple[str, str, str]:
    """Pick the chat backend.

    Preference: OpenRouter > Anthropic. OpenRouter is cheaper, single-key,
    and what we recommend in onboarding.

    Returns (provider, api_key, model). If neither key is present, returns
    ("none", "", "") and the chat handler 412s with a clear hint.
    """
    or_key = _read_env_value("OPENROUTER_API_KEY")
    if or_key:
        return ("openrouter", or_key, DEFAULT_OPENROUTER_MODEL)
    anth = _read_env_value("ANTHROPIC_API_KEY")
    if anth:
        return ("anthropic", anth, DEFAULT_ANTHROPIC_MODEL)
    return ("none", "", "")


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


# Allowlist: scripts the chat agent may invoke. Each entry maps a friendly
# name → (relative_path_from_agent_root, mutating?). Mutating scripts require
# `confirm: true` in the tool input — the operator should have asked for it
# in the same chat turn.
#
# Add new entries here as new safe-to-call scripts ship. Anything off-list
# returns "script_not_allowlisted" with the current allowlist in the error
# message so the agent learns what's available.
SCRIPT_ALLOWLIST: dict[str, dict] = {
    # --- read-only / safe ---
    "supabase_select": {"path": "scripts/supabase_tool.py", "subcmd": "select", "mutating": False,
                         "help": "Query a Supabase table. Args: table, --eq JSON, --limit, --project."},
    "supabase_list_tables": {"path": "scripts/supabase_tool.py", "subcmd": "list-tables", "mutating": False,
                              "help": "List Supabase tables. Args: --project bravo"},
    "revenue_engine_mrr": {"path": "scripts/revenue_engine.py", "subcmd": "mrr", "mutating": False,
                            "help": "Show current Net MRR + breakdown. Use --json for structured output."},
    "ceo_dashboard": {"path": "scripts/ceo_dashboard.py", "subcmd": "briefing", "mutating": False,
                       "help": "Daily CEO briefing — MRR, pipeline, today's plan, hot inbound."},
    "lead_engine_list": {"path": "scripts/lead_engine.py", "subcmd": "list", "mutating": False,
                          "help": "List leads. Args: --status qualified|new|won|lost, --limit N, --json"},
    "lead_engine_score": {"path": "scripts/lead_engine.py", "subcmd": "score", "mutating": False,
                           "help": "Re-score a lead. Args: --lead-id <uuid>"},
    "send_gateway_can_act": {"path": "scripts/send_gateway.py", "subcmd": "can-act", "mutating": False,
                              "help": "Pre-flight check before any send. Args: --lead-id <id> --channel email|dm"},
    "send_gateway_status": {"path": "scripts/send_gateway.py", "subcmd": "status", "mutating": False,
                             "help": "Show send-gateway state — recent sends, open cooldowns, daily caps."},
    "firecrawl_search": {"path": "scripts/firecrawl_tool.py", "subcmd": "search", "mutating": False,
                          "help": "Web search via Firecrawl. Args: 'query string'"},
    "agent_inbox_list": {"path": "scripts/agent_inbox.py", "subcmd": "list", "mutating": False,
                          "help": "List inbox messages for an agent. Args: --to bravo|atlas|maven|aura|hermes"},

    # --- mutating (require confirm: true) ---
    "send_gateway_send": {"path": "scripts/send_gateway.py", "subcmd": "send", "mutating": True,
                           "help": "Send an email/DM through the 8-gate safety pipeline. Args: --channel email --to … --subject … --body … --agent-source bravo. CASL/cooldown/cap/reputation gates enforced; send_gateway will refuse if blocked."},
    "lead_engine_add": {"path": "scripts/lead_engine.py", "subcmd": "add", "mutating": True,
                         "help": "Add a lead. Args: --name --email --company --source --score --notes"},
    "supabase_insert": {"path": "scripts/supabase_tool.py", "subcmd": "insert", "mutating": True,
                         "help": "Insert a Supabase row. Args: table --data JSON --project bravo"},
    "supabase_update": {"path": "scripts/supabase_tool.py", "subcmd": "update", "mutating": True,
                         "help": "Update Supabase rows. Args: table --eq JSON --data JSON --project bravo"},
    "agent_inbox_post": {"path": "scripts/agent_inbox.py", "subcmd": "post", "mutating": True,
                          "help": "Post a message to a sibling agent's inbox. Args: --to atlas|maven|aura|hermes --priority low|normal|high --body '...'"},
    # NOTE: late_tool.py / Zernio social-post scheduling is referenced in
    # brain/CAPABILITIES.md but the CLI script does not exist in this repo
    # yet. Re-add `late_create` to the allowlist once the script lands.
}

RUN_SCRIPT_TOOL = {
    "name": "run_script",
    "description": (
        "Run an allowlisted script in the agent's repo and return its stdout. "
        "Use this to ACT on the operator's request — query the database, "
        "score a lead, send an email, post to an agent inbox, schedule a "
        "social post, etc. Mutating scripts require confirm:true in the "
        "input — only set that when the operator explicitly asked you to "
        "perform the action in the SAME chat turn. Read-only scripts run "
        "freely. Output is captured (stdout/stderr) up to 100KB; runs cap "
        "at 60s. Allowlist: " + ", ".join(sorted(SCRIPT_ALLOWLIST.keys()))
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "Allowlist key (e.g. 'send_gateway_send', 'supabase_select', 'revenue_engine_mrr').",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Extra command-line arguments to pass after the subcommand. Example for supabase_select: ['user_profiles', '--limit', '5', '--project', 'bravo']",
            },
            "confirm": {
                "type": "boolean",
                "description": "Required true for mutating scripts. Set only when the operator asked for the action in this turn.",
            },
        },
        "required": ["script"],
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

THE RAG ROUTER (read this once on the first operator turn):
1. read_file("brain/AGENT_ROUTER.md") — routing-by-intent table. For every operator request, this tells you which deeper file to read for context.
2. read_file("brain/EXECUTION_RULES.md") — the iron law. Self-execute, never tell the operator to run commands you can run yourself, confirm after every mutation.
3. read_file("brain/INTENTS.md") — verb-by-verb playbooks. Read when an intent matches.
4. read_file("brain/WHEN_TO_USE_SKILLS.md") — trigger map for the 150+ skills.

You have TWO tools here:

1. `read_file(path)` — load deeper files lazily as the conversation calls for them. Path-allowlisted to this repo only.

2. `run_script(script, args?, confirm?)` — execute an allowlisted CLI script in this repo and return its stdout. This is your ACT path — query Supabase, score a lead, send an email, post to an inbox, etc. The full allowlist + mutating flag is in the tool's input schema (you'll see it). Rules:
   - **Read-only scripts run freely** (supabase_select, revenue_engine_mrr, ceo_dashboard, lead_engine_list, send_gateway_can_act, firecrawl_search, agent_inbox_list, etc.) — call them whenever you need live data instead of speculating.
   - **Mutating scripts require `confirm: true` in the input** AND the operator must have asked for the action in THIS turn. If they didn't, set confirm=false (or omit) so the script bounces back with `confirm_required` — surface that to the operator and wait for their go.
   - send_gateway_send specifically routes through 8 safety gates (CASL, cooldown, daily/hourly cap, domain cap, reputation, draft critic, bounce circuit, reservation guard). If a gate blocks, the response shows the reason; don't bypass.

Mutation surface beyond scripts:
- For DASHBOARD data changes (operator profile, MRR, agents_enabled, primary_agent), emit a `<dashboard-action type="..." >{{...}}</dashboard-action>` marker in your reply. The dashboard parses these post-stream and applies them server-side, tenant-scoped, audit-logged. Allowed action types live in apps/command-center/lib/agent-actions.ts.

Other rules:
- Up to {MAX_TURNS} tool calls per turn (any combination of read_file + run_script). If you're using more than 3, you're guessing — ask a clarifying question instead.
- read_file / run_script outside this repo will be rejected. Don't try to traverse to a sibling agent's repo — delegate via agent_inbox_post (mutating, requires confirm) instead.
- After ANY mutation, confirm in chat: WHAT changed, WHERE (table/file/inbox), WHAT'S NEXT (refresh/cron-tick/etc).

--- BEGIN {rel_entry} ---
{entry_text}
--- END {rel_entry} ---
"""


def _call_provider(
    provider: str,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict],
    stream: bool = True,
):
    """One streaming call. Provider toggles URL + auth header; the body
    shape is the same Anthropic /v1/messages contract either way (OpenRouter
    exposes a compatible passthrough), so the SSE consumer downstream is
    provider-agnostic.
    """
    body = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "tools": [READ_FILE_TOOL, RUN_SCRIPT_TOOL],
        "messages": messages,
        "stream": stream,
    }
    if provider == "openrouter":
        url = OPENROUTER_MESSAGES_API
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://agent-dashboard-cc90210.vercel.app",
            "X-Title": "OASIS Agent Command Center",
            "anthropic-version": "2023-06-01",
            "accept": "text/event-stream",
        }
    else:  # anthropic
        url = ANTHROPIC_API
        headers = {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "accept": "text/event-stream",
        }
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
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

        provider, api_key, model = _resolve_provider()
        if provider == "none" or not api_key:
            self._json(412, {
                "ok": False,
                "error": "no_provider_key",
                "hint": (
                    "No OPENROUTER_API_KEY or ANTHROPIC_API_KEY found in env "
                    "or operator's local secrets file. Add either one to "
                    "enable local chat."
                ),
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
            self._run_chat(agent, root, entry, provider, api_key, model, messages, emit)
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
        provider: str,
        api_key: str,
        model: str,
        messages: list[dict],
        emit,
    ) -> None:
        system = _system_prompt_for(agent, root, entry)
        # Anthropic-shape message thread (works for both providers since
        # OpenRouter exposes the same /v1/messages contract).
        thread: list[dict] = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("user", "assistant")
        ]
        emit("info", {
            "agent": agent,
            "root": str(root),
            "entry": str(entry.relative_to(root)),
            "provider": provider,
            "model": model,
        })

        for turn in range(MAX_TURNS):
            resp = _call_provider(provider, api_key, model, system, thread, stream=True)
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
                tool_name = use.get("name")
                tool_input = use.get("input", {}) or {}
                if tool_name == "read_file":
                    rel_path = str(tool_input.get("path", "")).strip()
                    emit("tool", {"name": "read_file", "path": rel_path})
                    content, is_error = self._safe_read(root, rel_path)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": use.get("id"),
                        "content": content,
                        "is_error": is_error,
                    })
                elif tool_name == "run_script":
                    script_key = str(tool_input.get("script", "")).strip()
                    args = tool_input.get("args") or []
                    if not isinstance(args, list):
                        args = []
                    args = [str(a) for a in args]
                    confirm = bool(tool_input.get("confirm", False))
                    emit("tool", {
                        "name": "run_script",
                        "script": script_key,
                        "args": args,
                        "confirm": confirm,
                    })
                    content, is_error = self._safe_run_script(root, script_key, args, confirm)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": use.get("id"),
                        "content": content,
                        "is_error": is_error,
                    })
                else:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": use.get("id"),
                        "content": f"unknown_tool: {tool_name}",
                        "is_error": True,
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

    def _safe_run_script(
        self,
        root: Path,
        script_key: str,
        extra_args: list,
        confirm: bool,
    ) -> tuple[str, bool]:
        """Execute an allowlisted script, capture output. Mutating scripts
        require confirm=True. Cwd is the agent root; path-allowlisted to
        scripts/* inside that root (no path traversal).
        """
        if not script_key:
            return "missing 'script' key", True
        spec = SCRIPT_ALLOWLIST.get(script_key)
        if not spec:
            allowed = ", ".join(sorted(SCRIPT_ALLOWLIST.keys()))
            return (
                f"script_not_allowlisted: '{script_key}' is not in the allowlist.\n"
                f"Allowed: {allowed}\n"
                f"To add a new script: edit SCRIPT_ALLOWLIST in bridge_chat_server.py."
            ), True
        if spec.get("mutating") and not confirm:
            return (
                f"confirm_required: '{script_key}' is a mutating script. "
                f"Re-call with confirm:true ONLY if the operator asked for the "
                f"action in this chat turn. Help: {spec.get('help', '')}"
            ), True

        rel_script = spec["path"]
        full_path = (root / rel_script).resolve()
        if not under_root(root, full_path) or not full_path.is_file():
            return f"script_missing: {rel_script} not found in agent root", True

        # Build the command — Python interpreter + script + subcmd + extra args
        cmd: list = [sys.executable, str(full_path)]
        subcmd = spec.get("subcmd")
        if subcmd:
            cmd.append(subcmd)
        cmd.extend(extra_args)

        try:
            r = subprocess.run(
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=60,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"timeout: '{script_key}' exceeded 60s", True
        except Exception as e:
            return f"spawn_failed: {e}", True

        out = (r.stdout or "")[-100_000:]   # cap returned bytes
        err = (r.stderr or "")[-10_000:]
        cmd_display = " ".join(shlex.quote(c) for c in cmd)
        body = f"$ {cmd_display}\n[exit {r.returncode}]\n--- stdout ---\n{out}"
        if err.strip():
            body += f"\n--- stderr ---\n{err}"
        # Treat non-zero exit as is_error so the model sees + handles failure
        return body, r.returncode != 0

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
