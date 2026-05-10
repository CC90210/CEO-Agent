"""PreToolUse hook — denies the LLM direct read access to secret files.

`.env.agents` and friends are loaded by Python CLI tool wrappers internally.
The agent itself never needs to see them. This guard intercepts:

  * Read tool targeting any secret file (`.env*`, `*.pem`, `*.key`,
    `credentials.json`, anything under `secrets/`).
  * Bash commands that would extract secrets via cat/grep/sed/awk/python -c
    or copy/move them to a readable location.

Modes (env var `EMPIRE_HOOK_SECRET_GUARD`):
  enforce          → block; log to state/secret_guard.log
  report (default) → log the would-block, allow
  off              → pass through
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.hook_runtime import (  # noqa: E402
    log_jsonl,
    mode_from_env,
    read_hook_input,
    state_log_path,
)

LOG_PATH = state_log_path("secret_guard")

# ── Path patterns that classify a target as a secret file ──────────────────
# Each alternative anchors itself — putting them all behind `(?:^|[\\/])` was
# wrong because file-suffix patterns like `\.pem$` need to match anywhere in
# the path tail (e.g., `tls/private.pem`). Path-prefix patterns (`secrets/`,
# `.env`) keep their boundary anchor so they don't false-positive on names
# like `myfile.envtech.txt`.
#
# `.env(?:\.[A-Za-z0-9_-]+)*$` uses `*` (zero-or-more) instead of `?`
# (zero-or-one) so all of these match equally:
#   .env, .env.agents, .env.agents.core, .env.agents.webhook,
#   .env.agents.dashboard, .env.local, .env.production
# The Phase 2 scoped-env fan-out (`.env.agents.{core,webhook,dashboard}`)
# was a self-inflicted gap before this patch — Codex caught it.
SECRET_PATH_RE = re.compile(
    r"(?:^|[\\/])\.env(?:\.[A-Za-z0-9_-]+)*$"
    r"|(?:^|[\\/])secrets?/"
    r"|(?:^|[\\/])credentials\.json$"
    r"|\.pem$"
    r"|\.p12$"
    r"|\.pfx$"
    r"|\.key$"
    r"|(?:^|[\\/])service[-_]?account[^/]*\.json$",
    re.IGNORECASE,
)

EXFIL_TOOLS = re.compile(
    r"\b(cat|less|more|head|tail|grep|awk|sed|tac|xxd|hexdump|od|base64|"
    r"strings|nl|tr|cut|sort|uniq|wc|file|stat|tee|sha256sum|md5sum|"
    r"python|python3|py|node|deno|ruby|perl|powershell|pwsh|gc|"
    r"Get-Content|Select-String|cp|copy|mv|move|rsync|scp|sftp|curl|wget)\b",
    re.IGNORECASE,
)

HEREDOC_RE = re.compile(r"<<\s*[A-Za-z_]+\s+.*\.env\.agents", re.DOTALL)


def _path_is_secret(path: str | None) -> bool:
    if not path:
        return False
    return bool(SECRET_PATH_RE.search(path))


def _command_is_secret_exfil(cmd: str) -> tuple[bool, str | None]:
    if not cmd:
        return (False, None)
    # `\.env(?:\.[\w-]+)*` (zero-or-more) so we extract the FULL path of
    # `.env.agents.core` etc. as one candidate, matching the SECRET_PATH_RE
    # change above. Previously we only captured the `.env.agents` prefix.
    candidates = re.findall(r"(?:[A-Za-z]:)?[\w./\\-]*\.env(?:\.[\w-]+)*\b", cmd)
    candidates += re.findall(r"[\w./\\-]*credentials\.json\b", cmd, re.IGNORECASE)
    candidates += re.findall(r"[\w./\\-]+\.(?:pem|key|p12|pfx)\b", cmd, re.IGNORECASE)
    matched = next((c for c in candidates if _path_is_secret(c)), None)
    if not matched:
        return (False, None)
    if EXFIL_TOOLS.search(cmd):
        return (True, matched)
    if HEREDOC_RE.search(cmd):
        return (True, matched)
    if re.search(r"<\s*[\w./\\-]*\.env\b", cmd):
        return (True, matched)
    return (False, matched)


REASON_READ = (
    "BLOCKED by secret_guard: '{path}' is not LLM-readable.\n"
    "Use a CLI tool wrapper that loads the secret internally and returns a sanitized payload:\n"
    "  python scripts/<service>_tool.py <verb> --json\n"
    "If no wrapper exists, build one (see skills/cli-anything/SKILL.md). Never inline secrets."
)
REASON_EXEC = (
    "BLOCKED by secret_guard: command would extract '{path}'.\n"
    "Use the appropriate CLI tool wrapper (e.g., scripts/stripe_tool.py, scripts/supabase_tool.py).\n"
    "Wrappers load secrets internally and never echo them to the agent."
)


def main() -> int:
    mode = mode_from_env("EMPIRE_HOOK_SECRET_GUARD", default="report")
    if mode == "off":
        return 0

    payload = read_hook_input()
    if not payload:
        return 0

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    target = None
    reason = None

    if tool_name == "Read":
        path = tool_input.get("file_path")
        if _path_is_secret(path):
            target = path
            reason = REASON_READ.format(path=path)
    elif tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = tool_input.get("file_path")
        if _path_is_secret(path):
            target = path
            reason = REASON_READ.format(path=path) + (
                "\n(Edit on a secret file is also blocked — they are immutable to the agent.)"
            )
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        is_exfil, matched = _command_is_secret_exfil(cmd)
        if is_exfil:
            target = matched
            reason = REASON_EXEC.format(path=matched)

    if not reason:
        return 0

    cmd_for_log = tool_input.get("command") if tool_name == "Bash" else target

    if mode == "enforce":
        log_jsonl(LOG_PATH, {"decision": "blocked", "target": target, "command": (cmd_for_log or "")[:500]})
        sys.stderr.write(reason + "\n")
        return 2

    log_jsonl(LOG_PATH, {"decision": "would-block", "target": target, "command": (cmd_for_log or "")[:500]})
    sys.stderr.write(f"[secret_guard report-mode] would block: {target}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
