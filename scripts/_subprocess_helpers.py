"""Shared subprocess constants for scripts/.

Single source of truth for the Windows-console-suppression flag. Before
this module, six different files redeclared `0x08000000` or
`subprocess.CREATE_NO_WINDOW` — each one a place to forget when adding
a new periodically-invoked script. Import from here instead.

Usage:
    from _subprocess_helpers import WINDOWLESS_FLAGS

    subprocess.run([...], creationflags=WINDOWLESS_FLAGS)
"""

from __future__ import annotations

import sys

# 0x08000000 == CREATE_NO_WINDOW on Windows. Hides the conhost flicker
# that otherwise appears every time a Task-Scheduler / PM2 / n8n /
# scheduler.run_script invocation shells out. Zero on non-Windows so
# code is portable.
WINDOWLESS_FLAGS: int = 0x08000000 if sys.platform == "win32" else 0
