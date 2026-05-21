"""Compatibility shim — moved to scripts/lib/outbound_log_post.py (2026-05-21).

Old import path:  `from _outbound_log_post import post_outbound_log`
New import path:  `from lib.outbound_log_post import post_outbound_log`

This file re-exports the canonical module so existing imports keep working.
New code should import from `lib.outbound_log_post` directly. The shim will
be removed once every caller has migrated (search: `from _outbound_log_post`).
"""

from lib.outbound_log_post import *  # noqa: F401,F403,E402
