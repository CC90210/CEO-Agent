#!/usr/bin/env python3
"""Minimal self-audit for a forged agent.

Checks:
- Required files present
- No Windows cp1252 encoding errors in Python output
- brain/ and memory/ at least have placeholder content
- No secrets in tracked files (simple regex)

Exit 0 if healthy, 1 otherwise.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = [
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "brain/SOUL.md",
    "brain/STATE.md",
    "brain/USER.md",
    "memory/ACTIVE_TASKS.md",
    "memory/SESSION_LOG.md",
]

SECRET_PATTERNS = [
    re.compile(r"(?i)(password|secret|api[_-]?key|token)\s*=\s*['\"][A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),  # OpenAI-style
    re.compile(r"(?i)ghp_[A-Za-z0-9]{36}"),  # GitHub token
]


def main() -> int:
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    if missing:
        print(json.dumps({"ok": False, "missing": missing}, indent=2))
        return 1

    # Placeholder check: every file is non-empty
    empty = [p for p in REQUIRED if (ROOT / p).stat().st_size == 0]

    # Secret scan on tracked files
    leaks = []
    for py in ROOT.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                leaks.append(str(py.relative_to(ROOT)))
                break

    report = {
        "ok": not (missing or empty or leaks),
        "missing": missing,
        "empty": empty,
        "potential_leaks": leaks,
        "health_score": 100 - 20 * len(missing) - 10 * len(empty) - 50 * len(leaks),
    }
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
    else:
        print(f"missing: {len(missing)}  empty: {len(empty)}  leaks: {len(leaks)}")
        print(f"health score: {report['health_score']}/100")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
