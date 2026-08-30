#!/usr/bin/env python3
"""machine_parity.py — bring any machine to full agentic parity, reproducibly.

The problem this solves
-----------------------
A `git pull` syncs *files* (skills/, scripts/, brain/, entry points). It does
NOT sync what actually makes this agent agentic: the Claude Code **hooks**
(memory injection, secret/exec guards, anti-pattern check, post-edit index,
SessionStart state load, pre-compact soul, sub-agent validator, Stop review).
Those live in `.claude/settings.local.json`, which is gitignored AND machine-
specific (interpreter + absolute repo path differ per OS). So a fresh clone is
a "dumb" Claude Code: the files are there, the loop is not.

This tool makes the hook set version-controlled and OS-portable, and self-checks
the rest of the substrate (deps, Codex, plugins, global config, .env.agents):

  python3 scripts/machine_parity.py --export-template
      (run on the SOURCE machine) capture the live hooks into the committed,
      portable template `.claude/settings.hooks.template.json`.

  python3 scripts/machine_parity.py --fix
      (run on a NEW machine) render the template for THIS OS, install the hooks
      into `.claude/settings.local.json`, self-test each hook, then check +
      auto-heal deps and report anything that needs a manual step.

  python3 scripts/machine_parity.py --check [--quiet] [--json]
      read-only parity report. `--quiet` prints ONE line only if NOT at parity
      (used by the SessionStart hook so drift self-announces every boot).

Design rules
------------
* STDLIB ONLY. This must run on a cold machine *before* `pip install`.
* NEVER print a secret value. The .env.agents audit emits KEY NAMES only.
* Idempotent. `--fix` can be run repeatedly; it overwrites only the hooks block
  and preserves any other local settings (permissions, etc.).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"
# Hide the console window when spawning subprocesses on Windows.
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

PLACEHOLDER_PY = "{{PY}}"
PLACEHOLDER_ROOT = "$CLAUDE_PROJECT_DIR"

# Critical pip packages the hook scripts + CLI tools rely on (probe a few).
CRITICAL_PYTHON_IMPORTS = ["anthropic", "supabase", "requests"]
# System binaries the agent loop / daemons assume.
SYSTEM_BINS = ["git", "node", "npm", "python3" if not IS_WINDOWS else "python"]
OPTIONAL_BINS = ["ffmpeg", "gh", "pm2", "caffeinate"]


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def find_repo_root() -> Path:
    """Walk up from this file until we find the repo root (has scripts/ + .claude/)."""
    p = Path(__file__).resolve()
    for cand in [p.parent, *p.parents]:
        if (cand / "scripts").is_dir() and (cand / ".claude").is_dir():
            return cand
    # Fallback: parent of scripts/
    return Path(__file__).resolve().parent.parent


REPO_ROOT = find_repo_root()
LOCAL_PATH = REPO_ROOT / ".claude" / "settings.local.json"
TEMPLATE_PATH = REPO_ROOT / ".claude" / "settings.hooks.template.json"


def _root_as_posix() -> str:
    """Repo root with forward slashes (matches the existing Windows config style)."""
    return REPO_ROOT.as_posix()


# --------------------------------------------------------------------------- #
# Command portablize / render
# --------------------------------------------------------------------------- #
_INTERP_RE = re.compile(r"^(pythonw|python3|python|py)(\.exe)?$", re.IGNORECASE)


def _split(cmd: str) -> list[str]:
    """Parse a hook command into tokens, honoring quotes (posix rules even on Windows,
    since all our paths use forward slashes — no backslash escapes to mangle)."""
    try:
        return shlex.split(cmd, posix=True)
    except ValueError:
        return cmd.split()


def _shquote(tok: str) -> str:
    """Double-quote a path token so spaces in it survive the shell. Bare PATH names
    (no separators, e.g. `pythonw`) and plain args (e.g. `--quiet`) are left as-is."""
    if ("/" in tok or "\\" in tok) and not (tok.startswith('"') and tok.endswith('"')):
        return f'"{tok}"'
    return tok


def portablize_command(cmd: str) -> str:
    """Turn an absolute machine-specific hook command into the portable template form.

    'pythonw C:/Users/User/Business-Empire-Agent/scripts/x.py --quiet'
        -> '{{PY}} $CLAUDE_PROJECT_DIR/scripts/x.py --quiet'
    """
    parts = _split(cmd.strip())
    if not parts:
        return cmd
    out = []
    for i, tok in enumerate(parts):
        norm = tok.replace("\\", "/")
        if i == 0 and _INTERP_RE.match(Path(norm).name):
            out.append(PLACEHOLDER_PY)
            continue
        # Rewrite any path that points inside the repo to a $CLAUDE_PROJECT_DIR-relative one.
        idx = norm.lower().find("/scripts/")
        if idx != -1:
            out.append(f"{PLACEHOLDER_ROOT}/{norm[idx + 1:]}")  # 'scripts/...'
        else:
            out.append(tok)
    return " ".join(out)


def render_command(cmd_template: str, interpreter: str, root: str) -> str:
    """Materialize a portable template command for THIS machine, quoting paths so
    spaces (e.g. macOS `~/iCloud Drive/...`) don't get split by the shell."""
    out = []
    for tok in _split(cmd_template):
        if tok == PLACEHOLDER_PY:
            out.append(_shquote(interpreter))
        elif tok.startswith(PLACEHOLDER_ROOT):
            out.append(_shquote(tok.replace(PLACEHOLDER_ROOT, root)))
        else:
            out.append(tok)
    return " ".join(out)


def venv_python(root: str, windowless: bool = False) -> Path | None:
    """Path to the repo venv interpreter for this OS, or None if no venv exists.

    windowless=True picks pythonw on Windows (console-less, for hook commands);
    False picks python (for capturing subprocess output, e.g. the hook self-test).
    """
    if IS_WINDOWS:
        cand = Path(root) / ".venv" / "Scripts" / ("pythonw.exe" if windowless else "python.exe")
    else:
        cand = Path(root) / ".venv" / "bin" / "python3"
    return cand if cand.exists() else None


def detect_interpreter(root: str) -> str:
    """Pick the interpreter for rendered hook commands on this OS.

    Prefer the repo venv (so hook scripts see installed deps); fall back to a
    PATH interpreter. On Windows use pythonw to avoid console flashes.
    """
    v = venv_python(root, windowless=True)
    if v:
        return v.as_posix()
    return "pythonw" if IS_WINDOWS else "python3"


def _portablize_hooks_block(hooks: dict) -> dict:
    out = json.loads(json.dumps(hooks))  # deep copy
    for _event, matchers in out.items():
        for matcher in matchers:
            for hk in matcher.get("hooks", []):
                if hk.get("type") == "command" and "command" in hk:
                    hk["command"] = portablize_command(hk["command"])
    return out


def _render_hooks_block(hooks_template: dict, interpreter: str, root: str) -> dict:
    out = json.loads(json.dumps(hooks_template))
    for _event, matchers in out.items():
        for matcher in matchers:
            for hk in matcher.get("hooks", []):
                if hk.get("type") == "command" and "command" in hk:
                    hk["command"] = render_command(hk["command"], interpreter, root)
    return out


def _count_commands(hooks: dict) -> int:
    return sum(
        1
        for matchers in hooks.values()
        for matcher in matchers
        for hk in matcher.get("hooks", [])
        if hk.get("type") == "command"
    )


def _iter_commands(hooks: dict):
    for event, matchers in hooks.items():
        for matcher in matchers:
            for hk in matcher.get("hooks", []):
                if hk.get("type") == "command" and "command" in hk:
                    yield event, hk["command"]


def _normalize_script(tok: str) -> str:
    """Repo-relative script path from a (possibly absolute or placeholder) token."""
    t = tok.replace("\\", "/")
    idx = t.lower().find("/scripts/")
    if idx != -1:
        return t[idx + 1:]
    if t.startswith(PLACEHOLDER_ROOT + "/"):
        return t[len(PLACEHOLDER_ROOT) + 1:]
    return t


def _hook_script_set(hooks: dict) -> set:
    """Interpreter- and root-agnostic signature of the hook wiring:
    {(event, matcher, repo_relative_script, args_tuple)}. This is what must match
    between template and local — it catches a missing / changed / extra guard
    regardless of which python runs it or where the repo lives (a same-count check
    would miss an omitted secret_guard; this does not)."""
    sig = set()
    for event, matchers in hooks.items():
        for m in matchers:
            matcher = m.get("matcher", "")
            for hk in m.get("hooks", []):
                if hk.get("type") != "command" or "command" not in hk:
                    continue
                toks = _split(hk["command"])
                sidx = next((i for i, t in enumerate(toks) if t.endswith(".py")), None)
                script = _normalize_script(toks[sidx]) if sidx is not None else ""
                args = tuple(toks[sidx + 1:]) if sidx is not None else ()
                sig.add((event, matcher, script, args))
    return sig


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
def export_template() -> int:
    if not LOCAL_PATH.exists():
        print(f"[export] ERROR: {LOCAL_PATH} not found — run on the source machine with hooks installed.")
        return 2
    local = json.loads(LOCAL_PATH.read_text(encoding="utf-8"))
    hooks = local.get("hooks")
    if not hooks:
        print("[export] ERROR: no 'hooks' block in settings.local.json.")
        return 2
    template = {
        "_comment": "PORTABLE hook template — version-controlled source of truth. "
        "Rendered per-machine by scripts/machine_parity.py --fix. "
        "{{PY}} = OS interpreter, $CLAUDE_PROJECT_DIR = repo root. DO NOT hand-edit paths.",
        "enableAllProjectMcpServers": local.get("enableAllProjectMcpServers", True),
        "enabledMcpjsonServers": local.get("enabledMcpjsonServers", []),
        "hooks": _portablize_hooks_block(hooks),
    }
    TEMPLATE_PATH.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    n = _count_commands(template["hooks"])
    print(f"[export] wrote {TEMPLATE_PATH.relative_to(REPO_ROOT)} — {n} hook commands captured.")
    return 0


def install_hooks() -> tuple[bool, str]:
    """Render the template into settings.local.json for this machine. Idempotent."""
    if not TEMPLATE_PATH.exists():
        return False, f"template missing ({TEMPLATE_PATH.name}) — run --export-template on the source machine + pull"
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    interpreter = detect_interpreter(_root_as_posix())
    rendered_hooks = _render_hooks_block(template.get("hooks", {}), interpreter, _root_as_posix())

    local = {}
    if LOCAL_PATH.exists():
        try:
            local = json.loads(LOCAL_PATH.read_text(encoding="utf-8"))
        except Exception:
            # Never silently discard a user's local settings (permissions, etc.).
            try:
                backup = LOCAL_PATH.with_suffix(".json.corrupt.bak")
                backup.write_text(LOCAL_PATH.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                print(f"[fix] WARNING: {LOCAL_PATH.name} was unparseable -> backed up to {backup.name} before rewrite")
            except Exception:
                pass
            local = {}
    # Overlay agentic config; preserve any other local keys (permissions, etc.).
    local["hooks"] = rendered_hooks
    if "enableAllProjectMcpServers" in template:
        local["enableAllProjectMcpServers"] = template["enableAllProjectMcpServers"]
    if template.get("enabledMcpjsonServers"):
        local["enabledMcpjsonServers"] = template["enabledMcpjsonServers"]

    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_PATH.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")
    n = _count_commands(rendered_hooks)
    return True, f"installed {n} hooks (interpreter: {interpreter})"


def self_test_hooks() -> list[tuple[str, bool, str]]:
    """Run each hook script once with benign stdin; flag import/crash failures.

    Catches the Windows-only-import class of bug (e.g. CREATE_NO_WINDOW) that
    would silently break the loop on macOS. We care about crashes, not the
    allow/deny exit code, so we inspect stderr for tracebacks.
    """
    results: list[tuple[str, bool, str]] = []
    if not LOCAL_PATH.exists():
        return results
    local = json.loads(LOCAL_PATH.read_text(encoding="utf-8"))
    # Test with the venv interpreter (where deps live), matching what the hooks use.
    _v = venv_python(_root_as_posix())
    runner = str(_v) if _v else sys.executable
    seen: set[str] = set()
    for event, cmd in _iter_commands(local.get("hooks", {})):
        toks = _split(cmd)
        script = next((t for t in toks if t.endswith(".py")), None)
        if not script:
            continue
        spath = Path(script)
        name = spath.name
        # Same shell-safety gate as check_hooks: an unquoted spaced path splits into
        # a relative fragment, so the stored command would break in the shell.
        if not spath.is_absolute():
            if script in seen:
                continue
            seen.add(script)
            results.append((f"{event}:{name}", False, "unsafe/relative path (unquoted spaces?)"))
            continue
        key = str(spath)
        if key in seen:
            continue
        seen.add(key)
        if not spath.exists():  # a missing script is a FAILURE, not a silent pass
            results.append((f"{event}:{name}", False, "script not found"))
            continue
        try:
            proc = subprocess.run(
                [runner, str(spath)], input="{}", capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, creationflags=_NO_WINDOW,
            )
            err = proc.stderr or ""
            bad = ("Traceback (most recent call last)", "ImportError", "ModuleNotFoundError",
                   "can't open file", "No such file", "[Errno 2]")
            if any(b in err for b in bad):
                last = err.strip().splitlines()[-1] if err.strip() else "error"
                results.append((f"{event}:{name}", False, last[:140]))
            else:
                results.append((f"{event}:{name}", True, "runs"))
        except subprocess.TimeoutExpired:
            results.append((f"{event}:{name}", False, "timeout (>30s)"))
        except Exception as exc:  # noqa: BLE001
            results.append((f"{event}:{name}", False, str(exc)[:140]))
    return results


# --------------------------------------------------------------------------- #
# Checks (read-only). Each returns (name, ok, detail, fix_hint)
# --------------------------------------------------------------------------- #
def _which(name: str) -> str | None:
    return shutil.which(name)


def check_hooks() -> tuple[str, bool, str, str]:
    if not TEMPLATE_PATH.exists():
        return ("hooks", False, "no committed template", "git pull, then --export-template on source")
    if not LOCAL_PATH.exists():
        return ("hooks", False, "settings.local.json missing -> ZERO hooks active", "run --fix")
    local = json.loads(LOCAL_PATH.read_text(encoding="utf-8"))
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    # Deep compare the wiring (event, matcher, script, args) — not just the count.
    expected = _hook_script_set(template.get("hooks", {}))
    actual = _hook_script_set(local.get("hooks", {}))
    missing, extra = expected - actual, actual - expected
    if missing or extra:
        bits = []
        if missing:
            ev, _mt, sc, _a = sorted(missing)[0]
            bits.append(f"{len(missing)} missing/changed (e.g. {ev}:{Path(sc).name})")
        if extra:
            bits.append(f"{len(extra)} unexpected")
        return ("hooks", False, f"{len(expected & actual)}/{len(expected)} hooks match template; " + ", ".join(bits), "run --fix")
    # Wiring matches; confirm each local command is shell-safe + resolvable on THIS machine.
    for _ev, cmd in _iter_commands(local.get("hooks", {})):
        toks = _split(cmd)
        if not toks:
            continue
        interp, interp_name = toks[0], Path(toks[0].replace("\\", "/")).name
        if "/" in interp or "\\" in interp:
            if not Path(interp).exists():
                return ("hooks", False, f"interpreter missing: {interp_name}", "run --fix")
        elif not _which(interp_name):
            return ("hooks", False, f"interpreter not on PATH: {interp_name}", "run --fix")
        sidx = next((i for i, t in enumerate(toks) if t.endswith(".py")), None)
        if sidx is None:
            return ("hooks", False, "hook command has no script token", "run --fix")
        sp = Path(toks[sidx])
        # Validate the STORED command is shell-safe, not just reconstructable. A
        # properly-quoted absolute path shlex-splits to ONE absolute token; an
        # unquoted path with spaces (e.g. macOS "iCloud Drive") splits into a
        # relative fragment here, so the command breaks in the shell and the guard
        # goes inactive. Reject anything that isn't a real absolute file.
        if not sp.is_absolute():
            return ("hooks", False, f"unsafe hook path (unquoted spaces?): ...{toks[sidx][-40:]}", "run --fix")
        if not sp.exists():
            return ("hooks", False, f"hook script not found: {sp.name}", "run --fix")
    return ("hooks", True, f"{len(expected)} hooks match template (scripts+matchers), shell-safe", "")


def check_python_deps() -> tuple[str, bool, str, str]:
    # Use the non-windowless venv python (reliable output capture); fall back to PATH.
    v = venv_python(_root_as_posix())
    interp = str(v) if v else (_which("python3") or _which("python"))
    if not interp:
        return ("python-deps", False, "no venv / python interpreter", "python3 -m venv .venv && pip install -r requirements.txt")
    venv_exists = v is not None
    probe = "import " + ", ".join(CRITICAL_PYTHON_IMPORTS)
    try:
        proc = subprocess.run(
            [interp, "-c", probe],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=_NO_WINDOW,
        )
        if proc.returncode == 0:
            return ("python-deps", True, f"venv {'present' if venv_exists else 'system'}, core imports OK", "")
        missing = (proc.stderr or "").strip().splitlines()[-1:] or ["import error"]
        return ("python-deps", False, missing[0][:80], "source .venv/bin/activate && pip install -r requirements.txt")
    except Exception as exc:  # noqa: BLE001
        return ("python-deps", False, str(exc)[:80], "pip install -r requirements.txt")


def check_node_deps() -> tuple[str, bool, str, str]:
    if not _which("node"):
        return ("node", False, "node not installed", "brew install node@20")
    if not (REPO_ROOT / "node_modules").exists():
        return ("node", False, "node_modules missing", "npm install")
    return ("node", True, "node + node_modules present", "")


def check_system_bins() -> tuple[str, bool, str, str]:
    missing = [b for b in SYSTEM_BINS if not _which(b)]
    opt_missing = [b for b in OPTIONAL_BINS if not _which(b)]
    if missing:
        return ("system-bins", False, f"missing required: {', '.join(missing)}", "brew install " + " ".join(missing))
    detail = "all required present"
    if opt_missing:
        detail += f" (optional missing: {', '.join(opt_missing)})"
    return ("system-bins", True, detail, "")


def check_codex() -> tuple[str, bool, str, str]:
    home = Path.home()
    companion = home / ".claude" / "codex-plugin" / "scripts" / "codex-companion.mjs"
    if not companion.exists():
        return ("codex", False, "codex-plugin not installed at ~/.claude/codex-plugin", "install the codex-plugin on this machine")
    if not _which("node"):
        return ("codex", False, "node missing (needed to run codex-companion)", "brew install node@20")
    try:
        proc = subprocess.run(
            ["node", str(companion), "status"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=45, creationflags=_NO_WINDOW,
        )
        if proc.returncode == 0:
            return ("codex", True, "codex-companion responds (verify OpenAI auth if reviews fail)", "")
        return ("codex", False, "codex present but status returned non-zero / unauthed", "run: node ~/.claude/codex-plugin/scripts/codex-companion.mjs status")
    except Exception as exc:  # noqa: BLE001
        return ("codex", False, f"status failed: {str(exc)[:60]}", "verify OpenAI auth for Codex")


def check_global_claude_md() -> tuple[str, bool, str, str]:
    g = Path.home() / ".claude" / "CLAUDE.md"
    if not g.exists():
        return ("global-CLAUDE.md", False, "~/.claude/CLAUDE.md missing", "cp docs/deploy/global-CLAUDE.md ~/.claude/CLAUDE.md")
    return ("global-CLAUDE.md", True, "present", "")


def check_plugins() -> tuple[str, bool, str, str]:
    manifest = REPO_ROOT / "docs" / "deploy" / "CAPABILITY_MANIFEST.md"
    plugins_dir = Path.home() / ".claude" / "plugins"
    if not plugins_dir.exists():
        return ("plugins", False, "~/.claude/plugins missing", "install marketplace plugins (see CAPABILITY_MANIFEST.md)")
    note = "present" if not manifest.exists() else "present (compare to CAPABILITY_MANIFEST.md)"
    return ("plugins", True, f"~/.claude/plugins {note}", "")


_ENV_GET_RE = re.compile(r"""(?:os\.environ|env|env_vars|_env)\.get\(["']([A-Z][A-Z0-9_]*)["']""")
_ENV_IDX_RE = re.compile(r"""(?:os\.environ|env|env_vars|_env)\[["']([A-Z][A-Z0-9_]*)["']\]""")
_ENV_NOISE = {
    "PATH", "HOME", "USER", "USERNAME", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "COMSPEC",
    "PYTHONPATH", "PYTHONUNBUFFERED", "WINDIR", "SYSTEMROOT", "CLAUDE_PLUGIN_ROOT", "NO_COLOR",
    "TERM", "OSTYPE", "PWD", "SHLVL", "LANG", "LC_ALL", "LOGNAME", "SHELL", "PROGRAMFILES",
    "PROGRAMDATA", "EDITOR", "USERPROFILE", "CLAUDE_PROJECT_DIR", "EMPIRE_V6_MODE",
}


# Required CORE credentials (OR-groups: at least one of each group must be set).
# Everything else a script references is optional / has a fallback / is cross-repo,
# so we report that as an ADVISORY count, never a hard parity failure.
REQUIRED_ENV_GROUPS = [
    ("ANTHROPIC_API_KEY", "BRAVO_ANTHROPIC_API_KEY", "CLAUDE_API_KEY"),
    ("TURSO_DATABASE_URL", "BRAVO_SUPABASE_URL", "SUPABASE_URL"),
    ("TURSO_AUTH_TOKEN", "BRAVO_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE_KEY"),
    ("TELEGRAM_BOT_TOKEN",),
]


def check_env_agents() -> tuple[str, bool, str, str]:
    """Audit .env.agents by KEY NAME only — never reads or prints values.

    Hard-fails only if .env.agents is absent or a required CORE credential group
    is entirely unset. The broad 'referenced in code' delta is noisy (fallbacks,
    optional keys, cross-repo) so it is surfaced as advisory only.
    """
    env_path = REPO_ROOT / ".env.agents"
    if not env_path.exists():
        return ("env.agents", False, ".env.agents missing", "create .env.agents on this machine (CC updates manually)")
    have: set[str] = set()
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            have.add(line.split("=", 1)[0].strip())
    missing_core = [g for g in REQUIRED_ENV_GROUPS if not any(k in have for k in g)]
    # Advisory: how many code-referenced keys are absent (informational, not a gate).
    referenced: set[str] = set()
    for p in (REPO_ROOT / "scripts").rglob("*.py"):
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        referenced.update(_ENV_GET_RE.findall(t))
        referenced.update(_ENV_IDX_RE.findall(t))
    advisory = len((referenced - _ENV_NOISE) - have)
    if missing_core:
        names = ", ".join(g[0] for g in missing_core)
        return ("env.agents", False, f"missing required core: {names}", "set the core credentials in .env.agents")
    detail = f"{len(have)} keys, core creds present"
    if advisory:
        detail += f"; {advisory} optional/fallback code-refs unset (advisory - run setup_wizard.py to audit)"
    return ("env.agents", True, detail, "")


#: The exact shape AVG exports — a kernel device handle, not a file path.
_POISONED_KEYLOG = r"\\.\avgMonFltProxy\DEADBEEFCAFE0000"


def check_tls_keylog() -> tuple[str, bool, str, str]:
    """Prove a poisoned SSLKEYLOGFILE cannot kill a daemon spawned on this rig.

    The 2026-07-29 outage: AVG exports SSLKEYLOGFILE=\\\\.\\avgMonFltProxy\\<handle>
    into process environments. CPython's ssl.create_default_context() opens that
    path, and once the handle goes stale it raises PermissionError from inside
    SSL context construction — killing every HTTPS client at build time. PM2
    froze one such handle into bravo-scheduler and 31 of 145 inbox sweeps died
    over 25h, silently, because notify.py died the same way.

    WHY THIS NO LONGER ASKS PM2 (2026-08-29)
    ----------------------------------------
    The second half of this check used to read `pm2 jlist` for apps carrying the
    variable, because a PM2 daemon froze the handle that was live when IT started
    into every child forever. PM2 is not the supervisor here any more:
    scripts/ops/fleet_watchdog.py replaced it (e7d0a50f), never invokes pm2, and
    both "PM2 Resurrect" tasks were disabled (0e88aa21) — so pm2's daemon is
    deliberately not running, and the guard that (correctly) refuses to invoke
    pm2 without one meant this check could only ever return "no pm2 daemon is
    running". Permanently red, for a dependency retired on purpose.

    It cannot simply be re-pointed at the new daemons: Windows does not expose
    another process's environment block, so there is nothing to audit. What CAN
    be proved is what the audit was a proxy for — that a poisoned value INHERITED
    ACROSS A SPAWN does not break the child. fleet_watchdog.start() launches
    every daemon with subprocess.Popen and no `env=`, so a child inherits this
    environment verbatim; the probe below reproduces that exact path with the
    poison in place, in a fresh interpreter, which is strictly more than the old
    in-process assertion proved.

    Still deliberately NOT asserted: the mere presence of an ambient
    SSLKEYLOGFILE. AVG re-exports a fresh handle into every new process for as
    long as HTTPS scanning is on, the fleet survives it (that is what the probe
    proves), and a check that fails on it would be red forever and get ignored.
    It is reported in the detail line instead.
    """
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.tls_trust import tls_diagnostics
    except Exception as exc:  # noqa: BLE001
        return ("tls-keylog", False, f"lib/tls_trust unavailable: {exc}",
                "check scripts/lib/tls_trust.py exists and imports")

    v = venv_python(_root_as_posix())
    interp = str(v) if v else (_which("python3") or _which("python"))
    if not interp:
        return ("tls-keylog", False, "no python interpreter to spawn the guard probe with",
                "python3 -m venv .venv && pip install -r requirements.txt")

    # A CHILD process, not this one: the daemons are spawned, so the guard has to
    # hold across the spawn. It also keeps the probe from mutating the parity
    # run's own os.environ, which the previous version did.
    probe = (
        "import ssl, sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT / 'scripts')!r})\n"
        "from lib.tls_trust import ensure_os_trust\n"
        "ensure_os_trust()\n"
        "ssl.create_default_context()\n"
        "print('GUARD-OK')\n"
    )
    try:
        proc = subprocess.run(
            [interp, "-c", probe],
            env={**os.environ, "SSLKEYLOGFILE": _POISONED_KEYLOG},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, creationflags=_NO_WINDOW,
        )
    except Exception as exc:  # noqa: BLE001
        return ("tls-keylog", False, f"could not run the guard probe: {type(exc).__name__}: {exc}",
                "run: python scripts/lib/tls_trust.py or pytest scripts/tests/test_tls_trust.py")

    if proc.returncode != 0 or "GUARD-OK" not in (proc.stdout or ""):
        err = (proc.stderr or "").strip().splitlines()
        why = err[-1][:120] if err else f"exit {proc.returncode}, no output"
        return ("tls-keylog", False,
                f"a daemon inheriting a poisoned SSLKEYLOGFILE would die: {why}",
                "scripts/lib/tls_trust.py neutralize_keylog is broken (or "
                "EMPIRE_ALLOW_SSLKEYLOG=1 is disabling it) - "
                "run pytest scripts/tests/test_tls_trust.py")

    ambient = tls_diagnostics()
    if not ambient["keylog_present"]:
        state = "no ambient SSLKEYLOGFILE"
    elif ambient["keylog_usable"]:
        state = "ambient SSLKEYLOGFILE is a real writable path"
    else:
        state = "ambient SSLKEYLOGFILE is poisoned but neutralized at startup"
    return ("tls-keylog", True, f"spawned daemons survive a poisoned handle; {state}", "")


def _schtasks_query(name: str) -> tuple[str | None, str]:
    """Verbose schtasks record for one task: (output, error).

    Three outcomes, kept distinct on purpose: (record, "") = it exists,
    (None, "") = it genuinely does not exist, (None, reason) = we could not
    look. The previous version collapsed every failure into `out = ""` and then
    read that empty string as a definite answer about the task — the same
    "absent is not zero" conflation that has bitten this subsystem repeatedly.
    """
    try:
        proc = subprocess.run(
            ["schtasks", "/query", "/tn", name, "/fo", "LIST", "/v"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=_NO_WINDOW,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"schtasks failed for '{name}' ({type(exc).__name__}: {exc})"
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout, ""
    blob = f"{proc.stdout}{proc.stderr}".strip()
    if "cannot find" in blob.lower():
        return None, ""
    tail = blob.splitlines()[-1][:90] if blob else f"exit {proc.returncode}, no output"
    return None, f"schtasks errored on '{name}': {tail}"


def _task_field(record: str, field: str) -> set[str]:
    """Every value schtasks reports for `field` (once per trigger row).

    Empty set = the field was not in the output, which callers must treat as
    "unknown", never as "fine". Reading a task's TRIGGERS while never reading
    its state is exactly how a DISABLED task was reported as a working recovery
    path for a day.
    """
    # Sliced by prefix length, not split(":", 1): schtasks labels contain their
    # own colons ("Repeat: Every:"), so a first-colon split returns half the
    # label as the value.
    prefix = f"{field}:"
    return {ln.strip()[len(prefix):].strip() for ln in record.splitlines()
            if ln.strip().startswith(prefix)}


def _has_battery() -> bool:
    """Does this machine actually run on a battery?

    'No Start On Batteries' is the schtasks default and is inert on a desktop
    (this rig reports Win32_SystemEnclosure ChassisTypes = 3 and no Win32_Battery),
    so firing on it here would be permanent noise — and noise is how a real
    laptop finding gets ignored. BatteryFlag 128 means "no system battery";
    anything else, including 255/unknown, errs toward reporting.
    """
    if os.name != "nt":
        return False
    import ctypes  # noqa: PLC0415

    class _PowerStatus(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

    status = _PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return True  # cannot tell -> assume a battery so the check speaks up
    return status.BatteryFlag != 128


def check_fleet_persistence() -> tuple[str, bool, str, str]:
    """Is the fleet supervised, by exactly ONE supervisor, and actually up?

    Was `pm2-persistence` until 2026-08-29. PM2 is no longer the supervisor:
    scripts/ops/fleet_watchdog.py replaced it (e7d0a50f) and both "PM2 Resurrect"
    tasks were disabled (0e88aa21), because their S4U principal ran them in
    Windows Session 0 — where a supervisor cannot read a session-1 command line,
    concludes the whole fleet is absent, and starts a second invisible copy of
    every daemon. That is the mechanism behind four concurrent bravo-schedulers.

    The old check read the DISABLED "PM2 Resurrect" task and reported GREEN
    ("boot trigger + battery-safe"): it parsed the task's triggers and never
    once read its state, so it certified a recovery path that had been switched
    off on purpose. Its dump.pm2 freshness rule was days from being permanently
    red for the same reason — nothing rewrites dump.pm2 any more, because
    `pm2 save` needs the daemon that is blocked.

    What is asserted now, and why each still guards something real:
      * the watchdog task exists and is ENABLED — no supervisor, no recovery;
      * it runs 'Interactive only', never S4U/Session 0 — the 08-28 root cause;
      * it has a repeating trigger, so a daemon that dies comes back in minutes;
      * it will start on battery IF this machine has one;
      * the retired supervisor stays retired — neither PM2 Resurrect task is
        re-enabled, because two supervisors IS the incident;
      * the manifest is non-empty — an empty one supervises nothing, silently;
      * the fleet is up, per fleet_watchdog's own single definition of down.

    Deliberately NOT asserted: a boot trigger. Getting one means an S4U
    principal, which means Session 0, which is the failure above. Recovery from
    an unattended reboot is a known, accepted gap on this rig — named in the
    detail line rather than held permanently red.
    """
    if platform.system() != "Windows":
        return ("fleet-persistence", True,
                "not Windows - the scheduled-task supervisor is a Windows concern", "")

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        from ops import fleet_watchdog  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return ("fleet-persistence", False,
                f"cannot import ops.fleet_watchdog - there is no supervisor "
                f"({type(exc).__name__}: {exc})",
                "restore scripts/ops/fleet_watchdog.py, then: "
                "python scripts/ops/fleet_watchdog.py install-task")

    problems: list[str] = []
    task = fleet_watchdog.TASK_NAME
    record, err = _schtasks_query(task)
    interval = "?"
    if err:
        problems.append(err)
    elif record is None:
        problems.append(f"no '{task}' scheduled task - nothing restarts a dead daemon")
    else:
        states = _task_field(record, "Scheduled Task State")
        if not states:
            problems.append(f"could not read the state of '{task}' from schtasks")
        elif "Disabled" in states:
            problems.append(f"'{task}' is DISABLED - the fleet is unsupervised")
        # S4U/"Interactive/Background" is how a supervisor lands in Session 0.
        modes = _task_field(record, "Logon Mode")
        if not modes:
            problems.append(f"could not read the logon mode of '{task}'")
        elif modes != {"Interactive only"}:
            problems.append(f"'{task}' logon mode is {sorted(modes)} - an S4U/background "
                            "principal runs it in Session 0, where it cannot see the fleet "
                            "it supervises and starts a duplicate of every daemon")
        repeats = {r for r in _task_field(record, "Repeat: Every") if r and r != "N/A"}
        if not repeats:
            problems.append(f"'{task}' has no repeating trigger - a daemon that dies "
                            "between logons is never restarted")
        else:
            interval = sorted(repeats)[0]
        if _has_battery() and "No Start On Batteries" in record:
            problems.append(f"'{task}' will not start on battery")

    # The retired supervisor must stay retired. Two supervisors, neither able to
    # see the other's daemons, is the 2026-08-28 incident — not a hypothetical.
    for retired in ("PM2 Resurrect", "PM2 Resurrect on Login"):
        rec, rerr = _schtasks_query(retired)
        if rerr:
            problems.append(rerr)
        elif rec is not None:
            rstates = _task_field(rec, "Scheduled Task State")
            if not rstates:
                problems.append(f"could not read the state of '{retired}'")
            elif rstates != {"Disabled"}:
                problems.append(f"'{retired}' is ENABLED again ({sorted(rstates)}) - that is a "
                                "second supervisor, running S4U in Session 0")
    # A live pm2 DAEMON would be the other half of "two supervisors", and
    # _pm2_daemon_alive() looks like the detector for it. It is not usable as a
    # gate: see its docstring — `wmic process get Name,CommandLine` times out at
    # 45s on this machine, every time, and the timeout returns False. Wiring a
    # guard onto it would add 45 seconds per --check to always report "no second
    # supervisor". The two scheduled-task states above cover the path that
    # actually persists across a reboot, cheaply and fail-closed.

    # LIVENESS, not just configuration. On 2026-08-28 this check reported GREEN
    # while coordination_agent.js had been crash-looping for two days and four
    # daemons — the scheduler among them, so no cron ran — were down. A green
    # light on a dead fleet is worse than no light: it is why nobody looked.
    #
    # Answered by fleet_watchdog's ONE definition (status + down_names), never a
    # private copy. The copy that used to live here re-derived "down" by hand and
    # would have diverged the moment classify() gained a state — the sixth such
    # duplication in this subsystem, after two claim mechanisms, two coverage
    # implementations, two ownership maps and two identity lists.
    fleet = ""
    try:
        rows = fleet_watchdog.status()
        if not rows:
            problems.append(f"fleet manifest is EMPTY ({fleet_watchdog.DUMP}) - the watchdog "
                            "is supervising nothing")
        else:
            down = fleet_watchdog.down_names(rows)
            if down:
                problems.append(f"{len(down)}/{len(rows)} managed process(es) NOT RUNNING: "
                                + ", ".join(down[:6]))
            # Counted by classify(), so "6/8 up" can never again read as "2 are
            # down" when the other two are an operator stop and a broken
            # manifest entry — two things nobody should be paged about.
            tally = {state: sum(1 for r in rows if fleet_watchdog.classify(r) == state)
                     for state in ("running", "disabled", "unrunnable")}
            fleet = ", ".join(f"{n} {state}" for state, n in tally.items() if n)
    except Exception as e:  # noqa: BLE001
        problems.append(f"could not verify fleet liveness via fleet_watchdog "
                        f"({type(e).__name__}: {e})")

    if problems:
        return ("fleet-persistence", False, "; ".join(problems),
                "python scripts/ops/fleet_watchdog.py status  (then `up`, or `install-task` if "
                "the task is missing) — do NOT run `pm2`, each call against the blocked pipe "
                "leaks another orphan daemon")
    return ("fleet-persistence", True,
            f"'{task}' enabled, interactive, repeats every {interval}; {fleet}; "
            "no boot trigger by design (S4U would run it in Session 0)", "")


def _pm2_daemon_alive() -> bool:
    """Is a pm2 daemon process actually running?

    Answered from the process table, never by invoking pm2 — invoking pm2 when
    no daemon is reachable spawns one, and if the pipe is blocked that spawn
    leaks. This predicate exists so the health checks can ask "is pm2 usable?"
    without making the answer worse.

    NOT USABLE AS A GATE ON THIS MACHINE (measured 2026-08-29). Its only source,
    `wmic process get Name,CommandLine`, hits the 45s timeout on every one of
    three consecutive runs, and the timeout lands in the except below, which
    returns False. So it costs 45 seconds to always answer "no daemon" — a
    fail-OPEN answer. It is retained because it is the pm2-CLI safety interlock
    the parity checks are pinned against, not because it currently discriminates.
    Anything that needs a trustworthy process table must use
    fleet_watchdog._process_table(): CIM first, self-verified against its own
    PID, and None (not "") when it cannot see.
    """
    try:
        out = subprocess.run(["wmic", "process", "get", "Name,CommandLine"],
                             capture_output=True, text=True, timeout=45,
                             errors="ignore", creationflags=_NO_WINDOW).stdout.lower()
    except Exception:  # noqa: BLE001
        return False

    # Match PER LINE, and require the line to be a node process.
    #
    # A whole-blob substring search reports a false positive against its OWN
    # CALLER: any shell command that merely MENTIONS the daemon path — a grep, a
    # Get-Process filter, this very diagnostic — appears in the process table and
    # matches. That is exactly what happened: this returned True with zero
    # daemons running, so the guard fell through, pm2 was invoked, and it leaked
    # the daemon the guard existed to prevent. A detector that matches the string
    # in its own invocation is measuring itself.
    for line in out.splitlines():
        if "node" not in line:
            continue
        if r"pm2\lib\daemon.js" in line or "pm2/lib/daemon.js" in line:
            # Exclude lines that are a *query about* the daemon rather than the
            # daemon itself (wmic/grep/powershell filters quoting the path).
            if any(tool in line for tool in ("wmic", "findstr", "select-string",
                                             "get-ciminstance", "get-process", "grep")):
                continue
            return True
    return False


def check_python_switch() -> tuple[str, bool, str, str]:
    """Is the Supabase->Turso switch installed in this machine's venv?

    The switch is a sitecustomize.py, so it must live in site-packages — which
    is in no repo. It therefore existed on exactly one workstation and never on
    the VPS, where setting EMPIRE_DATA_BACKEND=turso_cloud consequently did
    nothing at all, silently. Provisioning a rig has to install it, and this is
    the check that says whether it did.

    Asks the interpreter rather than looking for the file: a present-but-stale
    or shadowed sitecustomize is the same failure as an absent one.
    """
    fix = "python scripts/install_python_switch.py"
    v = venv_python(_root_as_posix())
    interp = str(v) if v else (_which("python3") or _which("python"))
    if not interp:
        return ("turso-switch", False, "no python interpreter", fix)
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from lib import turso_switch  # noqa: PLC0415

    status = turso_switch.probe(interp)
    return ("turso-switch", status.active, status.detail[:80], "" if status.active else fix)


ALL_CHECKS = [
    check_hooks,
    check_python_deps,
    check_python_switch,
    check_node_deps,
    check_system_bins,
    check_codex,
    check_global_claude_md,
    check_plugins,
    check_env_agents,
    check_tls_keylog,
    check_fleet_persistence,
]

# Cheap, no-subprocess subset for the SessionStart hook (pure file reads, <5ms).
# The hooks check is THE signal that the agentic loop is wired for this machine.
FAST_CHECKS = [check_hooks, check_global_claude_md]


def run_checks(fast: bool = False) -> list[tuple[str, bool, str, str]]:
    return [c() for c in (FAST_CHECKS if fast else ALL_CHECKS)]


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def print_report(results, self_tests=None) -> bool:
    print(f"\n  MACHINE PARITY - {platform.system()} - repo: {REPO_ROOT}")
    print("  " + "-" * 64)
    all_ok = True
    for name, ok, detail, hint in results:
        mark = "OK  " if ok else "FIX "
        print(f"  [{mark}] {name:<17} {detail}")
        if not ok:
            all_ok = False
            if hint:
                print(f"           -> {hint}")
    if self_tests:
        bad = [t for t in self_tests if not t[1]]
        print(f"  [{'OK  ' if not bad else 'FIX '}] {'hook-self-test':<17} {len(self_tests) - len(bad)}/{len(self_tests)} hook scripts run clean")
        for tname, ok, det in self_tests:
            if not ok:
                all_ok = False
                print(f"           -> {tname}: {det}")
    print("  " + "-" * 64)
    print(f"  RESULT: {'GREEN - at parity' if all_ok else 'NOT at parity - see FIX items above'}\n")
    return all_ok


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Bring this machine to full agentic parity.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--export-template", action="store_true", help="capture live hooks → committed portable template (source machine)")
    g.add_argument("--fix", action="store_true", help="install hooks for this OS + auto-heal + report (new machine)")
    g.add_argument("--check", action="store_true", help="read-only parity report")
    ap.add_argument("--quiet", action="store_true", help="with --check: print one line only if NOT at parity")
    ap.add_argument("--fast", action="store_true", help="with --check: cheap subset (hooks + global config) for the SessionStart hook")
    ap.add_argument("--dry-run", action="store_true", help="with --fix: render + self-test + report, but do NOT write settings.local.json")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()

    if args.export_template:
        return export_template()

    if args.fix:
        if args.dry_run:
            print("[fix] DRY RUN - not writing settings.local.json")
        else:
            _ok, msg = install_hooks()
            print(f"[fix] hooks: {msg}")
        self_tests = self_test_hooks()
        results = run_checks()
        if args.json:
            print(json.dumps({
                "results": [{"name": n, "ok": o, "detail": d} for n, o, d, _ in results],
                "self_tests": [{"name": n, "ok": o, "detail": d} for n, o, d in self_tests],
            }, indent=2))
            return 0
        at_parity = print_report(results, self_tests)
        print("  Next: RESTART Claude Code so the hooks load, then re-run --check to confirm GREEN.")
        return 0 if at_parity else 1

    # --check
    results = run_checks(fast=args.fast)
    if args.json:
        print(json.dumps({"results": [{"name": n, "ok": o, "detail": d, "hint": h} for n, o, d, h in results]}, indent=2))
        return 0
    at_parity = all(ok for _n, ok, _d, _h in results)
    if args.quiet:
        # Informational signal goes to STDOUT; ALWAYS exit 0 so a stdout-on-success-only
        # caller (the SessionStart hook's _run) still receives the drift warning.
        if not at_parity:
            fixes = [n for n, ok, _d, _h in results if not ok]
            print(f"[!] machine not at parity ({', '.join(fixes)}) - run: python3 scripts/machine_parity.py --fix")
        return 0
    print_report(results)
    return 0 if at_parity else 1


if __name__ == "__main__":
    sys.exit(main())
