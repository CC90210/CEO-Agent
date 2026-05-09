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
import shutil
import subprocess
import sys
import threading
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


def _env_files() -> list[Path]:
    """Every env file the bridge searches when resolving a credential.
    Each agent owns its own keys (Bravo: .env.agents in the BEA repo;
    Atlas: .env in CFO-Agent; Maven: .env.agents in CMO-Agent; Aura:
    .env in AURA). The dashboard's /integrations page reflects ALL of
    these so the operator sees green dots regardless of which agent
    owns the underlying key. This is the architectural fix for "I have
    the key but no green dot" — earlier the bridge only scanned its
    own repo and missed Atlas's WISE_API_TOKEN, the CCXT exchange keys,
    OANDA_TOKEN, etc.
    """
    home = Path.home()
    candidates = [
        # Bravo (this repo)
        Path.cwd() / ".env.agents",
        home / "Business-Empire-Agent" / ".env.agents",
        home / ".bravo" / ".env.agents",
        # Atlas (CFO)
        home / "APPS" / "CFO-Agent" / ".env",
        home / "APPS" / "CFO-Agent" / ".env.agents",
        # Maven (CMO)
        home / "CMO-Agent" / ".env.agents",
        home / "CMO-Agent" / ".env",
        # Aura (life/home)
        home / "AURA" / ".env",
        home / "AURA" / ".env.agents",
    ]
    # Resolve duplicates while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in candidates:
        s = str(p).lower()
        if s in seen:
            continue
        seen.add(s)
        out.append(p)
    return out


def _read_env_value(name: str) -> str:
    """Look up a single env var name, then fall back to scanning the
    operator's local secrets file. Never returns the value to a caller other
    than the chat path (which uses it solely for outbound API auth).
    """
    if name in os.environ:
        return os.environ[name]
    for p in _env_files():
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


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------
# Any text headed for ~/.oasis/bridge.log or for the SSE error 'detail' field
# is funnelled through `_redact_secrets()` first. The risk: claude subprocess
# can print env values in error messages (an MCP server failing to load with
# the env var echoed in its error, an API auth failure echoing the bearer
# token, etc). bridge.log is on disk forever; SSE 'detail' is persisted to
# chat_messages.error in Supabase. Both are sensitive surfaces.
#
# Strategy: on each stderr drain, snapshot all key=value pairs from the
# operator's .env.agents files, sort by value-length DESC (so a long key
# can't be partially scrubbed by a substring of another), replace each
# occurrence with [REDACTED:NAME]. Cached for 60s with mtime invalidation
# so editing .env.agents picks up new secrets without restart.

_REDACT_CACHE: dict = {"loaded_at": 0.0, "mtimes": {}, "pairs": []}
_REDACT_TTL_S = 60
# Don't try to redact values shorter than this — false positives explode
# (a 3-char "key" could match common substrings everywhere).
_MIN_REDACTABLE_LEN = 12


def _load_redactable_secrets() -> list[tuple[str, str]]:
    """Return [(env_name, value), ...] sorted by value length DESC. Reads
    every .env.agents we know about and the live process env (process env
    only for keys that look credential-shaped to avoid scrubbing PATH etc).
    """
    now = time.time()
    files = [p for p in _env_files() if p.is_file()]
    current_mtimes = {str(p): p.stat().st_mtime for p in files}
    if (
        _REDACT_CACHE["pairs"]
        and now - _REDACT_CACHE["loaded_at"] < _REDACT_TTL_S
        and current_mtimes == _REDACT_CACHE["mtimes"]
    ):
        return _REDACT_CACHE["pairs"]

    pairs: dict[str, str] = {}
    for p in files:
        try:
            for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if not k or not v or len(v) < _MIN_REDACTABLE_LEN:
                    continue
                if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", k):
                    continue
                pairs[k] = v
        except Exception:
            continue

    # Also pull credential-shaped values from live os.environ — covers
    # anything injected at bridge boot but missing from .env.agents.
    cred_pat = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|API|DSN|WEBHOOK)$")
    for k, v in os.environ.items():
        if not isinstance(v, str) or len(v) < _MIN_REDACTABLE_LEN:
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", k):
            continue
        if cred_pat.search(k):
            pairs.setdefault(k, v)

    sorted_pairs = sorted(pairs.items(), key=lambda kv: -len(kv[1]))
    _REDACT_CACHE["pairs"] = sorted_pairs
    _REDACT_CACHE["loaded_at"] = now
    _REDACT_CACHE["mtimes"] = current_mtimes
    return sorted_pairs


def _redact_secrets(text: str) -> str:
    if not text:
        return text
    try:
        pairs = _load_redactable_secrets()
    except Exception:
        return text
    out = text
    for name, value in pairs:
        if value and value in out:
            out = out.replace(value, f"[REDACTED:{name}]")
    return out


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
# [DEPRECATED — REMOVE AFTER 2026-05-14]: the retry constants above + the
# _call_provider / _run_chat methods below + READ_FILE_TOOL / RUN_SCRIPT_TOOL
# / LIST_TOOLS_TOOL definitions are only reachable when the operator sets
# OASIS_CHAT_LEGACY=1. Default chat path is _run_chat_via_claude (Claude
# Code subprocess). Retire one week post chunk H ship date once the new
# path proves stable in production.


# ──────────────────────────────────────────────────────────────────────
# Claude Code tool → SSE event translation
# ──────────────────────────────────────────────────────────────────────
# Claude Code emits native tool names: Read, Write, Edit, Bash, Glob,
# Grep, MultiEdit, NotebookEdit, WebFetch, etc., plus mcp__<server>__<tool>.
# ChatWidget historically rendered our two custom tools (read_file,
# run_script). We map the most common Claude Code tools to friendly SSE
# shapes so existing UI rendering keeps working, and ship a generic
# fallback for everything else.
def _map_tool_use(name: str, tinput: dict) -> dict:
    """Translate a Claude Code tool_use block into the SSE 'tool' event
    shape. Returns at least {name, summary} so ChatWidget can render a
    pill even for unknown tool types."""
    if name == "Read":
        return {
            "name": "read_file",
            "path": str(tinput.get("file_path") or ""),
            "raw_name": name,
        }
    if name in ("Bash", "BashOutput"):
        return {
            "name": "run_script",
            "script": "bash",
            "args": [str(tinput.get("command") or "")[:200]],
            "confirm": True,
            "raw_name": name,
        }
    if name in ("Edit", "MultiEdit", "NotebookEdit"):
        path = str(tinput.get("file_path") or tinput.get("notebook_path") or "")
        return {
            "name": "edit_file",
            "path": path,
            "raw_name": name,
            "summary": f"editing {path}",
        }
    if name == "Write":
        return {
            "name": "write_file",
            "path": str(tinput.get("file_path") or ""),
            "raw_name": name,
            "summary": f"writing {tinput.get('file_path') or ''}",
        }
    if name == "Glob":
        return {
            "name": "glob",
            "pattern": str(tinput.get("pattern") or ""),
            "raw_name": name,
            "summary": f"glob {tinput.get('pattern') or ''}",
        }
    if name == "Grep":
        return {
            "name": "grep",
            "pattern": str(tinput.get("pattern") or "")[:80],
            "raw_name": name,
            "summary": f"grep {tinput.get('pattern') or ''}",
        }
    if name == "WebFetch":
        return {
            "name": "web_fetch",
            "url": str(tinput.get("url") or ""),
            "raw_name": name,
        }
    if name.startswith("mcp__"):
        # mcp__playwright__browser_navigate, mcp__supabase__execute_sql, etc.
        parts = name.split("__")
        server = parts[1] if len(parts) > 1 else "mcp"
        tool = parts[2] if len(parts) > 2 else name
        return {
            "name": "mcp_call",
            "server": server,
            "tool": tool,
            "raw_name": name,
            "summary": f"{server} · {tool}",
        }
    # Generic fallback — ChatWidget will render a tool pill with the raw name.
    return {
        "name": "tool",
        "raw_name": name,
        "summary": name,
    }


_MSYS_NOISE_PATTERNS = [
    # Git Bash / MSYS startup noise that lands in every subprocess's stderr
    # when claude spawns `bash -c …` on Windows. None of it is the actual
    # tool output — it's profile.d / fstab / mtab cleanup that's irrelevant
    # to the operator and pollutes both the chat UI and the agent's
    # context tokens. CC reported confusion seeing /etc/hosts permission
    # errors after a clean email send.
    re.compile(r"^'[A-Z]:\\WINDOWS\\[^']+'\s*->\s*'/etc/[^']+'\s*$"),
    re.compile(r"^ln:\s*failed to create symbolic link\s+'/etc/mtab'.*$"),
    re.compile(r"^/usr/bin/cp:\s*cannot create regular file\s+'/etc/[^']+':\s*Permission denied\s*$"),
    re.compile(r"^rm:\s*cannot remove\s+'/etc/post-install/[^']+':\s*Permission denied\s*$"),
    re.compile(r"^\s*0\s*\[main\]\s+\S+\s+\d+\s+(child_copy|dofork|fork:).*$"),
    re.compile(r"^/usr/bin/bash:\s*fork:\s*(retry:\s*)?Resource temporarily unavailable\s*$"),
]


def _strip_msys_noise(text: str) -> str:
    """Remove well-known Git-Bash-on-Windows startup noise from a tool
    output body. Conservative: only strips lines that exactly match one
    of the known noise patterns, leaves everything else alone (including
    blank lines that follow). If the resulting body is empty after
    stripping, return the original — never erase a tool's actual output.
    """
    if not text or "\\WINDOWS\\" not in text and "/etc/" not in text and "[main]" not in text:
        # Fast path: nothing in the body matches any of the noise
        # signatures, skip the per-line walk entirely.
        return text
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        if any(pat.match(line) for pat in _MSYS_NOISE_PATTERNS):
            continue
        kept.append(line)
    cleaned = "\n".join(kept)
    return cleaned if cleaned.strip() else text


def _map_tool_result(block: dict, parent: dict) -> dict:
    """Translate a Claude Code tool_result block into the SSE 'tool_result'
    event shape. The block has tool_use_id + content; we surface the
    content as a body string the UI can show in the expandable pill."""
    raw_content = block.get("content")
    body: str
    if isinstance(raw_content, str):
        body = raw_content
    elif isinstance(raw_content, list):
        # Anthropic-style content block list: [{type: "text", text: "..."}]
        parts = []
        for c in raw_content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(str(c.get("text") or ""))
            else:
                parts.append(str(c))
        body = "\n".join(parts)
    else:
        body = json.dumps(raw_content)[:1000] if raw_content is not None else ""

    # Strip Git Bash on Windows startup noise BEFORE redaction or
    # truncation — irrelevant to the operator, eats context budget.
    body = _strip_msys_noise(body)

    truncated = len(body) > 12_288
    if truncated:
        body = body[:12_288] + "\n… [truncated]"

    return {
        "name": "tool_result",
        "tool_use_id": block.get("tool_use_id"),
        "body": body,
        "output": body,  # ChatWidget reads either body (read_file) or output (run_script)
        "truncated": truncated,
        "error": bool(block.get("is_error")),
    }


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
        # Optional Claude Code session id — when present we pass --resume
        # so the agent skips the cold context-load on subsequent turns.
        # First turn omits it; we mint a fresh session below and the
        # dashboard captures the new id from the 'session' SSE event.
        resume_session_id = payload.get("session_id")
        if isinstance(resume_session_id, str) and resume_session_id.strip():
            resume_session_id = resume_session_id.strip()
        else:
            resume_session_id = None

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

        # Default chat path: spawn `claude` CLI as a subprocess, stream its
        # JSON output as SSE. Identical pattern to telegram_agent.js. Gives
        # the dashboard chat the FULL Claude Code harness (Read, Write,
        # Edit, Bash, Glob, Grep, MultiEdit, every MCP server, every skill)
        # instead of the hand-rolled 3-tool loop we used to ship.
        #
        # Legacy path (raw /v1/messages with READ_FILE_TOOL etc.) stays
        # accessible behind OASIS_CHAT_LEGACY=1 for one-pass rollback.
        use_legacy = os.environ.get("OASIS_CHAT_LEGACY") == "1"

        # ---- Stream SSE back -----------------------------------------------
        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self._set_cors()
        self.end_headers()

        def emit(event: str, data: dict) -> None:
            try:
                self.wfile.write(
                    f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
                )
                self.wfile.flush()
            except Exception:
                pass  # Client disconnected — stop trying to write.

        if use_legacy:
            # Old path — keep working until the Claude subprocess flow is
            # battle-tested. Resolve provider/key/model the legacy way.
            provider, api_key, model = _resolve_provider()
            if provider == "none" or not api_key:
                emit("error", {
                    "message": "no_provider_key",
                    "detail": "No OPENROUTER_API_KEY or ANTHROPIC_API_KEY in .env.agents. Set OASIS_CHAT_LEGACY=0 to use Claude Code subprocess instead.",
                })
                emit("done", {})
                return
            try:
                self._run_chat(agent, root, entry, provider, api_key, model, messages, emit)
            except urllib.error.HTTPError as e:
                if e.code in _RETRYABLE_HTTP_CODES:
                    emit("error", {
                        "message": "provider_temporarily_unavailable",
                        "detail": f"{provider} returned HTTP {e.code} after {_PROVIDER_RETRY_ATTEMPTS} retries.",
                        "retryable": True,
                    })
                else:
                    emit("error", {
                        "message": f"provider_error_{e.code}",
                        "detail": f"{provider} rejected the request with HTTP {e.code}.",
                        "retryable": False,
                    })
                emit("done", {})
            except Exception as e:
                emit("error", {"message": _redact_secrets(f"chat_loop_failed: {e}")})
                emit("done", {})
            return

        # ---- Claude Code subprocess path (default) -------------------------
        try:
            self._run_chat_via_claude(agent, root, messages, emit, resume_session_id)
        except FileNotFoundError as e:
            emit("error", {
                "message": "claude_cli_not_found",
                "detail": (
                    "The `claude` CLI is not on PATH. Install Claude Code "
                    "(https://claude.com/claude-code) and re-run "
                    "`bravo bridge install`. Falling back: set "
                    "OASIS_CHAT_LEGACY=1 to use the raw API path."
                ),
            })
            emit("done", {})
        except Exception as e:
            emit("error", {"message": _redact_secrets(f"chat_loop_failed: {e}")})
            emit("done", {})

    # ──────────────────────────────────────────────────────────────────
    # CLAUDE CODE SUBPROCESS PATH (default)
    # ──────────────────────────────────────────────────────────────────
    # Replaces the hand-rolled /v1/messages loop with `spawn('claude', ...)`,
    # same architecture telegram_agent.js uses. The dashboard chat now has
    # the full Claude Code harness — Read/Write/Edit/Bash/Glob/Grep/etc.
    # plus every MCP server the operator has configured.
    #
    # Translation map (Claude Code stream-json → existing SSE shape):
    #   system/init               -> session
    #   assistant.message text    -> delta (one event per content block)
    #   assistant.message tool_use-> tool (name, input)
    #   user.message tool_result  -> tool_result (output)
    #   result/success            -> done (+ usage)
    #   anything else             -> ignored / logged
    def _run_chat_via_claude(
        self,
        agent: str,
        root: Path,
        messages: list[dict],
        emit: Callable[[str, dict], None],
        resume_session_id: str | None = None,
    ) -> None:
        """Spawn `claude --print --output-format=stream-json` and pipe the
        operator's latest message in. Translate stream-json events to the
        SSE shape ChatWidget already speaks.

        Session continuity: we map each dashboard chat session to a
        Claude Code session-id (UUID). Subsequent messages in the same
        session pass --resume so Claude Code reads its persisted history.
        For first messages we let Claude Code mint the session itself.
        """
        # The latest user message is the prompt. Claude Code maintains the
        # rest of the conversation via session persistence.
        last_user = next(
            (m for m in reversed(messages) if m.get("role") == "user"), None
        )
        if not last_user:
            emit("error", {"message": "no_user_message_in_payload"})
            emit("done", {})
            return
        prompt_text = str(last_user.get("content") or "").strip()
        if not prompt_text:
            emit("error", {"message": "empty_user_message"})
            emit("done", {})
            return

        # Resolve the claude binary. Mirror telegram_agent.js's discovery:
        # prefer `claude` in PATH; fall back to ~/.local/bin/claude.exe on
        # Windows when nvm-global isn't shimmed.
        claude_bin = shutil.which("claude")
        if not claude_bin and os.name == "nt":
            home = Path.home()
            candidates = [
                home / ".local" / "bin" / "claude.exe",
                home / "AppData" / "Roaming" / "npm" / "claude.cmd",
            ]
            for c in candidates:
                if c.is_file():
                    claude_bin = str(c)
                    break
        if not claude_bin:
            raise FileNotFoundError("claude CLI not on PATH")

        # Build args — copying telegram's pattern + adding stream-json
        # output so we get incremental events for SSE.
        args = [
            claude_bin,
            "-p", prompt_text,
            # bypassPermissions auto-approves MCP tool calls in addition to
            # edits. acceptEdits prompts for MCP tools, which hangs forever
            # because stdin is DEVNULL. Bridge runs as the operator in the
            # operator's repos, so the trust boundary already permits this.
            "--permission-mode", "bypassPermissions",
            "--output-format", "stream-json",
            "--verbose",  # required when --output-format=stream-json
            "--include-partial-messages",
            "--max-turns", "12",
            "--setting-sources", "project,local",
        ]
        # Latency win: if the dashboard provided a session_id from a prior
        # turn, pass --resume so claude skips cold context-load. First turn
        # mints a new session (claude assigns the id and we surface it via
        # the 'session' SSE event below).
        if resume_session_id:
            args.extend(["--resume", resume_session_id])

        # Spawn env — same approach as telegram_agent. Inherit current env,
        # set non-interactive flags so claude doesn't try to render TTY UI.
        env = dict(os.environ)
        env.update({
            "CI": "true",
            "NONINTERACTIVE": "true",
            "PAGER": "cat",
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
        })

        # Synthetic status pre-spawn so the dashboard can show "starting Atlas
        # in CFO-Agent…" instantly, before claude's cold start (~10-30s).
        emit("agent_status", {
            "phase": "spawning",
            "agent": agent,
            "cwd": str(root),
        })

        try:
            proc = subprocess.Popen(
                args,
                cwd=str(root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                shell=False,
                env=env,
                # On Windows, hide the console window the spawn would otherwise pop.
                creationflags=(0x08000000 if os.name == "nt" else 0),  # CREATE_NO_WINDOW
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,  # line-buffered
            )
        except Exception as e:
            emit("error", {"message": _redact_secrets(f"claude_spawn_failed: {e}")})
            emit("done", {})
            return

        # Subprocess is alive — flip from "spawning" to "thinking" so the UI
        # can swap the elapsed-time counter from "starting…" to "thinking…".
        emit("agent_status", {"phase": "thinking"})

        # Continuously drain stderr in a thread so on a non-zero exit we
        # have the FULL claude error message, not just whatever happens
        # to be in the pipe at exit time. The previous code did a lazy
        # `proc.stderr.read()` after wait() which could miss everything
        # because stderr was already drained / EOF-closed. We also tee
        # to ~/.oasis/bridge.log so CC can inspect the full session
        # output even if SSE truncated it.
        stderr_chunks: list[str] = []
        stderr_log_path = Path.home() / ".oasis" / "bridge.log"
        try:
            stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        def _drain_stderr() -> None:
            try:
                if proc.stderr is None:
                    return
                with stderr_log_path.open("a", encoding="utf-8", errors="replace") as logf:
                    logf.write(f"\n\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} agent={agent} pid={proc.pid} ===\n")
                    for line in proc.stderr:
                        # Redact known secrets BEFORE both in-memory append
                        # AND disk log write — bridge.log lives on disk
                        # indefinitely; stderr_chunks gets sent over SSE
                        # and persisted to chat_messages.error.
                        safe = _redact_secrets(line)
                        stderr_chunks.append(safe)
                        try:
                            logf.write(safe)
                            logf.flush()
                        except Exception:
                            pass
            except Exception:
                pass

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True, name="bridge-stderr-drain")
        stderr_thread.start()

        # Read line-by-line. Each line is a complete JSON event.
        emitted_session = False
        accumulated_text = ""
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue  # Some lines are not JSON (e.g. early diagnostic)

                etype = ev.get("type")
                subtype = ev.get("subtype")

                # 1. Session init -> emit session event so ChatWidget can store id.
                if etype == "system" and subtype == "init":
                    if not emitted_session:
                        emit("session", {"session_id": ev.get("session_id")})
                        emitted_session = True
                    continue

                # 2. Skip hook noise — these are SessionStart/PreToolUse/etc.
                if etype == "system" and subtype and subtype.startswith("hook_"):
                    continue

                # 3. Assistant turn — extract text + tool_use blocks.
                if etype == "assistant":
                    msg = ev.get("message") or {}
                    content = msg.get("content") or []
                    for block in content:
                        btype = block.get("type")
                        if btype == "text":
                            text = block.get("text") or ""
                            if text:
                                # Claude Code with --include-partial-messages
                                # emits incremental text. Forward each chunk
                                # as a delta so the UI streams.
                                emit("delta", {"text": text})
                                accumulated_text += text
                        elif btype == "tool_use":
                            tname = block.get("name") or "tool"
                            tid = block.get("id") or ""
                            tinput = block.get("input") or {}
                            mapped = _map_tool_use(tname, tinput)
                            mapped["tool_use_id"] = tid
                            emit("tool", mapped)
                    continue

                # 4. User turn — only the tool_result blocks matter to us.
                if etype == "user":
                    msg = ev.get("message") or {}
                    content = msg.get("content") or []
                    if isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") == "tool_result":
                                tres = _map_tool_result(block, ev)
                                emit("tool_result", tres)
                    continue

                # 5. Final result -> done.
                if etype == "result":
                    usage = ev.get("usage") or {}
                    emit("done", {
                        "stop_reason": ev.get("stop_reason"),
                        "input_tokens": usage.get("input_tokens"),
                        "output_tokens": usage.get("output_tokens"),
                        "total_cost_usd": ev.get("total_cost_usd"),
                        "num_turns": ev.get("num_turns"),
                    })
                    continue

                # 6. Anything else (e.g. system/error) — surface as error.
                if etype == "system" and subtype == "error":
                    raw_detail = ev.get("message") or json.dumps(ev)[:200]
                    emit("error", {
                        "message": "claude_subprocess_error",
                        "detail": _redact_secrets(str(raw_detail)),
                    })

            rc = proc.wait(timeout=5)
            if rc != 0:
                # Wait briefly for the stderr drainer to finish reading
                # whatever's still in the pipe — claude may have written
                # error context AFTER exiting.
                stderr_thread.join(timeout=2)
                stderr_full = "".join(stderr_chunks).strip()
                # Heuristic: detect stale --resume session id and tell the
                # user clearly. claude prints something like "Session
                # not found" or "Could not find session" when the resume
                # id is missing from its session storage.
                detail = stderr_full or "claude subprocess exited with non-zero code"
                if resume_session_id and (
                    "session not found" in stderr_full.lower()
                    or "could not find session" in stderr_full.lower()
                    or "no such session" in stderr_full.lower()
                ):
                    detail = (
                        f"Stale session id ({resume_session_id[:8]}…). "
                        "The dashboard had a session id from a previous "
                        "chat that claude no longer recognizes. Click "
                        "the refresh icon in the chat header to start a "
                        "fresh session and try again.\n\n--- claude stderr ---\n"
                        + stderr_full
                    )
                emit("error", {
                    "message": f"claude_exit_{rc}",
                    "detail": detail[:2000],  # bumped from 500 - users want to see the actual error
                    "log_path": str(stderr_log_path),
                })
                # Make sure the client sees an end signal.
                if not accumulated_text:
                    emit("done", {})
        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass
            stderr_thread.join(timeout=1)
            stderr_full = "".join(stderr_chunks).strip()
            emit("error", {
                "message": _redact_secrets(f"claude_stream_failed: {e}"),
                "detail": stderr_full[:2000] if stderr_full else None,
                "log_path": str(stderr_log_path),
            })
            emit("done", {})

    # [DEPRECATED — REMOVE AFTER 2026-05-14] Legacy raw /v1/messages path.
    # Reachable only via OASIS_CHAT_LEGACY=1. Default chat path is
    # _run_chat_via_claude above. Cut this whole method + _call_provider
    # + READ_FILE_TOOL/RUN_SCRIPT_TOOL/LIST_TOOLS_TOOL after the new path
    # proves stable for one week.
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


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard pairing + heartbeat (in-process, no separate `_loop` daemon)
# ──────────────────────────────────────────────────────────────────────────────
# The /devices section of the dashboard reads bridge_pairings.last_seen_at to
# decide whether a machine is online. Previously only the legacy `_loop` ping
# helper wrote there — but cmd_install registers bridge_chat_server as the
# auto-start, not _loop. So the bridge would run forever without the
# dashboard ever seeing it. Fix: chat server self-pairs on first boot via the
# HMAC secret already in .env.agents (issued by n8n_webhook_secret.py
# --save-env), then starts a daemon thread that pings /api/bridge/ping every
# 60s with the bearer token.

_HEARTBEAT_INTERVAL_S = 60.0
_PAIR_TIMEOUT_S = 8.0
_OASIS_DIR = Path.home() / ".oasis"
_BRIDGE_TOKEN_PATH = _OASIS_DIR / "bridge_token"


def _machine_fingerprint() -> str:
    """Stable per-machine identifier for the bridge_pairings row.
    Operator can connect multiple machines (Windows + Mac + Linux);
    each gets its own row keyed on this fingerprint.
    """
    import hashlib
    import platform
    parts = [
        platform.node() or "unknown-host",
        platform.system() or "unknown-os",
        platform.machine() or "unknown-arch",
    ]
    seed = "|".join(parts)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def _machine_label() -> str:
    import platform
    host = platform.node() or "machine"
    os_name = {"Darwin": "Mac", "Windows": "Windows", "Linux": "Linux"}.get(
        platform.system(), platform.system() or "Machine"
    )
    return f"{host} ({os_name})"


def _self_pair_if_needed() -> str | None:
    """Acquire a bridge_token. If ~/.oasis/bridge_token exists, return it.
    Otherwise POST to /api/auth/pair with HMAC headers (x-oasis-profile-id
    + x-oasis-secret), persist the returned token, return it. Returns None
    if pairing isn't possible (no HMAC creds, network down, etc.) — caller
    will skip heartbeats and the chat server still serves /chat fine.
    """
    try:
        if _BRIDGE_TOKEN_PATH.is_file():
            existing = _BRIDGE_TOKEN_PATH.read_text(encoding="utf-8").strip()
            if existing:
                return existing
    except Exception:
        pass

    profile_id = _read_env_value("OASIS_PROFILE_ID").strip()
    hmac_secret = _read_env_value("OASIS_OUTBOUND_HMAC_SECRET").strip()
    dashboard_url = (
        _read_env_value("OASIS_DASHBOARD_URL")
        or "https://agent-dashboard-cc90210.vercel.app"
    ).rstrip("/")
    if not profile_id or not hmac_secret:
        print(
            "[bridge] no OASIS_PROFILE_ID / OASIS_OUTBOUND_HMAC_SECRET — "
            "skipping self-pair (run `python scripts/n8n_webhook_secret.py "
            "issue --profile-email <you> --save-env` to enable).",
            file=sys.stderr,
        )
        return None

    payload = {
        "machine": {
            "label": _machine_label(),
            "fingerprint": _machine_fingerprint(),
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{dashboard_url}/api/auth/pair",
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-oasis-profile-id": profile_id,
            "x-oasis-secret": hmac_secret,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_PAIR_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception as exc:
        print(f"[bridge] self-pair failed: {exc}", file=sys.stderr)
        return None

    token = (data.get("bridge") or {}).get("token")
    if not token:
        print(f"[bridge] pair response missing token: {data}", file=sys.stderr)
        return None

    try:
        _OASIS_DIR.mkdir(parents=True, exist_ok=True)
        _BRIDGE_TOKEN_PATH.write_text(token, encoding="utf-8")
        if os.name != "nt":
            try:
                os.chmod(_BRIDGE_TOKEN_PATH, 0o600)
            except Exception:
                pass
    except Exception as exc:
        print(f"[bridge] couldn't persist bridge_token: {exc}", file=sys.stderr)

    print(f"[bridge] paired with dashboard as {_machine_label()}", file=sys.stderr)
    return token


# env_key → service_slug fallback mapping. The CANONICAL source is
# apps/command-center/lib/integrations-registry.ts — exposed via
# GET /api/integrations/registry so the bridge can fetch it at runtime.
# This dict is the cache the bridge uses when the dashboard is
# unreachable (offline / startup race). Adding a NEW api_key
# integration: register it in lib/integrations-registry.ts (the source
# of truth); update this fallback map only if you want it to work on
# a fully-offline bridge.
_ENV_KEY_TO_SERVICE_FALLBACK = {
    # Core / hosting
    "VERCEL_TOKEN": "vercel",
    "CLOUDFLARE_API_TOKEN": "cloudflare",
    "Cloudflare_token": "cloudflare",   # CC uses this casing — keep as alias
    "GITHUB_TOKEN": "github",
    "GITHUB_PERSONAL_ACCESS_TOKEN": "github",
    "HOSTINGER_API_KEY": "hostinger",
    "SUPABASE_ACCESS_TOKEN": "supabase",
    "BRAVO_SUPABASE_URL": "supabase",
    # Comms — single GMAIL_APP_PASSWORD covers the entire Google
    # Workspace surface via scripts/google_tool.py.
    "GMAIL_APP_PASSWORD": "gws",
    "TELEGRAM_BOT_TOKEN": "telegram",
    # Finance / trading (Atlas reads these from CFO-Agent/.env — the
    # bridge now scans sibling agent repos, see _env_files()).
    "STRIPE_API_KEY": "stripe",
    "STRIPE_SECRET_KEY": "stripe",
    "EXCHANGE_API_KEY": "kraken",       # CCXT-style — DEFAULT_EXCHANGE picks the venue
    "WISE_API_TOKEN": "wise",
    "OANDA_TOKEN": "oanda",
    "ALPHA_VANTAGE_KEY": "alpha_vantage",
    "FINNHUB_KEY": "finnhub",
    "FMP_KEY": "fmp",
    "NEWSAPI_KEY": "newsapi",
    # Content + scheduling
    "LATE_API_KEY": "late",
    "ELEVENLABS_API_KEY": "elevenlabs",
    # Data + automation
    "N8N_API_KEY": "n8n_inbound",
    "TURSO_AUTH_TOKEN": "turso",
    "TURSO_API_KEY": "turso",            # CC uses TURSO_API_KEY in .env.agents
    "NOTION_API_KEY": "notion",
    "OBSIDIAN_API_KEY": "obsidian",
    "FIRECRAWL_API_KEY": "firecrawl",
    # AI providers — these power CLOUD-MODE chat for clients who don't
    # have a Claude Code subscription. Bravo's local bridge invokes
    # `claude` CLI directly; the cloud path falls back to whichever of
    # these keys the operator has saved.
    "OPENROUTER_API_KEY": "openrouter",
    "ANTHROPIC_API_KEY": "anthropic",
    "OPENAI_API_KEY": "openai_codex",
    "GEMINI_API_KEY": "google_ai",
    "GOOGLE_AI_API_KEY": "google_ai",
}

# Three-layer registry cache:
#   1. In-memory cache (5min TTL) — heartbeat hot path, no I/O.
#   2. Disk cache (~/.oasis/registry.json) — survives bridge restart;
#      reload-on-startup means the bridge is functional even when the
#      dashboard is briefly unreachable at boot.
#   3. Hardcoded fallback — emergency last-resort if dashboard has
#      NEVER been reached + no disk cache exists (fresh install,
#      offline first run).
# This makes the canonical source (lib/integrations-registry.ts) the
# real single source of truth in steady state.
_REGISTRY_CACHE: dict = {"map": None, "fetched_at": 0.0}
_REGISTRY_TTL_S = 300
_REGISTRY_CACHE_FILE = Path.home() / ".oasis" / "registry.json"


def _load_disk_registry() -> dict | None:
    try:
        if _REGISTRY_CACHE_FILE.is_file():
            data = json.loads(_REGISTRY_CACHE_FILE.read_text(encoding="utf-8"))
            m = data.get("map")
            if isinstance(m, dict) and m:
                return m
    except Exception:
        return None
    return None


def _save_disk_registry(m: dict) -> None:
    try:
        _REGISTRY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _REGISTRY_CACHE_FILE.write_text(
            json.dumps({"map": m, "saved_at": time.time()}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass  # Disk cache is best-effort; in-memory still works.


def _fetch_registry_map() -> dict:
    """Pull the env_key -> service map from the dashboard with three-layer
    fallback (in-memory cache -> disk cache -> hardcoded). The in-memory
    cache is hot-path; disk cache survives restarts; hardcoded only fires
    on fresh install with no network.
    """
    now = time.time()
    cached = _REGISTRY_CACHE.get("map")
    if cached and now - _REGISTRY_CACHE["fetched_at"] < _REGISTRY_TTL_S:
        return cached

    # Build the union of (dashboard registry) ∪ (hardcoded fallback). The
    # dashboard exposes ONE canonical env_key per service, but operators
    # commonly use aliases (GITHUB_TOKEN vs GITHUB_PERSONAL_ACCESS_TOKEN,
    # CLOUDFLARE_API_TOKEN vs Cloudflare_token, TURSO_AUTH_TOKEN vs
    # TURSO_API_KEY, etc.). The fallback dict carries those aliases so
    # the integrations page lights up regardless of which spelling the
    # operator's .env.agents uses. Conflicts: dashboard wins (canonical
    # source); fallback only contributes alias keys not already mapped.
    dashboard_url = (
        _read_env_value("OASIS_DASHBOARD_URL")
        or "https://agent-dashboard-cc90210.vercel.app"
    ).rstrip("/")
    dash_map: dict = {}
    try:
        req = urllib.request.Request(
            f"{dashboard_url}/api/integrations/registry",
            headers={"accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for e in data.get("entries", []):
            env_key = e.get("env_key")
            service = e.get("service")
            if env_key and service:
                dash_map[env_key] = service
    except Exception:
        dash_map = {}

    if dash_map:
        merged: dict = dict(_ENV_KEY_TO_SERVICE_FALLBACK)
        merged.update(dash_map)  # dashboard wins on collision
        _REGISTRY_CACHE["map"] = merged
        _REGISTRY_CACHE["fetched_at"] = now
        _save_disk_registry(merged)
        return merged

    # Dashboard unreachable. Try disk cache.
    disk = _load_disk_registry()
    if disk:
        # Layer the static fallback under the disk cache so newly added
        # aliases are honored even when the dashboard is down.
        merged = dict(_ENV_KEY_TO_SERVICE_FALLBACK)
        merged.update(disk)
        return merged

    # Last resort: hardcoded fallback. Fresh install, offline.
    return _ENV_KEY_TO_SERVICE_FALLBACK


def _services_from_env_keys() -> dict[str, dict]:
    """Scan known env_keys present in the operator's environment / .env.agents
    and report each as 'healthy' on the dashboard. CC's mental model: a key
    present means the integration is configured. Real per-call pings still
    overwrite this with degraded/down if the service actually fails.
    Pulls the env_key -> service map from the dashboard (canonical source);
    falls back to a hardcoded copy if the dashboard is unreachable.
    """
    services: dict[str, dict] = {}
    seen_services: set[str] = set()
    registry = _fetch_registry_map()
    for env_key, service in registry.items():
        if service in seen_services:
            continue
        val = _read_env_value(env_key)
        if val and val.strip():
            services[service] = {
                "status": "healthy",
                "metadata": {"via": "env_key_present", "env_key": env_key},
            }
            seen_services.add(service)
    return services


def _services_from_local_installs() -> dict[str, dict]:
    """Probe local-install integrations (ffmpeg, whisper, IBKR TWS,
    browser_harness, playwright) and report healthy/down based on whether
    the underlying binary or service is present. Without this, services
    with connection_kind="local_install" never light up green even when
    the operator has them installed — there's no env_key for the bridge
    to scan against.
    """
    out: dict[str, dict] = {}

    # ffmpeg — `ffmpeg -version` exits 0 if installed.
    try:
        rc = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=4,
        )
        if rc.returncode == 0:
            ver = rc.stdout.split("\n", 1)[0][:80]
            out["ffmpeg"] = {"status": "healthy", "metadata": {"via": "local_probe", "version": ver}}
    except Exception:
        pass

    # whisper — Python module check; fall back to CLI.
    if "whisper" not in out:
        try:
            rc = subprocess.run(
                [sys.executable, "-c", "import whisper; print(whisper.__file__)"],
                capture_output=True, text=True, timeout=6,
            )
            if rc.returncode == 0 and rc.stdout.strip():
                out["whisper"] = {"status": "healthy", "metadata": {"via": "local_probe", "import": "ok"}}
        except Exception:
            pass
    if "whisper" not in out:
        try:
            rc = subprocess.run(
                ["whisper", "--help"], capture_output=True, text=True, timeout=4,
            )
            if rc.returncode == 0:
                out["whisper"] = {"status": "healthy", "metadata": {"via": "local_probe", "cli": "ok"}}
        except Exception:
            pass

    # Interactive Brokers — TWS desktop opens a socket on 7497 (paper)
    # or 7496 (live). If either is reachable on localhost, IBKR is up.
    try:
        import socket as _socket
        for port in (7497, 7496):
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    out["interactive_brokers"] = {
                        "status": "healthy",
                        "metadata": {"via": "local_probe", "port": port},
                    }
                    break
    except Exception:
        pass

    # Browser Harness — checks if Chrome/Edge launched with --remote-debugging-port
    # is reachable. Default ports: 9222 (Chrome), 9223 (Edge).
    try:
        import socket as _socket
        for port in (9222, 9223):
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    out["browser_harness"] = {
                        "status": "healthy",
                        "metadata": {"via": "local_probe", "cdp_port": port},
                    }
                    break
    except Exception:
        pass

    # Playwright — `npx playwright --version` is heavy; just check the
    # `playwright` binary on PATH.
    try:
        rc = subprocess.run(
            ["playwright", "--version"], capture_output=True, text=True, timeout=4,
        )
        if rc.returncode == 0:
            out["playwright"] = {"status": "healthy", "metadata": {"via": "local_probe", "version": rc.stdout.strip()[:40]}}
    except Exception:
        pass

    return out


def _heartbeat_once(token: str) -> bool:
    dashboard_url = (
        _read_env_value("OASIS_DASHBOARD_URL")
        or "https://agent-dashboard-cc90210.vercel.app"
    ).rstrip("/")
    # env-key-present services + locally-installed services. Both
    # contribute to /integrations green dots; together they cover the
    # full set of integrations the bridge can vouch for.
    services = _services_from_env_keys()
    services.update(_services_from_local_installs())
    body = json.dumps({"services": services}).encode("utf-8")
    req = urllib.request.Request(
        f"{dashboard_url}/api/bridge/ping",
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_PAIR_TIMEOUT_S) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            # Token revoked or rotated — drop it so next loop self-pairs again.
            try:
                _BRIDGE_TOKEN_PATH.unlink(missing_ok=True)
            except Exception:
                pass
        return False
    except Exception:
        return False


def _heartbeat_loop() -> None:
    """Daemon thread. Pings /api/bridge/ping every 60s so the dashboard's
    /devices and Today header show the machine as online. Re-pairs if the
    token gets nixed (e.g. operator revokes it from /settings)."""
    while True:
        token = _self_pair_if_needed()
        if token:
            ok = _heartbeat_once(token)
            if not ok:
                # Could be transient — try again next interval. If the token
                # was wiped above, _self_pair_if_needed will mint a fresh one.
                pass
        time.sleep(_HEARTBEAT_INTERVAL_S)


def _start_heartbeat_thread() -> None:
    import threading
    t = threading.Thread(target=_heartbeat_loop, name="bridge-heartbeat", daemon=True)
    t.start()


def serve_forever() -> int:
    """Entry point for `bravo bridge serve`."""
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), _ChatHandler)
    print(f"oasis-bridge-chat listening on http://127.0.0.1:{PORT}")
    print(f"  agents resolvable: {sum(1 for v in all_resolved().values() if v['root'])}/5")
    if os.environ.get("OASIS_BRIDGE_NO_HEARTBEAT") != "1":
        _start_heartbeat_thread()
        print("  heartbeat: every 60s -> /api/bridge/ping")
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
