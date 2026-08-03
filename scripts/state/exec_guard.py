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
    # ── GitHub CLI: account-level destruction + credential exfil.
    #    Added V7.5.0 (2026-08-03) from the davidondrej/skills denylist audit.
    #    `capability_probe.py list` reports github as OK — every agent on this
    #    fleet can run `gh` right now, and this guard had ZERO `gh` coverage.
    #    `gh auth token` is the important one: it prints a live OAuth token to
    #    stdout. secret_guard.py only guards `.env*`/`*.pem`/`*.key`/creds
    #    FILES, so a token read out of gh's own keychain never touches a
    #    guarded path — it bypassed the secret layer entirely.
    ("gh-auth-token",      re.compile(r"\bgh\s+auth\s+token\b", re.IGNORECASE)),
    # Flips a private business repo public in one command.
    ("gh-repo-public",     re.compile(r"\bgh\s+repo\s+edit\b[^|;&\n]*--visibility[=\s]+public\b", re.IGNORECASE)),
    ("gh-destructive-delete", re.compile(r"\bgh\s+(?:repo|release|secret|ssh-key|gpg-key)\s+delete\b", re.IGNORECASE)),
    ("gh-api-delete",      re.compile(r"\bgh\s+api\b[^|;&\n]*(?:-X|--method)[=\s]+DELETE\b", re.IGNORECASE)),
    # ── Remote-history destruction (V7.5.0). We already block force-push to
    #    main, but remote BRANCH deletion was wide open.
    #    `--dry-run` is exempted: git guarantees no mutation, and blocking the
    #    preview of a delete pushes operators toward doing it unpreviewed.
    ("git-push-delete-remote", re.compile(r"\bgit\s+push\b(?![^|;&\n]*--dry-run\b)[^|;&\n]*\s(?:--delete|-d)(?:\s|$)")),
    # `git push origin :branch` — the delete refspec. The leading \s means
    # `git push origin main:main` (a normal push) does NOT match.
    ("git-push-delete-refspec", re.compile(r"\bgit\s+push\b(?![^|;&\n]*--dry-run\b)[^|;&\n]*\s:[A-Za-z0-9._/-]+")),
    # ── Reflog destruction (V7.5.0). This matters BECAUSE of git-reset-hard-ref
    #    above: we hard-block `git reset --hard <ref>` but still allow the
    #    bare-HEAD form, and that allowance is only safe while the reflog
    #    exists to recover from it. Expiring the reflog turns every operation
    #    we currently permit into an unrecoverable one.
    ("git-reflog-expire-now", re.compile(r"\bgit\s+reflog\s+expire\b[^|;&\n]*--expire(?:-unreachable)?[=\s]+now\b")),
    ("git-gc-prune-now",   re.compile(r"\bgit\s+gc\b[^|;&\n]*--prune[=\s]+(?:now|all)\b")),
    # ── Disk destroyers (V7.5.0). VPS-relevant; inert on Windows paths.
    ("mkfs-format",        re.compile(r"\bmkfs(?:\.[A-Za-z0-9]+)?(?:\s|$)")),
    # Broader than dd-disk-overwrite above, which only fires when the SOURCE is
    # /dev/{zero,random,urandom}. `dd if=backup.img of=/dev/sda` was allowed.
    ("dd-to-device",       re.compile(r"\bdd\s[^|;&\n]*\bof=[\"']?/dev/")),
    ("redirect-raw-disk",  re.compile(r">\s*/dev/(?:r?disk|sd[a-z]|nvme)")),
    # `chmod 777 ./script.sh` and `chmod -R 755 dist` stay allowed — the `/`
    # must be the whole target. Codex audit 2026-08-03: the original `\s777\s`
    # missed `chmod 0777 /` and `chmod a+rwx /`; `-R` missed `--recursive` and
    # combined short flags (`-hR`). Both confirmed live before this widening.
    ("chmod-777-root",     re.compile(r"\bchmod\b[^|;&\n]*\s(?:0*777|[aou]*\+rwx|a\+w)\s+[\"']?/[\"']?(?:\s|$|[;&|])")),
    ("chown-recurse-root", re.compile(r"\bchown\b[^|;&\n]*\s(?:-[a-zA-Z]*R[a-zA-Z]*|--recursive)\b[^|;&\n]*\s/[\"']?(?:\s|$|[;&|])")),
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


# ── Canonicalization, added V7.5.4 after a Codex adversarial audit (2026-08-03).
#
# Every HARD_BLOCK is a regex over the raw command string, which made two whole
# classes of defect possible. Both were confirmed live before this fix:
#
#   BYPASS — the patterns anchor on `git push` / `gh repo` adjacency, but real
#   CLIs accept global options before the subcommand. `git -c foo=bar push
#   --force origin main` evaluated to ALLOW. This was NOT limited to the new
#   V7.5.0 rules: the pre-existing git-force-main and git-clean-fdx blocks were
#   bypassable the same way and had been since they were written.
#
#   FALSE POSITIVE — dangerous text quoted as DATA matched as if it were a
#   command. `echo 'gh auth token' >> notes.md` was blocked. This is not
#   theoretical: writing this feature tripped the guard twice on its own
#   documentation. An guard that interrupts writing docs about the guard is one
#   an operator switches off, and then nothing is protected.

# Commands whose quoted arguments are DATA, never code. Deliberately a short
# allowlist rather than "everything except interpreters" — masking defaults to
# OFF so an unknown command fails closed. `bash -c "rm -rf /"` must never be
# masked, and it isn't, because bash is simply not on this list.
_INERT_ARG_COMMANDS = frozenset({
    "echo", "printf", "cat", "jq", "grep", "rg", "egrep", "fgrep",
    "diff", "comm", "wc", "head", "tail", "sort", "uniq", "tee",
})
_INERT_ARG_SUBCOMMANDS = (
    re.compile(r"^\s*git\s+(?:commit|tag|notes)\b"),   # -m "rm -rf mention"
    re.compile(r"^\s*gh\s+(?:pr|issue|release)\s+(?:create|edit|comment)\b"),
)

_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_SEGMENT_SPLIT_RE = re.compile(r"(&&|\|\||;|\||`|\$\()")

# Leading wrappers that change nothing about what the command DOES.
_WRAPPER_RE = re.compile(
    r"(^|[;&|`(]\s*)"
    r"(?:sudo(?:\s+-[a-zA-Z]+)*|command|nice(?:\s+-n\s*-?\d+)?|time|"
    r"env(?:\s+[A-Za-z_][A-Za-z0-9_]*=[^\s;&|]*)*)\s+"
)
# Global options accepted BETWEEN the binary and its subcommand.
_GIT_GLOBAL_RE = re.compile(
    r"\bgit\s+(?:(?:-c\s+\S+|-C\s+\S+|--git-dir(?:=|\s+)\S+|--work-tree(?:=|\s+)\S+|"
    r"--namespace(?:=|\s+)\S+|--no-pager|--no-replace-objects|--bare|-P)\s+)+"
)
_GH_GLOBAL_RE = re.compile(
    r"\bgh\s+(?:(?:(?:-R|--repo)(?:=|\s+)\S+|--hostname(?:=|\s+)\S+)\s+)+"
)


def _strip_wrappers(cmd: str) -> str:
    """Remove sudo/env/nice prefixes and git/gh global options.

    Applied repeatedly — `sudo env FOO=1 git -c a=b -C /repo push --force main`
    peels one layer per pass.
    """
    prev = None
    out = cmd
    for _ in range(6):                       # bounded; 6 exceeds any real nesting
        if out == prev:
            break
        prev = out
        out = _WRAPPER_RE.sub(r"\1", out)
        out = _GIT_GLOBAL_RE.sub("git ", out)
        out = _GH_GLOBAL_RE.sub("gh ", out)
    return out


def _mask_data_arguments(cmd: str) -> str:
    """Blank the quoted arguments of commands that only ever treat them as text.

    Per chain segment, so `echo hi && bash -c "rm -rf /"` masks the echo half
    and leaves the bash half fully intact.
    """
    parts = _SEGMENT_SPLIT_RE.split(cmd)
    out = []
    for part in parts:
        if _SEGMENT_SPLIT_RE.fullmatch(part):
            out.append(part)
            continue
        head = part.strip().split(" ", 1)[0].rsplit("/", 1)[-1].lower()
        inert = head in _INERT_ARG_COMMANDS or any(
            p.search(part) for p in _INERT_ARG_SUBCOMMANDS
        )
        out.append(_QUOTED_RE.sub("''", part) if inert else part)
    return "".join(out)


def _canonical(cmd: str) -> str:
    """The form hard blocks are matched against."""
    return _mask_data_arguments(_strip_wrappers(cmd))


def _check_hard_blocks(cmd: str) -> tuple[str, str] | None:
    # Matched against the canonical form so wrapper/global-option spellings
    # cannot evade a rule. The SQL-AST and irreversible layers deliberately
    # still see the RAW command — _check_sql_ast extracts SQL from inside
    # quotes, which masking would destroy.
    canon = _canonical(cmd)
    for name, pat in HARD_BLOCKS:
        if pat.search(canon):
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
    # Wrapper-stripped so `sudo git status` / `git -c a=b status` take the same
    # fast path as `git status`. Chains are already rejected above, so this
    # cannot be used to smuggle a second command.
    tokens = _strip_wrappers(cmd).strip().split()
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
