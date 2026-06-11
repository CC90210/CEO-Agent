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

import hashlib
import hmac
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import threading
import tempfile
from contextlib import contextmanager
from pathlib import Path as _Path


# Critical Python modules the bridge's chat tools rely on. If ANY of
# these fail to import at startup, the self-heal below runs
# `pip install -r requirements.txt`. The list is intentionally short
# and biased toward third-party packages that don't transitively depend
# on each other — so a missing one is a strong signal the venv hasn't
# been kept in sync with requirements.txt at all.
#
# Add to this list when a new third-party dep becomes load-bearing for
# a chat tool. Stdlib modules NEVER belong here.
_CRITICAL_BRIDGE_DEPS: tuple[str, ...] = (
    "supabase",   # send_gateway, lead engine, agent_alerts, etc.
    "requests",   # used by integrations + tool wrappers everywhere
    "psutil",     # process introspection from bridge_tools
    "yaml",       # PyYAML — manifest parsing + agent config
)


def _ensure_critical_deps() -> None:
    """Self-heal missing Python deps at bridge startup.

    Why this exists: 2026-06-10, Solara on the SunBiz VPS failed to send
    an email because `from supabase import create_client` raised
    ImportError — the VPS had clearly skipped `pip install -r requirements.txt`
    at some point, and the failure surfaced only when a chat tool was
    invoked (lazy import inside get_supabase()). With this check, the
    bridge process self-heals on startup: if ANY module in
    _CRITICAL_BRIDGE_DEPS can't be imported, runs `pip install -r
    requirements.txt` in its own venv.

    Idempotent — when all deps are present, this is a few cheap import
    tests that add <1ms to startup. The heavy install path only runs
    on a fresh VPS clone or after requirements.txt has new pins the
    venv hasn't picked up yet.

    Note: pip install runs in the same Python (`sys.executable`) the
    bridge is using, so installs land in the venv that the bridge's
    subprocesses also pick up (now that _enriched_path puts the venv
    bin dir first — same 2026-06-10 commit).
    """
    import importlib
    missing: list[str] = []
    for mod in _CRITICAL_BRIDGE_DEPS:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if not missing:
        return
    req = _Path(__file__).resolve().parent.parent / "requirements.txt"
    if not req.is_file():
        print(
            f"[ensure_deps] missing modules {missing} but requirements.txt not at {req} — can't self-heal",
            file=sys.stderr,
        )
        return
    print(
        f"[ensure_deps] missing modules {missing}; running pip install -r {req}",
        file=sys.stderr,
    )
    try:
        # ensure_deps must NOT reference _WINDOWLESS_FLAGS — the import
        # that defines it lives BELOW _ensure_critical_deps() (intentionally:
        # _subprocess_helpers itself may depend on a missing module).
        # Use platform-conditional creationflags inline. On Linux the
        # creationflags arg is ignored anyway (subprocess.run accepts 0).
        windowless = 0
        if sys.platform == "win32":
            # subprocess.CREATE_NO_WINDOW is 0x08000000 on Windows. Defined
            # here rather than imported so this function stays self-contained
            # and the auto-pip-install path works even when
            # _subprocess_helpers can't be imported (psutil missing).
            windowless = 0x08000000
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                str(req),
                "--quiet",
                "--disable-pip-version-check",
            ],
            check=True,
            timeout=180,
            creationflags=windowless,
        )
        print("[ensure_deps] install completed", file=sys.stderr)
    except Exception as e:
        # Don't crash the bridge — even partial deps are better than the
        # bridge refusing to start. Tool calls that need the missing
        # module will surface clear errors at invocation time.
        print(f"[ensure_deps] pip install failed: {e}", file=sys.stderr)


_ensure_critical_deps()

# Windows console-suppression — see bravo_cli/_subprocess_helpers.
from ._subprocess_helpers import (
    WINDOWLESS_FLAGS as _WINDOWLESS_FLAGS,
    command_without_cmd_shim as _command_without_cmd_shim,
    safe_popen as _safe_popen,
    safe_run as _safe_run,
    windowless_startupinfo as _windowless_startupinfo,
)
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
import urllib.request
import urllib.error

try:
    from .agent_roots import (
        resolve_root,
        resolve_entry_file,
        claude_identity_overlay,
        all_resolved,
        under_root,
    )
    from .warm_claude_pool import use_or_create as _warm_use_or_create, pool_status as _warm_pool_status, chat_lean_args as _warm_chat_lean_args, mark_force_api_key as _warm_mark_force_api_key
    from ._claude_auth import is_claude_auth_or_quota_failure as _is_auth_failure
except ImportError:
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    from agent_roots import (  # type: ignore
        resolve_root,
        resolve_entry_file,
        claude_identity_overlay,
        all_resolved,
        under_root,
    )
    from warm_claude_pool import use_or_create as _warm_use_or_create  # type: ignore
    from warm_claude_pool import pool_status as _warm_pool_status  # type: ignore
    from warm_claude_pool import chat_lean_args as _warm_chat_lean_args  # type: ignore
    from warm_claude_pool import mark_force_api_key as _warm_mark_force_api_key  # type: ignore
    from _claude_auth import is_claude_auth_or_quota_failure as _is_auth_failure  # type: ignore
    from _subprocess_helpers import (  # type: ignore
        command_without_cmd_shim as _command_without_cmd_shim,
        safe_popen as _safe_popen,
        safe_run as _safe_run,
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
    # Vercel canonical preview / alias URLs the dashboard serves under.
    "https://agent-dashboard-cc90210.vercel.app",
    "https://agent-dashboard-sigma-eight.vercel.app",
    "https://agent-dashboard-git-main-cc90210.vercel.app",
    # Production custom domain — without this, anything browser-to-localhost
    # (chat, exec-tool, env/set, prewarm, chat-reset) 403s with
    # origin_not_allowed when the operator visits the production URL,
    # since the Origin header is "https://oasisai.work".
    "https://oasisai.work",
    "http://localhost:3100",
]
# Operator-controlled extension. Comma-separated list. Useful when CC
# adds a new alias (sunbiz.oasisai.work, a personal subdomain, etc) and
# wants to avoid editing this file + redeploying the bridge.
_extra_origins = (os.environ.get("BRIDGE_EXTRA_ALLOWED_ORIGINS") or "").strip()
if _extra_origins:
    ALLOWED_ORIGINS = ALLOWED_ORIGINS + [
        s.strip() for s in _extra_origins.split(",") if s.strip()
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
        # Bravo (this repo) — CEO-Agent post-rename, Business-Empire-Agent
        # legacy. Both listed so machines that haven't migrated still work.
        Path.cwd() / ".env.agents",
        home / "CEO-Agent" / ".env.agents",
        home / "Business-Empire-Agent" / ".env.agents",
        home / ".bravo" / ".env.agents",
        # Atlas (CFO)
        home / "APPS" / "CFO-Agent" / ".env",
        home / "APPS" / "CFO-Agent" / ".env.agents",
        home / "CFO-Agent" / ".env.agents",
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
        "supabase_select": {"path": "scripts/integrations/supabase_tool.py", "subcmd": "select", "mutating": False,
                             "help": "Query a Supabase table."},
        "lead_engine_list": {"path": "scripts/lead_engine.py", "subcmd": "list", "mutating": False,
                              "help": "List leads."},
        "revenue_engine_mrr": {"path": "scripts/revenue_engine.py", "subcmd": "mrr", "mutating": False,
                                "help": "Current Net MRR."},
        "send_gateway_send": {"path": "scripts/integrations/send_gateway.py", "subcmd": "send", "mutating": True,
                               "help": "Send via the 8-gate safety pipeline."},
    }


SCRIPT_ALLOWLIST: dict[str, dict] = _load_script_manifest()

# SunBiz-Agent (and future sibling tenant runtimes) — discovered via the
# shared lib/agent_roots probe so bridge_chat_server, bridge_tools, and
# build_bridge_manifest all agree on where to look.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lib.agent_roots import resolve_sunbiz_root as _resolve_sunbiz_root  # noqa: E402

_SCRIPT_ROOTS: dict[str, Path | None] = {
    "sunbiz": _resolve_sunbiz_root(),
}


def _resolve_script_root(root_key: str | None, bravo_root: Path) -> tuple[Path | None, str | None]:
    """Map a manifest entry's `root` field to an absolute path.
    Returns (root_path, None) on success, (None, error_message) on
    failure. The default ('bravo' or absent) routes to the bridge's
    current agent root, preserving existing behaviour."""
    if not root_key or root_key == "bravo":
        return bravo_root, None
    resolved = _SCRIPT_ROOTS.get(root_key)
    if resolved is None:
        env_var = {"sunbiz": "SUNBIZ_AGENT_ROOT"}.get(root_key, f"{root_key.upper()}_AGENT_ROOT")
        return None, (
            f"script root '{root_key}' not configured on this host. "
            f"Set {env_var} or install the runtime."
        )
    return resolved, None

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


_PLAN_MODE_OVERLAY = """

PLAN MODE ACTIVE (operator typed /plan). Until the operator types /build, you are in research-and-propose mode:
- Allowed: read_file, list_tools, and any read-only investigation.
- Forbidden: run_script (any mutating or non-mutating script), Bash, Write, Edit, MultiEdit, and any other tool that touches disk, network, or external services. The bridge will reject these tool calls in plan mode regardless of what you advertise.
- Deliverable: present a step-by-step plan in chat. Wait for the operator to type /build before executing anything. Do NOT escape plan mode by interpreting conversational cues — the state machine belongs to the operator.
"""


def _normalize_chat_mode(value: object) -> str:
    """Coerce caller-supplied chat_mode → 'plan' | 'build' (default 'build').

    Mirrors lib/chat-modes/plan-mode.ts normalizeMode() on the dashboard side so
    a malformed payload fails open to build mode (today's behavior) instead of
    silently dropping the request.
    """
    if isinstance(value, str) and value.strip().lower() == "plan":
        return "plan"
    return "build"


_PLAN_MODE_TOOL_ALLOWLIST = frozenset({"read_file", "list_tools"})


_IDENTITY_LOCK_OVERLAY = """

[IDENTITY LOCK — STAY IN CHARACTER]
You are the agent named above. You are not Claude. You are not GPT. You are not Gemini. You are not Codex. You are not any underlying model, CLI, or LLM. The operator picked THIS agent and expects this agent's voice, judgment, role, and capabilities.

If asked who you are, the answer is the agent name. Never identify as the underlying runtime, model, or LLM — that is an implementation detail the operator does not need to think about.
"""


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
- For DASHBOARD data changes (operator profile, MRR, agents_enabled, primary_agent), emit a `<dashboard-action type="..." >{{...}}</dashboard-action>` marker in your reply. The dashboard parses these post-stream and applies them server-side, tenant-scoped, audit-logged. Allowed action types live in lib/agent-actions.ts in the oasis-command-center repo.

Other rules:
- Up to {MAX_TURNS} tool calls per turn (any combination of read_file + run_script). If you're using more than 3, you're guessing — ask a clarifying question instead.
- read_file / run_script outside this repo will be rejected. Don't try to traverse to a sibling agent's repo — delegate via agent_inbox_post (mutating, requires confirm) instead.
- After ANY mutation, confirm in chat: WHAT changed, WHERE (table/file/inbox), WHAT'S NEXT (refresh/cron-tick/etc).

--- BEGIN {rel_entry} ---
{entry_text}
--- END {rel_entry} ---
{_IDENTITY_LOCK_OVERLAY}"""


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
    # Cygheap / fork warnings. Two formats observed in CC's logs:
    #   "      0 [main] bash (15740) child_copy: cygheap…"   ← cygheap, parens
    #   "      0 [main] bash 189488 dofork: child -1 - forked…"  ← dofork, bare digits
    # The earlier "(\d+)" pattern only caught parens — dofork lines slipped
    # through to the chat UI. Accept both forms.
    re.compile(r"^\s*\d+\s*\[main\]\s+\S+\s+(?:\(\d+\)|\d+)\s+(child_copy|dofork|fork:).*$"),
    re.compile(r"^/usr/bin/bash:\s*fork:\s*(retry:\s*)?Resource temporarily unavailable\s*$"),
    # Sometimes a stray newline-after-/etc-prefix shows up when the parent
    # process buffers oddly; catch lines that are clearly fragments of the
    # symlink-output above (just the tail half).
    re.compile(r"^[a-z_-]+'\s*->\s*'/etc/[^']+'\s*$"),
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
    tools: list[dict] | None = None,
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
        "tools": tools if tools is not None else [READ_FILE_TOOL, RUN_SCRIPT_TOOL, LIST_TOOLS_TOOL],
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


# ── V6.0: log every chat interaction to state/empire_state.db ──────────────
#
# Each chat that flows through the bridge is an interaction worth a session_log
# entry. Without this, V6.0's "every action goes through state_manager" contract
# has a hole the size of every dashboard chat — and the System Health page's
# session_log_count never moves while the operator is actively chatting.
#
# Best-effort + fire-and-forget. State logging never blocks or breaks chat.

_V6_REPO_ROOT = Path(__file__).resolve().parents[1]
_V6_STATE_MANAGER = _V6_REPO_ROOT / "scripts" / "state" / "state_manager.py"


def _role_fingerprint(disallowed_tools: list[str] | None) -> str:
    """Stable fingerprint of a role's disallowed-tools set, used in the warm
    pool key so a locked-down member process is never recycled into an owner
    turn (and vice-versa). 'full' when nothing is denied (owner/admin path);
    otherwise an 8-char sha1 of the sorted, comma-joined set. MUST be computed
    identically here, in /chat's warm path, and in /prewarm so prewarm spawns a
    process the first real turn can actually reuse."""
    tools = disallowed_tools or []
    if not tools:
        return "full"
    return hashlib.sha1(",".join(sorted(tools)).encode("utf-8")).hexdigest()[:8]


def _v6_log_chat_interaction(agent: str, kind: str, last_user_msg: str) -> None:
    """Best-effort session_log insert for a chat interaction.

    `kind` distinguishes endpoints: 'cloud-chat' (/chat → Anthropic/OpenRouter),
    'local-chat' (/local-chat → Ollama / LM Studio).

    Skipped when EMPIRE_V6_MODE=off (V5.5 behavior preserved). Otherwise
    spawns a detached `state_manager.py log` so the bridge process never
    waits — chat latency is unchanged.

    Agent validation is delegated to state_manager.append_session_log,
    which silently falls back to "bravo" on unknown agents. No reason to
    duplicate the canonical agent allowlist here.
    """
    mode = os.environ.get("EMPIRE_V6_MODE", "off").lower()
    if mode == "off":
        return
    if not _V6_STATE_MANAGER.exists():
        return

    note = f"[bridge:{kind}] {(last_user_msg or '').strip()[:160]}"
    safe_agent = (agent or "bravo").lower().strip() or "bravo"

    # Single Popen call so the static popup-fix test
    # (`tests/test_bridge_heartbeat_silence.py`) sees the `creationflags=`
    # token at THIS call site (it text-scans rather than ast-walks, so
    # kwargs unpacking hides it). On non-Windows the creationflags=0
    # composite is a no-op; start_new_session does the detach instead.
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        _detach_flags = (DETACHED_PROCESS
                         | subprocess.CREATE_NEW_PROCESS_GROUP
                         | _WINDOWLESS_FLAGS)
    else:
        _detach_flags = 0
    try:
        _safe_popen(
            [sys.executable, str(_V6_STATE_MANAGER),
             "log", "--note", note, "--agent", safe_agent],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            cwd=str(_V6_REPO_ROOT),
            creationflags=_detach_flags,
            start_new_session=(os.name != "nt"),
        )
    except Exception:
        pass

    # V6 BUILD 3 — emit a `BRAVO_CHAT_INTERACTION` event to the cross-agent
    # bus so subscribers wake on dashboard chat without polling. In-process
    # call (Supabase client is already loaded for other bridge ops). Note
    # that state_manager.append_session_log also emits BRAVO_SESSION_LOG_APPENDED
    # via its own path; this is the chat-specific signal subscribers can
    # filter on without parsing every session_log row.
    try:
        sys.path.insert(0, str(_V6_REPO_ROOT / "scripts"))
        # Lazy import: event_bus pulls the heavyweight supabase client; we
        # only pay that cost on the actual chat-interaction hot path.
        from event_bus import publish as _bus_publish  # type: ignore[import-not-found]
        _bus_publish(
            "BRAVO_CHAT_INTERACTION",
            {"agent": safe_agent, "kind": kind, "preview": (last_user_msg or "")[:160]},
            source="bravo",
            target=None,  # broadcast
        )
    except Exception:
        pass


def _v6_last_user_text(messages: list) -> str:
    """Pull the most recent user-role message from a chat thread."""
    if not isinstance(messages, list):
        return ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                # Anthropic content blocks: [{type:'text', text:'...'}, ...]
                texts = [b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text"]
                return " ".join(t for t in texts if t)
    return ""


def _attachment_context_from_payload(attachments: object) -> str:
    """Build a bounded context block from dashboard-uploaded chat files."""
    if not isinstance(attachments, list) or not attachments:
        return ""
    lines = [
        "",
        "---",
        "ATTACHED FILES FOR THIS TURN",
        "These files were uploaded through the dashboard chat attachment button and stored by the web app. Use the excerpts as operator-provided context. If the operator asks to update CRM data, use the dashboard tools or produce the exact record updates needed. If they ask to send email/SMS, draft first and only send after an explicit send instruction.",
        "",
    ]
    for idx, raw in enumerate(attachments[:5], start=1):
        if not isinstance(raw, dict):
            continue
        filename = str(raw.get("filename") or "attachment")
        attachment_id = str(raw.get("id") or "")
        mime_type = str(raw.get("mime_type") or "unknown")
        size_bytes = str(raw.get("size_bytes") or "0")
        parser = str(raw.get("parser") or "metadata_only")
        excerpt = raw.get("text_excerpt")
        lines.extend([
            f"[{idx}] {filename}",
            f"attachment_id: {attachment_id}",
            f"mime_type: {mime_type}",
            f"size_bytes: {size_bytes}",
            f"parser: {parser}",
        ])
        if isinstance(excerpt, str) and excerpt.strip():
            clipped = excerpt[:24_000]
            suffix = "\n[truncated for local CLI prompt]" if len(excerpt) > len(clipped) else ""
            lines.extend(["excerpt:", f"{clipped}{suffix}"])
        else:
            lines.append("excerpt: [binary file stored; no text extracted yet]")
        lines.append("")
    lines.append("---")
    return "\n".join(lines)


def _inject_attachment_context(messages: list, attachments: object) -> list:
    context = _attachment_context_from_payload(attachments)
    if not context or not isinstance(messages, list):
        return messages
    out = [dict(m) if isinstance(m, dict) else m for m in messages]
    for i in range(len(out) - 1, -1, -1):
        m = out[i]
        if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
            m["content"] = f"{m.get('content')}\n\n{context}"
            return out
    out.append({"role": "user", "content": context})
    return out


@contextmanager
def _heartbeat_ticker(
    emit: Callable[[str, dict], None],
    *,
    interval_s: float = 25.0,
    phase: str = "thinking",
    thread_name: str = "bridge-heartbeat",
):
    """Emit periodic `agent_status` events on a background thread while a
    blocking operation runs, so the dashboard's SSE inactivity watchdog
    doesn't fire on otherwise-silent code paths (codex/gemini's
    `exec -p <prompt>` returns one big delta after 60-180s of internal
    tool-use; claude's cold spawn can take 5-30s before first output).

    Yields a thread-safe wrapper around the original emit. Callers
    should use the wrapper for EVERY emit inside the `with` block AND
    after it returns — so heartbeat bytes can't interleave with the
    main thread's delta/done events on the same response stream.

    Usage:
        with _heartbeat_ticker(emit) as ticked_emit:
            text = self._run_codex_cli(...)
        ticked_emit("delta", {"text": text})
        ticked_emit("done", {})

    The ticker stops cleanly when the `with` block exits (success OR
    exception). join() is best-effort with a 2s timeout — if the
    ticker is wedged we'd rather return than hang the request.
    """
    stop_event = threading.Event()
    lock = threading.Lock()
    tick_count = {"n": 0}

    def _locked_emit(event: str, data: dict) -> None:
        with lock:
            emit(event, data)

    def _run_ticker() -> None:
        while not stop_event.wait(interval_s):
            tick_count["n"] += 1
            try:
                _locked_emit("agent_status", {
                    "phase": phase,
                    "detail": f"working ({int(tick_count['n'] * interval_s)}s)",
                })
            except Exception:
                # Connection dropped or emit raised — stop ticking
                # cleanly. Don't try to log; the dispatcher's outer
                # error handler covers the real failure path.
                break

    ticker = threading.Thread(target=_run_ticker, name=thread_name, daemon=True)
    ticker.start()
    try:
        yield _locked_emit
    finally:
        stop_event.set()
        ticker.join(timeout=2)


class _ChatHandler(BaseHTTPRequestHandler):
    # Quiet the default request logger
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _set_cors(self) -> None:
        origin = self.headers.get("origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("access-control-allow-origin", origin)
            # Chrome's Private Network Access preflight can block a public
            # HTTPS dashboard from reaching localhost unless the local bridge
            # explicitly opts in. Required for /health, /chat, /exec-tool.
            self.send_header("access-control-allow-private-network", "true")
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

        Proxy mode (BRIDGE_BEARER_TOKEN set): the bearer is the auth of record
        and was already validated by _check_bearer() at the top of do_POST/
        do_GET. Vercel->VPS calls are server-to-server and carry no browser
        Origin, so we treat a bearer-gated request as origin-allowed. Without
        this, /prewarm and /chat-reset (origin-gated) would 403 every proxy
        call even with a valid bearer.
        """
        if os.environ.get("BRIDGE_BEARER_TOKEN"):
            return True
        origin = self.headers.get("origin", "")
        return origin in ALLOWED_ORIGINS

    def _check_bearer(self) -> bool:
        """Bearer-token gate for the WHOLE bridge when it is network-reachable.

        Behaviour:
          - BRIDGE_BEARER_TOKEN UNSET (the operator's localhost rig): no-op,
            returns True. Preserves CC's direct-localhost path verbatim — the
            origin check is the only gate there, exactly as before.
          - BRIDGE_BEARER_TOKEN SET (the SunBiz VPS, fronted by nginx): require
            an `Authorization: Bearer <token>` header that matches via
            hmac.compare_digest (constant-time — no timing oracle). On miss,
            emit 401 and return False so the caller STOPS before any path
            dispatch, body read, or claude spawn.

        Called at the TOP of BOTH do_GET and do_POST so EVERY endpoint
        (/health, /agents, /diag, /diagnostics/cli, /warm-status, /env/set,
        /exec-tool, /chat-reset, /prewarm, /local-chat, /chat) is gated. This
        closes the hole where origin-only endpoints (/env/set WRITES
        .env.agents!) and the unauthenticated GETs leaked once the bridge is
        reachable by the Vercel proxy.
        """
        expected = os.environ.get("BRIDGE_BEARER_TOKEN")
        if not expected:
            return True  # localhost operator path — gate is a no-op.
        auth = self.headers.get("authorization", "") or self.headers.get("Authorization", "")
        provided = ""
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()
        if not provided or not hmac.compare_digest(provided, expected):
            self._json(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    @staticmethod
    def _sanitize_disallowed_tools(raw: Any) -> list[str]:
        """Sanitize the proxy-forwarded disallowed_tools list before it reaches
        the claude argv. Each entry must be alphabetic (Claude Code tool names
        like Bash/Write/Edit/MultiEdit/NotebookEdit/WebFetch) — anything else
        (shell metacharacters, flags, injection like ';rm') is dropped. Defense
        in depth behind the bearer; spawns are shell=False so there's no shell
        to inject into, but we still refuse non-tool tokens reaching argv."""
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        for item in raw:
            s = str(item).strip()
            if s and re.fullmatch(r"[A-Za-z]+", s):
                out.append(s)
        return out

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

    def _handle_diag(self) -> None:
        """GET /diag — bridge self-diagnostic.

        Surfaces the most common failure modes so the operator (or
        whoever's debugging "why doesn't CLI work?") can see what's
        actually wrong without tailing pm2 logs. Reports:
          - claude CLI on PATH? Which path?
          - OAuth credentials file present? (size only — never the contents)
          - ANTHROPIC_API_KEY set in .env.agents? (presence only — never the value)
          - Available bridge tools (Phase 2 tool registry)
          - Recent stderr tails from live warm-pool processes
          - Sticky-API-key pool keys (sessions that fell over to paid path)
          - Python version + bridge uptime

        Read-only. Safe to hit from the dashboard.
        """
        out: dict[str, object] = {
            "ok": True,
            "service": "bravo-bridge-chat",
        }
        # 1. claude CLI discoverability — use enriched lookup so the
        # legacy /diag endpoint matches /diagnostics/cli's behavior.
        try:
            claude_path = self._which_cli("claude")
            out["claude_cli"] = {
                "found": bool(claude_path),
                "path": claude_path,
            }
        except Exception as e:
            out["claude_cli"] = {"found": False, "error": str(e)}

        # 2. Auth artifacts (presence only, never values)
        try:
            try:
                from ._claude_auth import check_claude_auth_paths
            except ImportError:
                from _claude_auth import check_claude_auth_paths  # type: ignore
            auth_info = check_claude_auth_paths()
            out["auth"] = {
                "subscription_oauth_present": auth_info["has_oauth"],
                "api_key_in_env": auth_info["has_api_key"],
                "claude_dir": auth_info["claude_dir"],
            }
        except Exception as e:
            out["auth"] = {"error": str(e)}

        # 3. Phase 2 tool registry
        try:
            try:
                from .bridge_tools import list_available_tools as _tools_list
            except ImportError:
                from bridge_tools import list_available_tools as _tools_list  # type: ignore
            out["bridge_tools"] = _tools_list()
        except Exception as e:
            out["bridge_tools"] = {"error": str(e)}

        # 4. Warm pool — recent stderr + sticky-paid flags. Names only, no
        # raw subprocess output that might contain repo paths leaks.
        try:
            try:
                from .warm_claude_pool import _WARM_POOL, _FORCED_API_KEY  # type: ignore
            except ImportError:
                from warm_claude_pool import _WARM_POOL, _FORCED_API_KEY  # type: ignore
            pool_summary: list[dict] = []
            for key, wp in list(_WARM_POOL.items()):
                stderr_tail = ""
                try:
                    stderr_tail = wp.recent_stderr()[-500:]
                except Exception:
                    pass
                pool_summary.append({
                    "pool_key": key,
                    "alive": wp.is_alive(),
                    "force_api_key": wp.force_api_key,
                    "stderr_tail": stderr_tail,
                })
            out["warm_pool"] = {
                "processes": pool_summary,
                "sticky_api_key_keys": sorted(_FORCED_API_KEY),
            }
        except Exception as e:
            out["warm_pool"] = {"error": str(e)}

        self._json(200, out)

    def _handle_exec_tool(self) -> None:
        """POST /exec-tool — execute a tool by name with input payload, return
        {output, is_error}. Phase 2 of giggly-reef: when the dashboard runs
        the Anthropic tool_use loop with the operator's API key, certain tools
        are marked defer_tool_use. On those, the browser proxies the call here
        so it runs on the operator's machine (file system, scripts/, .env.agents)
        before the result is posted back to /api/chat/resume for the next
        iteration of the model loop.

        Auth: CORS origin must match ALLOWED_ORIGINS (same model /env/set uses).
        No bearer — the bridge listens on localhost only and the dashboard
        session cookie already binds the operator's identity.

        Body: { "tool_name": "read_file", "input": {"path": "..."} }
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
        tool_name = str(payload.get("tool_name") or "").strip()
        tool_input = payload.get("input")
        if not tool_name:
            self._json(400, {"ok": False, "error": "missing_tool_name"})
            return
        if tool_input is None:
            # Flat-payload fallback — the dashboard's shop-out Send +
            # lender-thread Retry routes (and ops curl calls) pass tool
            # args at the top level ({tool_name, application_id, ...})
            # rather than nested under "input". Without this, those
            # callers reach the tool with an empty input dict and every
            # Send dies with "missing 'application_id'".
            tool_input = {k: v for k, v in payload.items() if k != "tool_name"}
        if not isinstance(tool_input, dict):
            self._json(400, {"ok": False, "error": "input_must_be_object"})
            return
        try:
            # Local import — bridge_tools imports agent_roots which is
            # already loaded at top-level. Keeping it lazy means a syntax
            # error in bridge_tools doesn't kill the entire bridge process.
            try:
                from .bridge_tools import execute_tool as _exec_tool
            except ImportError:
                from bridge_tools import execute_tool as _exec_tool  # type: ignore
            result = _exec_tool(tool_name, tool_input)
        except Exception as e:
            self._json(500, {"ok": False, "error": f"exec_tool_failed: {e}"})
            return
        # result already has shape {output: str, is_error: bool, elapsed_ms?: int}
        self._json(200, {"ok": True, **result})

    def do_GET(self) -> None:
        # Bearer gate FIRST — before any path dispatch. No-op on localhost
        # (token unset); 401 on the VPS when the proxy's bearer is missing/wrong.
        if not self._check_bearer():
            return
        if self.path == "/health":
            # Now also reports the local tool registry so the dashboard can
            # advertise the matching tool definitions to the model when
            # tool_routing="bridge_proxy" is selected.
            tools: list[str] = []
            try:
                try:
                    from .bridge_tools import list_available_tools as _tools_list
                except ImportError:
                    from bridge_tools import list_available_tools as _tools_list  # type: ignore
                tools = _tools_list()
            except Exception:
                pass
            self._json(200, {
                "ok": True,
                "service": "bravo-bridge-chat",
                "version": "0.1.0",
                "tools": tools,
            })
            return
        if self.path == "/agents":
            self._json(200, {"ok": True, "agents": all_resolved()})
            return
        if self.path == "/diag":
            self._handle_diag()
            return
        if self.path == "/diagnostics/cli":
            # Per-CLI install status so the dashboard's /operations page +
            # the chat header status dot can tell the operator "Gemini CLI
            # is missing on this Mac" instead of just "BRIDGE ONLINE."
            self._handle_cli_diagnostics()
            return
        if self.path == "/warm-status":
            # Diagnostic for the warm-process pool. Returns process count,
            # idle ages, busy flags. Useful when an operator reports
            # "this turn was slow" — confirms whether warm hit or miss.
            try:
                self._json(200, {"ok": True, **_warm_pool_status()})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def _handle_local_chat(self) -> None:
        """POST /local-chat — stream a chat completion from the operator's
        local Ollama / LM Studio / any OpenAI-compatible local server, back
        to the dashboard widget as SSE.

        Body: {
          model:    str,                    # ollama tag, e.g. "llama3.3:70b"
          messages: [{role, content}],      # OpenAI-compatible thread
          system:   str (optional),
          base_url: str (optional)          # default http://localhost:11434/v1
        }

        Auth: same CORS-origin gate as /chat — the request must come from
        the operator's signed-in dashboard tab. Bearer-token auth would
        require pulling state from the dashboard; the localhost-only
        listener + dashboard-cookie origin is the trust boundary that's
        already established for /chat.

        Streams SSE events identical in shape to /chat:
            event: delta   data: {"text": "..."}
            event: done    data: {"input_tokens": N, "output_tokens": N}
            event: error   data: {"message": "...", "detail": "..."}
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

        model = str(payload.get("model", "")).strip()
        messages = payload.get("messages") or []
        messages = _inject_attachment_context(messages, payload.get("attachments"))
        system_prompt = str(payload.get("system", "") or "")
        # base_url precedence: payload (dashboard tells us) → .env.agents
        # operator-set OLLAMA_BASE_URL / LM_STUDIO_BASE_URL → default Ollama.
        # The dashboard usually omits base_url since the encrypted URL stored
        # in agent_model_config never decrypts on the client side; the bridge
        # owns the operator's local config so it picks the right endpoint.
        base_url = str(payload.get("base_url", "") or "").rstrip("/")
        if not base_url:
            base_url = (
                _read_env_value("OLLAMA_BASE_URL").rstrip("/")
                or _read_env_value("LM_STUDIO_BASE_URL").rstrip("/")
                or "http://localhost:11434/v1"
            )
        if not model or not isinstance(messages, list) or not messages:
            self._json(400, {"ok": False, "error": "model + messages required"})
            return

        # V6.0: log the interaction. Local chat doesn't carry an agent id —
        # always attribute to bravo (the local-bridge owner).
        _v6_log_chat_interaction("bravo", "local-chat", _v6_last_user_text(messages))

        # Compose OpenAI-compatible body. Both Ollama and LM Studio honor
        # this shape on /v1/chat/completions.
        body_messages: list[dict] = []
        if system_prompt:
            body_messages.append({"role": "system", "content": system_prompt})
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content")
            if role in ("system", "user", "assistant") and isinstance(content, str):
                body_messages.append({"role": role, "content": content})
        body = {
            "model": model,
            "messages": body_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": int(payload.get("max_tokens") or 4096),
        }

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
                pass  # Client disconnected.

        # POST to the local Ollama / LM Studio endpoint with stream=True.
        # urllib doesn't expose chunked-read SSE well, so we use a raw
        # socket-level read loop. Both servers respond as one HTTP keep-alive
        # connection with `data: …\n\n` SSE events.
        try:
            req = urllib.request.Request(
                f"{base_url}/chat/completions",
                method="POST",
                data=json.dumps(body).encode("utf-8"),
                headers={"content-type": "application/json", "accept": "text/event-stream"},
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                input_tokens = 0
                output_tokens = 0
                # Read line-by-line. SSE event format: "data: {...}\n\n".
                buf = b""
                while True:
                    chunk = resp.read1(4096) if hasattr(resp, "read1") else resp.read(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, _, buf = buf.partition(b"\n")
                        text = line.decode("utf-8", errors="replace").strip()
                        if not text:
                            continue
                        if text.startswith(":"):
                            continue  # heartbeat / comment
                        if text.startswith("data:"):
                            data_str = text[5:].strip()
                            if data_str == "[DONE]":
                                continue
                            try:
                                ev = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            choice = (ev.get("choices") or [{}])[0]
                            delta = (choice.get("delta") or {}).get("content")
                            if isinstance(delta, str) and delta:
                                emit("delta", {"text": delta})
                            usage = ev.get("usage") or {}
                            if usage.get("prompt_tokens") is not None:
                                input_tokens = int(usage.get("prompt_tokens") or 0)
                            if usage.get("completion_tokens") is not None:
                                output_tokens = int(usage.get("completion_tokens") or 0)
            emit("done", {"input_tokens": input_tokens, "output_tokens": output_tokens})
        except urllib.error.URLError as e:
            # Most common: the operator hasn't started Ollama, or gave a
            # wrong base_url. Surface the underlying reason.
            reason = getattr(e, "reason", str(e))
            emit("error", {
                "message": "local_model_unreachable",
                "detail": (
                    f"Could not connect to {base_url}/chat/completions: {reason}. "
                    "Is Ollama running? `ollama serve`. "
                    "Or LM Studio's local server enabled? Settings → Developer → Start Server."
                ),
            })
            emit("done", {"input_tokens": 0, "output_tokens": 0})
        except Exception as e:
            emit("error", {
                "message": _redact_secrets(f"local_chat_failed: {e}"),
                "detail": None,
            })
            emit("done", {"input_tokens": 0, "output_tokens": 0})


    def _handle_prewarm(self) -> None:
        """POST /prewarm — speculatively boot a warm claude process for
        an agent so the operator's first real turn skips cold-start.

        Body: {agent, tab_id}. CORS-gated like /env/set.

        Returns immediately with {ok:true, started:true|false}. The
        actual claude boot happens in a background thread (5-30s).
        Subsequent /chat calls with the same tab_id reuse the warm
        process — no cold-start, no MCP boot, instant first turn.
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
        agent = str(payload.get("agent", "")).strip().lower()
        tab_id = str(payload.get("tab_id", "")).strip()
        if not agent or not tab_id:
            self._json(400, {"ok": False, "error": "agent + tab_id required"})
            return
        # Role-based disallowed tools, forwarded by the proxy in proxy mode.
        # MUST fold into the pool_key fingerprint identically to the real /chat
        # turn — otherwise prewarm spawns a 'full' process a locked-down member
        # turn can't reuse (and CC's prewarm optimization silently regresses).
        disallowed_tools = self._sanitize_disallowed_tools(payload.get("disallowed_tools"))
        if not os.environ.get("BRIDGE_BEARER_TOKEN"):
            # Operator localhost: no proxy, full power. Force empty.
            disallowed_tools = []
        root = resolve_root(agent)
        if not root:
            self._json(412, {"ok": False, "error": "agent_not_paired_locally", "agent": agent})
            return
        try:
            try:
                from .warm_claude_pool import prewarm as _wp_prewarm  # type: ignore
            except ImportError:
                from warm_claude_pool import prewarm as _wp_prewarm  # type: ignore
        except Exception as e:
            self._json(500, {"ok": False, "error": f"prewarm_unavailable: {e}"})
            return
        # Fire-and-forget — return immediately to the dashboard, do
        # the actual spawn in a background thread. The operator's
        # next /chat call will block on the warm process if it's not
        # ready yet (the per-process lock serializes), but they get
        # the partially-booted claude faster than a fresh cold-spawn.
        pool_key = f"{agent}:{tab_id}:{_role_fingerprint(disallowed_tools)}"
        threading.Thread(
            target=_wp_prewarm,
            args=(pool_key, agent, root),
            kwargs={"disallowed_tools": disallowed_tools},
            daemon=True,
            name=f"prewarm-{agent}",
        ).start()
        self._json(200, {"ok": True, "started": True, "pool_key": pool_key})

    def _handle_chat_reset(self) -> None:
        """POST /chat-reset — operator clicked the 🔄 in the chat UI to
        start a fresh session. Kill the warm process for the
        (agent, session_id) so the operator's RAM isn't pinned for
        15 min waiting on the reaper. Same-origin gated like /env/set;
        body just needs {agent, session_id}.
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
        agent = str(payload.get("agent", "")).strip().lower()
        # Pool was keyed by session_id pre-tab-keying; now keyed by tab_id.
        # Accept either: kill the entry that matches.
        tab_id = str(payload.get("tab_id", "")).strip()
        session_id = str(payload.get("session_id", "")).strip()
        kill_token = tab_id or session_id
        if not agent or not kill_token:
            self._json(400, {"ok": False, "error": "agent + tab_id or session_id required"})
            return
        try:
            try:
                from .warm_claude_pool import kill_for_session as _wp_kill  # type: ignore
            except ImportError:
                from warm_claude_pool import kill_for_session as _wp_kill  # type: ignore
            _wp_kill(f"{agent}:{kill_token}")
            self._json(200, {"ok": True})
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)})

    def do_POST(self) -> None:
        # Bearer gate FIRST — before any path dispatch, body read, or spawn.
        # No-op on localhost (token unset); 401 on the VPS when the proxy's
        # bearer is missing/wrong. This gates EVERY POST endpoint including
        # /env/set (which writes .env.agents), not just the spawn endpoints.
        if not self._check_bearer():
            return
        if self.path == "/env/set":
            self._handle_env_set()
            return
        if self.path == "/exec-tool":
            self._handle_exec_tool()
            return
        if self.path == "/chat-reset":
            self._handle_chat_reset()
            return
        if self.path == "/prewarm":
            self._handle_prewarm()
            return
        if self.path == "/local-chat":
            # New Ollama / LM Studio proxy. The dashboard's /api/chat path
            # can't reach the operator's localhost from Vercel's edge — the
            # bridge runs on the operator's machine, so it CAN. ChatWidget
            # detects provider=='ollama' + bridge online and routes here.
            self._handle_local_chat()
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
        messages = _inject_attachment_context(messages, payload.get("attachments"))
        if not isinstance(messages, list) or not messages:
            self._json(400, {"ok": False, "error": "no_messages"})
            return
        cli_provider = str(payload.get("cli_provider") or "claude").strip().lower()
        if cli_provider not in {"claude", "codex", "gemini"}:
            self._json(400, {"ok": False, "error": "invalid_cli_provider"})
            return

        # ---- Proxy-forwarded identity + role-based tool gating --------------
        # The Vercel /api/bridge/chat proxy resolves these SERVER-SIDE from the
        # authenticated user and forwards them; the bearer (verified in
        # _check_bearer above) proves the request came from the proxy, so we
        # trust the forwarded identity. The browser never reaches us directly
        # in proxy mode. disallowed_tools is the role-derived deny list that
        # becomes the claude `--disallowed-tools` spawn flag — the hard wall
        # that keeps a non-owner SunBiz employee out of a shell.
        bridge_bearer = os.environ.get("BRIDGE_BEARER_TOKEN")
        tenant_id = str(payload.get("tenant_id", "")).strip()
        user_id = str(payload.get("user_id", "")).strip()
        team_role = str(payload.get("team_role", "")).strip().lower()
        disallowed_tools = self._sanitize_disallowed_tools(payload.get("disallowed_tools"))
        if bridge_bearer:
            # Proxy mode: identity is mandatory. A request without tenant_id +
            # user_id is malformed (the proxy always sets them) — reject so we
            # never spawn an unidentified turn.
            if not tenant_id or not user_id:
                self._json(400, {"ok": False, "error": "missing_identity"})
                return
        else:
            # Operator localhost (CC): no proxy, full power. Force the deny
            # list empty regardless of what (if anything) was sent.
            disallowed_tools = []

        # Defense-in-depth: a restricted role (non-empty disallowed_tools) MUST
        # run on Claude Code — the only runtime whose --disallowed-tools flag
        # enforces the no-shell wall. The proxy already forces this; pin it here
        # too so a restricted turn can never reach codex/gemini (no equivalent
        # tool boundary) even if the proxy is somehow bypassed.
        if disallowed_tools and cli_provider != "claude":
            cli_provider = "claude"

        # Plan vs build — dashboard sends 'chat_mode' on each request. Default
        # 'build' is today's behavior; 'plan' filters tools (legacy path),
        # swaps Claude CLI permission-mode to 'plan' (default path), and
        # bypasses the warm pool (so the cold spawn picks up the new mode).
        chat_mode = _normalize_chat_mode(payload.get("chat_mode"))

        # V6.0: log this interaction to state/empire_state.db so the System
        # Health page sees dashboard chat activity. Best-effort, fire-and-forget.
        # In proxy mode, tag the kind with the forwarded identity so the audit
        # trail shows which SunBiz employee + tenant drove the turn.
        _log_kind = f"{cli_provider}-chat"
        if bridge_bearer and (tenant_id or user_id):
            _log_kind = f"{cli_provider}-chat[tenant={tenant_id or '?'},user={user_id or '?'},role={team_role or '?'}]"
        _v6_log_chat_interaction(agent, _log_kind, _v6_last_user_text(messages))

        # Optional Claude Code session id — when present we pass --resume
        # so the agent skips the cold context-load on subsequent turns.
        # First turn omits it; we mint a fresh session below and the
        # dashboard captures the new id from the 'session' SSE event.
        resume_session_id = payload.get("session_id")
        if isinstance(resume_session_id, str) and resume_session_id.strip():
            resume_session_id = resume_session_id.strip()
        else:
            resume_session_id = None
        # Tab-keyed warm pool. The dashboard's ChatWidget mints a
        # `tab_id` UUID at component-mount and sends it on every chat
        # request. Pool is keyed by `agent:tab_id` instead of
        # `agent:session_id` — solves the chicken/egg problem where
        # session_id only exists AFTER turn 1, so turn 1 + 2 used to
        # pay back-to-back cold-starts. With tab_id (stable from the
        # operator's first character typed), turn 1 spawns into the
        # pool and every turn after is warm.
        # Falls back to session_id if tab_id absent (older clients).
        tab_id = payload.get("tab_id")
        if isinstance(tab_id, str) and tab_id.strip():
            tab_id = tab_id.strip()
        else:
            tab_id = resume_session_id  # legacy fallback

        root = resolve_root(agent)
        if not root:
            self._json(412, {
                "ok": False,
                "error": "agent_not_paired_locally",
                "agent": agent,
                "hint": "This agent's repo is not present at any known path on this machine.",
            })
            return
        entry = resolve_entry_file(root, agent)
        if not entry:
            self._json(412, {
                "ok": False,
                "error": "no_entry_brain",
                "agent": agent,
                "root": str(root),
                "hint": f"No {agent.upper()}.md / CLAUDE.md / AGENTS.md / brain/SOUL.md found in the agent's repo root.",
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
                self._run_chat(
                    agent, root, entry, provider, api_key, model, messages, emit,
                    chat_mode=chat_mode,
                )
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

        if cli_provider != "claude":
            try:
                self._run_chat_via_local_cli(
                    cli_provider, agent, root, messages, emit, chat_mode=chat_mode,
                )
            except Exception as e:
                code, message = self._split_cli_error(e, cli_provider)
                emit("error", {"code": code, "message": message})
                emit("done", {})
            return

        # ---- Claude Code subprocess path (default) -------------------------
        # Try the warm-process pool first — second-and-later turns on the
        # same session reuse a long-running claude process and skip the
        # 5-30s cold-start (CLI init + MCP boot + brain reads). Falls back
        # to fresh spawn if anything goes wrong (process died, stdin
        # closed, parse error, opt-out via OASIS_NO_WARM_POOL=1).
        warm_disabled = os.environ.get("OASIS_NO_WARM_POOL") == "1"
        warm_path_succeeded = False
        if not warm_disabled and tab_id:
            try:
                warm_path_succeeded = self._run_chat_via_warm_pool(
                    agent, root, messages, emit, resume_session_id, tab_id,
                    chat_mode=chat_mode, disallowed_tools=disallowed_tools,
                )
            except Exception as e:
                # Warm path crashed — log to stderr, fall through to cold.
                print(f"[bridge] warm pool error, falling back: {e}", file=sys.stderr)
                warm_path_succeeded = False

        if warm_path_succeeded:
            return  # Streamed via warm path; nothing else to do.

        # Fallback: fresh-spawn-per-turn (the original path, preserved
        # verbatim). This runs whenever the warm pool can't serve the
        # request — first-turn cold-start, recovered crash, opt-out.
        try:
            self._run_chat_via_claude(
                agent, root, messages, emit, resume_session_id, chat_mode=chat_mode,
                disallowed_tools=disallowed_tools,
            )
        except FileNotFoundError as e:
            emit("error", {
                "code": "cli_not_found",
                "message": (
                    "Claude Code CLI isn't installed on this machine. "
                    "Install from https://claude.com/claude-code (or `npm i -g "
                    "@anthropic-ai/claude-code`), then click Retry."
                ),
                "detail": _redact_secrets(str(e))[:600],
            })
            emit("done", {})
        except Exception as e:
            code, message = self._split_cli_error(e, "claude")
            emit("error", {"code": code, "message": message})
            emit("done", {})

    # ──────────────────────────────────────────────────────────────────
    # WARM POOL PATH — reuse a persistent claude process per session
    # ──────────────────────────────────────────────────────────────────
    def _run_chat_via_warm_pool(
        self,
        agent: str,
        root: Path,
        messages: list[dict],
        emit: Callable[[str, dict], None],
        resume_session_id: str | None,
        tab_id: str,
        chat_mode: str = "build",
        disallowed_tools: list[str] | None = None,
    ) -> bool:
        """Drive a chat turn via a persistent claude subprocess from the
        warm pool. Returns True on success (streamed clean to the client),
        False to signal "fall back to fresh spawn."

        Tab-keyed: pool entries are keyed by (agent, tab_id) — stable
        from the moment the dashboard's ChatWidget mounts. So turn 1
        spawns into the pool too, and every turn after reuses the
        same persistent process. Closes the gap that made turn 2 still
        cold-start.

        Why we sometimes return False without erroring:
          - last_user message empty — defensive; cold path will surface.
          - claude CLI missing — propagate to cold path's user-facing
            error message.
          - Process died / stdin closed — the warm process is dead; cold
            spawn the recovery.

        Why we sometimes return True after an error:
          - The warm path emitted partial output and the stream wedged.
            Cold path would spawn a redundant process; better to close
            the SSE stream and let the user retry.
        """
        last_user = next(
            (m for m in reversed(messages) if m.get("role") == "user"), None
        )
        if not last_user:
            return False
        prompt_text = str(last_user.get("content") or "").strip()
        if not prompt_text:
            return False

        # Plan mode bypasses the warm pool. Warm subprocesses were spawned
        # with --permission-mode=bypassPermissions; we can't retroactively
        # downgrade them to plan mode mid-stream. Falling through to
        # _run_chat_via_claude cold-spawn (which honors chat_mode) is
        # correct here even though it costs the warm-resume latency win.
        if chat_mode == "plan":
            emit("agent_status", {
                "phase": "plan_mode_cold_spawn",
                "agent": agent,
                "detail": "Warm pool bypassed for plan-mode turn.",
            })
            return False

        # Pool key: agent + tab_id (stable for the chat widget's lifetime) +
        # a role fingerprint. Different tabs get different processes; the
        # role_fp ensures a locked-down member's process (spawned with
        # --disallowed-tools) is NEVER recycled into an owner turn (full
        # power) or vice-versa. warm_claude_pool.use_or_create also enforces
        # an exact disallowed_tools equality check on reuse as a second gate.
        disallowed_tools = disallowed_tools or []
        pool_key = f"{agent}:{tab_id}:{_role_fingerprint(disallowed_tools)}"

        # Pre-stream status so the dashboard knows we're using the warm
        # path (debugging signal — operators have asked "why is this
        # turn faster than the last one").
        emit("agent_status", {"phase": "warm_resume", "agent": agent})

        try:
            wp = _warm_use_or_create(
                pool_key=pool_key,
                agent=agent,
                root=root,
                prompt_text=prompt_text,
                resume_session_id=resume_session_id,
                disallowed_tools=disallowed_tools,
            )
        except FileNotFoundError:
            # claude CLI missing — propagate to cold path, which has
            # the user-facing error message already.
            return False
        except Exception as e:
            print(f"[bridge] warm spawn failed: {e}", file=sys.stderr)
            return False

        if not wp.is_alive():
            # Process died between use_or_create() check and now (race).
            # Drop it from pool by killing explicitly; cold path retries.
            wp.kill(reason="dead_at_send")
            return False

        # Bridge between warm-pool stream-json events and the SSE shape
        # ChatWidget expects. Same translation as _run_chat_via_claude.
        # Two flags survive across the inner retry loop (mutable list so
        # the closure can write through):
        #   state["emitted_session"] — did we already send the session event?
        #   state["emitted_any_text"] — did the model emit any delta?
        #                                Used to gate the auth-fallback
        #                                retry: only retry if no partial
        #                                content was shipped (otherwise
        #                                retry would double-print).
        state = {"emitted_session": False, "emitted_any_text": False}

        def make_on_event() -> Callable[[dict], None]:
            def on_event(ev: dict) -> None:
                etype = ev.get("type")
                subtype = ev.get("subtype")

                if etype == "system" and subtype == "init":
                    if not state["emitted_session"]:
                        emit("session", {"session_id": ev.get("session_id")})
                        state["emitted_session"] = True
                    return
                if etype == "system" and subtype and subtype.startswith("hook_"):
                    return
                if etype == "assistant":
                    msg = ev.get("message") or {}
                    content = msg.get("content") or []
                    for block in content:
                        btype = block.get("type")
                        if btype == "text":
                            text = block.get("text") or ""
                            if text:
                                emit("delta", {"text": text})
                                state["emitted_any_text"] = True
                        elif btype == "tool_use":
                            tname = block.get("name") or "tool"
                            tid = block.get("id") or ""
                            tinput = block.get("input") or {}
                            mapped = _map_tool_use(tname, tinput)
                            mapped["tool_use_id"] = tid
                            emit("tool", mapped)
                    return
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
                    return
                if etype == "result":
                    usage = ev.get("usage") or {}
                    out_tokens = usage.get("output_tokens") or 0
                    # Phase 8.1.3 (warm path mirror) — surface empty
                    # success so the dashboard doesn't render a silent
                    # "no response" toast when hooks failed. Same logic
                    # as the cold-spawn path below.
                    if not state["emitted_any_text"] and out_tokens == 0:
                        result_text = ev.get("result")
                        is_empty_result = (
                            result_text is None
                            or (isinstance(result_text, str) and not result_text.strip())
                        )
                        if is_empty_result:
                            emit("error", {
                                "message": "claude_returned_empty_response",
                                "detail": (
                                    "Claude Code completed successfully but returned no content. "
                                    "Most common cause: a SessionStart hook errored. Check "
                                    "`pm2 logs claude-bridge --err --lines 50`. Switch to Cloud "
                                    "mode in the meantime to bypass the local CLI."
                                ),
                            })
                    emit("done", {
                        "stop_reason": ev.get("stop_reason"),
                        "input_tokens": usage.get("input_tokens"),
                        "output_tokens": out_tokens,
                        "total_cost_usd": ev.get("total_cost_usd"),
                        "num_turns": ev.get("num_turns"),
                        "warm": True,  # debugging — confirms warm path served this turn
                    })
                    return
                if etype == "system" and subtype == "error":
                    raw_detail = ev.get("message") or json.dumps(ev)[:200]
                    emit("error", {
                        "message": "claude_subprocess_error",
                        "detail": _redact_secrets(str(raw_detail)),
                    })

            return on_event

        ok = wp.send_turn(prompt_text, make_on_event(), max_seconds=300)
        if ok:
            return True

        # send_turn returned False — process died mid-turn or stream
        # ended without a result event. Pull captured stderr to decide
        # whether this looks like a subscription auth/quota failure.
        # If it does AND we haven't shipped any text yet AND we weren't
        # already on the paid API key, fall over: kill the warm proc,
        # mark the pool sticky-paid, respawn with ANTHROPIC_API_KEY in
        # env, retry send_turn ONCE.
        stderr_tail = ""
        try:
            stderr_tail = wp.recent_stderr()
        except Exception:
            pass
        exit_code = wp.proc.poll()
        wp.kill(reason="send_turn_failed")

        should_fallback = (
            not state["emitted_any_text"]
            and not wp.force_api_key
            and _is_auth_failure(stderr_tail, exit_code)
        )
        if not should_fallback:
            # Warm process died for a non-auth reason. Two sub-cases:
            #
            # 1. No text was streamed yet — safe to fall back to cold
            #    spawn. Return False so the dispatcher runs
            #    _run_chat_via_claude with the enriched PATH lookup that
            #    survives launchd's slim PATH on macOS. This converts
            #    a silent "agent returned no response" into a clean
            #    cold-spawned turn.
            #
            # 2. Some text WAS streamed before the warm proc died —
            #    can't safely restart (would duplicate the partial
            #    response). Emit a structured error so the dashboard's
            #    error banner surfaces a real reason + Retry button.
            try:
                print(
                    f"[bridge] warm pool aborted (exit={exit_code}, emitted_text={state['emitted_any_text']}, "
                    f"stderr_tail={stderr_tail!r})",
                    file=sys.stderr,
                    flush=True,
                )
            except Exception:
                pass
            if not state["emitted_any_text"]:
                # Cold-spawn fallback. The dispatcher reads `return False`
                # as "warm did not handle this turn, try cold."
                return False
            # Partial stream — close it with a real error so the user
            # sees what happened instead of a silent done.
            emit("error", {
                "code": "warm_pool_aborted",
                "message": (
                    f"The warm Claude process died mid-stream (exit {exit_code}). "
                    "Click Retry to spawn a fresh process."
                ),
            })
            emit("done", {"warm_aborted": True})
            return True

        # Auth/quota fallback — spawn a fresh process forced onto the
        # paid API key path. Sticky-mark the pool so subsequent turns
        # in this session skip the subscription attempt entirely.
        _warm_mark_force_api_key(pool_key)
        # Give the operator a one-line notice in the chat transcript so
        # they know what happened. Markdown italics for soft styling.
        emit("delta", {
            "text": "_Subscription was capped — switched to API key for the rest of this conversation._\n\n"
        })
        state["emitted_any_text"] = True

        try:
            wp2 = _warm_use_or_create(
                pool_key=pool_key,
                agent=agent,
                root=root,
                prompt_text=prompt_text,
                resume_session_id=resume_session_id,
                force_api_key=True,
                disallowed_tools=disallowed_tools,
            )
        except Exception as e:
            print(f"[bridge] auth-fallback respawn failed: {e}", file=sys.stderr)
            emit("done", {"warm_aborted": True, "fallback_attempted": True})
            return True

        if not wp2.is_alive():
            wp2.kill(reason="dead_at_send_after_fallback")
            emit("done", {"warm_aborted": True, "fallback_attempted": True})
            return True

        ok2 = wp2.send_turn(prompt_text, make_on_event(), max_seconds=300)
        if not ok2:
            # Both paths failed. Kill the second proc and bail — the
            # client will surface the empty-stream banner with its Retry
            # button as before.
            wp2.kill(reason="send_turn_failed_after_fallback")
            emit("done", {"warm_aborted": True, "fallback_attempted": True})
        return True


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
    def _handle_cli_diagnostics(self) -> None:
        # Per-CLI install + version probe. Used by the dashboard's
        # /operations page and the chat-header status dot to surface a
        # clear "Gemini CLI missing" diagnostic to the operator.
        #
        # No secrets leak — we only return the binary path, version string,
        # and a `ready` boolean. Versions come from `<bin> --version` with
        # a 2s timeout each so a hung CLI can't wedge the diagnostic.
        out: dict[str, dict[str, Any]] = {}
        for name in ("claude", "codex", "gemini"):
            entry: dict[str, Any] = {"installed": False, "path": None, "version": None, "error": None}
            try:
                resolved = self._which_cli(name)
                if resolved:
                    entry["installed"] = True
                    entry["path"] = resolved
                    try:
                        env = dict(os.environ)
                        env["PATH"] = self._enriched_path(resolved)
                        env["NO_COLOR"] = "1"
                        env["NONINTERACTIVE"] = "true"
                        proc = subprocess.run(
                            [resolved, "--version"],
                            capture_output=True,
                            text=True,
                            timeout=2,
                            env=env,
                            check=False,
                            creationflags=_WINDOWLESS_FLAGS,
                        )
                        ver = ((proc.stdout or proc.stderr) or "").strip().splitlines()
                        if ver:
                            entry["version"] = ver[0][:120]
                    except subprocess.TimeoutExpired:
                        entry["error"] = "version_probe_timed_out"
                    except Exception as e:
                        entry["error"] = _redact_secrets(str(e))[:200]
            except Exception as e:
                entry["error"] = _redact_secrets(str(e))[:200]
            out[name] = entry
        self._json(200, {
            "ok": True,
            "platform": os.name,
            "cli": out,
            "search_paths": self._macos_linux_search_paths() if os.name != "nt" else [],
        })

    def _split_cli_error(self, exc: BaseException, provider: str) -> tuple[str, str]:
        # Parse the "code|human message" convention used by _run_codex_cli /
        # _run_gemini_cli. Falls back to a generic code when the underlying
        # exception didn't follow the contract (e.g. unexpected TypeError).
        raw = str(exc or "").strip()
        if "|" in raw:
            head, _, tail = raw.partition("|")
            head = head.strip()
            if head and not any(c.isspace() for c in head) and head.startswith("cli_"):
                return head, _redact_secrets(tail.strip())
        if isinstance(exc, FileNotFoundError):
            return "cli_not_found", _redact_secrets(raw) or f"{provider} CLI not on PATH."
        if isinstance(exc, TimeoutError) or isinstance(exc, subprocess.TimeoutExpired):
            return "cli_timeout", f"{provider} timed out. Long prompts may need API-key mode."
        return f"{provider}_chat_failed", _redact_secrets(raw)[:600]

    def _run_chat_via_local_cli(
        self,
        provider: str,
        agent: str,
        root: Path,
        messages: list[dict],
        emit: Callable[[str, dict], None],
        chat_mode: str = "build",
    ) -> None:
        """Run one non-Claude local CLI turn and translate it to ChatWidget SSE."""
        # Resolve the agent's brain entry so the prompt can carry the actual
        # persona content into Codex/Gemini's context. Without this the
        # underlying runtime introduces itself as Codex or Gemini and the
        # operator's chosen agent persona is lost.
        #
        # Pass the agent slug so resolve_entry_file prefers <AGENT>.md (e.g.
        # HELIOS.md for the helios slug) over the generic CLAUDE.md fallback.
        # SunBiz-Agent hosts both Solara and Helios — without the slug, both
        # would receive Solara's CLAUDE.md and the identity would bleed.
        entry = resolve_entry_file(root, agent)
        prompt_text = self._build_local_cli_prompt(agent, messages, entry)
        if not prompt_text.strip():
            emit("error", {
                "code": "empty_user_message",
                "message": "The chat message was empty — type something and send again.",
            })
            emit("done", {})
            return

        # Codex / Gemini CLIs don't expose a structured plan-mode flag like
        # `claude --permission-mode plan`. The best we can do is (a) prepend
        # the plan-mode overlay to the prompt and (b) tell the dashboard the
        # bridge is honoring plan mode advisorily so the badge can show
        # "(advisory)". The model is asked NOT to call write/exec tools;
        # there is no hard gate the way the Claude CLI provides one.
        if chat_mode == "plan":
            prompt_text = _PLAN_MODE_OVERLAY.strip() + "\n\n" + prompt_text
            emit("info", {
                "chat_mode": "plan",
                "honored": "advisory",
                "detail": (
                    f"{provider} CLI has no plan-mode gate; overlay prepended "
                    "to the prompt but not enforced. Use Claude CLI for hard "
                    "plan-mode."
                ),
            })

        emit("agent_status", {"phase": "spawning", "agent": agent, "cwd": str(root)})
        emit("session", {"session_id": f"{provider}-{int(time.time() * 1000)}"})
        # Move to "thinking" BEFORE the blocking subprocess call so the
        # dashboard's status indicator updates immediately. The old order
        # (emit thinking AFTER the call returned) made the dashboard look
        # like it was stuck on "spawning" for 60-180s while codex/gemini
        # ran their internal tool loop silently.
        emit("agent_status", {"phase": "thinking"})

        # Wrap the codex/gemini call in the heartbeat ticker so the
        # dashboard sees an `agent_status thinking` event every 25s while
        # the subprocess runs — prevents the SSE inactivity watchdog
        # from firing on otherwise-silent code paths. See
        # _heartbeat_ticker docstring at module scope for the full
        # contract. `ticked_emit` MUST be used for every emit after the
        # call returns so the lock keeps covering main-thread emits.
        with _heartbeat_ticker(emit, thread_name=f"{provider}-heartbeat") as ticked_emit:
            # Pass chat_mode so each runtime can pick the right safety flag:
            #   plan  → codex --sandbox=read-only,   gemini --approval-mode=plan
            #   build → codex --sandbox=workspace-write, gemini --approval-mode=yolo
            # Without this, the CLIs were hardcoded to plan-mode equivalents
            # and the operator's /build command was ignored on these runtimes.
            if provider == "codex":
                text = self._run_codex_cli(root, prompt_text, chat_mode=chat_mode)
            elif provider == "gemini":
                text = self._run_gemini_cli(root, prompt_text, chat_mode=chat_mode)
            else:
                ticked_emit("error", {
                    "code": "invalid_cli_provider",
                    "message": f"Unknown CLI provider: {provider}. Pick Claude / Codex / Gemini.",
                })
                ticked_emit("done", {})
                return
        # Past this point we're past the ticker — but every remaining
        # emit goes through ticked_emit anyway so future code paths
        # that might re-enter blocking work stay covered by the lock.
        emit = ticked_emit
        text = (text or "").strip()
        if not text:
            # Defense in depth — the inner _run_*_cli functions now raise
            # cli_empty_output explicitly when this happens, so we should
            # never get here. Kept for paranoia / future provider additions.
            emit("error", {
                "code": "cli_empty_output",
                "message": f"{provider} returned an empty response. Likely a quota or auth issue.",
            })
            emit("done", {})
            return
        emit("delta", {"text": text})
        emit("done", {})

    def _build_local_cli_prompt(
        self,
        agent: str,
        messages: list[dict],
        entry: Path | None,
    ) -> str:
        """Compose the prompt sent to Codex/Gemini for one turn.

        2026-05-22 fix — operators reported that asking Bravo "who are you?"
        via the Codex CLI got "I'm Codex, backend executor..." in response,
        breaking the agent identity contract. Root cause: the prior prompt
        named the runtime ("running through Codex CLI") and lacked a hard
        identity lock + the agent's actual persona content.

        The runtime (`provider`) and repo path (`root`) are intentionally
        NOT taken as arguments — naming the runtime in this prompt is
        exactly what produced the bug, and the persona file path is fully
        captured by the resolved `entry`.

        Now the prompt:
          1. Hard-locks the model into the agent's identity at the top —
             "You are BRAVO. You are not Codex. You are not Gemini."
          2. Embeds the agent's persona/brain entry as the model's IDENTITY,
             not as instructions about a separate character.
          3. Tells the model explicitly: if asked "who are you", the answer
             is the AGENT, never the runtime. The runtime is an
             implementation detail the operator does not need to think
             about.
          4. Provides the conversation transcript and the latest turn last,
             so the model treats the identity block as established fact and
             responds in character.
        """
        agent_upper = agent.upper()

        # Read the agent's brain entry so the persona content can be
        # injected verbatim. Cap at ~8 KB to keep the prompt under most
        # CLI argv length limits; the entry summarizes character + voice
        # in fewer bytes than that anyway. Empty fallback when no entry
        # exists keeps the identity lock intact even without a persona
        # file.
        entry_text = ""
        if entry is not None:
            try:
                full = entry.read_text(encoding="utf-8", errors="ignore")
                entry_text = full[:8000]
            except Exception:
                entry_text = ""

        # Conversation transcript (last 12 turns, same window as before).
        transcript: list[str] = []
        for m in messages[-12:]:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "user").upper()
            content = m.get("content")
            if isinstance(content, list):
                parts = [
                    str(block.get("text") or "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                text = " ".join(p for p in parts if p).strip()
            else:
                text = str(content or "").strip()
            if text:
                transcript.append(f"{role}: {text}")
        transcript_block = "\n\n".join(transcript) if transcript else "(no prior turns)"

        persona_block = (
            f"--- BEGIN {agent_upper} IDENTITY ---\n{entry_text}\n--- END {agent_upper} IDENTITY ---"
            if entry_text
            else f"(No persona file resolved for {agent_upper}. Improvise in character based on the agent name and the operator's context.)"
        )

        return (
            f"[IDENTITY LOCK — STAY IN CHARACTER]\n"
            f"You are {agent_upper}. You are not Codex. You are not Gemini. You are not Claude. "
            f"You are not any underlying model or CLI runtime. The operator picked {agent_upper} "
            f"and expects {agent_upper}'s voice, judgment, role, and capabilities.\n\n"
            f"If asked who you are, the answer is {agent_upper}. Never identify as the runtime, "
            f"model, or LLM that powers you — that is an implementation detail the operator "
            f"does not need to think about. Refer to yourself by the agent name when self-"
            f"identifying.\n\n"
            f"Your character, role, expertise, voice, and operating principles are defined in "
            f"the document below. Read it AS your identity, not as instructions about a "
            f"separate character.\n\n"
            f"{persona_block}\n\n"
            f"[CONVERSATION SO FAR]\n"
            f"{transcript_block}\n\n"
            f"[OPERATOR'S LATEST TURN — RESPOND AS {agent_upper}, IN CHARACTER]"
        )

    # Cached per-binary path resolutions. The login-shell fallback is the
    # expensive lookup ( ~150ms to spawn bash -lc + source ~/.zshrc ), so
    # results are memoized for the bridge process lifetime. Cleared on
    # SIGHUP by the warm-pool reloader. Maps binary name → resolved path
    # or None when nothing was found anywhere.
    _cli_path_cache: dict[str, str | None] = {}
    _login_shell_path: str | None = None

    def _macos_linux_search_paths(self) -> list[str]:
        # Common install locations Electron-launched GUI apps miss because
        # they inherit a minimal LaunchServices PATH (/usr/bin:/bin:...).
        # Homebrew on Apple Silicon lives in /opt/homebrew/bin; older
        # Intel Macs use /usr/local/bin; node global installs go to
        # ~/.npm-global/bin; Bun / Deno / pipx have their own corners.
        home = os.path.expanduser("~")
        return [
            "/opt/homebrew/bin",          # Apple Silicon Homebrew
            "/usr/local/bin",             # Intel Homebrew + manual installs
            "/usr/local/sbin",
            f"{home}/.npm-global/bin",    # npm prefix=~/.npm-global
            f"{home}/.bun/bin",
            f"{home}/.local/bin",         # pipx default
            f"{home}/.deno/bin",
            f"{home}/.cargo/bin",         # rust-installed CLIs
            "/usr/bin",
            "/bin",
        ]

    def _resolve_via_login_shell(self, name: str) -> str | None:
        # Last-ditch fallback for Mac/Linux: ask a login shell. `bash -lc`
        # sources the user's profile so PATH matches what they see in
        # Terminal. We use `command -v` which is POSIX-safe (zsh + bash
        # both support it) and faster than `which`. 1.5s timeout so a
        # broken profile can't wedge chat for 30s.
        if os.name == "nt":
            return None
        try:
            proc = subprocess.run(
                ["bash", "-lc", f"command -v {shlex.quote(name)} || true"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
                creationflags=_WINDOWLESS_FLAGS,
            )
            path = (proc.stdout or "").strip().splitlines()
            if path and path[0] and os.path.exists(path[0]):
                return path[0]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return None

    def _login_shell_full_path(self) -> str | None:
        # One-shot lookup of `echo $PATH` inside a login shell. Cached so
        # subprocess env enrichment doesn't re-spawn bash on every chat.
        if self._login_shell_path is not None:
            return self._login_shell_path
        if os.name == "nt":
            self._login_shell_path = ""
            return None
        try:
            proc = subprocess.run(
                ["bash", "-lc", "echo $PATH"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
                creationflags=_WINDOWLESS_FLAGS,
            )
            full = (proc.stdout or "").strip().splitlines()
            self._login_shell_path = full[0] if full else ""
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            self._login_shell_path = ""
        return self._login_shell_path or None

    def _which_cli(self, name: str) -> str | None:
        # Cached. None means "tried everything, not found"; "" never used.
        if name in self._cli_path_cache:
            return self._cli_path_cache[name]
        # 1. Standard shutil.which against the subprocess PATH. Fast win.
        found = shutil.which(name)
        if not found and os.name == "nt":
            for suffix in (".cmd", ".exe"):
                found = shutil.which(name + suffix)
                if found:
                    break
        # 2. Mac/Linux: walk curated install dirs by hand. Catches Homebrew /
        #    npm-global / Bun / Deno / pipx / cargo that LaunchServices's
        #    GUI-inherited PATH doesn't include.
        if not found and os.name != "nt":
            for d in self._macos_linux_search_paths():
                candidate = os.path.join(d, name)
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    found = candidate
                    break
        # 3. Last resort: spawn a login shell and ask. Slow ( ~150ms ) so
        #    cache the result; cheap on subsequent calls.
        if not found:
            found = self._resolve_via_login_shell(name)
        self._cli_path_cache[name] = found or None
        return found or None

    def _enriched_path(self, found_bin: str | None) -> str:
        # Build the PATH passed to subprocesses. Order: dir of sys.executable
        # FIRST (so subprocess `python3` resolves to the same venv python
        # the bridge runs, not /usr/bin/python3 — the 2026-06-10 SunBiz
        # send_gateway ImportError was claude's bash subprocess picking up
        # system python which had no `supabase` package), parent of the
        # resolved binary (so its sibling helpers like `gemini-utils`
        # resolve), then the curated Mac/Linux dirs, then the login-shell
        # PATH if we have it, then whatever was already in os.environ.
        parts: list[str] = []
        py_bin_dir = os.path.dirname(sys.executable)
        if py_bin_dir:
            parts.append(py_bin_dir)
        if found_bin:
            parts.append(os.path.dirname(found_bin))
        if os.name != "nt":
            parts.extend(self._macos_linux_search_paths())
            shell_path = self._login_shell_full_path()
            if shell_path:
                parts.extend(shell_path.split(os.pathsep))
        existing = os.environ.get("PATH", "")
        if existing:
            parts.extend(existing.split(os.pathsep))
        # De-dup preserving order. Some paths show up multiple times via
        # the layered sources above; dedupe so PATH doesn't grow unbounded.
        seen: set[str] = set()
        ordered: list[str] = []
        for p in parts:
            if p and p not in seen:
                seen.add(p)
                ordered.append(p)
        return os.pathsep.join(ordered)

    def _run_cli_command(
        self,
        args: list[str],
        root: Path,
        # ====================================================================
        # PAIRED with oasis-command-center/components/ChatWidget.tsx —
        # BRIDGE_TOOL_TIMEOUT_MS (browser fetch timeout) MUST stay >= this
        # value (in ms). If the client cap is lower, the browser cuts off
        # a working bridge run; if it's higher, the user waits past the
        # point the server has already given up.
        # The watchdog further down (WATCHDOG_TIMEOUT_SEC) likewise pairs
        # with the client's SSE_INACTIVITY_TIMEOUT_MS.
        # ====================================================================
        # Bumped 2026-05-28 from 300s (5min) to 21600s (6h). CC hit
        # the prior cap on Gemini CLI tool-use loops that legitimately
        # take an hour+ (deep research, multi-file refactor). The
        # SSE watchdog further down still kills the subprocess after
        # WATCHDOG_TIMEOUT_SEC seconds of pure silence, so a wedged
        # CLI still gets reclaimed — this just stops killing CLIs
        # that are actually working.
        timeout_s: int = 21_600,
        path_hint: str | None = None,
        stdin_input: str | None = None,
    ) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        # Enriched PATH so subprocess children (gemini → node → npm
        # subcommands, codex → bash helpers, claude → ripgrep + sed
        # detection) all see the same install dirs the bridge used to
        # locate the entry binary. Without this, even when _which_cli
        # finds Gemini at /opt/homebrew/bin/gemini, Gemini's own
        # subprocess spawns can fail because Node's PATH is the slim
        # LaunchServices PATH.
        env["PATH"] = self._enriched_path(path_hint or (args[0] if args else None))
        env.update({
            "CI": "true",
            "NONINTERACTIVE": "true",
            "PAGER": "cat",
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
        })
        cmd = [*_command_without_cmd_shim(args[0]), *args[1:]] if args else args
        # When stdin_input is supplied (Codex v0.136+ prompt path), pipe it
        # via subprocess.PIPE + input=... and let _safe_run feed it. Without
        # input, stay on DEVNULL so the CLI doesn't sit waiting for stdin
        # that will never come (the SubprocessError default).
        run_kwargs: dict = dict(
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            creationflags=_WINDOWLESS_FLAGS,
            startupinfo=_windowless_startupinfo(),
        )
        if stdin_input is None:
            run_kwargs["stdin"] = subprocess.DEVNULL
        else:
            run_kwargs["stdin"] = subprocess.PIPE
            run_kwargs["input"] = stdin_input
        return _safe_run(cmd, **run_kwargs)

    def _run_codex_cli(self, root: Path, prompt_text: str, chat_mode: str = "build") -> str:
        codex_bin = self._which_cli("codex")
        if not codex_bin:
            # Structured error so the dispatcher can emit a specific code
            # to the dashboard. Format: "<code>|<human message>" — parsed
            # at the dispatch site. Keeps backward-compat with the existing
            # RuntimeError surface for callers that just stringify.
            raise FileNotFoundError(
                "cli_not_found|Codex CLI isn't installed on this machine. "
                "Install it via `npm i -g @openai/codex` then click Retry."
            )
        # Plan mode → read-only sandbox (no writes, no shell). Build mode →
        # workspace-write so codex can actually edit files in the agent root.
        # "danger-full-access" is intentionally NOT exposed; operators get
        # workspace-scoped write at most, scoped to the agent's repo root.
        sandbox_mode = "read-only" if chat_mode == "plan" else "workspace-write"
        out_path = ""
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as fh:
                out_path = fh.name
            # Codex CLI v0.136+ (gpt-5.5 era) reads the prompt from STDIN when
            # invoked with --stdin, even when a positional prompt arg is
            # present. Previously we passed the prompt as a positional arg
            # and stdin=DEVNULL — the new CLI saw EOF on stdin and emitted
            # "Reading additional input from stdin..." then exited 1.
            # Switching to stdin-piping matches Codex's documented batch
            # invocation pattern and works with both old and new CLI versions.
            args = [
                codex_bin,
                "exec",
                "--sandbox",
                sandbox_mode,
                "--skip-git-repo-check",
                "-C",
                str(root),
                "--output-last-message",
                out_path,
                "-",  # read prompt from stdin
            ]
            # Bumped 2026-05-28 from 180s to 21600s (6h) — long Codex
            # refactor runs were getting killed mid-loop. Watchdog
            # below catches true wedges.
            proc = self._run_cli_command(
                args, root, timeout_s=21_600, path_hint=codex_bin,
                stdin_input=prompt_text,
            )
            try:
                text = Path(out_path).read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                text = ""
            if proc.returncode != 0:
                detail = _redact_secrets((proc.stderr or proc.stdout or "").strip())[:2000]
                # Detect auth-required state from codex's exit signature.
                # `codex exec` returns non-zero + writes "Please run `codex
                # login`" to stderr when the user's account isn't signed in.
                low = (detail or "").lower()
                if "codex login" in low or "not signed in" in low or "unauthorized" in low:
                    raise RuntimeError(
                        "cli_auth_required|Codex CLI says you need to sign in. "
                        "Run `codex login` in Terminal, then click Retry."
                    )
                raise RuntimeError(
                    f"cli_nonzero_exit|Codex exited {proc.returncode}. "
                    f"Stderr tail: {detail or '(empty)'}"
                )
            resolved = text or self._strip_cli_noise(proc.stdout)
            if not resolved.strip():
                stderr_tail = _redact_secrets((proc.stderr or "").strip())[:600]
                raise RuntimeError(
                    "cli_empty_output|Codex ran but returned nothing. "
                    f"Stderr tail: {stderr_tail or '(none)'} — likely a "
                    "quota or auth issue."
                )
            return resolved
        finally:
            if out_path:
                try:
                    Path(out_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _run_gemini_cli(self, root: Path, prompt_text: str, chat_mode: str = "build") -> str:
        gemini_bin = self._which_cli("gemini")
        if not gemini_bin:
            raise FileNotFoundError(
                "cli_not_found|Gemini CLI isn't installed on this machine. "
                "Install via `npm i -g @google/generative-ai-cli` or `brew "
                "install gemini-cli`, then click Retry."
            )
        # Plan mode → --approval-mode=plan (gemini researches + proposes,
        # never executes). Build mode → --approval-mode=yolo (auto-approve
        # tool calls so chat doesn't hang on stdin prompts; bridge runs
        # non-interactively so any approval prompt is fatal).
        approval_mode = "plan" if chat_mode == "plan" else "yolo"
        args = [
            gemini_bin,
            "-p",
            self._cli_arg_prompt(prompt_text),
            "--output-format",
            "json",
            "--approval-mode",
            approval_mode,
            "--skip-trust",
        ]
        # Bumped 2026-05-28 from 120s to 21600s (6h). CC observed
        # this firing on legitimate multi-file Gemini runs — the prior
        # 120s was the single most operator-visible bug in the bridge.
        # Watchdog (600s of pure SSE silence) still reclaims a wedge.
        proc = self._run_cli_command(args, root, timeout_s=21_600, path_hint=gemini_bin)
        if proc.returncode != 0:
            detail = _redact_secrets((proc.stderr or proc.stdout or "").strip())[:2000]
            low = (detail or "").lower()
            # Gemini CLI prints "Please run `gemini auth login`" when the
            # OAuth refresh token is missing or expired. Surface that as a
            # specific code so the dashboard hints the right command.
            if "gemini auth" in low or "not authenticated" in low or "401" in low:
                raise RuntimeError(
                    "cli_auth_required|Gemini CLI says you need to sign in. "
                    "Run `gemini auth login` in Terminal, then click Retry."
                )
            # `--skip-trust` is a 2025+ flag. Old gemini-cli builds error on
            # unknown flag — detect that and tell the operator to upgrade
            # rather than blame the prompt.
            if "unknown" in low and ("skip-trust" in low or "approval-mode" in low):
                raise RuntimeError(
                    "cli_outdated|Your Gemini CLI is too old to accept the "
                    "--skip-trust flag. Run `npm i -g @google/generative-ai-cli` "
                    "to upgrade, then click Retry."
                )
            raise RuntimeError(
                f"cli_nonzero_exit|Gemini exited {proc.returncode}. "
                f"Stderr tail: {detail or '(empty)'}"
            )
        extracted = self._extract_gemini_text(proc.stdout) or self._strip_cli_noise(proc.stdout)
        if not extracted.strip():
            stderr_tail = _redact_secrets((proc.stderr or "").strip())[:600]
            raise RuntimeError(
                "cli_empty_output|Gemini ran but returned no content. "
                f"Stderr tail: {stderr_tail or '(none)'} — often a quota "
                "exceeded or auth issue. Check `gemini --help` in Terminal."
            )
        return extracted

    def _extract_gemini_text(self, stdout: str) -> str:
        text = (stdout or "").strip()
        if not text:
            return ""
        candidates = [line.strip() for line in text.splitlines() if line.strip().startswith("{")]
        if text.startswith("{"):
            candidates.append(text)
        for candidate in reversed(candidates):
            try:
                data = json.loads(candidate)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            for key in ("response", "text", "content", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            nested = data.get("candidates")
            if isinstance(nested, list) and nested:
                return json.dumps(nested[0], ensure_ascii=False)
        return ""

    def _strip_cli_noise(self, stdout: str) -> str:
        lines: list[str] = []
        for line in (stdout or "").splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("Warning:") or s.startswith("[ERROR]") or s.startswith("[INFO]"):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _cli_arg_prompt(self, prompt_text: str) -> str:
        # Windows .cmd shims are brittle when an argv token contains literal
        # newlines. Preserve the transcript shape as escaped line breaks.
        return prompt_text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")

    def _run_chat_via_claude(
        self,
        agent: str,
        root: Path,
        messages: list[dict],
        emit: Callable[[str, dict], None],
        resume_session_id: str | None = None,
        chat_mode: str = "build",
        disallowed_tools: list[str] | None = None,
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

        # Resolve the claude binary via the same enriched lookup the
        # codex/gemini paths use — walks Homebrew + npm-global + Bun +
        # Deno + login-shell PATH so Electron's slim GUI PATH (no
        # ~/.nvm/.../bin) doesn't make us miss the install.
        claude_bin = self._which_cli("claude")
        if not claude_bin:
            raise FileNotFoundError("claude CLI not on PATH")

        # Build args — copying telegram's pattern + adding stream-json
        # output so we get incremental events for SSE.
        # Plan mode swaps bypassPermissions → plan so the Claude CLI's
        # native plan-mode gate prevents Write/Edit/Bash from firing.
        # The operator types /build to drop back to bypassPermissions on
        # the next turn (warm pool is bypassed in plan mode — see
        # _run_chat_via_warm_pool — so each plan-mode turn cold-spawns
        # with the correct permission mode).
        permission_mode = "plan" if chat_mode == "plan" else "bypassPermissions"
        # Multi-agent repos (SunBiz-Agent hosts both Solara at CLAUDE.md AND
        # Helios at HELIOS.md): suppress project's CLAUDE.md and inject the
        # per-agent file as --append-system-prompt so Helios doesn't speak in
        # Solara's voice when spawned in the shared cwd. Single-agent repos
        # (Bravo, Atlas, Maven, etc.) return ("", "project,local") — claude
        # loads CLAUDE.md the usual way and behavior is unchanged.
        identity_override, setting_sources = claude_identity_overlay(root, agent)
        args = [
            claude_bin,
            "-p", prompt_text,
            # bypassPermissions auto-approves MCP tool calls in addition to
            # edits. acceptEdits prompts for MCP tools, which hangs forever
            # because stdin is DEVNULL. Bridge runs as the operator in the
            # operator's repos, so the trust boundary already permits this.
            "--permission-mode", permission_mode,
            "--output-format", "stream-json",
            "--verbose",  # required when --output-format=stream-json
            "--include-partial-messages",
            "--max-turns", "12",
            "--setting-sources", setting_sources,
        ]
        if identity_override:
            args.extend(["--append-system-prompt", identity_override])
        # Boot-context strip — see warm_claude_pool.chat_lean_args() for
        # the measured 87% drop in cache_creation_input_tokens (50k → 6.6k).
        # Splice before --resume so resume args (if any) come last.
        args.extend(_warm_chat_lean_args())
        # Role-based tool gating — the HARD wall. When the proxy forwarded a
        # disallowed set (non-owner SunBiz employee), Claude Code itself
        # refuses to invoke these tools; the model literally cannot get a
        # shell or write files. Empty for owner/admin + CC's localhost path.
        # Tokens are already sanitized to [A-Za-z]+ by _sanitize_disallowed_tools;
        # shell=False on the spawn means there's no shell to inject into anyway.
        disallowed_tools = disallowed_tools or []
        if disallowed_tools:
            args.extend(["--disallowed-tools", *disallowed_tools])
        # Latency win: if the dashboard provided a session_id from a prior
        # turn, pass --resume so claude skips cold context-load. First turn
        # mints a new session (claude assigns the id and we surface it via
        # the 'session' SSE event below).
        if resume_session_id:
            args.extend(["--resume", resume_session_id])

        # Spawn env — same approach as telegram_agent. Inherit current env,
        # set non-interactive flags so claude doesn't try to render TTY UI.
        #
        # NOTE on auth: this cold-spawn path deliberately keeps the env
        # unmodified — claude picks ANTHROPIC_API_KEY if set, OAuth
        # otherwise. The warm-pool path (warm_claude_pool.py) IS
        # subscription-first via build_claude_spawn_env() and has the
        # auth-fallback retry from Phase 1 of giggly-reef. Cold spawn only
        # fires when warm pool is disabled (OASIS_NO_WARM_POOL=1) or
        # crashes — a rare path. Leaving the env model as-is for cold
        # spawn keeps the change-surface tight; if Phase 2/3 wants to
        # unify the auth model across both paths, swap this dict for
        # build_claude_spawn_env() AND add the retry-on-auth-failure
        # block (cold spawn has no equivalent today, so going
        # subscription-first here without the retry would regress the
        # rare-path UX).
        env = dict(os.environ)
        # Enriched PATH — Claude's own child processes (ripgrep, node, sed,
        # the user's hooks) need to see Homebrew + npm-global + nvm. Same
        # treatment _run_cli_command gives codex/gemini spawns.
        env["PATH"] = self._enriched_path(claude_bin)
        env.update({
            "CI": "true",
            "NONINTERACTIVE": "true",
            "PAGER": "cat",
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
            # Phase 8.1.1 — Claude Code hooks (.claude/settings.local.json)
            # reference `${CLAUDE_PROJECT_DIR}/scripts/hooks/*.py`. Without
            # this env var the substitution produces `/scripts/hooks/...`,
            # the hook exits 2, and Claude Code 2.1.39+ suppresses the
            # assistant response — the bridge then sees an empty result
            # event and the dashboard renders "no response from agent".
            # Setting CLAUDE_PROJECT_DIR to the same path we use for cwd
            # keeps hooks consistent with what the operator would see
            # running `claude -p` directly in that repo.
            "CLAUDE_PROJECT_DIR": str(root),
        })
        # Defense-in-depth: expose the role's denied-tool set to hooks/logging
        # in the spawned environment. The --disallowed-tools FLAG above is the
        # actual wall; this env var is informational only (a hook could log or
        # double-check it, but Claude Code does not read it for gating).
        if disallowed_tools:
            env["BRIDGE_DISALLOWED_TOOLS"] = " ".join(disallowed_tools)

        # Synthetic status pre-spawn so the dashboard can show "starting Atlas
        # in CFO-Agent…" instantly, before claude's cold start (~10-30s).
        emit("agent_status", {
            "phase": "spawning",
            "agent": agent,
            "cwd": str(root),
        })

        try:
            proc = _safe_popen(
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
        # Track whether we've already sent the terminal `done` event so
        # we never double-emit AND never leave the SSE stream open
        # without one. Closes the chat-hang bug from 2026-05-10: claude
        # could exit cleanly (rc=0) after a short reply without ever
        # emitting a `result` event, leaving the dashboard reader loop
        # waiting indefinitely. Now every exit path checks this flag.
        emitted_done = False
        # Last-event wall-clock for the watchdog thread below. Reset on
        # every event we receive from claude's stdout; if it goes stale
        # for >WATCHDOG_TIMEOUT_SEC we kill the proc so the SSE stream
        # can close. Protects against pure-stdin hangs (e.g. claude
        # waiting for an MCP tool that never returns). Wrapped in a
        # list so the closure below can observe live updates from the
        # event loop without needing `nonlocal`.
        last_event_at = [time.time()]
        # Bumped 2026-05-28 from 90s to 600s (10 min). The dashboard
        # side's SSE_INACTIVITY_TIMEOUT_MS is now 600_000 too, so the
        # client + server agree on what counts as "actually wedged."
        # 600s is the safety net behind the 25s heartbeat ticker —
        # only fires if the ticker itself stalls, not for legitimate
        # silent tool-use windows.
        WATCHDOG_TIMEOUT_SEC = 600
        watchdog_stop = threading.Event()

        def _watchdog() -> None:
            while not watchdog_stop.wait(5):
                if time.time() - last_event_at[0] > WATCHDOG_TIMEOUT_SEC:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return

        watchdog_thread = threading.Thread(target=_watchdog, daemon=True, name="bridge-watchdog")
        watchdog_thread.start()
        # Track when the most recent emit was a tool_use, so the next
        # text delta gets a paragraph break prepended. CC reported chat
        # showing "I'll send the email now.Email sent..." mashed
        # together with no separator — Claude Code emits a text block
        # before the tool_use ("I'll do X") and a separate text block
        # after the tool_result ("Done — result"), and the bridge was
        # concatenating them without a newline. Inserting `\n\n`
        # creates a real paragraph break in the rendered markdown.
        last_emitted_was_tool = False
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                # Reset watchdog on EVERY readline — including ones we
                # skip below — so a noisy hook stream doesn't trip the
                # timeout. Only true silence does.
                last_event_at[0] = time.time()
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
                                #
                                # Paragraph fix: when the previous emit was
                                # a tool_use AND this text doesn't already
                                # start with a newline, prepend `\n\n`. This
                                # turns the single concatenated bubble into
                                # two paragraphs ("I'll send the email." /
                                # "Email sent — subject X.") matching the
                                # logical phases of the response.
                                if (
                                    last_emitted_was_tool
                                    and accumulated_text
                                    and not text.startswith("\n")
                                    and not accumulated_text.endswith("\n")
                                ):
                                    emit("delta", {"text": "\n\n"})
                                    accumulated_text += "\n\n"
                                emit("delta", {"text": text})
                                accumulated_text += text
                                last_emitted_was_tool = False
                        elif btype == "tool_use":
                            tname = block.get("name") or "tool"
                            tid = block.get("id") or ""
                            tinput = block.get("input") or {}
                            mapped = _map_tool_use(tname, tinput)
                            mapped["tool_use_id"] = tid
                            emit("tool", mapped)
                            last_emitted_was_tool = True
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
                    out_tokens = usage.get("output_tokens") or 0
                    # Phase 8.1.3 — surface the "empty success" case. Claude
                    # Code 2.1.39 returns a clean result event with no text
                    # blocks and 0 output_tokens when the model declined to
                    # answer (often because a SessionStart hook errored
                    # before the first turn). The dashboard previously saw
                    # a silent done event and rendered a generic "no
                    # response" toast. Now the operator gets the actual
                    # diagnostic — including the CLAUDE_PROJECT_DIR-not-set
                    # hint, which was the bug Phase 8.1.1 fixed.
                    if not accumulated_text.strip() and out_tokens == 0:
                        result_text = ev.get("result")
                        is_empty_result = (
                            result_text is None
                            or (isinstance(result_text, str) and not result_text.strip())
                        )
                        if is_empty_result:
                            emit("error", {
                                "message": "claude_returned_empty_response",
                                "detail": (
                                    "Claude Code completed successfully but returned no content "
                                    "(output_tokens=0, no text blocks emitted). Most common cause: "
                                    "a SessionStart hook errored before the assistant turn ran. "
                                    "Check `pm2 logs claude-bridge --err --lines 50` for hook "
                                    "exit codes. If you recently changed .claude/settings.local.json "
                                    "hooks, verify they run standalone with "
                                    "`echo '{\"hook_event_name\":\"SessionStart\"}' | python <hook_script>`. "
                                    "Switch the chat to Cloud mode in the meantime to bypass the local CLI."
                                ),
                            })
                    emit("done", {
                        "stop_reason": ev.get("stop_reason"),
                        "input_tokens": usage.get("input_tokens"),
                        "output_tokens": out_tokens,
                        "total_cost_usd": ev.get("total_cost_usd"),
                        "num_turns": ev.get("num_turns"),
                    })
                    emitted_done = True
                    continue

                # 6. Anything else (e.g. system/error) — surface as error.
                if etype == "system" and subtype == "error":
                    raw_detail = ev.get("message") or json.dumps(ev)[:200]
                    emit("error", {
                        "message": "claude_subprocess_error",
                        "detail": _redact_secrets(str(raw_detail)),
                    })

            rc = proc.wait(timeout=5)
            watchdog_stop.set()  # stream's done; stop the timeout timer
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
            # Always emit a terminal `done` if the loop didn't already.
            # Covers two real failure modes seen 2026-05-10:
            #   (1) clean exit (rc=0) where claude flushed assistant text
            #       blocks but never emitted a `result` event — the SSE
            #       stream was being left open with no terminal signal,
            #       so the dashboard reader hung forever
            #   (2) error exit (rc!=0) — the pre-fix only emitted done
            #       when accumulated_text was empty; if claude emitted
            #       partial text then crashed, no done was sent
            if not emitted_done:
                emit("done", {
                    "stop_reason": "ok" if rc == 0 else f"claude_exit_{rc}",
                    "num_turns": 0,
                })
                emitted_done = True
        except Exception as e:
            watchdog_stop.set()
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
            if not emitted_done:
                emit("done", {})
                emitted_done = True

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
        chat_mode: str = "build",
    ) -> None:
        system = _system_prompt_for(agent, root, entry)
        if chat_mode == "plan":
            system = system + _PLAN_MODE_OVERLAY
            tools_payload = [READ_FILE_TOOL, LIST_TOOLS_TOOL]
        else:
            tools_payload = [READ_FILE_TOOL, RUN_SCRIPT_TOOL, LIST_TOOLS_TOOL]
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
            "chat_mode": chat_mode,
        })

        for turn in range(MAX_TURNS):
            resp = _call_provider(
                provider, api_key, model, system, thread, stream=True, tools=tools_payload,
            )
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
                # Plan-mode default-deny — if the model produced a tool_use
                # outside the allowlist (e.g. the tools-payload filter was
                # bypassed by a malformed advertise), refuse here too.
                # Same belt-and-braces pattern as cloud-tool-runner.ts.
                if chat_mode == "plan" and tool_name not in _PLAN_MODE_TOOL_ALLOWLIST:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": use.get("id"),
                        "content": (
                            f"plan_mode_blocked: '{tool_name}' is not available "
                            f"in plan mode. Allowed: read_file, list_tools. "
                            f"Ask the operator to type /build before executing."
                        ),
                        "is_error": True,
                    })
                    continue
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
        # Per-entry root resolution. Default ('bravo' or absent) routes
        # to the bridge's agent root (CEO-Agent); 'sunbiz' resolves to
        # SUNBIZ_AGENT_ROOT-style probe; others surface a config error.
        script_root, root_err = _resolve_script_root(spec.get("root"), root)
        if root_err is not None:
            return f"script_root_unresolved: {root_err}", True
        full_path = (script_root / rel_script).resolve()
        if not under_root(script_root, full_path) or not full_path.is_file():
            return (
                f"script_missing: {rel_script} not found under "
                f"{spec.get('root', 'bravo')} root ({script_root})"
            ), True

        cmd: list = [sys.executable, str(full_path)]
        subcmd = spec.get("subcmd")
        if subcmd:
            cmd.append(subcmd)
        cmd.extend(extra_args)

        timeout_s = 60 if spec.get("mutating") else 180

        try:
            proc = _safe_popen(
                cmd,
                cwd=str(script_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                creationflags=_WINDOWLESS_FLAGS,
                startupinfo=_windowless_startupinfo(),
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
            "skipping self-pair (run `python scripts/integrations/n8n_webhook_secret.py "
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
# lib/integrations-registry.ts in the oasis-command-center repo — exposed via
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
    # Workspace surface via scripts/integrations/google_tool.py.
    "GMAIL_APP_PASSWORD": "gws",
    "TELEGRAM_BOT_TOKEN": "telegram",
    "TWILIO_ACCOUNT_SID": "text_torrent",
    "JOTFORM_WEBHOOK_URL": "jotform",
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
        rc = _safe_run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=4,
        )
        if rc.returncode == 0:
            ver = rc.stdout.split("\n", 1)[0][:80]
            out["ffmpeg"] = {"status": "healthy", "metadata": {"via": "local_probe", "version": ver}}
    except Exception:
        pass

    # whisper: detect the Python module directly. Avoid the `whisper.exe`
    # console-script shim; it can spawn child python.exe without our flags.
    if "whisper" not in out:
        try:
            rc = _safe_run(
                [
                    sys.executable,
                    "-c",
                    "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('whisper') else 1)",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=6,
            )
            if rc.returncode == 0:
                out["whisper"] = {"status": "healthy", "metadata": {"via": "local_probe", "import": "ok"}}
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

    # Playwright: detect the Python module directly. Avoid the console-script
    # wrappers; they can spawn their own node/python children and leak conhost.
    try:
        rc = _safe_run(
            [
                sys.executable,
                "-c",
                "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('playwright') else 1)",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4,
        )
        if rc.returncode == 0:
            out["playwright"] = {"status": "healthy", "metadata": {"via": "local_probe", "import": "ok"}}
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
    # Stamp the heartbeat result into a watchable file in ~/.oasis so the
    # operator can verify the daemon thread is alive without grepping the
    # log (and without depending on Python's stdout flush behavior, which
    # under launchd's StandardOutPath buffers ~4KB before writing). The
    # file's mtime is the last successful ping; absence means the loop
    # never started or has been hung for >60s.
    last_ping_marker = _OASIS_DIR / "bridge_chat.last_heartbeat"
    while True:
        try:
            token = _self_pair_if_needed()
            if token:
                ok = _heartbeat_once(token)
                if ok:
                    try:
                        last_ping_marker.write_text(
                            f"{datetime.now(timezone.utc).isoformat()} ok\n",
                            encoding="utf-8",
                        )
                    except OSError:
                        pass
                else:
                    try:
                        last_ping_marker.write_text(
                            f"{datetime.now(timezone.utc).isoformat()} fail\n",
                            encoding="utf-8",
                        )
                    except OSError:
                        pass
        except Exception as exc:
            # Never let an exception kill the thread — that would silently
            # take the dashboard's "bridge online" indicator down with no
            # observable failure mode. Stamp the error into the marker
            # file so we can diagnose post-mortem.
            try:
                last_ping_marker.write_text(
                    f"{datetime.now(timezone.utc).isoformat()} error {exc!r}\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
        time.sleep(_HEARTBEAT_INTERVAL_S)


def _start_heartbeat_thread() -> None:
    import threading
    t = threading.Thread(target=_heartbeat_loop, name="bridge-heartbeat", daemon=True)
    t.start()


_CHAT_PID_PATH = _OASIS_DIR / "bridge_chat.pid"


def serve_forever() -> int:
    """Entry point for `bravo bridge serve`."""
    # Hydrate BRIDGE_BEARER_TOKEN from .env.agents into the process env at
    # boot. The bearer gate (_check_bearer) and the proxy-mode identity/role
    # logic read os.environ["BRIDGE_BEARER_TOKEN"] directly, but on the VPS the
    # canonical secret store is .env.agents (the operator never exports it into
    # the shell). Without this hydration the gate silently no-ops even though
    # the token is provisioned. Only sets when found, so CC's localhost rig
    # (no token in its .env.agents) keeps the no-op path verbatim.
    _bearer = _read_env_value("BRIDGE_BEARER_TOKEN")
    if _bearer and not os.environ.get("BRIDGE_BEARER_TOKEN"):
        os.environ["BRIDGE_BEARER_TOKEN"] = _bearer
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), _ChatHandler)
    print(f"oasis-bridge-chat listening on http://127.0.0.1:{PORT}")
    print(f"  agents resolvable: {sum(1 for v in all_resolved().values() if v['root'])}/5")
    if os.environ.get("OASIS_BRIDGE_NO_HEARTBEAT") != "1":
        _start_heartbeat_thread()
        print("  heartbeat: every 60s -> /api/bridge/ping")
    print("  Ctrl+C to stop.")
    # Write PID so `bravo bridge restart` can find and kill us. Without
    # this, restart has to scan tasklist for the python command line —
    # works but slower and fragile when multiple python processes exist.
    try:
        _OASIS_DIR.mkdir(parents=True, exist_ok=True)
        _CHAT_PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        httpd.server_close()
        try:
            _CHAT_PID_PATH.unlink(missing_ok=True)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(serve_forever())
