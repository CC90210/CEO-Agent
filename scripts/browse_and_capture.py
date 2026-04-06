#!/usr/bin/env python3
"""
Browse & Capture — Opens URL in CC's real Chrome and captures a screenshot.
ONE command, ONE result. No turns wasted.

Usage:
  python scripts/browse_and_capture.py --url "https://amazon.ca/gp/cart/view.html"
  python scripts/browse_and_capture.py --url "https://gmail.com" --wait 5
  python scripts/browse_and_capture.py --url "https://amazon.ca" --path "C:\\Temp\\amazon.png"

Output: JSON with screenshot path (auto-relayed to Telegram by the bridge).
"""

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time

CREATE_NO_WINDOW = 0x08000000


def main():
    parser = argparse.ArgumentParser(description="Open URL in Chrome and capture screenshot")
    parser.add_argument("--url", required=True, help="URL to open")
    parser.add_argument("--wait", type=int, default=4, help="Seconds to wait for page load (default: 4)")
    parser.add_argument("--path", help="Screenshot save path")
    args = parser.parse_args()

    target = args.path or os.path.join(os.environ.get("TEMP", "."), "browser_check.png")

    # Step 1: Open URL in CC's real Chrome (new tab)
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "chrome", args.url],
            creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        subprocess.Popen(
            [r"C:\Program Files\Google\Chrome\Application\chrome.exe", args.url],
            creationflags=CREATE_NO_WINDOW
        )

    # Step 2: Wait for page to load
    time.sleep(args.wait)

    # Step 3: Focus Chrome window
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             '$p = Get-Process chrome -EA SilentlyContinue | ? { $_.MainWindowHandle -ne 0 } | Select -First 1; '
             'if ($p) { '
             'Add-Type @"' + "\n" +
             'using System; using System.Runtime.InteropServices;' + "\n" +
             'public class FG { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); '
             '[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c); }' + "\n" +
             '"@' + "\n" +
             '[FG]::ShowWindow($p.MainWindowHandle, 9) | Out-Null; '
             '[FG]::SetForegroundWindow($p.MainWindowHandle) | Out-Null }'],
            capture_output=True, timeout=5, creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        pass

    time.sleep(1)

    # Step 4: Take screenshot
    try:
        import mss
        with mss.mss() as sct:
            sct.shot(output=target)
        size = os.path.getsize(target)
        print(json.dumps({
            "ok": True,
            "output": f"Opened {args.url} in Chrome and captured screenshot.\nScreenshot saved to {target}",
            "file": target
        }))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
