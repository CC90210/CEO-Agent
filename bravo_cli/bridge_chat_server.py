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
import random
import re
import shlex
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
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
def _load_script_manifest() -> dict[str, dict]:
    """Load scripts/_bridge_manifest.json into a dict keyed by entry key.
    Falls back to a small static set if the manifest is missing so the
    bridge still boots in environments where build_bridge_manifest.py
    hasn't been run.
    """
    candidates = [
        Path(__file__).resolve().parent.parent / "scripts" / "_bridge_manifest.json",
        Path.cwd() / "scripts" / "_bridge_manifest.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                entries = data.get("entries", [])
                manifest = {e["key"]: e for e in entries if "key" in e}
                if manifest:
                    return manifest
            except Exception as exc:
                print(f"[bridge] manifest load failed: {exc}", file=sys.stderr)
    # Static fallback — keeps the bridge usable without a manifest.
    print("[bridge] no _bridge_manifest.json found; using static fallback", file=sys.stderr)
    return {
        "supabase_select": {"path": "scripts/supabase_tool.py", "subcmd": "select", "mutating": False,
                             "help": "Query a Supabase table."},
        "lead_engine_list": {"path": "scripts/lead_engine.py", "subcmd": "list", "mutating": False,
                              "help": "List leads."},
        "revenue_engine_mrr": {"path": "scripts/revenue_engine.py", "subcmd": "mrr", "mutating": False,
                                "help": "Current Net MRR."},
        "send_gateway_send": {"path": "scripts/send_gateway.py", "subcmd": "send", "mutating": True,
                               "help": "Send via the 8-gate safety pipeline."},
    }


SCRIPT_ALLOWLIST: dict[str, dict] = _load_script_manifest()

RUN_SCRIPT_TOOL = {
    "name": "run_script",
    "description": (
        f"Run an allowlisted script in the agent's repo and return its "
        f"stdout. Use this to ACT on the operator's request — query the "
        f"database, score a lead, send an email, post to an agent inbox, "
        f"etc. Mutating scripts require confirm:true; only set that when "
        f"the operator explicitly asked for the action in this turn. "
        f"Read-only scripts run freely. Output captured up to 100KB; "
        f"60s timeout. The full allowlist has {len(SCRIPT_ALLOWLIST)} "
        f"scripts — call list_tools first if you don't know the exact key."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "Allowlist key (e.g. 'send_gateway_send', 'supabase_select', 'revenue_engine_mrr'). Call list_tools to discover available keys.",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Extra CLI args after the subcommand. Example for supabase_select: ['user_profiles', '--limit', '5', '--project', 'bravo']",
            },
            "confirm": {
                "type": "boolean",
                "description": "Required true for mutating scripts. Set only when the operator asked for the action in this turn.",
            },
        },
        "required": ["script"],
    },
}


LIST_TOOLS_TOOL = {
    "name": "list_tools",
    "description": (
        "Discover what scripts are available for run_script. Returns a "
        "filtered list of {key, path, subcmd, mutating, help} entries. "
        "Use this when the operator's intent doesn't match a key you "
        "already know — pass `query` to filter by substring (matches "
        "key, path, or help text). Without args, returns the first 30 "
        "entries grouped by script."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Substring to filter by (matches key/path/help). Examples: 'lead', 'stripe', 'send', 'mrr'.",
            },
            "mutating_only": {
                "type": "boolean",
                "description": "If true, only return mutating (confirm-required) scripts. If false, only read-only. Omit for both.",
            },
            "limit": {
                "type": "number",
                "description": "Max entries to return. Default 50.",
            },
        },
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

You have THREE tools here:

1. `read_file(path)` — load deeper files lazily as the conversation calls for them. Path-allowlisted to this repo only.

2. `list_tools(query?, mutating_only?, limit?)` — discover what scripts are available before calling run_script. The allowlist is auto-generated from scripts/ (~290 entries across 77 scripts), so memorizing keys is hopeless. When the operator's intent doesn't match a key you already know, call this FIRST with a substring query (e.g. `query: "lead"`, `query: "stripe"`, `query: "send"`). Returns matching entries with their path + help text + mutating flag. Use the returned `key` as the input to run_script.

3. `run_script(script, args?, confirm?)` — execute an allowlisted CLI script and return its stdout. This is your ACT path — query Supabase, score a lead, send an email, post to an inbox, etc. Rules:
   - **Read-only scripts run freely.** Call them whenever you need live data instead of speculating.
   - **Mutating scripts require `confirm: true`** AND the operator must have asked for the action in THIS turn. If they didn't, omit confirm so the script bounces back with `confirm_required` — surface that and wait.
   - send_gateway_send specifically routes through 8 safety gates (CASL, cooldown, daily/hourly cap, domain cap, reputation, draft critic, bounce circuit, reservation guard). If a gate blocks, the response shows the reason; don't bypass.

Discovery pattern when the operator asks for something you don't have a key for:
   1. `list_tools(query: "<topic>")` to find candidates
   2. Pick the right key from the returned entries
   3. `run_script(script: <key>, args: [...], confirm: true|false)`
   4. Surface the result + confirmation in chat

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


_RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504, 522, 524}
_PROVIDER_RETRY_ATTEMPTS = 3
_PROVIDER_RETRY_BASE_MS = 2000  # 2s, 4s, 8s with ±20% jitter


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

    Wraps urlopen in jittered exponential backoff for retryable HTTP codes
    (408, 429, 5xx). A single 503 from the provider used to surface as a
    raw "chat_loop_failed" to the operator with no second chance — now we
    retry up to 3 times before giving up. Non-retryable codes (400, 401,
    403, 404) raise immediately.
    """
    body = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "tools": [READ_FILE_TOOL, RUN_SCRIPT_TOOL, LIST_TOOLS_TOOL],
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
    body_bytes = json.dumps(body).encode("utf-8")

    last_exc: Exception | None = None
    for attempt in range(_PROVIDER_RETRY_ATTEMPTS):
        req = urllib.request.Request(url, method="POST", data=body_bytes, headers=headers)
        try:
            return urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code not in _RETRYABLE_HTTP_CODES:
                raise
            if attempt == _PROVIDER_RETRY_ATTEMPTS - 1:
                raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # DNS hiccups, connection resets, transient network blips —
            # all worth a retry.
            last_exc = e
            if attempt == _PROVIDER_RETRY_ATTEMPTS - 1:
                raise

        delay_ms = _PROVIDER_RETRY_BASE_MS * (2 ** attempt)
        # ±20% jitter so concurrent retries don't synchronize
        jitter = random.uniform(-0.2, 0.2) * delay_ms
        time.sleep(max(0, (delay_ms + jitter) / 1000))

    # Loop should always either return or raise; this is belt-and-suspenders.
    if last_exc:
        raise last_exc
    raise RuntimeError("provider_call_failed_with_no_exception")


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
        self.send_header("access-control-allow-headers", "content-type, authorization")
        self.end_headers()

    def _check_origin_allowed(self) -> bool:
        """For mutating endpoints, require the request to come from a
        CORS-allowed origin. Browsers refuse cross-origin POSTs, so this
        gates access to the operator's authed dashboard session — no
        random LAN browser can hit /env/set.

        Same model as /chat, which has run unauthenticated since v1.
        """
        origin = self.headers.get("origin", "")
        return origin in ALLOWED_ORIGINS

    def _handle_env_set(self) -> None:
        """POST /env/set — write a key=value to .env.agents and ping the
        named integration_health service. Settings → Integrations key-paste
        modal targets this so operators don't have to edit dotfiles manually.

        Auth: CORS origin must match ALLOWED_ORIGINS (operator's authed
        dashboard session). No bearer token — bridge runs on localhost
        only and the dashboard cookie already binds the session.

        Body: { "key": "STRIPE_API_KEY", "value": "...", "ping_service": "stripe" }
        """
        if not self._check_origin_allowed():
            self._json(403, {"ok": False, "error": "origin_not_allowed"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw or b"{}")
        except Exception:
            self._json(400, {"ok": False, "error": "invalid_json"})
            return
        key = str(payload.get("key", "")).strip()
        value = str(payload.get("value", ""))
        ping_service = (payload.get("ping_service") or "").strip()
        if not key or not value:
            self._json(400, {"ok": False, "error": "key + value required"})
            return
        # Strict allowlist on keys we're willing to write — refuses anything
        # that doesn't look like a credential env var so a hostile dashboard
        # response can't smuggle in arbitrary writes.
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", key):
            self._json(400, {"ok": False, "error": "key must match [A-Z][A-Z0-9_]{2,63}"})
            return
        repo_root = Path(__file__).resolve().parent.parent
        env_path = repo_root / ".env.agents"
        try:
            existing = env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []
            out: list[str] = []
            seen = False
            for line in existing:
                if "=" in line and not line.strip().startswith("#"):
                    k = line.split("=", 1)[0].strip()
                    if k == key:
                        out.append(f"{key}={value}")
                        seen = True
                        continue
                out.append(line)
            if not seen:
                if out and out[-1].strip() != "":
                    out.append("")
                out.append(f"# Added via dashboard key-paste modal")
                out.append(f"{key}={value}")
            env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
            try:
                if os.name != "nt":
                    os.chmod(env_path, 0o600)
            except Exception:
                pass
        except Exception as e:
            self._json(500, {"ok": False, "error": f"write_failed: {e}"})
            return

        # Best-effort ping so the dashboard's green dot flips immediately.
        if ping_service:
            try:
                # Make sure the just-written key is visible to integration_health
                os.environ[key] = value
                sys.path.insert(0, str(repo_root / "scripts"))
                from integration_health import ping  # type: ignore
                ping(ping_service, status="healthy")
            except Exception:
                pass

        self._json(200, {"ok": True, "key": key, "pinged": ping_service or None})

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "bravo-bridge-chat", "version": "0.1.0"})
            return
        if self.path == "/agents":
            self._json(200, {"ok": True, "agents": all_resolved()})
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path == "/env/set":
            self._handle_env_set()
            return
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
        except urllib.error.HTTPError as e:
            # Translate raw HTTP errors into a friendlier surface for the
            # operator. Provider blips that survived the retry loop in
            # _call_provider land here. We've already retried 3 times, so
            # this is a real outage — not just a transient hiccup.
            try:
                if e.code in _RETRYABLE_HTTP_CODES:
                    emit("error", {
                        "message": "provider_temporarily_unavailable",
                        "detail": f"{provider} returned HTTP {e.code} after {_PROVIDER_RETRY_ATTEMPTS} retries. Try again in a minute.",
                        "retryable": True,
                    })
                else:
                    emit("error", {
                        "message": f"provider_error_{e.code}",
                        "detail": f"{provider} rejected the request with HTTP {e.code}. Check your API key + model in Settings.",
                        "retryable": False,
                    })
                emit("done", {})
            except Exception:
                pass
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
                    # Surface the body to the dashboard so the operator can
                    # expand the read pill inline. Cap at 12KB — the SSE
                    # channel isn't sized for full files, and the UI panel
                    # scrolls anyway. Errors (path outside root, file
                    # missing, etc.) ship through too so the operator sees
                    # *why* the agent's attempt didn't work.
                    body_preview = content if isinstance(content, str) else str(content)
                    truncated = len(body_preview) > 12_288
                    if truncated:
                        body_preview = body_preview[:12_288] + "\n… [truncated]"
                    emit("tool_result", {
                        "name": "read_file",
                        "path": rel_path,
                        "body": body_preview,
                        "truncated": truncated,
                        "error": bool(is_error),
                    })
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

                    def _progress(elapsed_s: int, _key: str = script_key) -> None:
                        # ChatWidget reads tool_progress and surfaces
                        # "still running… (Ns)" so a 90s ceo_dashboard call
                        # doesn't feel broken.
                        emit("tool_progress", {
                            "name": "run_script",
                            "script": _key,
                            "elapsed_s": elapsed_s,
                        })

                    content, is_error = self._safe_run_script(
                        root, script_key, args, confirm, progress_cb=_progress,
                    )
                    output_preview = content if isinstance(content, str) else str(content)
                    truncated = len(output_preview) > 12_288
                    if truncated:
                        output_preview = output_preview[:12_288] + "\n… [truncated]"
                    emit("tool_result", {
                        "name": "run_script",
                        "script": script_key,
                        "args": args,
                        "output": output_preview,
                        "truncated": truncated,
                        "error": bool(is_error),
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": use.get("id"),
                        "content": content,
                        "is_error": is_error,
                    })
                elif tool_name == "list_tools":
                    query = str(tool_input.get("query", "")).lower().strip()
                    mutating_only = tool_input.get("mutating_only")
                    try:
                        limit = max(1, min(200, int(tool_input.get("limit") or 50)))
                    except Exception:
                        limit = 50
                    emit("tool", {"name": "list_tools", "query": query, "mutating_only": mutating_only})
                    matches = []
                    for key, spec in SCRIPT_ALLOWLIST.items():
                        if mutating_only is True and not spec.get("mutating"):
                            continue
                        if mutating_only is False and spec.get("mutating"):
                            continue
                        if query:
                            hay = f"{key} {spec.get('path', '')} {spec.get('help', '')}".lower()
                            if query not in hay:
                                continue
                        matches.append({
                            "key": key,
                            "path": spec.get("path"),
                            "subcmd": spec.get("subcmd"),
                            "mutating": bool(spec.get("mutating")),
                            "help": spec.get("help", ""),
                        })
                    matches.sort(key=lambda m: (m["path"] or "", m["key"]))
                    body = {
                        "total_matches": len(matches),
                        "showing": min(limit, len(matches)),
                        "entries": matches[:limit],
                    }
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": use.get("id"),
                        "content": json.dumps(body, indent=2),
                        "is_error": False,
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
        progress_cb: "Callable[[int], None] | None" = None,
    ) -> tuple[str, bool]:
        """Execute an allowlisted script, capture output. Mutating scripts
        require confirm=True. Cwd is the agent root; path-allowlisted to
        scripts/* inside that root (no path traversal).

        Timeouts:
            - read-only scripts: 180s (status / dashboard / lookup paths
              legitimately take a while when they aggregate Supabase queries).
            - mutating scripts: 60s (anything writing should be fast; a
              minute-long mutation usually means runaway behavior, kill it).

        Progress: if `progress_cb` is provided, it is invoked every ~10s
        with the elapsed seconds while the subprocess is still running.
        The chat surface uses this to show "still running… (Ns)" so a 90s
        ceo_dashboard call doesn't feel broken.
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

        cmd: list = [sys.executable, str(full_path)]
        subcmd = spec.get("subcmd")
        if subcmd:
            cmd.append(subcmd)
        cmd.extend(extra_args)

        timeout_s = 60 if spec.get("mutating") else 180

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
            )
        except Exception as e:
            return f"spawn_failed: {e}", True

        start = time.monotonic()
        next_progress_at = start + 10.0
        try:
            while True:
                try:
                    out, err = proc.communicate(timeout=1.0)
                    break  # process exited
                except subprocess.TimeoutExpired:
                    elapsed = time.monotonic() - start
                    if elapsed >= timeout_s:
                        proc.kill()
                        try:
                            proc.communicate(timeout=2.0)
                        except Exception:
                            pass
                        return (
                            f"timeout: '{script_key}' exceeded {timeout_s}s "
                            f"(read-only cap is 180s, mutating cap is 60s)"
                        ), True
                    if progress_cb is not None and time.monotonic() >= next_progress_at:
                        try:
                            progress_cb(int(elapsed))
                        except Exception:
                            pass  # progress emit is best-effort
                        next_progress_at += 10.0
        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass
            return f"run_failed: {e}", True

        rc = proc.returncode if proc.returncode is not None else -1
        out = (out or "")[-100_000:]
        err = (err or "")[-10_000:]
        cmd_display = " ".join(shlex.quote(c) for c in cmd)
        body = f"$ {cmd_display}\n[exit {rc}]\n--- stdout ---\n{out}"
        if err.strip():
            body += f"\n--- stderr ---\n{err}"
        return body, rc != 0

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
