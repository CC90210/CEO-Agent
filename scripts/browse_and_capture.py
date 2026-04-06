#!/usr/bin/env python3
"""
Browse & Capture — Opens URL in CC's real Chrome and captures a screenshot.
ONE command, ONE result. No turns wasted.

Usage:
  python scripts/browse_and_capture.py --url "https://amazon.ca/gp/cart/view.html"
  python scripts/browse_and_capture.py --url "https://gmail.com" --wait 5

Output: JSON with screenshot path (auto-relayed to Telegram by the bridge).
"""

import argparse
import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import time

CREATE_NO_WINDOW = 0x08000000
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def get_chrome_window_rect():
    """Find Chrome window and return its bounding rect (left, top, width, height)."""
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

    if chrome_hwnd:
        # Restore if minimized, bring to front
        user32.ShowWindow(chrome_hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(chrome_hwnd)

        # Get window rect
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(chrome_hwnd, ctypes.byref(rect))
        return {
            "hwnd": chrome_hwnd,
            "left": rect.left,
            "top": rect.top,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top
        }
    return None


def main():
    parser = argparse.ArgumentParser(description="Open URL in Chrome and capture screenshot")
    parser.add_argument("--url", required=True, help="URL to open")
    parser.add_argument("--wait", type=int, default=4, help="Seconds to wait for page load")
    args = parser.parse_args()

    target = os.path.join(os.environ.get("TEMP", "."), "browser_check.png")

    # Step 1: Open URL in Chrome
    subprocess.Popen([CHROME, args.url], creationflags=CREATE_NO_WINDOW)

    # Step 2: Wait for page to load
    time.sleep(args.wait)

    # Step 3: Find Chrome window and get its rect
    time.sleep(0.5)
    chrome = get_chrome_window_rect()

    if chrome:
        # Step 4: Screenshot JUST the Chrome window (not full screen — avoids focus issues)
        import mss
        with mss.mss() as sct:
            monitor = {
                "left": max(chrome["left"], 0),
                "top": max(chrome["top"], 0),
                "width": chrome["width"],
                "height": chrome["height"]
            }
            img = sct.grab(monitor)
            mss.tools.to_png(img.rgb, img.size, output=target)
    else:
        # Fallback: full screen screenshot
        import mss
        with mss.mss() as sct:
            sct.shot(output=target)

    print(json.dumps({
        "ok": True,
        "output": f"Opened {args.url} in Chrome and captured screenshot.\nScreenshot saved to {target}",
        "file": target
    }))


if __name__ == "__main__":
    main()
