#!/usr/bin/env python3
"""
bravo — the unified CLI front door for Business-Empire-Agent.

Usage:
    bravo doctor              Full system health check
    bravo status              One-screen operational summary
    bravo setup               Guided first-time setup wizard
    bravo tools               List available CLI tools (from manifest)
    bravo skills              List registered skills
    bravo run <script>        Run a script from scripts/ by name
    bravo config show|set     Show or set product config (~/.bravo/config.toml)
    bravo browser             setup | doctor | learn <site>
    bravo agent               list | create <name> | doctor <name>
    bravo sessions            search <q> | recent | stats | ingest
    bravo profile             list | show | use <name>
    bravo logs                Tail ~/.bravo/logs
    bravo update              git pull + catalog sync + session ingest
    bravo version             Show version and agent info

Wraps existing scripts + the runtime layer. Never duplicates business logic.
Preserves V5.6 outbound chokepoint (scripts/send_gateway.py).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────────

VERSION = "0.3.0"
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
SKILLS_DIR = REPO_ROOT / "skills"
AGENTS_DIR = REPO_ROOT / "agents"
BRAIN_DIR = REPO_ROOT / "brain"
MEMORY_DIR = REPO_ROOT / "memory"
TEMPLATES_DIR = REPO_ROOT / "templates"
ENV_FILE = REPO_ROOT / ".env.agents"
BRAVO_HOME = Path(os.path.expanduser("~/.bravo"))

# Make `runtime` package importable without installing.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ANSI colors — degrade gracefully on dumb terminals
_COLOR = os.environ.get("NO_COLOR") is None and sys.stdout.isatty()

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text

BOLD = lambda t: _c("1", t)
DIM = lambda t: _c("2", t)
GREEN = lambda t: _c("32", t)
YELLOW = lambda t: _c("33", t)
RED = lambda t: _c("31", t)
CYAN = lambda t: _c("36", t)
MAGENTA = lambda t: _c("35", t)

# Safe symbols — fall back to ASCII if terminal can't handle Unicode
def _safe(uchar: str, fallback: str) -> str:
    try:
        uchar.encode(sys.stdout.encoding or "utf-8")
        return uchar
    except (UnicodeEncodeError, LookupError):
        return fallback

OK = _safe("\u2713", "+")       # ✓ or +
FAIL = _safe("\u2717", "X")     # ✗ or X
WARN = _safe("\u25cb", "o")     # ○ or o
ALERT = _safe("\u26a0", "!")    # ⚠ or !

BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║    ██████╗ ██████╗  █████╗ ██╗   ██╗ ██████╗                 ║
║    ██╔══██╗██╔══██╗██╔══██╗██║   ██║██╔═══██╗                ║
║    ██████╔╝██████╔╝███████║██║   ██║██║   ██║                ║
║    ██╔══██╗██╔══██╗██╔══██║╚██╗ ██╔╝██║   ██║                ║
║    ██████╔╝██║  ██║██║  ██║ ╚████╔╝ ╚██████╔╝                ║
║    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝   ╚═════╝                 ║
║                                                              ║
║    Agent Factory · Business-in-a-Box                         ║
║    Made by OASIS AI · oasisai.work                           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

TAGLINE = "Agent Factory — Business-in-a-Box · Made by OASIS AI"

# ── Helpers ────────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO_ROOT), text=True,
            capture_output=True, timeout=timeout
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}


def _tool_check(name: str) -> tuple[bool, str | None]:
    path = shutil.which(name)
    return (bool(path), path)


def _read_state_field(field: str) -> str:
    """Quick extraction from STATE.md — finds | **field** | value |."""
    state_path = BRAIN_DIR / "STATE.md"
    if not state_path.exists():
        return "unknown"
    text = state_path.read_text(encoding="utf-8", errors="ignore")
    pattern = rf"\|\s*\*\*{re.escape(field)}\*\*\s*\|\s*([^|]+)\|"
    m = re.search(pattern, text)
    return m.group(1).strip() if m else "unknown"


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_version(_args: argparse.Namespace) -> int:
    print(f"{BOLD('Bravo CLI')} v{VERSION}")
    print(f"  Repo: {REPO_ROOT}")
    print(f"  System version: {_read_state_field('Version')}")
    print(f"  Python: {sys.version.split()[0]}")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Unified health check — wraps self_audit + onboarding_diagnostics."""
    print(BOLD(CYAN("BRAVO DOCTOR")))
    print(f"  {DIM(str(dt.datetime.now().strftime('%Y-%m-%d %H:%M')))}")
    print()

    # 1. Toolchain
    print(BOLD("1. Toolchain"))
    required_tools = ["python", "git", "node", "npm"]
    optional_tools = ["uv", "rg", "browser-harness"]
    all_ok = True
    for name in required_tools:
        ok, path = _tool_check(name)
        mark = GREEN(OK) if ok else RED(FAIL)
        label = f"{path}" if ok else "missing"
        print(f"  {mark} {name:20s} {DIM(label)}")
        if not ok:
            all_ok = False
    for name in optional_tools:
        ok, path = _tool_check(name)
        mark = GREEN(OK) if ok else YELLOW(WARN)
        label = f"{path}" if ok else "not installed (optional)"
        print(f"  {mark} {name:20s} {DIM(label)}")
    print()

    # 2. Required structure
    print(BOLD("2. Required Files"))
    required_files = [
        "CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md", "AGENTS.md",
        "brain/STATE.md", "brain/SOUL.md", "brain/USER.md",
        "memory/SESSION_LOG.md", "memory/ACTIVE_TASKS.md",
        "skills/browser-harness/SKILL.md",
        "browser/SAFETY.md",
        ".env.agents",
    ]
    for relpath in required_files:
        exists = (REPO_ROOT / relpath).exists()
        mark = GREEN(OK) if exists else RED(FAIL)
        print(f"  {mark} {relpath}")
        if not exists:
            all_ok = False
    print()

    # 3. Self-audit
    print(BOLD("3. Self-Audit"))
    result = _run([sys.executable, str(SCRIPTS_DIR / "self_audit.py"), "--json"])
    if result["ok"]:
        try:
            audit = json.loads(result["stdout"])
            score = audit.get("health_score", 0)
            color = GREEN if score >= 85 else (YELLOW if score >= 70 else RED)
            print(f"  Health score: {color(f'{score}/100')}")
            print(f"  Markdown files: {audit.get('total_md_files', '?')}")
            print(f"  Skills: {audit.get('skills_total', '?')}")
            print(f"  Scripts: {audit.get('scripts_total', '?')}")
            print(f"  MCP servers in sync: {GREEN('YES') if audit.get('mcp_configs_in_sync') else RED('NO')}")
            if audit.get("orphans"):
                print(f"  Orphans: {YELLOW(str(len(audit['orphans'])))}")
        except json.JSONDecodeError:
            print(f"  {YELLOW('Could not parse self-audit output')}")
    else:
        print(f"  {RED('Self-audit failed')}: {result.get('stderr', '')[:200]}")
        all_ok = False
    print()

    # 4. Browser Harness
    print(BOLD("4. Browser Harness"))
    bh_script = SCRIPTS_DIR / "browser_harness_doctor.py"
    if bh_script.exists():
        bh_result = _run([sys.executable, str(bh_script), "--json"])
        if bh_result["ok"] or bh_result["stdout"]:
            try:
                bh = json.loads(bh_result["stdout"])
                install_mark = GREEN(OK) if bh.get("install_ok") else RED(FAIL)
                attach_mark = GREEN(OK) if bh.get("attach_ok") else YELLOW(WARN + " PENDING")
                print(f"  Install: {install_mark}")
                print(f"  Attach:  {attach_mark}")
                if bh.get("attach_hint"):
                    print(f"  {DIM(bh['attach_hint'])}")
            except json.JSONDecodeError:
                print(f"  {YELLOW('Could not parse browser harness output')}")
        else:
            print(f"  {YELLOW('Browser harness doctor did not produce output')}")
    else:
        print(f"  {DIM('browser_harness_doctor.py not found — skipping')}")
    print()

    # 5. Env file
    print(BOLD("5. Environment"))
    if ENV_FILE.exists():
        env_text = ENV_FILE.read_text(encoding="utf-8", errors="ignore")
        keys_present = [
            line.split("=")[0].strip()
            for line in env_text.splitlines()
            if "=" in line and not line.strip().startswith("#")
            and line.split("=", 1)[1].strip()
        ]
        print(f"  .env.agents: {GREEN('✓')} ({len(keys_present)} keys configured)")
    else:
        print(f"  .env.agents: {RED('✗ missing')}")
        all_ok = False
    print()

    # Verdict
    if all_ok:
        print(GREEN(BOLD("VERDICT: HEALTHY ✓")))
    else:
        print(YELLOW(BOLD("VERDICT: ISSUES FOUND — see above")))
    return 0 if all_ok else 1


def cmd_status(_args: argparse.Namespace) -> int:
    """One-screen operational summary."""
    print(BOLD(CYAN("BRAVO STATUS")))
    print(f"  {DIM(str(dt.datetime.now().strftime('%Y-%m-%d %H:%M')))}")
    print()

    # Read key fields from STATE.md
    fields = ["Version", "Position", "Confidence", "Focus Area", "Energy", "Memory Health"]
    for f in fields:
        val = _read_state_field(f)
        print(f"  {BOLD(f'{f}:'):25s} {val}")
    print()

    # Active tasks
    tasks_path = MEMORY_DIR / "ACTIVE_TASKS.md"
    if tasks_path.exists():
        text = tasks_path.read_text(encoding="utf-8", errors="ignore")
        # Count P0/P1/P2 tasks
        p0 = len(re.findall(r"^\s*-\s*\[[ x]\].*P0", text, re.MULTILINE | re.IGNORECASE))
        p1 = len(re.findall(r"^\s*-\s*\[[ x]\].*P1", text, re.MULTILINE | re.IGNORECASE))
        p2 = len(re.findall(r"^\s*-\s*\[[ x]\].*P2", text, re.MULTILINE | re.IGNORECASE))
        total = len(re.findall(r"^\s*-\s*\[[ ]\]", text, re.MULTILINE))
        done = len(re.findall(r"^\s*-\s*\[x\]", text, re.MULTILINE | re.IGNORECASE))
        print(f"  {BOLD('Active Tasks:'):25s} {total} open, {done} done")
        if p0:
            print(f"  {'':25s} {RED(f'{p0} P0')}", end="")
            if p1:
                print(f" / {YELLOW(f'{p1} P1')}", end="")
            if p2:
                print(f" / {DIM(f'{p2} P2')}", end="")
            print()
    print()

    # Last session log entry
    log_path = MEMORY_DIR / "SESSION_LOG.md"
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="ignore")
        # Find first ### header after frontmatter
        entries = re.findall(r"^### (.+)$", text, re.MULTILINE)
        if entries:
            print(f"  {BOLD('Last Session:'):25s} {entries[0]}")
    print()

    # Quick counts
    scripts_count = len(list(SCRIPTS_DIR.glob("*.py"))) if SCRIPTS_DIR.exists() else 0
    skills_count = sum(1 for d in SKILLS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")) if SKILLS_DIR.exists() else 0
    print(f"  {BOLD('Scripts:'):25s} {scripts_count}")
    print(f"  {BOLD('Skills:'):25s} {skills_count}")

    return 0


def cmd_tools(args: argparse.Namespace) -> int:
    """List available CLI tools from scripts/."""
    print(BOLD(CYAN("BRAVO TOOLS")))
    print()

    # Group scripts by category
    categories: dict[str, list[tuple[str, str]]] = {
        "Communication": [],
        "Data & CRM": [],
        "Finance": [],
        "Content": [],
        "Browser": [],
        "System": [],
        "Other": [],
    }

    category_keywords = {
        "Communication": ["email", "send", "notify", "outreach", "inbound", "gmail"],
        "Data & CRM": ["supabase", "lead", "client", "context", "funnel", "mem0", "memory"],
        "Finance": ["stripe", "revenue", "cost", "financial"],
        "Content": ["late", "instagram", "skool", "content", "transcribe", "generate_covers"],
        "Browser": ["browser", "firecrawl", "browse", "scrape"],
        "System": ["self_audit", "onboarding", "state_sync", "cron", "n8n", "google", "scheduler"],
    }

    for py in sorted(SCRIPTS_DIR.glob("*.py")):
        if py.name.startswith("_") or py.name.startswith("test_"):
            continue
        name = py.stem
        # Read first docstring line for description
        desc = ""
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'"""(.+?)"""', text, re.DOTALL)
            if m:
                desc = m.group(1).strip().split("\n")[0][:60]
        except Exception:
            pass

        placed = False
        for cat, keywords in category_keywords.items():
            if any(kw in name.lower() for kw in keywords):
                categories[cat].append((name, desc))
                placed = True
                break
        if not placed:
            categories["Other"].append((name, desc))

    for cat, tools in categories.items():
        if not tools:
            continue
        print(f"  {BOLD(cat)}")
        for name, desc in tools:
            desc_str = f"  {DIM(desc)}" if desc else ""
            print(f"    {CYAN(name):35s}{desc_str}")
        print()

    total = sum(len(t) for t in categories.values())
    print(f"  {DIM(f'Total: {total} tools')}")
    print(f"  {DIM('Run with: python scripts/<name>.py [args]')}")
    print(f"  {DIM('Or:       bravo run <name> [args]')}")
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    """List registered skills."""
    print(BOLD(CYAN("BRAVO SKILLS")))
    print()

    if not SKILLS_DIR.exists():
        print(f"  {RED('Skills directory not found')}")
        return 1

    skills: list[tuple[str, str, bool]] = []
    for sub in sorted(SKILLS_DIR.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        skill_md = sub / "SKILL.md"
        has_skill = skill_md.exists()
        desc = ""
        if has_skill:
            try:
                text = skill_md.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"description:\s*(.+)", text[:500])
                if m:
                    desc = m.group(1).strip()[:70]
            except Exception:
                pass
        skills.append((sub.name, desc, has_skill))

    for name, desc, has_file in skills:
        mark = GREEN(OK) if has_file else YELLOW(WARN)
        desc_str = f"  {DIM(desc)}" if desc else ""
        print(f"  {mark} {CYAN(name):35s}{desc_str}")

    print()
    valid = sum(1 for _, _, h in skills if h)
    print(f"  {DIM(f'{valid}/{len(skills)} skills have SKILL.md')}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run a script from scripts/ by stem name."""
    script_name = args.script
    if not script_name.endswith(".py"):
        script_name += ".py"
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f"{RED('Script not found:')} {script_name}")
        print(f"  Run {CYAN('bravo tools')} to see available scripts.")
        return 1

    extra = args.extra_args or []
    cmd = [sys.executable, str(script_path)] + extra
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


def cmd_setup(args: argparse.Namespace) -> int:
    """Guided first-time setup wizard.

    Default: interactive Q&A (profile picker, AI providers, chat bridges,
    business integrations). Writes directly to <repo>/.env.agents so all
    existing scripts in scripts/ pick up the keys immediately.

    Use `bravo setup --noninteractive` to run the diagnostic-only flow.
    Use `bravo setup --profile atlas` (etc.) to skip the profile picker.
    """
    if not getattr(args, "noninteractive", False):
        try:
            from bravo_cli.wizard import run_wizard
        except Exception as exc:
            print(f"{RED('Wizard failed to load:')} {exc}")
            return 1
        return run_wizard(profile_override=getattr(args, "profile", None))

    # Legacy: diagnostic-only mode
    print(BOLD(MAGENTA(BANNER)))
    print(BOLD("BRAVO SETUP (diagnostic mode)"))
    print(f"  {DIM('Checking environment only — no prompts.')}")
    print()

    steps_passed = 0
    steps_total = 0

    # Step 1: Check Python
    steps_total += 1
    print(f"{BOLD('Step 1:')} Python environment")
    ok, path = _tool_check("python")
    if ok:
        ver = sys.version.split()[0]
        print(f"  {GREEN('✓')} Python {ver} at {path}")
        steps_passed += 1
    else:
        print(f"  {RED('✗')} Python not found. Install Python 3.12+ from python.org")
    print()

    # Step 2: Check Git
    steps_total += 1
    print(f"{BOLD('Step 2:')} Git")
    ok, path = _tool_check("git")
    if ok:
        print(f"  {GREEN('✓')} Git at {path}")
        steps_passed += 1
    else:
        print(f"  {RED('✗')} Git not found. Install from git-scm.com")
    print()

    # Step 3: Check Node
    steps_total += 1
    print(f"{BOLD('Step 3:')} Node.js")
    ok, path = _tool_check("node")
    if ok:
        print(f"  {GREEN('✓')} Node at {path}")
        steps_passed += 1
    else:
        print(f"  {RED('✗')} Node.js not found. Install from nodejs.org")
    print()

    # Step 4: .env.agents
    steps_total += 1
    print(f"{BOLD('Step 4:')} Environment file")
    if ENV_FILE.exists():
        print(f"  {GREEN('✓')} .env.agents exists")
        steps_passed += 1
    else:
        print(f"  {RED('✗')} .env.agents not found")
        env_example = REPO_ROOT / ".env.agents.example"
        if env_example.exists():
            print(f"  {DIM('Copy .env.agents.example to .env.agents and fill in your keys')}")
        else:
            print(f"  {DIM('Create .env.agents with your API keys (see brain/QUICK_REFERENCE.md)')}")
    print()

    # Step 5: Brain structure
    steps_total += 1
    print(f"{BOLD('Step 5:')} Brain structure")
    critical = ["brain/STATE.md", "brain/SOUL.md", "memory/SESSION_LOG.md"]
    all_brain_ok = all((REPO_ROOT / p).exists() for p in critical)
    if all_brain_ok:
        print(f"  {GREEN('✓')} Core brain files present")
        steps_passed += 1
    else:
        for p in critical:
            exists = (REPO_ROOT / p).exists()
            mark = GREEN(OK) if exists else RED(FAIL)
            print(f"  {mark} {p}")
    print()

    # Step 6: Self-audit
    steps_total += 1
    print(f"{BOLD('Step 6:')} Running self-audit...")
    result = _run([sys.executable, str(SCRIPTS_DIR / "self_audit.py")])
    if result["ok"]:
        print(f"  {GREEN('✓')} Self-audit passed")
        steps_passed += 1
    else:
        print(f"  {YELLOW('⚠')} Self-audit found issues:")
        for line in (result["stdout"] or "").split("\n")[-10:]:
            if line.strip():
                print(f"    {line.strip()}")
    print()

    # Step 7: Browser Harness
    steps_total += 1
    print(f"{BOLD('Step 7:')} Browser Harness")
    bh_ok, bh_path = _tool_check("browser-harness")
    if bh_ok:
        print(f"  {GREEN('✓')} Browser Harness executable found at {bh_path}")
        print(f"  {DIM('Run: npm run browser:setup   to attach to your browser')}")
        steps_passed += 1
    else:
        print(f"  {YELLOW('○')} Browser Harness not installed (optional)")
        print(f"  {DIM('See skills/browser-harness/SKILL.md for installation')}")
    print()

    # Summary
    print(f"{BOLD('Setup complete:')} {steps_passed}/{steps_total} checks passed")
    if steps_passed == steps_total:
        print(GREEN(BOLD("All systems ready. Run 'bravo doctor' for a full health check.")))
    else:
        print(YELLOW(f"Fix the {steps_total - steps_passed} issue(s) above, then run 'bravo doctor'."))
    return 0 if steps_passed == steps_total else 1


# ── New commands: config, browser, agent, sessions, profile, logs, update ─────

def _dispatch_runtime(module: str, argv: list[str]) -> int:
    """Invoke a runtime.<module> module with argv."""
    cmd = [sys.executable, "-m", f"runtime.{module}"] + argv
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


def cmd_config(args: argparse.Namespace) -> int:
    """Show or edit ~/.bravo/config.toml."""
    config_path = BRAVO_HOME / "config.toml"
    action = (args.action or "show").lower()

    if action == "show":
        if not config_path.exists():
            print(f"{YELLOW('Not initialized.')} Run: {CYAN('bravo profile init')} "
                  f"or {CYAN('python -m runtime.profile_home init')}")
            return 1
        print(BOLD(CYAN(f"BRAVO CONFIG")) + f"  {DIM(str(config_path))}")
        print()
        print(config_path.read_text(encoding="utf-8"))
        return 0

    if action == "path":
        print(config_path)
        return 0

    if action == "set":
        if not args.key or args.value is None:
            print(f"{RED('Usage:')} bravo config set <key> <value>")
            return 1
        # Simple TOML key=value replacement (section.key or top-level)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        key = args.key
        value = args.value
        quoted = f'"{value}"' if not value.replace(".", "").replace("-", "").isalnum() else value
        # Replace `key = ...` if present; else append
        pattern = rf"^({re.escape(key)})\s*=\s*.+$"
        if re.search(pattern, text, re.MULTILINE):
            text = re.sub(pattern, rf"\1 = {quoted}", text, flags=re.MULTILINE)
        else:
            text = text.rstrip() + f"\n{key} = {quoted}\n"
        config_path.write_text(text, encoding="utf-8")
        print(f"{GREEN(OK)} set {BOLD(key)} = {quoted}")
        return 0

    print(f"{RED('Unknown action:')} {action}")
    return 1


def cmd_browser(args: argparse.Namespace) -> int:
    """Browser Harness setup / doctor / learn <site>."""
    action = (args.action or "doctor").lower()

    if action == "doctor":
        print(BOLD(CYAN("BRAVO BROWSER DOCTOR")))
        print()
        return subprocess.call(
            [sys.executable, str(SCRIPTS_DIR / "browser_harness_doctor.py")]
            + (["--strict"] if args.strict else []),
            cwd=str(REPO_ROOT),
        )

    if action == "setup":
        print(BOLD(CYAN("BRAVO BROWSER SETUP")))
        print()
        print(f"  {DIM('This runs browser-harness --setup and walks Chrome remote-debug approval.')}")
        print(f"  {DIM('Required one time per machine.')}")
        print()
        return subprocess.call(
            ["powershell", "-NoProfile", "-Command",
             "& (Get-Command browser-harness).Source --setup"],
            cwd=str(REPO_ROOT),
        )

    if action == "learn":
        if not args.site:
            print(f"{RED('Usage:')} bravo browser learn <site>")
            print(f"  {DIM('Creates a new browser/domain-skills/<site>.md stub from the template.')}")
            return 1
        # Sanitize: only allow [a-z0-9_-], lowercase. Blocks path traversal
        # (../), absolute paths (/etc/...), and funky unicode.
        site = args.site.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", site):
            print(f"{RED('Invalid site slug:')} {args.site!r}")
            print(f"  {DIM('Allowed: a-z, 0-9, _, -. Max 64 chars. Must start with a letter/digit.')}")
            return 1
        template = REPO_ROOT / "browser" / "DOMAIN_SKILL_TEMPLATE.md"
        domain_skills_dir = (REPO_ROOT / "browser" / "domain-skills").resolve()
        out = (domain_skills_dir / f"{site}.md").resolve()
        # Defense in depth: even after regex, verify the resolved path is
        # inside domain_skills_dir.
        try:
            out.relative_to(domain_skills_dir)
        except ValueError:
            print(f"{RED('Path escape detected — refusing to write outside browser/domain-skills/')}")
            return 1
        if out.exists():
            print(f"{YELLOW('Exists:')} {out}")
            return 0
        if not template.exists():
            print(f"{RED('Template missing:')} {template}")
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        content = template.read_text(encoding="utf-8").replace("<site>", site)
        out.write_text(content, encoding="utf-8")
        print(f"{GREEN(OK)} Created {out}")
        print(f"  {DIM('Fill in URL patterns, selectors, waits, traps, approval actions.')}")
        return 0

    print(f"{RED('Unknown browser action:')} {action}")
    return 1


def cmd_agent(args: argparse.Namespace) -> int:
    """Agent Forge — list, create, doctor named agents."""
    action = (args.action or "list").lower()

    if action == "list":
        print(BOLD(CYAN("BRAVO AGENTS")))
        print()
        from runtime.tool_manifest import _collect_agents  # lazy
        agents = _collect_agents()
        by_location: dict[str, list[dict]] = {}
        for a in agents:
            by_location.setdefault(a["location"], []).append(a)
        for loc, items in sorted(by_location.items()):
            print(f"  {BOLD(loc)}")
            for a in items:
                desc = f"  {DIM(a['description'])}" if a["description"] else ""
                model = f"  [{a['model']}]" if a["model"] != "unspecified" else ""
                print(f"    {CYAN(a['name']):30s}{model}{desc}")
            print()
        print(f"  {DIM(f'{len(agents)} agents total')}")
        return 0

    if action == "create":
        if not args.name:
            print(f"{RED('Usage:')} bravo agent create <name> [--template <template>] [--path <repo-path>]")
            return 1
        template = args.template or "default"
        scaffold = TEMPLATES_DIR / "agent-scaffold"
        if not scaffold.exists():
            print(f"{RED('Scaffold template missing:')} {scaffold}")
            print(f"  {DIM('Expected at templates/agent-scaffold/ — create it first.')}")
            return 1
        target = Path(args.path).expanduser() if args.path else (REPO_ROOT / "agents" / f"_forge_{args.name}")
        if target.exists() and any(target.iterdir()):
            print(f"{RED('Target not empty:')} {target}")
            return 1
        target.mkdir(parents=True, exist_ok=True)
        # Copy scaffold tree, templating {{AGENT_NAME}}
        copied = 0
        for src in scaffold.rglob("*"):
            if src.is_dir() or ".git" in src.parts:
                continue
            rel = src.relative_to(scaffold)
            dest = target / str(rel).replace("__AGENT__", args.name.lower())
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                text = src.read_text(encoding="utf-8")
                text = (text.replace("{{AGENT_NAME}}", args.name)
                            .replace("{{agent_name}}", args.name.lower())
                            .replace("{{AGENT_ROLE}}", args.role or "operations")
                            .replace("{{AGENT_TEMPLATE}}", template)
                            .replace("{{DATE}}", dt.datetime.now().strftime("%Y-%m-%d")))
                dest.write_text(text, encoding="utf-8")
            except (UnicodeDecodeError, UnicodeError):
                shutil.copy2(src, dest)
            copied += 1
        print(f"{GREEN(OK)} Forged agent {BOLD(args.name)} at {target}")
        print(f"  Files copied: {copied}")
        print(f"  Template: {template}")
        print(f"  Next: {CYAN(f'cd {target} && bravo agent doctor {args.name}')}")
        return 0

    if action == "doctor":
        if not args.name:
            print(f"{RED('Usage:')} bravo agent doctor <name>")
            return 1
        # Look for the agent in known locations
        candidates = [
            AGENTS_DIR / f"{args.name}.md",
            REPO_ROOT / ".claude" / "agents" / f"{args.name}.md",
            REPO_ROOT / "agents" / "voltagent" / f"{args.name}.md",
            REPO_ROOT / "agents" / f"_forge_{args.name}" / "AGENTS.md",
        ]
        found = [p for p in candidates if p.exists()]
        if not found:
            print(f"{RED('Agent not found:')} {args.name}")
            return 1
        print(BOLD(CYAN(f"AGENT DOCTOR: {args.name}")))
        print()
        for p in found:
            rel = p.relative_to(REPO_ROOT)
            text = p.read_text(encoding="utf-8", errors="ignore")
            has_desc = "description:" in text[:500].lower()
            has_tools = "tools:" in text[:500].lower()
            has_model = "model:" in text[:500].lower()
            print(f"  {GREEN(OK)} {rel}")
            for label, ok in [("description", has_desc), ("tools", has_tools), ("model", has_model)]:
                mark = GREEN(OK) if ok else YELLOW(WARN)
                print(f"    {mark} {label}")
        return 0

    print(f"{RED('Unknown agent action:')} {action}")
    return 1


def cmd_sessions(args: argparse.Namespace) -> int:
    """Session FTS search / recent / stats / ingest."""
    action = (args.action or "recent").lower()
    if action == "search":
        if not args.query:
            print(f"{RED('Usage:')} bravo sessions search <query>")
            return 1
        return _dispatch_runtime("session_store",
                                 ["search", args.query, "--limit", str(args.limit)])
    if action == "recent":
        return _dispatch_runtime("session_store",
                                 ["recent", "--limit", str(args.limit)])
    if action == "stats":
        return _dispatch_runtime("session_store", ["stats"])
    if action == "ingest":
        return _dispatch_runtime("session_store", ["ingest"])
    print(f"{RED('Unknown sessions action:')} {action}")
    return 1


def cmd_profile(args: argparse.Namespace) -> int:
    """Profile home management."""
    action = (args.action or "list").lower()
    if action == "list":
        return _dispatch_runtime("profile_home", ["list"])
    if action == "init":
        return _dispatch_runtime("profile_home", ["init"])
    if action == "info" or action == "show":
        return _dispatch_runtime("profile_home", ["info"])
    if action == "use":
        if not args.name:
            print(f"{RED('Usage:')} bravo profile use <name>")
            return 1
        config_path = BRAVO_HOME / "config.toml"
        if not config_path.exists():
            print(f"{RED('Config not initialized.')} Run: {CYAN('bravo profile init')}")
            return 1
        text = config_path.read_text(encoding="utf-8")
        new_text = re.sub(r'^active\s*=\s*".*?"',
                          f'active = "{args.name}"', text, flags=re.MULTILINE, count=1)
        if new_text == text:
            new_text = text.rstrip() + f'\n[profile]\nactive = "{args.name}"\n'
        config_path.write_text(new_text, encoding="utf-8")
        print(f"{GREEN(OK)} Active profile set to {BOLD(args.name)}")
        return 0
    print(f"{RED('Unknown profile action:')} {action}")
    return 1


def cmd_logs(args: argparse.Namespace) -> int:
    """Tail the most recent logs in ~/.bravo/logs/."""
    logs_dir = BRAVO_HOME / "logs"
    if not logs_dir.exists():
        print(f"{YELLOW('Logs dir not initialized:')} {logs_dir}")
        print(f"  Run: {CYAN('bravo profile init')}")
        return 1
    files = sorted(logs_dir.glob("*.log"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print(f"{DIM('No log files in')} {logs_dir}")
        return 0
    path = files[0]
    print(BOLD(CYAN(f"{path.name}"))
          + DIM(f"  (last {args.tail} lines)"))
    print()
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines[-args.tail:]:
            print(line)
    except Exception as exc:
        print(f"{RED('Error reading log:')} {exc}")
        return 1
    return 0


def cmd_update(_args: argparse.Namespace) -> int:
    """Run git pull + catalog_sync + session_store ingest (safe, idempotent)."""
    print(BOLD(CYAN("BRAVO UPDATE")))
    print()
    print(f"{BOLD('1.')} git pull --ff-only")
    r1 = _run(["git", "pull", "--ff-only"])
    print(r1["stdout"] or r1["stderr"])
    print()
    print(f"{BOLD('2.')} catalog sync")
    r2 = _run([sys.executable, str(SCRIPTS_DIR / "catalog_sync.py")])
    print(r2["stdout"] or r2["stderr"])
    print()
    print(f"{BOLD('3.')} session store ingest")
    r3 = _run([sys.executable, "-m", "runtime.session_store", "ingest"])
    print(r3["stdout"] or r3["stderr"])
    print()
    all_ok = r1["ok"] and r2["ok"] and r3["ok"]
    print(GREEN(OK + " Update complete") if all_ok else YELLOW(WARN + " Some steps had warnings"))
    return 0 if all_ok else 1


# ── Main parser ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bravo",
        description="Bravo — Business-Empire-Agent CLI (Agent Factory + Operations Brain)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Core:
  doctor               Full system health check
  status               One-screen operational summary
  setup                Guided first-time setup wizard
  version              Show version info

Discovery:
  tools                List available CLI tools
  skills               List registered skills
  agent list           List registered sub-agents

Runtime:
  config show|set      View / edit ~/.bravo/config.toml
  profile list|use     Switch active agent profile
  sessions search <q>  FTS search across session logs
  sessions recent      Most recent sessions
  logs [--tail N]      Tail the newest log file

Automation:
  browser setup        One-time Chrome remote-debug approval
  browser doctor       Browser Harness diagnostics
  browser learn <site> Scaffold a new browser domain skill
  agent create <name>  Forge a new agent from template
  agent doctor <name>  Validate an agent's structure
  run <script>         Run a script from scripts/
  update               git pull + catalog sync + session ingest
""",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="Full system health check")
    sub.add_parser("status", help="One-screen operational summary")
    setup_p = sub.add_parser("setup", help="Guided first-time setup wizard")
    setup_p.add_argument("--noninteractive", action="store_true",
                         help="Skip prompts; run diagnostic-only mode")
    setup_p.add_argument("--profile",
                         choices=["bravo", "atlas", "maven", "aura", "hermes", "custom"],
                         help="Pre-select a profile (skips the picker)")
    sub.add_parser("tools", help="List available CLI tools", aliases=["tool"])
    sub.add_parser("skills", help="List registered skills", aliases=["skill"])
    sub.add_parser("version", help="Show version info")
    sub.add_parser("update", help="git pull + catalog sync + session ingest")

    run_p = sub.add_parser("run", help="Run a script from scripts/")
    run_p.add_argument("script", help="Script name (without .py)")
    run_p.add_argument("extra_args", nargs=argparse.REMAINDER, help="Arguments to pass to the script")

    # config show | set <key> <value> | path
    cfg_p = sub.add_parser("config", help="View / edit ~/.bravo/config.toml")
    cfg_p.add_argument("action", nargs="?", default="show",
                       choices=["show", "set", "path"])
    cfg_p.add_argument("key", nargs="?")
    cfg_p.add_argument("value", nargs="?")

    # browser setup | doctor | learn <site>
    br_p = sub.add_parser("browser", help="Browser Harness setup / doctor / learn")
    br_p.add_argument("action", nargs="?", default="doctor",
                      choices=["setup", "doctor", "learn"])
    br_p.add_argument("site", nargs="?", help="Site slug for `browser learn <site>`")
    br_p.add_argument("--strict", action="store_true",
                      help="Doctor: fail if browser attach is not live")

    # agent list | create <name> | doctor <name>
    ag_p = sub.add_parser("agent", help="Agent Forge — list / create / doctor")
    ag_p.add_argument("action", nargs="?", default="list",
                      choices=["list", "create", "doctor"])
    ag_p.add_argument("name", nargs="?")
    ag_p.add_argument("--template", help="Template name (default: default)")
    ag_p.add_argument("--role", help="Role description for the new agent")
    ag_p.add_argument("--path", help="Target path (defaults to agents/_forge_<name>/)")

    # sessions search <q> | recent | stats | ingest
    ss_p = sub.add_parser("sessions", help="Session FTS search / recent / stats")
    ss_p.add_argument("action", nargs="?", default="recent",
                      choices=["search", "recent", "stats", "ingest"])
    ss_p.add_argument("query", nargs="?", help="Search query")
    ss_p.add_argument("--limit", type=int, default=10)

    # profile list | show | use <name> | init
    pr_p = sub.add_parser("profile", help="Agent profile home management")
    pr_p.add_argument("action", nargs="?", default="list",
                      choices=["list", "show", "info", "use", "init"])
    pr_p.add_argument("name", nargs="?")

    # logs --tail N
    lg_p = sub.add_parser("logs", help="Tail the most recent log in ~/.bravo/logs")
    lg_p.add_argument("--tail", type=int, default=50,
                      help="Number of lines to print (default 50)")

    return parser


COMMAND_MAP = {
    "doctor": cmd_doctor,
    "status": cmd_status,
    "setup": cmd_setup,
    "tools": cmd_tools,
    "tool": cmd_tools,
    "skills": cmd_skills,
    "skill": cmd_skills,
    "run": cmd_run,
    "version": cmd_version,
    "config": cmd_config,
    "browser": cmd_browser,
    "agent": cmd_agent,
    "sessions": cmd_sessions,
    "profile": cmd_profile,
    "logs": cmd_logs,
    "update": cmd_update,
}


def _launch_banner() -> None:
    """Branded launch screen — shown on bare `bravo` invocation."""
    print(BOLD(CYAN(BANNER)))
    print(f"  {BOLD('Bravo')} {DIM(f'v{VERSION}')}  {DIM('|')}  "
          f"{MAGENTA(TAGLINE)}")
    print(f"  {DIM(str(dt.datetime.now().strftime('%Y-%m-%d %H:%M')))}"
          f"  {DIM('|')}  {DIM('Only good things from now on.')}")
    print()
    # Profile + health glance
    try:
        from runtime.profile_home import get_active_profile
        profile = get_active_profile()
    except Exception:
        profile = "bravo"
    version = _read_state_field("Version")
    pos = _read_state_field("Position")
    line = f"  Profile: {CYAN(profile):20s}  Version: {CYAN(version):18s}  Stance: {CYAN(pos)}"
    print(line)
    # MRR line if available from STATE.md
    mrr = _read_state_field("MRR")
    target = _read_state_field("Target")
    if mrr and mrr != "unknown":
        print(f"  MRR:     {GREEN(mrr):20s}  Target:  {CYAN(target or '$5,000')}")
    print()
    print(f"  {DIM('Commands:')} "
          f"{CYAN('doctor')} {DIM('|')} "
          f"{CYAN('status')} {DIM('|')} "
          f"{CYAN('agent')} {DIM('|')} "
          f"{CYAN('browser')} {DIM('|')} "
          f"{CYAN('sessions')} {DIM('|')} "
          f"{CYAN('update')}")
    print(f"  {DIM('Help:')}     bravo --help")
    print()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        _launch_banner()
        return cmd_status(args)

    handler = COMMAND_MAP.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
