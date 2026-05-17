"""UserPromptSubmit hook — selective context injection from memory_retriever.

Fires when CC submits a prompt. Triages the prompt by length + intent shape:
  - T1 (chat/lookup, <60 chars or starts with greeting): no injection
  - T2 (operational, default): query memory_retriever for top 3 snippets
  - T3 (architectural keywords: "design"/"refactor"/"architecture"): top 5 snippets

This is the silver-platter principle applied to prompts themselves — instead
of the agent searching FTS5 mid-conversation, we pre-resolve the top hits and
inject them as context so the agent starts on the synthesis layer.

Output contract:
    {
      "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "<markdown block>"
      }
    }

Fast-fails on error — empty additionalContext rather than blocking.
Wired in .claude/settings.local.json UserPromptSubmit matcher.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "state"
LOG_PATH = STATE_DIR / "user_prompt_submit.log"
TIMEOUT_SEC = 3

T1_GREETING_RE = re.compile(r"^\s*(wsp|yo|hi|hey|hello|sup|thanks|thx|gm|gn|ok|okay)\b", re.I)
T3_ARCH_RE = re.compile(r"\b(architecture|refactor|redesign|migrate|migration|schema|design system|cross-agent)\b", re.I)
CONTEXT_MD = PROJECT_ROOT / "CONTEXT.md"
CONTEXT_TERM_RE = re.compile(r"^- \*\*([^*]+)\*\* — (.+)$")
CONTEXT_MAX_INJECTIONS = 5

_context_cache: dict[str, tuple[str, str]] | None = None
_context_cache_mtime: float = 0.0


def _load_context_terms() -> dict[str, tuple[str, str]]:
    """Parse CONTEXT.md once per (mtime, process). Returns {lower_term: (display, def)}.

    Reads only `- **Term** — definition` lines under any section header.
    Cached across hook invocations within a Python session — but since this
    hook spawns fresh each prompt, the cache survives only when something
    else holds the module loaded. Fine; parse cost is <2ms.
    """
    global _context_cache, _context_cache_mtime
    if not CONTEXT_MD.exists():
        return {}
    try:
        mtime = CONTEXT_MD.stat().st_mtime
    except OSError:
        return {}
    if _context_cache is not None and mtime == _context_cache_mtime:
        return _context_cache
    out: dict[str, tuple[str, str]] = {}
    try:
        for line in CONTEXT_MD.read_text(encoding="utf-8").splitlines():
            m = CONTEXT_TERM_RE.match(line)
            if not m:
                continue
            term = m.group(1).strip()
            defn = m.group(2).strip()
            # Skip identity self-references like "**CC** — The operator."
            # if the definition is itself <8 chars (rare).
            if len(defn) < 8:
                continue
            out[term.lower()] = (term, defn)
    except OSError:
        return {}
    _context_cache = out
    _context_cache_mtime = mtime
    return out


def _match_context_terms(prompt: str) -> list[tuple[str, str]]:
    """Return up to CONTEXT_MAX_INJECTIONS (term, definition) tuples whose term
    appears as a word-boundary match in the prompt (case-insensitive).

    Bias: prefer longer terms first ("OASIS Outbound" before "OASIS") to avoid
    redundant injection of a parent term when a more-specific term matched.
    """
    terms = _load_context_terms()
    if not terms:
        return []
    plower = prompt.lower()
    matched: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    # Sort by length-desc so longer terms get first dibs.
    for key in sorted(terms, key=len, reverse=True):
        if key in seen:
            continue
        if re.search(rf"\b{re.escape(key)}\b", plower):
            term, defn = terms[key]
            matched.append((len(key), term, defn))
            seen.add(key)
            if len(matched) >= CONTEXT_MAX_INJECTIONS:
                break
    return [(t, d) for _, t, d in matched]


def _log(payload: dict) -> None:
    try:
        STATE_DIR.mkdir(exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _tier(prompt: str) -> str:
    p = prompt.strip()
    if not p:
        return "skip"
    if len(p) < 60 and T1_GREETING_RE.match(p):
        return "T1"
    if T3_ARCH_RE.search(p):
        return "T3"
    return "T2"


def _query_retriever(prompt: str, limit: int) -> list[dict]:
    try:
        result = subprocess.run(
            ["python", "scripts/memory_retriever.py", "query", "--json", "--limit", str(limit), prompt],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
            cwd=str(PROJECT_ROOT),
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("hits", []) or data.get("results", []) or []
    return []


def _format_hits(hits: list[dict]) -> str:
    if not hits:
        return ""
    lines = []
    for h in hits:
        src = h.get("source") or h.get("path") or "?"
        line_start = h.get("line_start") or h.get("line") or ""
        heading = h.get("heading", "")
        snippet = (h.get("text") or h.get("snippet") or "").strip()
        if len(snippet) > 280:
            snippet = snippet[:280] + "..."
        ref = f"{src}:{line_start}" if line_start else src
        head = f" — {heading}" if heading else ""
        lines.append(f"- **{ref}**{head}\n  {snippet}")
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}

    prompt = payload.get("prompt") or payload.get("input", {}).get("prompt") or ""
    tier = _tier(prompt)

    # V6.8 — CONTEXT.md term injection runs on EVERY non-skip prompt (even T1).
    # Glossary definitions are cheap and load-bearing for vocabulary discipline.
    ctx_matches = _match_context_terms(prompt) if tier != "skip" else []
    ctx_block = ""
    if ctx_matches:
        ctx_lines = "\n".join(f"- **{term}** — {defn}" for term, defn in ctx_matches)
        ctx_block = (
            "## Canonical Vocabulary (CONTEXT.md)\n"
            "_Domain terms in your prompt resolved against the empire glossary. "
            "Use these definitions; do not re-derive._\n\n"
            f"{ctx_lines}\n\n"
        )

    if tier in ("skip", "T1"):
        if ctx_block:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": ctx_block.rstrip(),
                }
            }))
        else:
            print(json.dumps({}))
        _log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "tier": tier,
            "prompt_chars": len(prompt),
            "hits": 0,
            "context_terms": len(ctx_matches),
        })
        return 0

    limit = 5 if tier == "T3" else 3
    hits = _query_retriever(prompt, limit)
    formatted = _format_hits(hits)

    if not formatted and not ctx_block:
        print(json.dumps({}))
        _log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "tier": tier,
            "prompt_chars": len(prompt),
            "hits": 0,
            "context_terms": 0,
        })
        return 0

    memory_block = ""
    if formatted:
        memory_block = (
            f"## Relevant Memory ({tier}, top {limit})\n"
            f"_Pre-resolved snippets from memory/, skills/, brain/ matching your prompt. "
            f"Read the file at the cited line if a snippet is on-target._\n\n"
            f"{formatted}"
        )

    context = (ctx_block + memory_block).rstrip()
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    _log({
        "ts": datetime.now(timezone.utc).isoformat(),
        "tier": tier,
        "prompt_chars": len(prompt),
        "hits": len(hits),
        "context_terms": len(ctx_matches),
    })
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        _log({"ts": datetime.now(timezone.utc).isoformat(), "status": "error", "error": str(e)})
        print(json.dumps({}))
        raise SystemExit(0)
