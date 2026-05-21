"""Compatibility shim — moved to scripts/lib/subprocess_helpers.py (2026-05-21).

Old import path:  `from _subprocess_helpers import WINDOWLESS_FLAGS, safe_run, ...`
New import path:  `from lib.subprocess_helpers import WINDOWLESS_FLAGS, safe_run, ...`

This file re-exports the canonical module so existing imports keep working.
New code should import from `lib.subprocess_helpers` directly. The shim will
be removed once every caller has migrated (search: `from _subprocess_helpers`).
"""

from lib.subprocess_helpers import *  # noqa: F401,F403,E402
