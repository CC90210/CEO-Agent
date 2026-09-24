"""pytest conftest for scripts/.

Adds the scripts/ directory to sys.path so test modules can use the same
`from email_engine import ...` / `from _subprocess_helpers import ...` form
the production scripts use at runtime. Without this, pytest collection
fails with ModuleNotFoundError before the test bodies execute (they each
do their own sys.path insertion, but that happens too late for the
import statements at module top).
"""

from __future__ import annotations

import sys
import importlib
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

# `scripts/bravo_cli.py` is a legacy executable whose basename collides with
# the real `bravo_cli/` package. Keep the repository root ahead of scripts and
# pin the package before individual legacy tests prepend scripts/ themselves.
for path in reversed((REPO_ROOT, SCRIPTS_DIR)):
    value = str(path)
    if value in sys.path:
        sys.path.remove(value)
    sys.path.insert(0, value)
importlib.import_module("bravo_cli")
