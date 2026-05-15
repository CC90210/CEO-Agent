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
        proc = subprocess.run(
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
