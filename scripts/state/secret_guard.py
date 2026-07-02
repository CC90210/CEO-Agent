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

# Put scripts/ (the parent of state/) on the path so `import lib.hook_runtime`
# resolves. The previous .parent pointed at state/ itself, so the import raised
# ModuleNotFoundError and the hook exited non-zero — fail-OPEN (the guard never
# enforced or even logged). scripts/ = state/'s parent = __file__.parent.parent.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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
    r"python|python3|py|node|deno|ruby|perl|powershell|pwsh|gc|type|"
    r"Get-Content|Get-Item|Select-String|sls|cp|copy|mv|move|rsync|scp|sftp|curl|wget|"
    # PowerShell exfil cmdlets (the PowerShell tool is now routed here too):
    r"Invoke-WebRequest|Invoke-RestMethod|iwr|irm|Out-File|Set-Content|"
    r"Add-Content|Copy-Item|Move-Item|Export-Csv|ConvertTo-Json|Format-Hex)\b",
    re.IGNORECASE,
)

# Bash heredoc (<<EOF … .env.agents) AND PowerShell here-strings (@'…'@ / @"…"@)
# that embed a secret path. GAP-7: the bash-only form let a PowerShell
# here-string pipe a secret out undetected.
HEREDOC_RE = re.compile(
    r"<<\s*[A-Za-z_]+\s+.*\.env(?:\.[\w-]+)*"
    r"|@[\"'][\s\S]*?\.env(?:\.[\w-]+)*[\s\S]*?[\"']@",
    re.DOTALL | re.IGNORECASE,
)


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
    "Use the appropriate CLI tool wrapper (e.g., scripts/integrations/stripe_tool.py, scripts/integrations/supabase_tool.py).\n"
    "Wrappers load secrets internally and never echo them to the agent."
)


def main() -> int:
    mode = mode_from_env("EMPIRE_HOOK_SECRET_GUARD", default="enforce")
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
    elif tool_name in ("Bash", "PowerShell"):
        # PowerShell was previously unguarded (audit GAP-1): a Get-Content on
        # .env.agents piped to Invoke-WebRequest would exfiltrate secrets with
        # no gate. The PowerShell tool's field is `command` (fall back to
        # `script`).
        cmd = tool_input.get("command", "") or tool_input.get("script", "")
        is_exfil, matched = _command_is_secret_exfil(cmd)
        if is_exfil:
            target = matched
            reason = REASON_EXEC.format(path=matched)
    elif tool_name in ("Grep", "Glob"):
        # GAP-5: only the Read tool was path-filtered, so Grep/Glob could read a
        # secret file by pointing `path` straight at it (e.g. Grep pattern=STRIPE
        # path=.env.agents surfaces the secret in matching lines). Block when the
        # path targets a secret. (Grep on a *directory* is mitigated separately:
        # ripgrep respects .gitignore, and .env* is gitignored.)
        path = tool_input.get("path")
        if _path_is_secret(path):
            target = path
            reason = REASON_READ.format(path=path)

    if not reason:
        return 0

    cmd_for_log = (
        (tool_input.get("command") or tool_input.get("script"))
        if tool_name in ("Bash", "PowerShell")
        else target
    )

    if mode == "enforce":
        log_jsonl(LOG_PATH, {"decision": "blocked", "target": target, "command": (cmd_for_log or "")[:500]})
        sys.stderr.write(reason + "\n")
        return 2

    log_jsonl(LOG_PATH, {"decision": "would-block", "target": target, "command": (cmd_for_log or "")[:500]})
    sys.stderr.write(f"[secret_guard report-mode] would block: {target}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
