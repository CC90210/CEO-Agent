"""Cross-agent self-improvement sweep for Bravo, Atlas, and Maven.

Runs each agent's self_audit, scans memory staleness, rebuilds the
capability graph, and applies mechanical fixes (drift markers, stale
flags). Returns a single human-readable digest for Telegram.

Mechanical fixes applied automatically:
  - Capability graph rebuild (catches new/renamed skills + scripts)
  - Stale memory flagging (writes to memory/STALE_MEMORY.md)

Judgment-call fixes are surfaced, not applied:
  - Mistakes review summary
  - Drift items requiring human decisions

Usage:
    python scripts/core/agent_self_improvement.py run [--json]
    python scripts/core/agent_self_improvement.py run --agents bravo,atlas
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable

AGENT_ROOTS = {
    "bravo": REPO_ROOT,
    "atlas": Path(r"C:\Users\User\APPS\CFO-Agent"),
    "maven": Path(r"C:\Users\User\CMO-Agent"),
}


@dataclass
class AgentReport:
    name: str
    health_score: int | None = None
    drift_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


def _run(cmd: list[str], cwd: Path, timeout: int = 90) -> tuple[int, str, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout, env=env, encoding="utf-8", errors="replace",
         creationflags=WINDOWLESS_FLAGS)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except FileNotFoundError as exc:
        return 127, "", f"command not found: {exc}"


def audit_agent(name: str, root: Path) -> AgentReport:
    report = AgentReport(name=name)

    if not root.exists():
        report.skipped = True
        report.skip_reason = f"repo missing at {root}"
        return report

    audit_script = root / "scripts" / "self_audit.py"
    if not audit_script.exists():
        report.skipped = True
        report.skip_reason = "no self_audit.py in scripts/"
        return report

    rc, out, err = _run([PYTHON, str(audit_script), "--json"], cwd=root)
    # Several agents return nonzero exit when health<threshold but still emit
    # valid JSON. Trust the JSON over the rc.
    if not out.strip().startswith("{"):
        report.errors.append(f"self_audit no JSON (rc={rc}): {(err or out)[:200]}")
        return report

    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        report.errors.append(f"self_audit JSON parse failed: {exc}")
        return report

    report.health_score = data.get("health_score")
    report.drift_count = data.get("capability_drift_count", 0)
    for w in data.get("warnings", []) or []:
        report.warnings.append(str(w))

    return report


def rebuild_capability_graph(root: Path) -> str | None:
    builder = root / "scripts" / "build_capability_graph.py"
    if not builder.exists():
        return None
    rc, _out, err = _run([PYTHON, str(builder)], cwd=root, timeout=120)
    if rc == 0:
        return "capability graph rebuilt"
    return f"capability rebuild failed: {err[:120]}"


def autofix_drift(root: Path) -> str | None:
    """Run deterministic drift autofix (zero LLM cost). Returns a one-line
    summary or None if the script is missing in this repo."""
    autofix = root / "scripts" / "drift_autofix.py"
    if not autofix.exists():
        return None
    rc, out, err = _run([PYTHON, str(autofix), "apply", "--json"], cwd=root, timeout=120)
    if rc != 0 or not out.strip().startswith("{"):
        return f"autofix failed: {(err or out)[:120]}"
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return "autofix output unparseable"
    skills = len(data.get("skill_fixes", []))
    scripts = len(data.get("script_fixes", []))
    if skills == 0 and scripts == 0:
        return None  # nothing to report
    return f"autofixed {skills} skills + {scripts} scripts"


def archive_stale_memory(root: Path) -> str | None:
    """Move stale memory entries to archives. Pure script call, no LLM."""
    aging = root / "scripts" / "memory_aging.py"
    if not aging.exists():
        return None
    rc, out, err = _run(
        [PYTHON, str(aging), "archive", "--json"],
        cwd=root, timeout=60,
    )
    if rc != 0:
        return f"archive failed: {(err or out)[:120]}"
    try:
        data = json.loads(out)
        archived = data.get("archived", 0) if isinstance(data, dict) else 0
    except json.JSONDecodeError:
        return None
    if archived:
        return f"archived {archived} stale memory entries"
    return None


def scan_memory_staleness(root: Path, days: int = 7) -> tuple[int, str | None]:
    aging = root / "scripts" / "memory_aging.py"
    if not aging.exists():
        return 0, None
    rc, out, err = _run(
        [PYTHON, str(aging), "stale", "--days", str(days), "--json"],
        cwd=root,
    )
    if rc != 0:
        return 0, f"memory_aging failed: {(err or out)[:120]}"
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        # Fallback: count lines in plain output
        return out.count("\n"), None
    if isinstance(data, list):
        return len(data), None
    if isinstance(data, dict):
        return data.get("count", 0) or len(data.get("entries", []) or []), None
    return 0, None


def collect_recent_mistakes(root: Path, limit: int = 5) -> list[str]:
    """Return recent individual-mistake titles. Prefers `### ` (per-mistake
    headings used by all 3 agents). Falls back to `## ` only when no h3 exist,
    skipping known section headers (Template, Archive, Related, Obsidian Links,
    System Mistakes, CFO-Era Mistakes, etc).
    """
    mistakes = root / "memory" / "MISTAKES.md"
    if not mistakes.exists():
        return []
    skip_substrings = ("template", "related", "obsidian", "archive",
                       "system mistake", "era mistake")
    h3, h2 = [], []
    for ln in mistakes.read_text(encoding="utf-8", errors="replace").splitlines():
        s = ln.strip()
        if s.startswith("### "):
            h3.append(s.lstrip("#").strip())
        elif s.startswith("## "):
            title = s.lstrip("#").strip()
            if title and not any(sub in title.lower() for sub in skip_substrings):
                h2.append(title)
    return (h3 or h2)[:limit]


def detect_mistake_repeats(root: Path) -> list[str]:
    """Find evidence that a prevention rule isn't sticking.

    Two signals:
    1. Title contains 'REPEAT' or '(repeat)' — explicitly flagged
    2. Same tag (e.g. `time-context`) appears in 2+ mistakes — pattern emerging

    Returns short human-readable warnings ready for the digest.
    """
    mistakes = root / "memory" / "MISTAKES.md"
    if not mistakes.exists():
        return []
    text = mistakes.read_text(encoding="utf-8", errors="replace")

    repeat_titles: list[str] = []
    tag_counts: dict[str, int] = {}
    current_title: str | None = None

    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("### "):
            current_title = s.lstrip("#").strip()
            if "repeat" in current_title.lower():
                repeat_titles.append(current_title)
        elif s.lower().startswith("**tag:**") or s.lower().startswith("tag:"):
            # Format: **Tag:** `time-context`, `late-night-slip`.
            tags = [t.strip(" *`,.\"'") for t in s.split(":", 1)[1].split(",")]
            for tag in tags:
                if tag and len(tag) < 60:
                    tag_counts[tag.lower()] = tag_counts.get(tag.lower(), 0) + 1

    warnings: list[str] = []
    for title in repeat_titles[:2]:
        warnings.append(f"REPEAT mistake flagged: {title[:100]}")
    repeated_tags = [(t, c) for t, c in tag_counts.items() if c >= 2]
    repeated_tags.sort(key=lambda x: -x[1])
    for tag, count in repeated_tags[:2]:
        warnings.append(f"tag '{tag}' in {count} mistakes — prevention rule not sticking")
    return warnings


def run_sweep(agents: list[str]) -> dict[str, Any]:
    reports: dict[str, AgentReport] = {}
    for name in agents:
        root = AGENT_ROOTS.get(name)
        if not root:
            r = AgentReport(name=name, skipped=True, skip_reason="unknown agent")
            reports[name] = r
            continue
        r = audit_agent(name, root)
        if not r.skipped and not r.errors:
            # Auto-fix mechanical drift FIRST so the rebuild reflects the fixes
            autofix_msg = autofix_drift(root)
            if autofix_msg:
                r.fixes_applied.append(autofix_msg)
            archive_msg = archive_stale_memory(root)
            if archive_msg:
                r.fixes_applied.append(archive_msg)
            rebuild_msg = rebuild_capability_graph(root)
            if rebuild_msg:
                r.fixes_applied.append(rebuild_msg)

            # Build warnings in priority order (repeat patterns first — they're
            # evidence that a prevention rule isn't sticking, the strongest
            # signal for actual self-improvement).
            self_audit_warnings = list(r.warnings)
            r.warnings = []
            r.warnings.extend(detect_mistake_repeats(root))

            stale_count, stale_err = scan_memory_staleness(root)
            if stale_err:
                r.warnings.append(stale_err)
            elif stale_count:
                r.warnings.append(f"{stale_count} memory entries stale (>7d)")

            recent = collect_recent_mistakes(root, limit=3)
            if recent:
                r.fixes_applied.append(f"recent mistakes: {len(recent)}")
                r.warnings.append(f"latest mistake: {recent[0][:120]}")

            # self_audit warnings (drift counts) last — informational, not actionable
            r.warnings.extend(self_audit_warnings)
        reports[name] = r
    return {n: asdict(r) for n, r in reports.items()}


def format_digest(results: dict[str, Any]) -> str:
    icons = {"bravo": "🤖", "atlas": "💰", "maven": "📣"}
    lines = ["🧠 Agent Self-Improvement Sweep", ""]
    for name, r in results.items():
        icon = icons.get(name, "•")
        if r.get("skipped"):
            lines.append(f"{icon} {name.capitalize()}: skipped — {r.get('skip_reason', '')}")
            continue
        if r.get("errors"):
            lines.append(f"{icon} {name.capitalize()}: ERROR — {r['errors'][0][:120]}")
            continue
        score = r.get("health_score")
        drift = r.get("drift_count", 0)
        score_txt = f"{score}/100" if score is not None else "n/a"
        lines.append(f"{icon} {name.capitalize()}: health {score_txt} · drift {drift}")
        for w in (r.get("warnings") or [])[:3]:
            lines.append(f"   ⚠ {w[:140]}")
        for f in (r.get("fixes_applied") or [])[:2]:
            lines.append(f"   ✓ {f[:140]}")
        lines.append("")
    lines.append("Run details: scripts/core/agent_self_improvement.py run --json")
    return "\n".join(lines).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-agent self-improvement sweep")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="Run sweep across agents")
    p_run.add_argument("--agents", default="bravo,atlas,maven",
                       help="Comma-separated agent names (default: all)")
    p_run.add_argument("--json", action="store_true", help="Emit raw JSON results")
    args = parser.parse_args()

    if args.cmd == "run":
        agents = [a.strip().lower() for a in args.agents.split(",") if a.strip()]
        results = run_sweep(agents)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(format_digest(results))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
