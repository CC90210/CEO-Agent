"""Silent Skool Watchdog — runs via pythonw.exe (no console window).

Replaces skool-watchdog.cmd which opened a visible terminal every 5 minutes.
This .pyw file is executed by pythonw.exe automatically — completely invisible.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
WATCHDOG_SCRIPT = ROOT / "scripts" / "skool_watchdog.py"

CREATE_NO_WINDOW = 0x08000000

if __name__ == "__main__":
    subprocess.run(
        [str(VENV_PYTHON), str(WATCHDOG_SCRIPT)],
        cwd=str(ROOT),
        creationflags=CREATE_NO_WINDOW,
        capture_output=True,
        timeout=30,
    )
