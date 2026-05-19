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
    """True if a `pm2 logs --lines …` shell is running anywhere on the
    system. We don't strictly require it to be inside Windows Terminal
    (the user could have it open in plain cmd.exe) — but the Startup
    launcher always wraps it in wt.exe, so in practice both are true."""
    if sys.platform != "win32":
        return True  # No cockpit concept on POSIX
    try:
        result = safe_run(
            ["wmic", "process", "get", "CommandLine", "/FORMAT:CSV"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return False
    for line in (result.stdout or "").splitlines():
        if "pm2 logs --lines" in line:
            return True
    return False


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
