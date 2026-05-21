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
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
