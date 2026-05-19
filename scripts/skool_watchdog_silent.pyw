"""Skool Watchdog — ARCHIVED 2026-05-18.

The Skool community comment/reply automation was retired when CC stepped away
from the primary retainer (2026-05-18). The full implementation is preserved under
`scripts/_archive/skool/` for revival when CC launches their own Skool
community (see scripts/_archive/skool/README.md for the revival steps).

The Windows scheduled task `\\SkoolWatchdog` still fires every 5 minutes (it
requires admin rights to disable and that hasn't been done yet). This launcher
is now a no-op so each fire is harmless — it exits immediately without
launching anything.

DO NOT delete this file — the scheduled task references it by path. Restoring
the original behavior is a single `git mv` from the archive directory.
"""

if __name__ == "__main__":
    pass
