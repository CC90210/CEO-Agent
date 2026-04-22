#!/usr/bin/env python3
"""
bravo — the unified CLI front door for Business-Empire-Agent.

Usage:
    bravo doctor          Full system health check
    bravo status          One-screen operational summary
    bravo setup           Guided first-time setup wizard
    bravo tools [list]    List available CLI tools
    bravo skills [list]   List registered skills
    bravo run <script>    Run a script from scripts/ by name
    bravo version         Show version and agent info

This wraps existing scripts — it never duplicates business logic.
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

VERSION = "0.1.0"
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
SKILLS_DIR = REPO_ROOT / "skills"
BRAIN_DIR = REPO_ROOT / "brain"
MEMORY_DIR = REPO_ROOT / "memory"
ENV_FILE = REPO_ROOT / ".env.agents"
CONFIG_EXAMPLE = REPO_ROOT / "config" / "bravo-config.example.toml"

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
 ____  ____    __    _  _  _____
(  _ \(  _ \  /__\  ( \/ )(  _  )
 ) _ < )   / /(__)\  \  /  )(_)(
(____/(_)\_)(__)(__)  \/  (_____)
"""

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


def _count_lines(path: Path, ext: str) -> int:
    total = 0
    for f in path.rglob(f"*{ext}"):
        try:
            total += sum(1 for _ in f.open(encoding="utf-8", errors="ignore"))
        except Exception:
            pass
    return total


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


def cmd_setup(_args: argparse.Namespace) -> int:
    """Guided first-time setup wizard."""
    print(BOLD(MAGENTA(BANNER)))
    print(BOLD("BRAVO SETUP WIZARD"))
    print(f"  {DIM('Setting up your Business-Empire-Agent environment')}")
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


# ── Main parser ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bravo",
        description="Bravo — Business-Empire-Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  doctor      Full system health check
  status      One-screen operational summary
  setup       Guided first-time setup wizard
  tools       List available CLI tools
  skills      List registered skills
  run <name>  Run a script from scripts/ by name
  version     Show version info
""",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="Full system health check")
    sub.add_parser("status", help="One-screen operational summary")
    sub.add_parser("setup", help="Guided first-time setup wizard")
    sub.add_parser("tools", help="List available CLI tools", aliases=["tool"])
    sub.add_parser("skills", help="List registered skills", aliases=["skill"])
    sub.add_parser("version", help="Show version info")

    run_p = sub.add_parser("run", help="Run a script from scripts/")
    run_p.add_argument("script", help="Script name (without .py)")
    run_p.add_argument("extra_args", nargs=argparse.REMAINDER, help="Arguments to pass to the script")

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
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        # No command — show banner + status
        print(BOLD(MAGENTA(BANNER)))
        print(f"  {BOLD('Bravo CLI')} v{VERSION}")
        print(f"  {DIM('Business-Empire-Agent')}")
        print(f"  {DIM('Run: bravo <command> — or: bravo --help')}")
        print()
        return cmd_status(args)

    handler = COMMAND_MAP.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
