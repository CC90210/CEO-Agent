"""Browser Harness CLI — wrapper around browser_use for Bravo.

This replaces the broken uv-generated shim at ~/.local/bin/browser-harness.exe.
It provides the same interface (--version, --doctor, --setup) but uses the
installed browser_use package directly.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_version(args) -> int:
    """Print browser_use version info."""
    try:
        import browser_use
        # browser_use doesn't expose __version__, check package metadata
        try:
            from importlib.metadata import version
            ver = version("browser-use")
        except Exception:
            ver = "unknown"

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browsers = p.chromium
                print(f"browser-harness: browser_use {ver}")
                print(f"playwright: {version('playwright')}")
        except Exception:
            print(f"browser-harness: browser_use {ver}")
            print("playwright: not available")

    except ImportError as exc:
        print(f"browser-harness: NOT INSTALLED ({exc})", file=sys.stderr)
        return 1
    return 0


def cmd_doctor(args) -> int:
    """Run diagnostics on browser_use installation."""
    results = []

    # Check browser_use
    try:
        from browser_use.browser import BrowserSession, BrowserProfile
        results.append({"check": "browser_use.browser", "status": "OK"})
    except ImportError as exc:
        results.append({"check": "browser_use.browser", "status": "FAIL", "error": str(exc)})

    # Check playwright
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            results.append({"check": "playwright.chromium", "status": "OK"})
    except Exception as exc:
        results.append({"check": "playwright.chromium", "status": "FAIL", "error": str(exc)})

    # Check cloakbrowser
    try:
        import cloakbrowser
        results.append({
            "check": "cloakbrowser",
            "status": "OK",
            "chromium": cloakbrowser.CHROMIUM_VERSION,
        })
    except ImportError:
        results.append({"check": "cloakbrowser", "status": "NOT INSTALLED"})

    # Check browser-use Agent
    try:
        from browser_use.agent.service import Agent
        results.append({"check": "browser_use.agent", "status": "OK"})
    except ImportError as exc:
        results.append({"check": "browser_use.agent", "status": "FAIL", "error": str(exc)})

    all_ok = all(r["status"] in ("OK", "NOT INSTALLED") for r in results)

    for r in results:
        status = r.pop("status")
        mark = "OK" if status == "OK" else status
        print(f"  [{mark}] {r.pop('check')}")
        for k, v in r.items():
            print(f"         {k}: {v}")

    if all_ok:
        print("\nBrowser Harness is ready.")
    else:
        print("\nSome checks failed. Run: pip install browser-use cloakbrowser")

    return 0 if all_ok else 1


def cmd_setup(args) -> int:
    """Setup browser harness — verify browser installation."""
    print("Browser Harness setup...")
    print("  Checking Playwright browsers...")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://example.com", timeout=10000)
            title = page.title()
            context.close()
            browser.close()
            print(f"  Chromium OK — loaded: {title}")
    except Exception as exc:
        print(f"  Chromium failed: {exc}")
        print("  Run: python -m playwright install chromium")
        return 1

    print("  Browser Harness daemon is up.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Browser Harness CLI")
    parser.add_argument("--version", action="store_true", help="Print version")
    parser.add_argument("--doctor", action="store_true", help="Run diagnostics")
    parser.add_argument("--setup", action="store_true", help="Setup browsers")

    args = parser.parse_args()

    if args.version:
        return cmd_version(args)
    if args.doctor:
        return cmd_doctor(args)
    if args.setup:
        return cmd_setup(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
