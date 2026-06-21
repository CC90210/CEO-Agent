"""PreToolUse Bash hook — layered policy gate against destructive commands.

Layers (evaluated in order):
  1. Hard blocklist (regex)         → exit 2, block
  2. AST-validated SQL via sqlglot  → exit 2, block on Drop/Truncate/AlterDrop/Delete-without-Where
  3. Irreversible-op allowlist      → log only, allow (Phase 1)
  4. CLI tool fast-path             → exit 0 immediately

Modes (env var `EMPIRE_HOOK_EXEC_GUARD`):
  enforce          → block on hits
  report (default) → log the would-block, allow
  off              → pass through
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# scripts/ (parent of state/) must be on the path for `import lib.hook_runtime`.
# Was .parent (state/ itself) → ModuleNotFoundError → hook crashed fail-OPEN.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.hook_runtime import (  # noqa: E402
    log_jsonl,
    mode_from_env,
    read_hook_input,
    state_log_path,
)

LOG_PATH = state_log_path("exec_guard")

# ── Layer 1: hard blocklist (regex). Tested against the full command string. ──
HARD_BLOCKS: list[tuple[str, re.Pattern]] = [
    ("rm-rf-root",         re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*)\s+/(?!tmp\b|var/tmp\b|home/[^/\s]+/(?:Business-Empire-Agent/)?tmp\b)")),
    # `rm -rf` followed by NOTHING in this command — a downstream pipe /
    # xargs / cmdsubst supplies the path. Codex caught this: chained
    # commands smuggled the destruction past the path-anchored regex.
    ("rm-rf-no-path",      re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s*(?:$|[|;&])")),
    # `xargs rm` — explicit dynamic-path delete chain.
    ("xargs-rm",           re.compile(r"\bxargs\b(?:\s+-[a-zA-Z0-9-]+(?:\s+\S+)?)*\s+rm\b", re.IGNORECASE)),
    ("rm-etc",             re.compile(r"\brm\s+(-[a-zA-Z]+\s+)?/etc(?:/|\s|$)")),
    ("rm-windows-system",  re.compile(r"\brm\s+(-[a-zA-Z]+\s+)?(?:/c/Windows|C:\\Windows)", re.IGNORECASE)),
    # rm -rf of the home dir (~ or $HOME) — red-team override-email-21 (2026-06-09)
    # found `rm -rf ~/` slipped past rm-rf-root (which anchors on a literal `/`).
    ("rm-rf-home",         re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:~|\$HOME)(?:/|\s|$)")),
    # fetch-and-execute: curl/wget piped into a shell/interpreter — red-team
    # toolbait-email-07 (2026-06-09) found `curl … | bash` runs arbitrary remote code.
    ("curl-pipe-shell",    re.compile(r"\b(?:curl|wget)\b[^|]*\|\s*(?:sudo\s+)?(?:bash|sh|zsh|dash|python3?|node|perl|ruby)\b", re.IGNORECASE)),
    ("rm-env-agents",      re.compile(r"\brm\s+(-[a-zA-Z]+\s+)?\.env\.agents\b")),
    ("rm-state-db",        re.compile(r"\brm\s+(-[a-zA-Z]+\s+)?state/empire_state\.db\b")),
    ("drop-database",      re.compile(r"\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX|VIEW)\b", re.IGNORECASE)),
    ("truncate-table",     re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE)),
    # DELETE FROM <table> followed by ; / EOL / non-WHERE token = unsafe.
    # The previous regex used a `(\s*[^W])` tail that incorrectly fired on
    # legitimate `DELETE FROM x WHERE ...` (the space + 'W' tail was
    # consumed by the wrong alternative). New form anchors the danger to
    # the actual end-of-statement state.
    ("delete-no-where",    re.compile(r"\bDELETE\s+FROM\s+\w+\s*(?:;|$|\s+(?!WHERE\b))", re.IGNORECASE)),
    ("alter-drop-col",     re.compile(r"\bALTER\s+TABLE\b[^;]*\bDROP\s+(COLUMN|CONSTRAINT)\b", re.IGNORECASE)),
    ("git-force-main",     re.compile(r"\bgit\s+push\s+(?:-f\b|--force(?!-with-lease)\b)[^|;]*\b(main|master|production|prod)\b")),
    ("git-reset-hard-ref", re.compile(r"\bgit\s+reset\s+--hard\s+(?!HEAD\s*$)(?!HEAD\b\s*$)\S+")),
    ("git-clean-fdx",      re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*[fdx]")),
    ("env-overwrite",      re.compile(r">\s*\.env\.agents\b")),
    ("fork-bomb",          re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")),
    ("dd-disk-overwrite", re.compile(r"\bdd\s+if=/dev/(zero|random|urandom)\s+of=/(?:dev/)?\w+")),
]

IRREVERSIBLE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("git-push",                re.compile(r"\bgit\s+push\b")),
    ("vercel-prod",             re.compile(r"\bvercel\s+(deploy\s+)?(--prod|--production)\b")),
    ("stripe-charge-or-refund", re.compile(r"\bstripe_tool\.py\s+(charge|refund|payout)\b")),
    ("supabase-migration",      re.compile(r"\bsupabase\s+(db\s+)?(push|reset|apply_migration)\b")),
    ("n8n-publish",             re.compile(r"\bn8n_tool\.py\s+publish_workflow\b")),
    ("prod-keyword",            re.compile(r"\b(prod|production|live)\b.*\b(deploy|push|publish|migrate)\b")),
]

READ_ONLY_VERBS = {"list", "get", "search", "query", "status", "show", "describe",
                   "count", "ls", "cat", "view", "info", "help", "--help", "-h",
                   "--version", "doctor", "test", "check", "audit"}

# Any of these in the command means another command can run after the
# "read-only" verb. Disqualifies the fast path. Codex caught this: the
# previous fast-path looked at `tokens[2]`, saw `status`, exited 0 — never
# noticed the `&& rm -rf /` chained behind it.
_CHAIN_OPS = re.compile(
    r"&&|\|\||(?<!\\);|(?<!\|)\|(?!\|)|`|\$\(|<\(|>\(",
)


def _check_hard_blocks(cmd: str) -> tuple[str, str] | None:
    for name, pat in HARD_BLOCKS:
        if pat.search(cmd):
            return (name, f"matches hard blocklist pattern '{name}'")
    return None


def _check_sql_ast(cmd: str) -> tuple[str, str] | None:
    if not re.search(r"\b(psql|sqlite3|supabase_tool\.py\s+execute-sql|run-sql)\b", cmd):
        return None
    sql_match = re.search(r'["\']([^"\']*(?:SELECT|INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE)[^"\']*)["\']',
                          cmd, re.IGNORECASE)
    if not sql_match:
        return None
    sql = sql_match.group(1)
    try:
        import sqlglot
        from sqlglot import expressions as exp
    except ImportError:
        return None
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception:
        return None
    for stmt in statements:
        if stmt is None:
            continue
        if isinstance(stmt, (exp.Drop, exp.TruncateTable)):
            return ("sql-ast-drop", f"SQL AST: {type(stmt).__name__} forbidden")
        if isinstance(stmt, exp.Delete) and stmt.args.get("where") is None:
            return ("sql-ast-delete-no-where", "SQL AST: DELETE without WHERE forbidden")
        if isinstance(stmt, exp.Alter):
            for action in stmt.args.get("actions", []) or []:
                if isinstance(action, exp.Drop):
                    return ("sql-ast-alter-drop", "SQL AST: ALTER TABLE … DROP forbidden")
    return None


def _check_irreversible(cmd: str) -> tuple[str, str] | None:
    for name, pat in IRREVERSIBLE_PATTERNS:
        if pat.search(cmd):
            return (name, f"irreversible-op '{name}' (logged, not blocked)")
    return None


def _is_read_only_cli(cmd: str) -> bool:
    # Reject command chains outright. A "read-only" verb at the start of a
    # chain says NOTHING about the safety of the rest. Without this, a
    # destructive command tucked behind `&&` / `;` / `|` slips past every
    # later layer too.
    if _CHAIN_OPS.search(cmd):
        return False
    tokens = cmd.strip().split()
    if not tokens:
        return False
    if tokens[0] in ("python", "py", "python3") and len(tokens) >= 3:
        return tokens[2].lower() in READ_ONLY_VERBS
    if len(tokens) >= 2 and tokens[1].lower() in READ_ONLY_VERBS:
        return True
    return False


def _evaluate(cmd: str) -> tuple[str, str | None, str | None]:
    if _is_read_only_cli(cmd):
        return ("allow", "fast-path-readonly", None)
    hit = _check_hard_blocks(cmd)
    if hit:
        return ("block", "hard-blocklist", hit[1])
    hit = _check_sql_ast(cmd)
    if hit:
        return ("block", "sql-ast", hit[1])
    hit = _check_irreversible(cmd)
    if hit:
        return ("irreversible", "irreversible-allowlist", hit[1])
    return ("allow", "default-pass", None)


def main() -> int:
    mode = mode_from_env("EMPIRE_HOOK_EXEC_GUARD", default="enforce")
    if mode == "off":
        return 0

    payload = read_hook_input()
    if not payload:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0
    cmd = payload.get("tool_input", {}).get("command", "")
    if not cmd:
        return 0

    decision, layer, reason = _evaluate(cmd)
    cmd_clip = cmd[:1000]

    if decision == "allow":
        return 0

    if decision == "irreversible":
        log_jsonl(LOG_PATH, {"decision": "logged", "layer": layer, "command": cmd_clip})
        return 0

    # decision == "block"
    # The block IS the protection. No override / approval-request path
    # exists anymore (deleted 2026-05-22 per CC: "I don't want to be an
    # approval bot — agents pick a different approach when blocked").
    # If a future need for human approval emerges, do it as an explicit
    #, narrow workflow — not a default-deny queue.
    if mode == "enforce":
        log_jsonl(LOG_PATH, {
            "decision": "blocked",
            "layer": layer,
            "command": cmd_clip,
        })
        sys.stderr.write(
            f"BLOCKED by exec_guard ({layer}): {reason}\n"
            f"  Command: {cmd[:200]}{'...' if len(cmd) > 200 else ''}\n"
            "  Pick a safer alternative. Do NOT bypass with eval, base64, "
            "or --no-verify (bypass attempts are logged).\n"
        )
        return 2

    # report mode — log a would-be block, no DB write, no approval request.
    log_jsonl(LOG_PATH, {
        "decision": "would-block",
        "layer": layer,
        "command": cmd_clip,
    })
    sys.stderr.write(
        f"[exec_guard report-mode] would block ({layer}): {cmd[:160]}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
