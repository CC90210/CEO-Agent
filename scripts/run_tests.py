#!/usr/bin/env python3
"""Run pytest on the repo's own interpreter, over the repo's own testpaths.

Two bugs this exists to prevent, both of which shipped:

1. `npm test` ran whatever bare `python` resolved to on PATH — usually the
   system interpreter, which lacks this repo's dependencies. Hardcoding a venv
   path into package.json can't fix it: Windows wants .venv/Scripts/python.exe,
   the VPS wants .venv/bin/python, and CI has no venv at all. Probing at runtime
   is right on all three from a single npm string. Same ladder as
   review_fix.detect_test_cmd.

2. Every npm test script named `scripts/` explicitly, so `tests/` — 209 cases,
   including the whole hybrid-retrieval suite — was never in the local loop and
   four failures survived there unseen. This passes NO target paths, leaving
   pyproject.toml's `testpaths` as the single source of truth for scope.

Extra args are forwarded: `python scripts/run_tests.py -x -k retrieval`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def interpreter() -> str:
    """The venv python if this repo has one, else the current interpreter.

    The fallback is what makes CI work unchanged: no .venv there, and
    sys.executable is already the setup-python one.
    """
    for candidate in (
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",   # Windows
        PROJECT_ROOT / ".venv" / "bin" / "python",           # Linux VPS / macOS
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def main() -> int:
    py = interpreter()
    # stderr, not stdout: keeps it out of anything parsing pytest's report, and
    # turns "which python ran my tests?" from a guess into a line of output.
    print(f"[run_tests] interpreter: {py}", file=sys.stderr)
    # subprocess rather than os.execv — execv replaces the process image in a
    # way that confuses npm's child-process tracking on Windows.
    return subprocess.run(
        [py, "-m", "pytest", *sys.argv[1:]], cwd=str(PROJECT_ROOT)
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
