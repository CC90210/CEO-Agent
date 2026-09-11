"""Ensure the Bravo Console cockpit is alive.

CC's reboot UX requirement: exactly one Bravo Console on screen tailing all
PM2 logs. The Startup-folder shortcut (`Bravo Console.lnk`) launches it on
logon, but if CC closes it manually, accidentally, or the process dies,
there's no automatic recovery — the visible status indicator goes dark while
the daemons keep running invisibly.

The console is a plain `cmd.exe /k "...\\scripts\\bravo_console_tail.cmd"`
window. bravo_console_launcher.vbs stopped wrapping it in Windows Terminal on
2026-08-14; its header records why.

This script is idempotent:
  - If a cmd.exe running `bravo_console_tail.cmd` is already open, exit 0 —
    nothing to do.
  - If the process table cannot be read, exit 0 WITHOUT launching (see
    _cockpit_is_alive).
  - Otherwise, invoke `bravo_console_launcher.vbs` via wscript HIDDEN
    (//B, so wscript itself never flashes a console; the launcher sets the
    console's own window style).

Wired into:
  - SessionStart hook (every Claude session start) → cockpit verified
    silently. The process-table read takes ~2-3s (measured 2026-09-11).
  - Manually: `python scripts/ensure_cockpit.py` whenever needed.

Exit codes:
  0 — cockpit alive (already running, or just launched), or liveness unknown
  1 — launch attempted but no console appeared in 5s
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _subprocess_helpers import safe_run  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_VBS = ROOT / "scripts" / "bravo_console_launcher.vbs"

# The file bravo_console_launcher.vbs hands to `cmd /k`. A cmd.exe running it
# is the console; nothing else proves one is open.
CONSOLE_MARKER = "bravo_console_tail.cmd"

# Printed only after the query succeeded: $ErrorActionPreference = 'Stop' ends
# the script before this line on any CIM failure, so a missing marker means the
# table was never read — not that no console is open.
_END = "END-OF-TABLE"
_CONSOLE_QUERY = [
    "powershell", "-NoProfile", "-NonInteractive", "-Command",
    "$ErrorActionPreference = 'Stop'; "
    "Get-CimInstance Win32_Process -Filter \"Name = 'cmd.exe'\" | "
    "ForEach-Object { $_.CommandLine }; '" + _END + "'",
]


def _cockpit_is_alive(timeout: float = 30) -> bool | None:
    """True if a Bravo Console is open, False if none is, None if unknown.

    Matches a cmd.exe whose command line runs bravo_console_tail.cmd — the
    process the launcher really starts. This used to look for
    WindowsTerminal.exe, which the launcher stopped using on 2026-08-14. From
    then on the answer was always "no console", so every Claude session start
    opened another one: 100 were open on 2026-09-11, each with its own
    `pm2 logs` node process.

    None, not False, when the table cannot be read. False means "launch one",
    and launching on no evidence is the same leak by another road.

    tasklist cannot show a command line, and the command line is the only thing
    that separates the console from every other cmd.exe, so this reads
    Win32_Process through CIM — the source scripts/ops/fleet_watchdog.py also
    trusts (wmic is deprecated)."""
    if sys.platform != "win32":
        return True  # No cockpit concept on POSIX
    try:
        result = safe_run(_CONSOLE_QUERY, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    lines = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
    if result.returncode != 0 or not lines or lines[-1] != _END:
        return None
    return any(CONSOLE_MARKER in ln.lower() for ln in lines[:-1])


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

    alive = _cockpit_is_alive()
    if alive:
        print("[ensure_cockpit] alive — no action needed")
        return 0
    if alive is None:
        print("[ensure_cockpit] could not read the process table — not launching "
              "(a launch on no evidence is how the consoles piled up)")
        return 0

    if not LAUNCHER_VBS.exists():
        print(f"[ensure_cockpit] launcher missing: {LAUNCHER_VBS}", file=sys.stderr)
        return 1

    print("[ensure_cockpit] cockpit missing — launching")
    _launch_cockpit()

    # Verify the launch took. A 5-second budget rather than a count of checks:
    # each check is now a ~2s process-table read, so the old ten-check loop
    # would hold a session start for ~25s whenever a launch failed. Each check
    # also gets only what is left of the budget as its timeout: with the
    # query's own 30s, one stalled read could hold the session start that long.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _cockpit_is_alive(timeout=max(1.0, deadline - time.monotonic())):
            print("[ensure_cockpit] cockpit launched")
            return 0
        time.sleep(0.5)

    print("[ensure_cockpit] launch fired but cockpit didn't come up in 5s", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
