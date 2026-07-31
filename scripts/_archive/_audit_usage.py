"""One-shot audit: for every Python file in scripts/, determine who uses it.

Produces a markdown table that distinguishes ACTIVE (cron-scheduled OR
imported OR CLI-invoked elsewhere) from STANDALONE (only ever invoked
by CC manually).

Run: python scripts/_audit_usage.py
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

# Force UTF-8 output on Windows cp1252 terminals so em-dashes + arrows render.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


# Scan targets: every .py / .js / .sh in the project (skip venv, node_modules, .next)
SKIP_DIRS = {".venv", "node_modules", ".next", ".git", "tmp", ".claude", "courses"}
def walk() -> list[Path]:
    out: list[Path] = []
    for p in ROOT.rglob("*"):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix in (".py", ".js", ".sh", ".ps1", ".md", ".json"):
            out.append(p)
    return out


def main() -> None:
    all_files = walk()
    text_map: dict[Path, str] = {f: read(f) for f in all_files}

    # Scheduler-registered scripts — scan scheduler.py for run_script("X.py", ...)
    sched_text = read(SCRIPTS / "scheduler.py")
    sched_scripts: set[str] = set()
    for m in re.finditer(r'run_script\(\s*["\']([\w_\-]+\.py)', sched_text):
        sched_scripts.add(m.group(1))

    # PM2 ecosystem scripts — scan ecosystem.config.js
    pm2_text = read(ROOT / "ecosystem.config.js")
    pm2_scripts: set[str] = set()
    for m in re.finditer(r'["\']([\w_\-]+\.py)["\']', pm2_text):
        pm2_scripts.add(m.group(1))

    # Startup programs — Telegram bridge forwards commands
    tg_text = read(ROOT / "telegram_agent.js")
    tg_scripts: set[str] = set()
    for m in re.finditer(r'scripts[/\\]([\w_\-]+\.py)', tg_text):
        tg_scripts.add(m.group(1))

    py_scripts = sorted(SCRIPTS.glob("*.py"))
    print(f"Audited {len(py_scripts)} scripts against {len(all_files)} project files.\n")

    rows: list[tuple[str, str, str, str, str, str]] = []
    for s in py_scripts:
        stem = s.stem
        name = s.name
        imports: set[str] = set()
        invokes: set[str] = set()

        for f, text in text_map.items():
            if f == s:
                continue
            # Import detection: 'from <stem> import' or 'import <stem>'
            if re.search(rf"\b(from|import)\s+{re.escape(stem)}\b", text):
                imports.add(f.name)
            # Subprocess / shell invocation detection
            if f"scripts/{name}" in text or f"scripts\\{name}" in text:
                invokes.add(f.name)

        in_sched = "cron" if name in sched_scripts else ""
        in_pm2 = "pm2" if name in pm2_scripts else ""
        in_tg = "tg" if name in tg_scripts else ""
        runtime = "+".join(x for x in (in_sched, in_pm2, in_tg) if x) or "—"

        used_anywhere = bool(imports or invokes or runtime != "—")
        status = "ACTIVE" if used_anywhere else "STANDALONE"

        imp_s = ", ".join(sorted(imports)[:2])
        if len(imports) > 2:
            imp_s += f" +{len(imports) - 2}"
        inv_s = ", ".join(sorted(invokes)[:2])
        if len(invokes) > 2:
            inv_s += f" +{len(invokes) - 2}"

        rows.append((stem, imp_s or "—", inv_s or "—", runtime, status, ""))

    # Print as markdown table
    print("| Script | Imported by | Invoked via CLI/subprocess | Runtime | Status |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(f"| `{r[0]}` | {r[1]} | {r[2]} | {r[3]} | {r[4]} |")

    active = sum(1 for r in rows if r[4] == "ACTIVE")
    standalone = sum(1 for r in rows if r[4] == "STANDALONE")
    print(f"\n**Totals:** {active} ACTIVE, {standalone} STANDALONE, {len(rows)} scripts total")
    print(f"\n**Scheduler-scheduled ({len(sched_scripts)}):** {', '.join(sorted(sched_scripts))}")
    print(f"\n**PM2-managed ({len(pm2_scripts)}):** {', '.join(sorted(pm2_scripts))}")


if __name__ == "__main__":
    main()
