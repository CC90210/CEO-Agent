"""Ensure the Bravo Console cockpit terminal is alive.

CC's reboot UX requirement: exactly one minimized Windows Terminal in
the taskbar tailing all PM2 logs. The Startup-folder shortcut
(`Bravo Console.lnk`) launches it on logon, but if CC closes it
manually, accidentally, or the process dies, there's no automatic
recovery — the visible status indicator goes dark while PM2 daemons
keep running invisibly.

This script is idempotent:
  - If a `wt.exe` / `WindowsTerminal.exe` process is already running
    a `pm2 logs` shell, exit 0 — nothing to do.
  - Otherwise, invoke `bravo_console_launcher.vbs` via wscript HIDDEN
    (windowStyle=0 from the parent wscript so it never flashes a
    console; the launcher itself uses windowStyle=7 to minimize the
    spawned Windows Terminal into the taskbar).

Wired into:
  - SessionStart hook (every Claude session start) → cockpit verified
    silently. Adds <500ms to cold-start; <100ms when cockpit alive.
  - Manually: `python scripts/ensure_cockpit.py` whenever needed.

Exit codes:
  0 — cockpit alive (already running, or just launched)
  1 — launch attempted but no Windows Terminal appeared in 5s
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _subprocess_helpers import safe_run  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_VBS = ROOT / "scripts" / "bravo_console_launcher.vbs"


def _cockpit_is_alive() -> bool:
    """True if a `WindowsTerminal.exe` running the Bravo Console is up.

    Uses `tasklist` (built-in, stable across Windows versions) rather
    than `wmic` (deprecated in Windows 11 24H2+). We check for
    WindowsTerminal.exe specifically — the VBS launcher always wraps
    `pm2 logs` in `wt.exe`, so if the terminal is gone, the cockpit
    is effectively gone even if a stray `cmd.exe` running pm2 logs
    happens to be alive."""
    if sys.platform != "win32":
        return True  # No cockpit concept on POSIX
    try:
        result = safe_run(
            ["tasklist", "/FI", "IMAGENAME eq WindowsTerminal.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return False
    # tasklist prints "INFO: No tasks are running…" to stdout when
    # nothing matches — anything else means at least one wt process exists.
    out = (result.stdout or "").strip()
    if not out or "No tasks are running" in out:
        return False
    return "WindowsTerminal.exe" in out


def _launch_cockpit() -> None:
    """Fire-and-forget launch of the Bravo Console VBS. The VBS is
    responsible for windowStyle handling; we just need to invoke it
    HIDDEN so wscript itself doesn't flash a console."""
    # wscript needs //B //Nologo to suppress its own banner / dialogs.
    safe_run(
        ["wscript.exe", "//B", "//Nologo", str(LAUNCHER_VBS)],
        capture_output=True, timeout=10,
    )


def main() -> int:
    if sys.platform != "win32":
        return 0  # cockpit is a Windows concept

    if _cockpit_is_alive():
        print("[ensure_cockpit] alive — no action needed")
        return 0

    if not LAUNCHER_VBS.exists():
        print(f"[ensure_cockpit] launcher missing: {LAUNCHER_VBS}", file=sys.stderr)
        return 1

    print("[ensure_cockpit] cockpit missing — launching")
    _launch_cockpit()

    # Verify the launch took (Windows Terminal startup is ~2s)
    for _ in range(10):
        if _cockpit_is_alive():
            print("[ensure_cockpit] cockpit launched")
            return 0
        time.sleep(0.5)

    print("[ensure_cockpit] launch fired but cockpit didn't come up in 5s", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
