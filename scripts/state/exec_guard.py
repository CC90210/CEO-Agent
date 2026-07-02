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
    # Reverting uncommitted work silently destroys another process's changes
    # with no undo. 2026-07-02 incident: a read-only agent ran
    # `git checkout <files> && rm -rf <untracked dir>` to "clean" the tree.
    # These block the revert forms while leaving branch switches
    # (`git checkout main`, `git checkout -b feat/x`, `git checkout <sha>`) allowed.
    # `git restore` discards the working tree. Only `--staged` WITHOUT `--worktree`
    # is safe (unstage-only). Codex audit: the old single pattern allowed
    # `git restore --staged --worktree file` because --staged was present.
    ("git-restore-default",   re.compile(r"\bgit\s+restore\b(?![^|;&]*--staged\b)")),   # no --staged → worktree discard
    ("git-restore-worktree",  re.compile(r"\bgit\s+restore\b[^|;&]*--worktree\b")),      # explicit --worktree even with --staged
    ("git-checkout-pathspec", re.compile(r"\bgit\s+checkout\b[^|;&]*?(?:\s--\s|\s--$|\s\.(?:\s|$))")),
    # File revert via `git checkout [HEAD] <file>`. Codex audit: top-level files
    # have no slash, so require a filename EXTENSION (alpha, so version tags like
    # v1.2 aren't caught) instead of a slash. Branch switches (no .ext) stay allowed.
    ("git-checkout-file",     re.compile(r"\bgit\s+checkout\b(?!\s+-[bB]\b)[^|;&]*?\s(?:HEAD\s+|HEAD~\d+\s+)?\S*\.[A-Za-z][A-Za-z0-9]*(?:\s|$)")),
    ("git-stash-destroy",     re.compile(r"\bgit\s+stash\s+(?:drop|clear)\b")),
    # rm -rf of a relative directory that is NOT a known-safe build/cache/tmp
    # target — catches the incident's `rm -rf bugzil.la/` (untracked work).
    # Codex audit: accept BOTH flag orders (-rf and -fr).
    ("rm-rf-untracked-dir",   re.compile(r"\brm\s+-(?:[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*)\s+(?!(?:\./)?(?:tmp|node_modules|__pycache__|\.next|\.turbo|dist|build|out|\.cache|coverage|\.pytest_cache)[\s/])[\w.\-]+/")),
    ("env-overwrite",      re.compile(r">\s*\.env\.agents\b")),
    ("fork-bomb",          re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")),
    ("dd-disk-overwrite", re.compile(r"\bdd\s+if=/dev/(zero|random|urandom)\s+of=/(?:dev/)?\w+")),
    # ── PowerShell destructive forms (the PowerShell tool is guarded too; see
    #    main() tool_name handling + settings.local.json). Harmlessly inert
    #    against bash strings. ──
    ("ps-remove-recurse",  re.compile(r"\bRemove-Item\b[^|;&\n]*\s-(?:Recurse|r)\b", re.IGNORECASE)),
    # PowerShell aliases for Remove-Item (rm/rmdir/del/ri/erase) with -Recurse.
    # Codex audit: `rm -Recurse foo` / `rmdir -Recurse foo` missed Remove-Item.
    ("ps-rm-recurse-alias", re.compile(r"\b(?:rm|rmdir|del|ri|erase)\b[^|;&\n]*\s-Recurse\b", re.IGNORECASE)),
    ("ps-rmdir-recurse",   re.compile(r"\b(?:rmdir|rd)\b[^|;&\n]*\s/s\b", re.IGNORECASE)),
    ("ps-clear-content-env", re.compile(r"\bClear-Content\b[^|;&\n]*\.env", re.IGNORECASE)),
    ("git-force-main-ps",  re.compile(r"\bgit\s+push\s+(?:-f\b|--force(?!-with-lease)\b)[^\n]*\b(main|master|production|prod)\b", re.IGNORECASE)),
]

IRREVERSIBLE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("git-push",                re.compile(r"\bgit\s+push\b")),
    ("vercel-prod",             re.compile(r"\bvercel\s+(deploy\s+)?(--prod|--production)\b")),
    ("stripe-charge-or-refund", re.compile(r"\bstripe_tool\.py\s+(charge|refund|payout)\b")),
    ("supabase-migration",      re.compile(r"\bsupabase\s+(db\s+)?(push|reset|apply_migration)\b")),
    ("n8n-publish",             re.compile(r"\bn8n_tool\.py\s+publish_workflow\b")),
    ("prod-keyword",            re.compile(r"\b(prod|production|live)\b.*\b(deploy|push|publish|migrate)\b")),
    # SQL loaded from a file bypasses the inline-SQL AST check (the guard can't
    # read the file). Log it as irreversible for the audit trail rather than
    # hard-blocking (that would break legit migration application). Audit gap
    # GAP-4, 2026-07-02.
    ("sql-from-file",           re.compile(r"\b(?:psql|sqlite3|supabase_tool\.py\s+execute-sql)\b[^|;&]*(?:--file\b|--file=|\s-f\s|<\s*\S+\.sql)", re.IGNORECASE)),
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

    # Guard both the Bash tool and the Windows PowerShell tool. PowerShell was
    # entirely unguarded (audit GAP-1, CRITICAL) — it could run
    # `Remove-Item -Recurse` / `git push --force` / secret exfil with no gate.
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    tool_input = payload.get("tool_input", {}) or {}
    cmd = tool_input.get("command", "") or tool_input.get("script", "")
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
