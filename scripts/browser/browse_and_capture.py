#!/usr/bin/env python3
"""
Browse & Capture — Opens URL in CC's real Chrome and captures a screenshot.
ONE command, ONE result. No turns wasted.

Usage:
  python scripts/browser/browse_and_capture.py --url "https://amazon.ca/gp/cart/view.html"
  python scripts/browser/browse_and_capture.py --url "https://gmail.com" --wait 5

Output: JSON with screenshot path (auto-relayed to Telegram by the bridge).
"""

import argparse
import json
import os
import subprocess
import sys
import time
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# Output path
if IS_WIN:
    TARGET = os.path.join(os.environ.get("TEMP", "."), "browser_check.png")
else:
    TARGET = "/tmp/browser_check.png"


# ── Windows helpers ──────────────────────────────────────────────────────────

def _win_open_chrome(url):
    import ctypes
    CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen([CHROME, url], creationflags=CREATE_NO_WINDOW)


def _win_screenshot(target):
    """Find Chrome window rect and screenshot it; fallback to full screen."""
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    chrome_hwnd = None

    def enum_callback(hwnd, _):
        nonlocal chrome_hwnd
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if "Chrome" in buf.value:
                chrome_hwnd = hwnd
                return False
        return True

    user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

    import mss
    if chrome_hwnd:
        user32.ShowWindow(chrome_hwnd, 9)   # SW_RESTORE
        user32.SetForegroundWindow(chrome_hwnd)
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(chrome_hwnd, ctypes.byref(rect))
        monitor = {
            "left": max(rect.left, 0),
            "top": max(rect.top, 0),
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
        }
        with mss.mss() as sct:
            img = sct.grab(monitor)
            mss.tools.to_png(img.rgb, img.size, output=target)
    else:
        with mss.mss() as sct:
            sct.shot(output=target)


# ── macOS helpers ────────────────────────────────────────────────────────────

def _mac_open_chrome(url):
    subprocess.Popen(["open", "-a", "Google Chrome", url], creationflags=WINDOWLESS_FLAGS)


def _mac_screenshot(target):
    """Full-screen screenshot with sound suppressed (-x)."""
    subprocess.run(["screencapture", "-x", target], check=False, creationflags=WINDOWLESS_FLAGS)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Open URL in Chrome and capture screenshot")
    parser.add_argument("--url", required=True, help="URL to open")
    parser.add_argument("--wait", type=int, default=4, help="Seconds to wait for page load")
    args = parser.parse_args()

    if not IS_WIN and not IS_MAC:
        print(json.dumps({"ok": False, "error": "Unsupported platform: only macOS and Windows are supported"}))
        sys.exit(1)

    # Step 1: Open URL in Chrome
    if IS_WIN:
        _win_open_chrome(args.url)
    else:
        _mac_open_chrome(args.url)

    # Step 2: Wait for page to load
    time.sleep(args.wait)

    # Step 3: Screenshot
    if IS_WIN:
        time.sleep(0.5)
        _win_screenshot(TARGET)
    else:
        _mac_screenshot(TARGET)

    print(json.dumps({
        "ok": True,
        "output": f"Opened {args.url} in Chrome and captured screenshot.\nScreenshot saved to {TARGET}",
        "file": TARGET,
    }))


if __name__ == "__main__":
    main()
