"""Every place in this repo that spawns the `claude` binary strips the Claude
Spillover lane vars.

WHY (2026-09-12, scripts/spillover/CONTRACT.md §13). Claude Code sessions route
through a local spillover proxy by way of ANTHROPIC_BASE_URL, and a session
exports CLAUDE_CODE_ENTRYPOINT=cli to everything it launches. A claude child
that inherits either can land an automation in the proxy, or make it look
spill-eligible. The fix is one builder per language: build_claude_spawn_env
(Python) and buildClaudeSpawnEnv (Node) strip `lane_env_strip` from the
inherited env. But a builder protects only the spawn sites that call it:
bridge_chat_server's cold spawn hand-copied os.environ while the warm pool
beside it used the builder.

This scan finds every spawn of the claude binary and fails on any whose env did
not come through the builder or an explicit lane strip.

  * Python, by AST, per function. A spawn is a subprocess call (run / Popen /
    safe_run / ...) whose argv is a claude argv: a list whose first element is
    "claude", a claude_bin / claude_exe / CLAUDE_EXE name, or a resolver call.
    Its env= must be a builder call, a name every assignment of which is one
    (build_claude_spawn_env / strip_lane_env), or a name passed to
    strip_lane_env. No env= at all inherits the parent env unscrubbed.
  * Node, by text. A spawn of CLAUDE_EXE / this._CLAUDE_EXE / 'claude'
    (directly, or through a variable assigned one) must pass an env whose
    assignment calls buildClaudeSpawnEnv / stripLaneEnv, or safeBaseEnv (an
    allowlist; checked below to carry no lane or credential name).

Known blind spot, named plainly: a spawn behind a generic wrapper that takes
argv as a parameter (bridge_chat_server._run_cli_command, bridge_tools._run) is
invisible here. Today those wrappers serve codex, gemini and `claude --version`.
`claude --version` probes are exempt: a version probe makes no API call, so
there is nothing to route.

Run: python -m pytest scripts/tests/test_spawn_sites.py -q
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LANE_VARS: list[str] = json.loads(
    (REPO / "config" / "claude_auth_signals.json").read_text(encoding="utf-8"))["lane_env_strip"]

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "_archive",
             "site-packages", ".next", "dist", "build", "coverage", ".pytest_cache",
             ".mypy_cache", ".ruff_cache"}

# Intentional exceptions, keyed by repo-relative POSIX path, each with the reason
# that site cannot use the builder. Empty on purpose: every spawn found today
# uses the builder or an explicit strip. A row here is a decision, and its
# reason is the review record for that decision.
ALLOWLIST: dict[str, str] = {}

# Sites the scan must SEE. If a refactor renames a variable and the detector goes
# blind, "no violations" would be a lie; this turns that into a failure.
KNOWN_PY_SITES = {
    "scripts/lib/claude_cli.py",
    "scripts/review_fix.py",
    "scripts/integrations/extraction_consumer.py",
    "bravo_cli/warm_claude_pool.py",
    "bravo_cli/bridge_chat_server.py",
    "skills/skill-creator/scripts/run_eval.py",
}
KNOWN_JS_SITES = {"telegram_agent.js", "gateway/adapters/telegram.js", "coordination_agent.js"}

# ------------------------------------------------------------------ walking ---


def _skip_dir(path: Path) -> bool:
    # A junction or symlink leads into another tree (a worktree's link into a
    # shared checkout, say); scanning it would judge someone else's code.
    isjunction = getattr(os.path, "isjunction", None)
    return path.name in SKIP_DIRS or path.is_symlink() or bool(isjunction and isjunction(path))


def _repo_files(suffixes: tuple[str, ...]) -> tuple[list[Path], list[str]]:
    """Every file with one of `suffixes`, plus every directory that could not be
    read. os.walk drops unreadable directories silently unless told otherwise."""
    files: list[Path] = []
    unreadable: list[str] = []
    for root, dirs, names in os.walk(REPO, onerror=lambda e: unreadable.append(
            f"{e.filename}: {e.strerror}")):
        dirs[:] = [d for d in dirs if not _skip_dir(Path(root) / d)]
        files.extend(Path(root) / n for n in names
                     if n.endswith(suffixes) and not n.endswith(".min.js"))
    return files, unreadable


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()

# ------------------------------------------------------------------- Python ---


SPAWN_FUNCS = {"run", "Popen", "call", "check_call", "check_output", "safe_run",
               "safe_popen", "safe_daemon_popen", "_safe_run", "_safe_popen",
               "create_subprocess_exec"}
SAFE_ENV_CALLS = ("build_claude_spawn_env", "strip_lane_env")
CLAUDE_NAME = re.compile(r"^_?(?:claude_(?:bin|exe|path|cli)|CLAUDE_(?:EXE|BIN))$")
CLAUDE_LITERALS = {"claude", "claude.exe", "claude.cmd"}
WHICH_FUNCS = {"which", "_which", "which_cli", "_which_cli"}


def _call_name(node: ast.AST) -> str:
    func = node.func if isinstance(node, ast.Call) else node
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _is_claude_head(node: ast.AST) -> bool:
    """Is this argv[0] the claude binary?"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.lower() in CLAUDE_LITERALS
    if isinstance(node, (ast.Name, ast.Attribute)):
        return bool(CLAUDE_NAME.match(_call_name(node)))
    if isinstance(node, ast.Call):
        name = _call_name(node)
        if name.endswith("resolve_claude_bin"):
            return True
        return (name in WHICH_FUNCS and bool(node.args)
                and isinstance(node.args[0], ast.Constant) and node.args[0].value == "claude")
    if isinstance(node, ast.BoolOp):  # env.get("BRAVO_CLAUDE_EXE") or "claude"
        return any(_is_claude_head(v) for v in node.values)
    return False


def _claude_list(node: ast.AST) -> bool:
    return isinstance(node, (ast.List, ast.Tuple)) and bool(node.elts) and _is_claude_head(node.elts[0])


def _is_version_probe(node: ast.AST) -> bool:
    return (isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) >= 2
            and isinstance(node.elts[1], ast.Constant) and node.elts[1].value == "--version")


def _scope_nodes(scope: ast.AST):
    """Nodes of one function (or the module) without descending into nested ones."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))


def _is_safe_env_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node).endswith(SAFE_ENV_CALLS)


def _py_spawns(tree: ast.AST, rel: str) -> tuple[list[str], list[str]]:
    """(every claude spawn site, the ones whose env is not scrubbed) as rel:line."""
    sites: list[str] = []
    bad: list[str] = []
    scopes = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for scope in scopes:
        nodes = list(_scope_nodes(scope))
        argv_names: dict[str, bool] = {}          # name -> is a version probe
        assigned: dict[str, list[ast.AST]] = {}   # name -> every value assigned to it
        stripped: set[str] = set()
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        assigned.setdefault(target.id, []).append(node.value)
                        if _claude_list(node.value):
                            argv_names[target.id] = _is_version_probe(node.value)
            elif (isinstance(node, ast.Call) and _call_name(node).endswith("strip_lane_env")
                  and node.args and isinstance(node.args[0], ast.Name)):
                stripped.add(node.args[0].id)
        for node in nodes:
            if not (isinstance(node, ast.Call) and _call_name(node) in SPAWN_FUNCS and node.args):
                continue
            argv = node.args[0]
            if _claude_list(argv):
                probe = _is_version_probe(argv)
            elif isinstance(argv, ast.Name) and argv.id in argv_names:
                probe = argv_names[argv.id]
            else:
                continue
            if probe:
                continue
            site = f"{rel}:{node.lineno}"
            sites.append(site)
            env = next((k.value for k in node.keywords if k.arg == "env"), None)
            if env is None:
                bad.append(f"{site} (no env=: inherits the parent env unscrubbed)")
            elif _is_safe_env_call(env):
                continue
            elif isinstance(env, ast.Name) and (
                    env.id in stripped
                    or (assigned.get(env.id) and all(_is_safe_env_call(v) for v in assigned[env.id]))):
                continue
            else:
                bad.append(f"{site} (env is not from build_claude_spawn_env / strip_lane_env)")
    return sites, bad

# --------------------------------------------------------------------- Node ---


JS_SPAWN = re.compile(r"\b(?:spawn|spawnSync|execFile|execFileSync)\s*\(")
JS_CLAUDE_CMD = re.compile(r"^(?:this\.)?_?CLAUDE_EXE$|^['\"`]claude(?:\.exe|\.cmd)?['\"`]$")
JS_SAFE_ENV = ("buildClaudeSpawnEnv(", "stripLaneEnv(", "safeBaseEnv(")


def _js_call_args(text: str, open_paren: int) -> str | None:
    """The argument text of the call whose "(" is at `open_paren`, skipping
    quoted strings so a "(" inside one does not unbalance the count."""
    depth, i, quote = 0, open_paren, None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1:i]
        i += 1
    return None


def _js_env_is_safe(text: str, name: str, before: int) -> bool:
    """Every assignment to `name` shortly before the spawn builds it safely."""
    region = text[max(0, before - 4000):before]
    windows = []
    for m in re.finditer(rf"(?:\b(?:const|let|var)\s+|[;{{}}(\n]\s*){re.escape(name)}\s*=(?![=>])",
                         region):
        rest = region[m.end():m.end() + 600]
        semi = rest.find(";")
        windows.append(rest if semi == -1 else rest[:semi])
    return bool(windows) and all(any(s in w for s in JS_SAFE_ENV) for w in windows)


def _js_spawns(text: str, rel: str) -> tuple[list[str], list[str]]:
    sites: list[str] = []
    bad: list[str] = []
    claude_vars = set(re.findall(r"\b(\w+)\s*=\s*(?:this\.)?_?CLAUDE_EXE\b", text))
    for m in JS_SPAWN.finditer(text):
        args = _js_call_args(text, m.end() - 1)
        if args is None:
            continue
        cmd = args.split(",", 1)[0].strip()
        if not (JS_CLAUDE_CMD.match(cmd) or cmd in claude_vars):
            continue
        site = f"{rel}:{text.count(chr(10), 0, m.start()) + 1}"
        sites.append(site)
        explicit = re.search(r"\benv\s*:\s*([^,}\n]+)", args)
        if explicit:
            expr = explicit.group(1).strip()
        elif re.search(r"[{,]\s*env\s*(?=[,}])", args):
            expr = "env"  # shorthand { env, ... }
        else:
            bad.append(f"{site} (no env: inherits process.env unscrubbed)")
            continue
        if expr.startswith(tuple(s.rstrip("(") for s in JS_SAFE_ENV)) or \
                expr.startswith(("cSuite.buildClaudeSpawnEnv", "this.buildClaudeSpawnEnv")):
            continue
        ident = re.match(r"[A-Za-z_$][\w$]*$", expr)
        if not (ident and _js_env_is_safe(text, expr, m.start())):
            bad.append(f"{site} (env {expr!r} is not from buildClaudeSpawnEnv / stripLaneEnv)")
    return sites, bad

# -------------------------------------------------------------------- tests ---


def test_every_python_claude_spawn_strips_the_lane_vars():
    files, unreadable = _repo_files((".py",))
    assert not unreadable, f"directories the scan could not read: {unreadable}"
    found: dict[str, list[str]] = {}
    violations: list[str] = []
    unparsed: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "claude" not in text.lower():
            continue
        rel = _rel(path)
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            unparsed.append(f"{rel}: {e.msg} (line {e.lineno})")
            continue
        sites, bad = _py_spawns(tree, rel)
        if sites:
            found[rel] = sites
        if rel not in ALLOWLIST:
            violations.extend(bad)
    assert not unparsed, f"files that mention claude but do not parse, so cannot be checked: {unparsed}"
    missing = KNOWN_PY_SITES - set(found)
    assert not missing, f"the scan no longer sees these claude spawns — it has gone blind: {missing}"
    assert not violations, (
        "claude spawned with an env that did not go through build_claude_spawn_env "
        f"or strip_lane_env — inherited lane vars would reach it: {violations}")


def test_every_node_claude_spawn_strips_the_lane_vars():
    files, unreadable = _repo_files((".js", ".mjs", ".cjs"))
    assert not unreadable, f"directories the scan could not read: {unreadable}"
    found: dict[str, list[str]] = {}
    violations: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "claude" not in text.lower():
            continue
        rel = _rel(path)
        sites, bad = _js_spawns(text, rel)
        if sites:
            found[rel] = sites
        if rel not in ALLOWLIST:
            violations.extend(bad)
    missing = KNOWN_JS_SITES - set(found)
    assert not missing, f"the scan no longer sees these claude spawns — it has gone blind: {missing}"
    assert not violations, (
        "claude spawned with an env that did not go through buildClaudeSpawnEnv "
        f"or stripLaneEnv — inherited lane vars would reach it: {violations}")


def test_every_allowlist_entry_has_a_reason_and_still_exists():
    for rel, reason in ALLOWLIST.items():
        assert (REPO / rel).is_file(), f"allowlisted {rel} no longer exists; drop the row"
        assert len(reason.strip()) > 20, f"allowlisted {rel} needs a real justification"


def test_the_untrusted_allowlist_env_carries_no_lane_or_credential_var():
    """safeBaseEnv is accepted above as safe only because it is an allowlist."""
    text = (REPO / "coordination_agent.js").read_text(encoding="utf-8")
    m = re.search(r"function safeBaseEnv\(\)\s*\{\s*const keep = \[(.*?)\];", text, re.S)
    assert m, "safeBaseEnv's keep-list moved; re-check that it is still an allowlist"
    keep = set(re.findall(r"'([^']+)'", m.group(1)))
    lane = {name.upper() for name in LANE_VARS}
    assert not {k for k in keep if k.upper() in lane
                or k.upper().startswith(("ANTHROPIC_", "CLAUDE_"))}, keep


# ----------------------------------------------- the detector, attacked first ---
# A scan that passes proves nothing until it has been shown to fail on the bug it
# exists for. These are the two shapes that bug took.

_BAD_PY = '''
import os, subprocess
def cold_spawn(claude_bin):
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    args = [claude_bin, "-p", "hi"]
    return subprocess.Popen(args, env=env)
def bare():
    return subprocess.run(["claude", "-p"])
def probe(claude_bin):
    return subprocess.run([claude_bin, "--version"])
'''
_GOOD_PY = '''
import os, subprocess
from lib.claude_auth import build_claude_spawn_env, strip_lane_env
def a(claude_bin):
    env = build_claude_spawn_env(extras={"CI": "true"})
    env["PATH"] = "x"
    return subprocess.run([claude_bin, "-p"], env=env)
def b():
    child = dict(os.environ)
    strip_lane_env(child)
    return subprocess.run(["claude", "-p"], env=child)
'''
_BAD_JS = """
const CLAUDE_EXE = 'claude.exe';
function go() {
    const env = { ...process.env };
    delete env.ANTHROPIC_API_KEY;
    return spawn(CLAUDE_EXE, ['-p', 'hi'], { env, stdio: 'pipe' });
}
function bare() { return spawn('claude', ['-p', 'Read(x)'], { stdio: 'pipe' }); }
"""
_GOOD_JS = """
function go() {
    const spawnEnv = buildClaudeSpawnEnv({ extras: { CI: 'true' } });
    return spawn(this._CLAUDE_EXE, args, { env: spawnEnv, shell: false });
}
"""


def test_the_python_detector_flags_the_bug_it_exists_for():
    sites, bad = _py_spawns(ast.parse(_BAD_PY), "bad.py")
    assert len(sites) == 2 and len(bad) == 2, (sites, bad)
    sites, bad = _py_spawns(ast.parse(_GOOD_PY), "good.py")
    assert len(sites) == 2 and not bad, (sites, bad)


def test_the_node_detector_flags_the_bug_it_exists_for():
    sites, bad = _js_spawns(_BAD_JS, "bad.js")
    assert len(sites) == 2 and len(bad) == 2, (sites, bad)
    sites, bad = _js_spawns(_GOOD_JS, "good.js")
    assert len(sites) == 1 and not bad, (sites, bad)
