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

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Add the repo's scripts/ to sys.path so we can import the canonical
# subprocess helper. bridge_tools runs from bravo_cli/ (sibling of
# scripts/) under the claude-bridge PM2 daemon — every shell/script
# spawn from here MUST be windowless or the user sees a cmd.exe popup
# on each bridge tool call.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
from _subprocess_helpers import (  # noqa: E402
    command_without_cmd_shim,
    enriched_path,
    safe_popen,
    safe_run,
    which_cli,
)

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


# Per-agent root allowlist for read_file / write_file. Tools only touch
# paths that resolve INSIDE one of these roots. Closes Codex adversarial
# finding 2026-05-22 #4 — the prior implementation accepted absolute paths
# anywhere on disk because under_root() was a documented helper that
# nobody actually called.
_ALLOWED_FILE_ROOTS: list[Path] = []


def _allowed_roots() -> list[Path]:
    """Resolve once + cache. Returns all known agent repo roots
    (bravo, atlas, maven, aura, hermes, …) the bridge is allowed to
    touch. resolve_root() returns None for un-paired agents — we
    skip those so the allowlist matches the operator's actual layout."""
    if _ALLOWED_FILE_ROOTS:
        return _ALLOWED_FILE_ROOTS
    for slug in ("bravo", "atlas", "maven", "aura", "hermes"):
        root = resolve_root(slug)
        if root:
            try:
                _ALLOWED_FILE_ROOTS.append(Path(root).resolve(strict=False))
            except OSError:
                continue
    return _ALLOWED_FILE_ROOTS


# Secret-file name patterns — refused even when the path otherwise resolves
# inside an allowed root. Defense in depth against prompt-injection
# attempts to exfiltrate credentials from the agent's own repo.
_SECRET_FILENAME_PATTERNS = (
    ".env", ".env.local", ".env.production", ".env.agents",
    "credentials.json", "service-account.json",
    "id_rsa", "id_ed25519",
)
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def _is_secret_path(p: Path) -> bool:
    """True if the path's basename matches a known secret-file pattern.
    Case-insensitive. Returns true on .env* variants too (e.g.,
    .env.agents, .env.local, .env.production)."""
    name = p.name.lower()
    if name in _SECRET_FILENAME_PATTERNS:
        return True
    if name.startswith(".env"):
        return True
    for suf in _SECRET_SUFFIXES:
        if name.endswith(suf):
            return True
    return False


def _resolve_under_allowed_root(raw_path: str) -> tuple[Path | None, str | None]:
    """Resolve raw_path and verify it falls under one of _allowed_roots().
    Returns (resolved_path, None) on success, (None, error_msg) on rejection.

    Rules:
      - Relative paths resolve against the Bravo repo root (existing
        ergonomics — the agent is usually working on Bravo).
      - Absolute paths are honored ONLY if they resolve under one of
        the allowlisted agent roots.
      - Secret-file names (.env*, *.pem, *.key, credentials.json, …) are
        refused regardless of location.
    """
    p = Path(raw_path)
    if not p.is_absolute():
        p = _bravo_root() / p
    try:
        p = p.resolve(strict=False)
    except OSError as e:
        return None, f"path_resolve_failed: {e}"
    roots = _allowed_roots()
    if not roots:
        # No agent roots registered yet — fall back to Bravo cwd only.
        # Safer than wide-open on fresh-clone / single-agent setups.
        roots = [Path.cwd().resolve(strict=False)]
    under_any = False
    for root in roots:
        try:
            p.relative_to(root)
            under_any = True
            break
        except ValueError:
            continue
    if not under_any:
        return None, (
            f"path_outside_allowed_roots: {p} is not inside any of "
            f"{[str(r) for r in roots]}"
        )
    if _is_secret_path(p):
        return None, f"refused_secret_file: {p.name} matches a credential pattern"
    return p, None


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

    Path resolution: relative paths resolve against the Bravo repo root.
    Absolute paths are honored ONLY if they resolve under an agent root
    in _allowed_roots() (bravo, atlas, maven, aura, hermes). Secret-file
    names (.env*, *.pem, *.key, credentials.json, …) are refused.
    Hardened 2026-05-22 per Codex adversarial finding #4 — the prior
    implementation accepted any absolute path, only OS perms gated it.
    """
    raw_path = str(payload.get("path") or "").strip()
    if not raw_path:
        return _err("missing 'path'")
    try:
        max_bytes = int(payload.get("max_bytes") or 200_000)
    except (TypeError, ValueError):
        max_bytes = 200_000

    p, err = _resolve_under_allowed_root(raw_path)
    if err or p is None:
        return _err(err or "path_resolution_failed")
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
    """{path: str, content: str, create_dirs?: bool} → "wrote N bytes".

    Same path-allowlisting as _tool_read_file: writes are confined to
    one of _allowed_roots() and secret-file names are refused. Hardened
    2026-05-22 per Codex adversarial finding #4.
    """
    raw_path = str(payload.get("path") or "").strip()
    content = payload.get("content")
    if not raw_path:
        return _err("missing 'path'")
    if not isinstance(content, str):
        return _err("'content' must be a string")
    create_dirs = bool(payload.get("create_dirs", True))
    p, err = _resolve_under_allowed_root(raw_path)
    if err or p is None:
        return _err(err or "path_resolution_failed")
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
        proc = safe_run(
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
        proc = safe_run(
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
    """{to: str, subject: str, body: str, lead_id?: str, cc?: str|list} → send_gateway.

    2026-05-16 Codex review finding #5 fix: this used to shell out
    directly to scripts/integrations/google_tool.py mail send, which bypassed
    scripts/integrations/send_gateway.py — the SINGLE outbound chokepoint that
    enforces CASL suppression, per-recipient cooldown, daily caps,
    multi-brand routing, and the audit ledger. A chat-initiated email
    that skipped send_gateway could (a) re-mail a recently-contacted
    lead inside their cooldown window, (b) re-mail an opted-out
    recipient, or (c) blow past the daily-cap.

    Route every chat-driven email through send_gateway. agent_source
    'manual_cc' tags the audit ledger so operator-initiated chats are
    distinguishable from scheduler / engine sends.

    2026-05-31: under SunBiz's shared-inbox From: model the reply lands
    in submissions@, so the chat-driving operator (and any other rep
    they want on the thread) must be CC'd or they never see the reply.
    Accept `cc` as either a comma-separated string or a list of strings;
    send_gateway re-parses + de-dupes server-side.
    """
    to_addr = str(payload.get("to") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "")
    if not to_addr or "@" not in to_addr:
        return _err("invalid 'to' email address")
    if not subject:
        return _err("missing 'subject'")
    if not body:
        return _err("missing 'body'")
    # send_gateway.py defines --json as a TOP-LEVEL flag on the main
    # parser BEFORE the subparser (send_gateway.py:3648). Argparse
    # rejects --json when it appears after the `send` subcommand.
    # VPS agent surfaced this 2026-06-09; cost: chat-driven send_email
    # tool exits 2 with "unrecognized arguments: --json".
    args = [
        "scripts/integrations/send_gateway.py", "--json", "send",
        "--channel", "email",
        "--agent-source", "manual_cc",
        "--to", to_addr,
        "--subject", subject,
        "--body", body,
    ]
    lead_id = payload.get("lead_id")
    if isinstance(lead_id, str) and lead_id.strip():
        args.extend(["--lead-id", lead_id.strip()])
    # CC normalization — shared with shop_out_sender + the batch send
    # tool via send_gateway.normalize_cc so all three sites agree on
    # what's a valid address shape (no inline parsing drift).
    from integrations.send_gateway import normalize_cc  # local import; avoids loading send_gateway on every bridge boot
    cc_clean = normalize_cc(payload.get("cc"))
    if cc_clean:
        args.extend(["--cc", cc_clean])
    return _run_script(args)


def _tool_send_sms(payload: dict) -> dict:
    """{to: str, body: str, lead_id?: str} → send_gateway.

    Same fix as _tool_send_email (Codex finding #5). Previously shelled
    out to scripts/twilio_tool.py send directly. send_gateway carries
    the SMS opt-out check (Codex finding #4, still in-flight) once
    that ships — until then the gateway at least enforces cooldown +
    daily cap + audit logging. Never call twilio_tool.py / TextTorrent
    directly from the bridge layer.
    """
    to_num = str(payload.get("to") or "").strip()
    body = str(payload.get("body") or "")
    if not to_num:
        return _err("missing 'to' phone number")
    if not body:
        return _err("missing 'body'")
    # Same --json placement fix as _tool_send_email above.
    # send_gateway.py defines --json on the main parser, not on send.
    args = [
        "scripts/integrations/send_gateway.py", "--json", "send",
        "--channel", "sms",
        "--agent-source", "manual_cc",
        "--to", to_num,
        "--body", body,
    ]
    lead_id = payload.get("lead_id")
    if isinstance(lead_id, str) and lead_id.strip():
        args.extend(["--lead-id", lead_id.strip()])
    return _run_script(args)


# ──────────────────────────────────────────────────────────────────
# Generic Python tool runner — Phase A of harness completeness
#
# Above this point we have 5 typed wrappers (read_file, write_file, bash,
# send_email, send_sms) and the model is blind to the other ~47 CLI
# tools sitting in scripts/. list_scripts + run_script close that gap:
# list_scripts gives the model the catalog with one-line synopses so it
# knows what's available; run_script gives a typed interface to invoke
# any of them by name with structured args.
#
# Path safety: run_script resolves the script name against scripts/ in
# the Bravo repo root and refuses paths that escape that directory.
# Refusing absolute paths + ".." in the name; the bash tool exists for
# anything outside scripts/.
# ──────────────────────────────────────────────────────────────────

# In-process cache of list_scripts results. Scanning the dir + reading
# docstrings every call would re-do the work on every model turn. Five-
# minute TTL is long enough to amortize the cost across a chat session
# but short enough that a freshly-added script shows up before the next
# chat. Cleared on bridge restart anyway.
_LIST_SCRIPTS_CACHE: dict = {"at": 0.0, "data": None}


def _read_docstring_or_top_comment(text: str) -> str:
    """Extract the first useful one-liner from a Python script's content.
    Tries module docstring first, then the first non-blank comment line,
    then the shebang/import context. Returns at most 200 chars."""
    # Module docstring: """..."""  or  '''...'''
    stripped = text.lstrip()
    if stripped.startswith(("'''", '"""')):
        q = stripped[:3]
        rest = stripped[3:]
        end = rest.find(q)
        if end != -1:
            doc = rest[:end].strip()
            first = doc.splitlines()[0].strip() if doc else ""
            if first:
                return first[:200]
    # First comment after shebang / coding line
    for line in text.splitlines()[:20]:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#!") or s.startswith("# -*-"):
            continue
        if s.startswith("#"):
            return s.lstrip("# ").rstrip()[:200]
        # Non-comment / non-empty content — give up on doc extraction
        break
    return ""


def _tool_list_scripts(payload: dict) -> dict:
    """{filter?: str} → catalog of Python scripts in the operator's
    scripts/ directory with one-line synopses. Used by the model for
    discovery before calling run_script.

    Results are cached for 5 minutes per bridge process to keep model
    turns snappy. A `filter` substring matches against script names
    (case-insensitive) — useful when the model is hunting for a
    specific kind of tool ("stripe", "supabase", "send")."""
    now = time.time()
    if _LIST_SCRIPTS_CACHE["data"] is None or (now - _LIST_SCRIPTS_CACHE["at"]) > 300:
        bravo = _bravo_root()
        scripts_dir = bravo / "scripts"
        catalog: list[dict] = []
        if scripts_dir.is_dir():
            for p in sorted(scripts_dir.glob("*.py")):
                # Skip private / dunder files — they're internal helpers
                # the model shouldn't be invoking directly.
                if p.name.startswith("_") or p.name.startswith("."):
                    continue
                try:
                    head = p.read_text(encoding="utf-8", errors="replace")[:8192]
                    summary = _read_docstring_or_top_comment(head)
                except OSError:
                    summary = ""
                # Tag `*_tool.py` scripts as "tool" — those are the
                # documented CLI-tool layer with --json + --help args.
                kind = "tool" if p.name.endswith("_tool.py") else "script"
                catalog.append({
                    "name": p.name,
                    "kind": kind,
                    "summary": summary,
                })
        _LIST_SCRIPTS_CACHE["at"] = now
        _LIST_SCRIPTS_CACHE["data"] = catalog
    catalog = _LIST_SCRIPTS_CACHE["data"] or []
    flt = str(payload.get("filter") or "").strip().lower()
    if flt:
        catalog = [c for c in catalog if flt in c["name"].lower()]
    return _ok(_json_dumps_compact({
        "count": len(catalog),
        "scripts": catalog,
    }))


def _json_dumps_compact(obj) -> str:
    """JSON-serialize for tool output. Compact (no indent) so the model
    sees the most data within the truncation cap."""
    import json as _json
    return _json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


# Names that would let the model break out of scripts/. The path-resolve
# check below catches `..` but rejecting up-front is clearer + faster.
_FORBIDDEN_SCRIPT_TOKENS = ("..", "/", "\\", "\x00")


def _tool_run_script(payload: dict) -> dict:
    """{script: str, args?: list[str], timeout_s?: int, parse_json?: bool}
    → run the named script from scripts/ with the given args. Returns
    exit code + stdout + stderr. If parse_json is true (default) and
    stdout parses as JSON, the parsed value goes into a 'parsed' field
    so the model gets structured data without having to re-parse.

    Path resolution is allowlisted to scripts/<name>.py inside the Bravo
    repo root — no traversal, no absolute paths. For anything outside
    scripts/, the model should use the `bash` tool instead."""
    script_name = str(payload.get("script") or "").strip()
    if not script_name:
        return _err("missing 'script' name")
    # Reject obvious traversal attempts up front. The resolve() check
    # below would also catch these, but the explicit error tells the
    # model exactly why its call was rejected.
    for token in _FORBIDDEN_SCRIPT_TOKENS:
        if token in script_name:
            return _err(
                f"script name must be a simple filename — found forbidden token {token!r}. "
                "Use only files inside scripts/. For paths outside scripts/, use the bash tool."
            )
    if not script_name.endswith(".py"):
        script_name = script_name + ".py"

    raw_args = payload.get("args") or []
    if not isinstance(raw_args, list) or any(not isinstance(a, (str, int, float)) for a in raw_args):
        return _err("'args' must be a list of strings/numbers")
    args = [str(a) for a in raw_args]
    try:
        timeout_s = max(1, min(int(payload.get("timeout_s") or SCRIPT_TIMEOUT_S), 300))
    except (TypeError, ValueError):
        timeout_s = SCRIPT_TIMEOUT_S
    parse_json = payload.get("parse_json")
    parse_json = True if parse_json is None else bool(parse_json)

    bravo = _bravo_root()
    script_path = (bravo / "scripts" / script_name).resolve()
    # Sanity: resolved path MUST be inside scripts/. Defends against the
    # edge cases the upfront token-rejection misses (case-folding tricks,
    # symlinks, etc.).
    try:
        script_path.relative_to((bravo / "scripts").resolve())
    except ValueError:
        return _err(f"script_path_escapes_scripts_dir: {script_path}")
    if not script_path.is_file():
        return _err(f"script_not_found: scripts/{script_name}")

    try:
        proc = safe_run(
            [sys.executable, str(script_path), *args],
            cwd=str(bravo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        return _err(
            f"script_timeout after {timeout_s}s: scripts/{script_name}\n"
            f"--- partial stdout ---\n{(e.stdout or '')}\n"
            f"--- partial stderr ---\n{(e.stderr or '')}"
        )
    except OSError as e:
        return _err(f"script_spawn_failed: {e}")

    result: dict = {
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if parse_json and proc.stdout.strip():
        try:
            import json as _json
            result["parsed"] = _json.loads(proc.stdout)
        except (ValueError, TypeError):
            # stdout isn't JSON — fine, model still has the raw text.
            pass

    out_blob = _json_dumps_compact(result)
    if proc.returncode != 0:
        return {"output": _truncate(out_blob), "is_error": True}
    return _ok(out_blob)


# ──────────────────────────────────────────────────────────────────
# Typed wrappers for the documented *_tool.py CLI layer — Phase C
#
# Each of these is a 3-line wrapper around _run_script that pre-fills
# the script name and auto-appends --json. The model COULD reach the
# same scripts via run_script, but typed tools mean:
#   - The Anthropic tools[] palette advertises them by name (better
#     discoverability than scanning list_scripts each turn).
#   - Input schema is structured (action + args) so the model gets
#     better completions than free-form argv.
#   - Lower latency (no --help round-trip needed).
#
# Each wrapper takes {action: str, args?: list[str]} and translates to
# `python scripts/<tool>.py <action> <...args> --json`. The auto-json
# suffix is skipped when the action is --help or already contains --json.
# ──────────────────────────────────────────────────────────────────

def _run_typed_tool(script_name: str, payload: dict) -> dict:
    """Shared wrapper body for the typed _tool.py CLIs. Pulls action +
    args from the payload, builds the argv, runs via _run_script, and
    auto-appends --json so the model gets structured output."""
    action = str(payload.get("action") or "").strip()
    if not action:
        return _err(f"missing 'action' (e.g. 'list', 'create', '--help'). Run with action='--help' to see available subcommands.")
    raw_args = payload.get("args") or []
    if not isinstance(raw_args, list) or any(not isinstance(a, (str, int, float)) for a in raw_args):
        return _err("'args' must be a list of strings/numbers")
    str_args = [str(a) for a in raw_args]
    # Typed tool CLIs live under scripts/integrations/ (supabase_tool.py,
    # n8n_tool.py, firecrawl_tool.py, stripe_tool.py, notebooklm_tool.py) —
    # matching each _tool_* docstring. The bare scripts/ prefix pointed at a
    # nonexistent path, so every typed tool failed with "can't open file".
    argv = [f"scripts/integrations/{script_name}", action, *str_args]
    # Auto --json for structured output unless asking for help or already present
    if action != "--help" and "--help" not in str_args and "--json" not in str_args:
        argv.append("--json")
    return _run_script(argv)


def _tool_stripe(payload: dict) -> dict:
    """Stripe SDK — payments, customers, subscriptions, payment links,
    refunds. Calls scripts/integrations/stripe_tool.py. Actions include: list-accounts,
    balance, customers, products, prices, invoices, subscriptions, charges,
    payment-links, create-payment-link, create-price, quick-link,
    create-customer, create-invoice, refund, events."""
    return _run_typed_tool("stripe_tool.py", payload)


def _tool_supabase(payload: dict) -> dict:
    """Supabase — query the operator's database, manage tables, run RPCs.
    Calls scripts/integrations/supabase_tool.py. Most useful actions: query (raw SQL),
    list, get, insert, update, delete."""
    return _run_typed_tool("supabase_tool.py", payload)


def _tool_n8n(payload: dict) -> dict:
    """n8n — list workflows, execute by name, get execution status, manage
    webhooks. Calls scripts/integrations/n8n_tool.py."""
    return _run_typed_tool("n8n_tool.py", payload)


def _tool_firecrawl(payload: dict) -> dict:
    """Firecrawl — scrape a URL, crawl a site, get markdown extraction.
    Calls scripts/integrations/firecrawl_tool.py. Use when the operator wants competitor
    research, page extraction, or a starting-point for content drafting."""
    return _run_typed_tool("firecrawl_tool.py", payload)


def _tool_notebooklm(payload: dict) -> dict:
    """NotebookLM — query the operator's curated knowledge base, get
    citations, ask multi-doc questions. Calls scripts/integrations/notebooklm_tool.py."""
    return _run_typed_tool("notebooklm_tool.py", payload)


# ──────────────────────────────────────────────────────────────────
# Skill discovery + invocation — Phase B of harness completeness
#
# The operator has ~65 skills/<name>/SKILL.md playbooks documenting
# how their agents handle specific scenarios (CEO briefing, sales
# closing, debugging, etc.). In CLI/subscription mode, Claude Code
# auto-discovers and loads these via the skill system. In API-key
# mode the model is blind to them.
#
# list_skills returns the catalog (name + description + triggers from
# frontmatter); load_skill returns the full SKILL.md body so the model
# can follow the SOP step-by-step. Both cached for 5 minutes.
# ──────────────────────────────────────────────────────────────────

_LIST_SKILLS_CACHE: dict = {"at": 0.0, "data": None}


def _parse_skill_frontmatter(text: str) -> dict:
    """Extract YAML-ish frontmatter from a SKILL.md file. The repo's
    convention is the standard `---\\n<key>: <value>\\n---\\n` markdown
    frontmatter block at the top. Not parsing arbitrary YAML — just the
    keys this skill registry cares about (name, description, triggers,
    tags). Array values can be inline JSON-ish (["a","b"]) or YAML-
    style (`- a` lines below the key); we handle both with best-effort
    eval. Anything we can't parse we drop silently — the file is still
    loadable via load_skill, just less discoverable."""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return {}
    rest = stripped[3:]
    end = rest.find("\n---")
    if end == -1:
        return {}
    block = rest[:end]
    fm: dict = {}
    current_key: str | None = None
    list_buf: list[str] | None = None
    for line in block.splitlines():
        if not line.strip():
            continue
        # YAML list continuation: "  - value"
        if list_buf is not None and line.lstrip().startswith("- "):
            list_buf.append(line.lstrip()[2:].strip().strip('"').strip("'"))
            continue
        # New key — commit any pending list, start fresh
        if list_buf is not None and current_key:
            fm[current_key] = list_buf
            list_buf = None
            current_key = None
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # Inline list: triggers: ["a", "b"]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                fm[key] = []
            else:
                items = []
                # Naive split — works for simple quoted-string lists.
                # Anything fancier (nested objects) and we just skip.
                depth = 0
                buf = ""
                for ch in inner + ",":
                    if ch == "," and depth == 0:
                        s = buf.strip().strip('"').strip("'")
                        if s:
                            items.append(s)
                        buf = ""
                    else:
                        if ch in "[{":
                            depth += 1
                        elif ch in "]}":
                            depth -= 1
                        buf += ch
                fm[key] = items
        elif val == "" or val == "|" or val == ">":
            # Block-style list follows on subsequent `- ...` lines
            current_key = key
            list_buf = []
        else:
            # Scalar — strip quotes if present
            fm[key] = val.strip('"').strip("'")
    if list_buf is not None and current_key:
        fm[current_key] = list_buf
    return fm


def _tool_list_skills(payload: dict) -> dict:
    """{filter?: str} → catalog of skills/*/SKILL.md playbooks with their
    name + description + triggers. Use this to discover the operator's
    SOPs before running a workflow; then call load_skill to read the
    full body and follow the steps.

    Cached 5 minutes per bridge process. Filter is a case-insensitive
    substring match against skill name, description, AND triggers."""
    now = time.time()
    if _LIST_SKILLS_CACHE["data"] is None or (now - _LIST_SKILLS_CACHE["at"]) > 300:
        bravo = _bravo_root()
        skills_dir = bravo / "skills"
        catalog: list[dict] = []
        if skills_dir.is_dir():
            for skill_path in sorted(skills_dir.iterdir()):
                if not skill_path.is_dir() or skill_path.name.startswith("."):
                    continue
                md = skill_path / "SKILL.md"
                if not md.is_file():
                    continue
                try:
                    head = md.read_text(encoding="utf-8", errors="replace")[:4096]
                except OSError:
                    continue
                fm = _parse_skill_frontmatter(head)
                # Fallback: use the directory name when frontmatter is missing
                name = fm.get("name") or skill_path.name
                catalog.append({
                    "name": str(name),
                    "description": str(fm.get("description") or "")[:300],
                    "triggers": fm.get("triggers") if isinstance(fm.get("triggers"), list) else [],
                    "tags": fm.get("tags") if isinstance(fm.get("tags"), list) else [],
                })
        _LIST_SKILLS_CACHE["at"] = now
        _LIST_SKILLS_CACHE["data"] = catalog
    catalog = _LIST_SKILLS_CACHE["data"] or []
    flt = str(payload.get("filter") or "").strip().lower()
    if flt:
        catalog = [
            c for c in catalog
            if flt in str(c.get("name", "")).lower()
            or flt in str(c.get("description", "")).lower()
            or any(flt in str(t).lower() for t in c.get("triggers", []))
        ]
    return _ok(_json_dumps_compact({
        "count": len(catalog),
        "skills": catalog,
    }))


# Forbidden in skill names — same set as scripts, plus we additionally
# refuse names with slashes since skills are directory-keyed and a path
# would be a structural error.
_FORBIDDEN_SKILL_TOKENS = ("..", "/", "\\", "\x00")


def _tool_load_skill(payload: dict) -> dict:
    """{name: str} → full SKILL.md body for a named skill. Use after
    list_skills has identified the right playbook. Returns the raw
    markdown — the model reads the steps and follows them.

    Path resolution: skills/<name>/SKILL.md inside the Bravo repo root.
    No traversal, no slashes in name."""
    name = str(payload.get("name") or "").strip()
    if not name:
        return _err("missing 'name'")
    for token in _FORBIDDEN_SKILL_TOKENS:
        if token in name:
            return _err(f"skill name must be a simple identifier — found forbidden token {token!r}")

    bravo = _bravo_root()
    md_path = (bravo / "skills" / name / "SKILL.md").resolve()
    try:
        md_path.relative_to((bravo / "skills").resolve())
    except ValueError:
        return _err(f"skill_path_escapes_skills_dir: {md_path}")
    if not md_path.is_file():
        # Soft hint — point the model at list_skills so it can find the
        # right name if it spelled this one wrong.
        return _err(
            f"skill_not_found: skills/{name}/SKILL.md. "
            "Call list_skills to see what's available."
        )
    try:
        body = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return _err(f"read_failed: {e}")
    # Skills can be long. Truncate to the soft cap so the model can
    # still reason about the rest of the context.
    return _ok(body)


# ──────────────────────────────────────────────────────────────────
# Registry + dispatcher
# ──────────────────────────────────────────────────────────────────

def _tool_underwriting_run(payload: dict) -> dict:
    """SunBiz-domain bridge tool — body lives in SunBiz-Agent.

    The bridge daemon is shared infra; the underwriting tool is
    SunBiz-specific (application_underwriting table, daemon contract,
    paper-grade rubric, dual-write to data.underwriting_jsonb).

    This shim imports the implementation from
    SUNBIZ_AGENT_ROOT/scripts/bridge_tool_underwriting_run.py (default
    ~/SunBiz-Agent). Payload contract preserved verbatim.

    Payload: {application_id: str,
              triggered_by?: 'manual'|'rerun'|'chat',
              wait_for_complete?: bool (default True),
              poll_interval_s?: int (default 5, max 60),
              poll_timeout_s?: int (default 1800, max 3600)}
    """
    # SunBiz-Agent runtime probe — delegated to the shared resolver in
    # CEO-Agent/scripts/lib/agent_roots.py so bridge_chat_server,
    # bridge_tools, and build_bridge_manifest all read from one source.
    sys.path.insert(0, str(_bravo_root() / "scripts"))
    from lib.agent_roots import resolve_sunbiz_root  # type: ignore
    sunbiz_root = resolve_sunbiz_root()
    if sunbiz_root is None:
        return _err(
            "SunBiz-Agent runtime not found. Set SUNBIZ_AGENT_ROOT, or "
            "clone SunBiz-Agent at ~/SunBiz-Agent (Mac/Linux) or "
            "C:\\Users\\User\\SunBiz-Agent (Windows)."
        )
    scripts_path = str(sunbiz_root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    try:
        from bridge_tool_underwriting_run import underwriting_run  # type: ignore
    except ImportError as e:
        return _err(f"failed to import SunBiz underwriting bridge tool: {e}")
    return underwriting_run(payload, _ok, _err)


def _tool_shop_out_send_batch(payload: dict) -> dict:
    """{application_id: str} → fire send_gateway.send for every pending
    application_lender_threads row.

    Round 3 R3-4 / Codex production-readiness fix: /api/applications/[id]/
    shop-out previously inserted rows at status='pending' but never
    physically dispatched. The UI honestly said 'queued: N' but the
    lender emails never went out. This handler closes that loop.

    Per-thread dispatch:
      1. Resolve the thread row (lender_id, subject, recipient).
      2. Look up the lender's contact email from tenant_records.
      3. Build the email body using the same template the planner
         renders during the dry-run preview (kept on the thread row's
         data jsonb when shop-out queued).
      4. Subprocess scripts/integrations/send_gateway.py send --channel email
         --agent-source manual_cc --to <lender> --subject ... --body ...
         --lead-id <app's lead_id> --json. send_gateway enforces
         CASL/cooldown/daily-cap automatically.
      5. On success, capture gmail_thread_id (sent-message id), flip
         status='sent', stamp sent_at.
      6. On failure, capture the error in last_response_summary and
         flip status='error'.

    Bank statement attachments are intentionally NOT inlined yet —
    send_gateway's CLI doesn't expose --attachments today. Following
    up: extend send_gateway to accept --attachments <paths> for the
    email channel. For Monday, the thread carries the bank statement
    paths in its data jsonb so the operator can attach manually if
    needed; for the smoke test we ship without attachments first to
    verify the send path is healthy.
    """
    application_id = str(payload.get("application_id") or "").strip()
    if not application_id:
        return _err("missing 'application_id'")

    bravo = _bravo_root()
    try:
        from supabase import create_client  # type: ignore
        from scripts.lib.secret_loader import load_env  # type: ignore
    except Exception:
        sys.path.insert(0, str(bravo))
        sys.path.insert(0, str(bravo / "scripts"))
        from supabase import create_client  # type: ignore
        from lib.secret_loader import load_env  # type: ignore

    try:
        env = load_env([
            "BRAVO_SUPABASE_URL",
            "BRAVO_SUPABASE_SERVICE_ROLE_KEY",
        ])
        sb = create_client(env["BRAVO_SUPABASE_URL"], env["BRAVO_SUPABASE_SERVICE_ROLE_KEY"])
    except Exception as e:
        return _err(f"supabase init failed: {e}")

    # Fetch the application + its pending threads.
    app_row = (
        sb.table("tenant_records")
        .select("id, tenant_id, data")
        .eq("id", application_id)
        .eq("entity_type", "application")
        .maybeSingle()
        .execute()
    )
    if not app_row.data:
        return _err(f"application_id {application_id} not found in tenant_records")
    tenant_id = app_row.data.get("tenant_id")
    app_data = app_row.data.get("data") or {}
    lead_id = app_data.get("lead_id")

    threads = (
        sb.table("application_lender_threads")
        .select("id, lender_id, subject, body, recipient_email, status, data, cc_emails")
        .eq("application_id", application_id)
        .eq("tenant_id", tenant_id)
        .eq("status", "pending")
        .execute()
    )
    pending_rows = threads.data or []
    if not pending_rows:
        return _ok(json.dumps({
            "ok": True,
            "application_id": application_id,
            "sent": 0,
            "failed": 0,
            "skipped_no_pending": True,
        }))

    sent_count = 0
    failed_count = 0
    failures: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for thread in pending_rows:
        recipient = thread.get("recipient_email")
        subject = thread.get("subject") or "Funding application from SunBiz Funding"
        body = thread.get("body") or ""
        if not recipient:
            # Pre-existing recipient-missing rows were inserted at
            # status='error' upstream, but defensive — if any pending
            # row lacks a recipient, mark error and skip dispatch.
            sb.table("application_lender_threads").update({
                "status": "error",
                "last_response_summary": "missing recipient_email",
                "updated_at": now_iso,
            }).eq("id", thread["id"]).execute()
            failed_count += 1
            failures.append({"thread_id": thread["id"], "reason": "missing_recipient"})
            continue

        send_args = [
            "scripts/integrations/send_gateway.py", "send",
            "--channel", "email",
            "--agent-source", "manual_cc",
            "--to", recipient,
            "--subject", subject,
            "--body", body,
            "--json",
        ]
        if lead_id:
            send_args.extend(["--lead-id", str(lead_id)])
        # Pass through the per-row CC list the dashboard merged at queue
        # time (operator-typed + lender's submission_cc_emails + assigned
        # rep email under shared-inbox). Without this the catalog routing
        # is dead at the bridge layer — CCs land in the DB but never on
        # the wire. Shared with shop_out_sender + send_email tool via
        # send_gateway.normalize_cc.
        from integrations.send_gateway import normalize_cc
        cc_clean = normalize_cc(thread.get("cc_emails"))
        if cc_clean:
            send_args.extend(["--cc", cc_clean])

        send_res = _run_script(send_args)
        if not send_res.get("ok"):
            failures.append({
                "thread_id": thread["id"],
                "lender_id": thread.get("lender_id"),
                "reason": f"send_gateway failed: {send_res.get('content','')[:300]}",
            })
            sb.table("application_lender_threads").update({
                "status": "error",
                "last_response_summary": (send_res.get("content") or "send_gateway failed")[:500],
                "updated_at": now_iso,
            }).eq("id", thread["id"]).execute()
            failed_count += 1
            continue

        # send_gateway returns its own JSON shape on success. The
        # gmail_thread_id (or twilio message_sid for SMS channels) is
        # in the result.message_id field.
        try:
            sg = json.loads(send_res.get("content", "{}"))
            status = sg.get("status")
            if status == "sent":
                gmail_thread_id = sg.get("gmail_thread_id") or sg.get("message_id") or None
                sb.table("application_lender_threads").update({
                    "status": "sent",
                    "gmail_thread_id": gmail_thread_id,
                    "sent_at": now_iso,
                    "updated_at": now_iso,
                }).eq("id", thread["id"]).execute()
                sent_count += 1
            elif status == "suppressed":
                # CASL opt-out — flip to a terminal state so the
                # classifier daemon doesn't keep polling.
                sb.table("application_lender_threads").update({
                    "status": "suppressed",
                    "last_response_summary": f"CASL suppressed: {sg.get('reason','')}",
                    "updated_at": now_iso,
                }).eq("id", thread["id"]).execute()
                failed_count += 1
                failures.append({"thread_id": thread["id"], "reason": f"suppressed: {sg.get('reason','')}"})
            elif status == "blocked":
                # Cooldown — leave as pending so a future re-run picks
                # it up after cooldown_until.
                failures.append({
                    "thread_id": thread["id"],
                    "reason": f"cooldown until {sg.get('cooldown_until','?')}",
                })
                failed_count += 1
            else:
                # Unknown status — log and treat as error.
                sb.table("application_lender_threads").update({
                    "status": "error",
                    "last_response_summary": f"send_gateway returned: {status}",
                    "updated_at": now_iso,
                }).eq("id", thread["id"]).execute()
                failed_count += 1
                failures.append({"thread_id": thread["id"], "reason": f"status={status}"})
        except json.JSONDecodeError as e:
            sb.table("application_lender_threads").update({
                "status": "error",
                "last_response_summary": f"send_gateway returned non-JSON: {e}",
                "updated_at": now_iso,
            }).eq("id", thread["id"]).execute()
            failed_count += 1
            failures.append({"thread_id": thread["id"], "reason": "non_json_response"})

    return _ok(json.dumps({
        "ok": True,
        "application_id": application_id,
        "sent": sent_count,
        "failed": failed_count,
        "total_pending": len(pending_rows),
        "failures": failures[:20],
    }))


def _tool_cli_status(payload: dict) -> dict:
    """Phase 8.2.1 — probe locally-installed AI CLIs (Claude Code, Codex,
    Gemini) so the dashboard's Settings page can show real-time install +
    auth status for the "Connect via local CLI" cards.

    For each CLI we report:
      - installed: whether the binary is on PATH (or known install paths)
      - authenticated: whether the operator's logged-in subscription is
        usable (CLI-specific check)
      - version: the version string the CLI reports
      - install_hint_url: where to install if missing

    No arguments. Returns JSON with three top-level keys: claude, codex,
    gemini. Each value is `{installed, authenticated, version, install_hint_url}`.

    All probes wrap in 5s timeouts; failures resolve to installed=false so
    the dashboard always renders a stable shape.
    """
    del payload  # unused — this is a no-arg probe

    # _which delegates to the shared which_cli helper so this probe sees
    # the same Homebrew / npm-global / nvm install dirs that the chat
    # path now uses. Without this, the dashboard reports "NOT INSTALLED"
    # for nvm-installed claude/codex/gemini even though chat finds them
    # via login-shell PATH.
    def _which(name: str) -> str | None:
        return which_cli(name)

    def _run(args: list[str], timeout: int = 5) -> tuple[int, str]:
        cmd = [*command_without_cmd_shim(args[0]), *args[1:]] if args else args
        env = dict(os.environ)
        env["PATH"] = enriched_path(args[0] if args else None)
        try:
            r = safe_run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            return r.returncode, (r.stdout or "").strip() + ("\n" + r.stderr.strip() if r.stderr else "")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return -1, ""

    def _probe_claude() -> dict:
        bin_path = _which("claude")
        if not bin_path:
            return {"installed": False, "authenticated": False, "version": None,
                    "install_hint_url": "https://docs.anthropic.com/en/docs/claude-code/quickstart"}
        rc, out = _run([bin_path, "--version"])
        if rc != 0:
            return {"installed": True, "authenticated": False, "version": None,
                    "install_hint_url": "https://docs.anthropic.com/en/docs/claude-code/quickstart"}
        version = out.splitlines()[0].strip() if out else None
        # Auth check — credentials file or env. Reuse the existing helper.
        try:
            from _claude_auth import check_claude_auth_paths  # type: ignore
        except ImportError:
            from ._claude_auth import check_claude_auth_paths  # type: ignore
        auth = check_claude_auth_paths()
        authenticated = bool(auth.get("has_oauth") or auth.get("has_api_key"))
        return {"installed": True, "authenticated": authenticated, "version": version,
                "install_hint_url": "https://docs.anthropic.com/en/docs/claude-code/quickstart"}

    def _probe_codex() -> dict:
        # Codex CLI ships as 'codex' (when installed via npm @openai/codex
        # or the codex-plugin bundle). We reuse scripts/codex_health.py
        # for the canonical authoritative answer — it knows the plugin
        # install paths + auth file locations.
        codex_health = _bravo_root() / "scripts" / "codex_health.py"
        if not codex_health.exists():
            # Fallback: minimal which-based probe.
            bin_path = _which("codex")
            return {"installed": bool(bin_path), "authenticated": False,
                    "version": None,
                    "install_hint_url": "https://github.com/openai/codex"}
        rc, out = _run([sys.executable, str(codex_health), "--json"], timeout=10)
        if rc != 0 or not out:
            return {"installed": False, "authenticated": False, "version": None,
                    "install_hint_url": "https://github.com/openai/codex"}
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return {"installed": False, "authenticated": False, "version": None,
                    "install_hint_url": "https://github.com/openai/codex"}
        cli_block = data.get("cli") or {}
        auth_block = data.get("auth") or {}
        cli_status = str(cli_block.get("status") or "").lower()
        auth_status = str(auth_block.get("status") or "").lower()
        return {
            "installed": bool(
                cli_block.get("installed")
                or cli_status in {"ok", "ready"}
                or cli_block.get("version")
            ),
            "authenticated": bool(
                auth_block.get("ready")
                or auth_block.get("authenticated")
                or auth_status in {"ok", "ready"}
            ),
            "version": cli_block.get("version"),
            "install_hint_url": "https://github.com/openai/codex",
        }

    def _probe_gemini() -> dict:
        bin_path = _which("gemini")
        if not bin_path:
            return {"installed": False, "authenticated": False, "version": None,
                    "install_hint_url": "https://github.com/google-gemini/gemini-cli"}
        rc, out = _run([bin_path, "--version"])
        if rc != 0:
            return {"installed": True, "authenticated": False, "version": None,
                    "install_hint_url": "https://github.com/google-gemini/gemini-cli"}
        version = out.splitlines()[0].strip() if out else None
        # Auth check: gemini CLI stores OAuth at ~/.gemini/settings.json or
        # uses GEMINI_API_KEY env var.
        home = Path.home()
        has_oauth = (home / ".gemini" / "oauth_creds.json").exists() or (home / ".config" / "google-cloud-sdk").exists()
        import os
        has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        return {"installed": True, "authenticated": has_oauth or has_key, "version": version,
                "install_hint_url": "https://github.com/google-gemini/gemini-cli"}

    result = {
        "claude": _probe_claude(),
        "codex": _probe_codex(),
        "gemini": _probe_gemini(),
    }
    return _ok(json.dumps(result))


# ──────────────────────────────────────────────────────────────────
# install_cli — npm install -g <package> for Claude Code / Codex / Gemini
# ──────────────────────────────────────────────────────────────────
#
# Phase 8.3 (2026-05-19). Dashboard's LocalCliProvidersCard calls this
# when the operator clicks "Install" on a not-yet-installed CLI card.
# We whitelist the three packages to avoid arbitrary npm-install attack
# surface. Each install:
#
#   1. Resolves npm on PATH (npm.cmd on Windows)
#   2. Runs `npm install -g <package>` with a 5-minute timeout
#   3. Catches EACCES/EPERM and surfaces a clear "elevate the bridge"
#      message instead of dumping the raw npm error
#
# Returns _ok / _err per the tool convention.

_NPM_PACKAGE_MAP: dict[str, str] = {
    "claude": "@anthropic-ai/claude-code",
    "codex": "@openai/codex",
    "gemini": "@google/gemini-cli",
}


def _current_cli_info(provider: str) -> dict | None:
    try:
        res = _tool_cli_status({})
        if res.get("is_error"):
            return None
        data = json.loads(str(res.get("output") or "{}"))
        info = data.get(provider)
        return info if isinstance(info, dict) else None
    except Exception:
        return None


def _tool_install_cli(payload: dict) -> dict:
    """{provider: "claude" | "codex" | "gemini"} → install status.

    Runs `npm install -g <whitelisted-package>`. Whitelist enforced
    server-side: any other provider value returns an error without
    invoking npm.
    """
    provider = str(payload.get("provider") or "").lower().strip()
    pkg = _NPM_PACKAGE_MAP.get(provider)
    if not pkg:
        return _err(f"unknown provider: {provider!r}. Expected one of: claude, codex, gemini.")
    current = _current_cli_info(provider)
    if current and current.get("installed"):
        ready = " and authenticated" if current.get("authenticated") else ""
        version = f" ({current.get('version')})" if current.get("version") else ""
        return _ok(
            f"{pkg} is already installed{ready}{version}. "
            "No npm install was needed; click Refresh if the card has not updated."
        )
    # Resolve npm via the enriched lookup so nvm-installed Node (in
    # ~/.nvm/versions/node/<v>/bin/npm) is found even when the bridge
    # inherits the slim LaunchServices PATH. The old shutil.which call
    # missed this on macOS GUI launches.
    npm_bin = which_cli("npm")
    if not npm_bin:
        return _err(
            "npm not found on PATH. Install Node.js first from https://nodejs.org "
            "(any recent LTS works), then click Install again."
        )
    # Subprocess env carries the same enriched PATH so npm's own helpers
    # (npx, node, etc.) resolve too.
    spawn_env = dict(os.environ)
    spawn_env["PATH"] = enriched_path(npm_bin)
    try:
        proc = safe_run(
            [*command_without_cmd_shim(npm_bin), "install", "-g", pkg],
            capture_output=True,
            text=True,
            timeout=300,  # 5 min — global installs can be slow on first run
            encoding="utf-8",
            errors="replace",
            env=spawn_env,
        )
    except subprocess.TimeoutExpired:
        return _err(f"npm install -g {pkg} timed out after 5 minutes")
    except Exception as e:
        return _err(f"npm install failed to spawn: {e}")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        # Friendly errors for the most common operator-side failures.
        if any(token in err for token in ("EACCES", "EPERM", "Operation not permitted", "Access is denied")):
            return _err(
                f"Permission denied installing {pkg}. The bridge needs to run in an "
                "elevated shell to install global npm packages. Either:\n"
                "  1. Stop the bridge daemon, re-open your terminal as Administrator "
                "(Windows) or with sudo (Mac/Linux), restart the bridge, then click "
                "Install again. OR\n"
                f"  2. Run this manually in your terminal: npm install -g {pkg}\n\n"
                f"Raw detail: {err[:400]}"
            )
        # EBUSY happens when an earlier install is still finalizing file
        # copies. Tell the operator to wait a few seconds and retry.
        if "EBUSY" in err or "resource busy or locked" in err:
            current = _current_cli_info(provider)
            if current and current.get("installed"):
                ready = " and authenticated" if current.get("authenticated") else ""
                version = f" ({current.get('version')})" if current.get("version") else ""
                return _ok(
                    f"{pkg} is already usable{ready}{version}. npm reported EBUSY "
                    "because the CLI binary is currently running or a prior install "
                    "is still settling. The dashboard can use the CLI now; close any "
                    "running CLI terminal only if you want to upgrade it."
                )
            return _err(
                f"{pkg} is currently in use (likely a prior install still finalizing, "
                "or the CLI binary is running). Wait 10 seconds and click Install "
                "again. If it persists, close any open terminal that has the CLI "
                f"running.\n\nRaw detail: {err[:400]}"
            )
        return _err(f"npm install failed (exit {proc.returncode}): {err[:1500]}")
    # npm exited 0, but the binary's shim files can take a moment to
    # appear on PATH (especially on Windows where it writes .cmd shims
    # after the package files). Brief settle delay so the post-install
    # cli_status probe sees installed=true on the first try.
    time.sleep(1.5)
    return _ok(
        f"Installed {pkg}.\n\n"
        f"{(proc.stdout or '').strip()[:1500] or '(no stdout)'}"
    )


# ──────────────────────────────────────────────────────────────────
# cli_auth_start — kick off CLI's interactive auth flow
# ──────────────────────────────────────────────────────────────────
#
# The CLI itself handles the OAuth roundtrip locally (it starts a
# loopback HTTP server, opens the browser to the provider's OAuth
# screen, captures the callback). The bridge's job is to invoke the
# auth subcommand non-blockingly and return immediately — the
# dashboard polls cli_status to detect when authentication completes.

_AUTH_CMD_MAP: dict[str, list[str]] = {
    "codex": ["auth", "login"],
    "gemini": ["auth", "login"],
    # Claude Code auths on first interactive use (`claude` → /login).
    # No subcommand path to spawn; we surface guidance text instead.
}


def _tool_cli_auth_start(payload: dict) -> dict:
    """{provider: "claude" | "codex" | "gemini"} → started + auth URL.

    Spawns the CLI's auth subcommand in the background and captures
    the first ~5 seconds of stdout/stderr. CLIs print "Visit https://..."
    to stdout in the OAuth flow — we surface that text to the dashboard
    so the operator can click the URL directly instead of hunting for a
    console window.

    The CLI process keeps running after we return (we don't .wait()).
    Its loopback HTTP server handles the OAuth callback locally; the
    dashboard polls cli_status to detect READY.
    """
    import shutil
    import threading
    import queue
    provider = str(payload.get("provider") or "").lower().strip()
    # Claude Code doesn't expose an auth subcommand — the CLI prompts
    # for /login on first interactive run. Best we can do is guide.
    if provider == "claude":
        return _ok(
            "Claude Code authenticates on first interactive use. Open a terminal, "
            "run `claude`, type `/login`, and follow the printed URL. Once you've "
            "signed in, click Refresh in the dashboard."
        )
    if provider not in _AUTH_CMD_MAP:
        return _err(f"unknown provider: {provider!r}. Expected one of: claude, codex, gemini.")
    args = _AUTH_CMD_MAP[provider]
    bin_path = shutil.which(provider) or shutil.which(provider + ".cmd")
    if not bin_path:
        return _err(
            f"{provider} is not installed. Click Install on the {provider} card first, "
            "then click Sign in."
        )
    # Spawn with combined stdout/stderr capture. We want to surface the
    # CLI's "Visit https://..." line in the dashboard. Detaching with
    # DEVNULL hid that output and made the flow opaque.
    try:
        proc = safe_popen(
            [*command_without_cmd_shim(bin_path), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # line-buffered so we get URLs as they print
        )
    except FileNotFoundError:
        return _err(f"{provider} binary disappeared between status check and spawn")
    except Exception as e:
        return _err(f"failed to start {provider} auth: {e}")

    # Background reader thread + queue so we can poll for early output
    # without blocking on a process that runs for the entire OAuth
    # roundtrip (which can be minutes).
    out_q: queue.Queue[str] = queue.Queue()

    def _reader() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                out_q.put(line)
        except Exception:
            pass

    threading.Thread(target=_reader, daemon=True).start()

    # Collect output for up to 5 seconds, or until the process exits,
    # or until we've seen a URL (early-out so the dashboard is snappy).
    deadline = time.time() + 5.0
    collected: list[str] = []
    while time.time() < deadline:
        try:
            line = out_q.get(timeout=0.25)
            collected.append(line)
            # Early-out as soon as a URL surfaces.
            if "http://" in line or "https://" in line:
                # Drain any immediately-following lines (often the
                # CLI prints a blank-line separator after the URL).
                for _ in range(3):
                    try:
                        collected.append(out_q.get_nowait())
                    except queue.Empty:
                        break
                break
        except queue.Empty:
            # If the process died early, surface whatever it said.
            if proc.poll() is not None:
                break

    raw = "".join(collected).strip()
    if not raw:
        return _ok(
            f"Started {provider} sign-in (pid {proc.pid}). Your browser should "
            "open shortly. If it doesn't, watch this card — when the CLI "
            "prints a URL the next probe will surface it. Click Refresh after "
            "you've signed in."
        )
    return _ok(
        f"{provider} sign-in started. Copy/paste the URL below into your browser "
        f"if it doesn't auto-open:\n\n{raw[:2000]}"
    )


TOOL_REGISTRY: dict[str, Callable[[dict], dict]] = {
    "read_file": _tool_read_file,
    "write_file": _tool_write_file,
    "bash": _tool_bash,
    "send_email": _tool_send_email,
    "send_sms": _tool_send_sms,
    "list_scripts": _tool_list_scripts,
    "run_script": _tool_run_script,
    "list_skills": _tool_list_skills,
    "load_skill": _tool_load_skill,
    "stripe": _tool_stripe,
    "supabase": _tool_supabase,
    "n8n": _tool_n8n,
    "firecrawl": _tool_firecrawl,
    "notebooklm": _tool_notebooklm,
    "underwriting_run": _tool_underwriting_run,
    "shop_out_send_batch": _tool_shop_out_send_batch,
    "cli_status": _tool_cli_status,
    "install_cli": _tool_install_cli,
    "cli_auth_start": _tool_cli_auth_start,
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
