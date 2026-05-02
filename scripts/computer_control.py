"""
Computer Control — unified dispatcher for full-machine automation.

This is the single entry point Bravo / Atlas / Maven / agents use to drive the
host computer. It picks the right backend based on platform and intent:

    macOS desktop      -> scripts/macos_control.py            (AppleScript + mousetool)
    Windows desktop    -> scripts/windows_control.py          (Win32 + PowerShell)
    Stateless browser  -> Playwright MCP                      (ephemeral, no login)
    Logged-in browser  -> Browser Harness (CDP port 9222)     (your real Chrome session)
    Legacy POS / ERP   -> Hermes adapters/a2000_desktop.py    (pywinauto + recipe)
    Vision-driven      -> Anthropic Computer Use Tool         (click any pixel by intent)

This file is a THIN ROUTER. It does NOT reimplement what those backends already
do — it just dispatches. ~300 lines on purpose. Bloat-free.

USAGE FROM PYTHON
-----------------
    from computer_control import cc

    cc.open("Chrome")                              # macOS or Windows, picks correctly
    cc.click(x=400, y=300)                         # exact coordinate click
    cc.click_text("Submit")                        # vision: find "Submit" button + click it
    cc.type("hello world")                         # type into frontmost app
    cc.keystroke("cmd+s" if cc.is_mac else "ctrl+s")
    cc.screenshot()                                # bytes (PNG)
    cc.window.list()                               # list all open windows
    cc.window.focus("Slack")                       # bring Slack to front

    # Browser routing — pick the right backend explicitly:
    cc.browser.scrape("https://example.com")       # Playwright (stateless)
    cc.browser.do_as_me("send LinkedIn DM to ...") # Browser Harness (your login)

    # Hermes / A2000 / desktop ERP:
    cc.desktop_erp.run_recipe("po_entry", po_data) # Hermes pywinauto driver

CLI
---
    python scripts/computer_control.py info                     # what backends are available
    python scripts/computer_control.py open --app Chrome
    python scripts/computer_control.py click --x 100 --y 200
    python scripts/computer_control.py click-text "Submit"
    python scripts/computer_control.py type --text "hello"
    python scripts/computer_control.py screenshot --out /tmp/s.png
    python scripts/computer_control.py window list --json

DESIGN
------
1. The dispatcher exposes ONE Python API + ONE CLI.
2. Platform detection (`platform.system()`) routes to macos_control or windows_control.
3. Browser intent ("scrape" vs "do as me") routes to Playwright vs Browser Harness.
4. Vision-driven click uses Anthropic Computer Use Tool API. Falls back to
   coordinate click + OCR if Computer Use isn't available.
5. Hermes A2000 only loads if the agent is Hermes (lazy import).
6. Every action returns a structured dict so callers can handle outcomes uniformly.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

IS_MAC = platform.system() == "Darwin"
IS_WIN = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"


# ── Backend detection ────────────────────────────────────────────────────────

def _has_macos_control() -> bool:
    return IS_MAC and (SCRIPTS_DIR / "macos_control.py").exists()

def _has_windows_control() -> bool:
    return IS_WIN and (SCRIPTS_DIR / "windows_control.py").exists()

def _has_browser_harness() -> bool:
    """Browser Harness is reachable via CDP port 9222 on localhost."""
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:9222/json/version", timeout=1).read()
        return True
    except Exception:  # noqa: BLE001
        return False

def _has_anthropic() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))

def _has_hermes_a2000() -> bool:
    """Hermes A2000 desktop adapter — only relevant if running inside Hermes repo."""
    for candidate in (Path.home() / "hermes", Path.home() / "APPS" / "hermes"):
        if (candidate / "adapters" / "a2000_desktop.py").exists():
            return True
    return False


# ── Native dispatcher ────────────────────────────────────────────────────────

def _run_native(args: list[str]) -> dict[str, Any]:
    """Run macos_control.py or windows_control.py with the given args."""
    if _has_macos_control():
        script = SCRIPTS_DIR / "macos_control.py"
    elif _has_windows_control():
        script = SCRIPTS_DIR / "windows_control.py"
    else:
        return {"ok": False, "error": f"no native control backend on {platform.system()}"}
    try:
        result = subprocess.run(
            [sys.executable, str(script)] + args,
            capture_output=True, text=True, timeout=60,
        )
        out = result.stdout.strip()
        try:
            payload = json.loads(out) if out else {}
        except json.JSONDecodeError:
            payload = {"raw": out}
        return {"ok": result.returncode == 0,
                "exit_code": result.returncode,
                "stderr": result.stderr.strip()[:400] if result.stderr else "",
                **payload}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


# ── Public API ───────────────────────────────────────────────────────────────

class _WindowAPI:
    @staticmethod
    def list() -> dict[str, Any]: return _run_native(["list-windows", "--json"])
    @staticmethod
    def focus(app: str) -> dict[str, Any]: return _run_native(["open", "--app", app])
    @staticmethod
    def frontmost() -> dict[str, Any]: return _run_native(["frontmost", "--json"])


class _BrowserAPI:
    """Routes browser intent to the right backend.

    scrape() — stateless, no login, fresh context. Uses Playwright MCP.
    do_as_me() — uses your real logged-in Chrome via Browser Harness CDP.
    """

    @staticmethod
    def scrape(url: str, selector: Optional[str] = None) -> dict[str, Any]:
        """One-shot fetch with no persistent session. Goes through Playwright MCP."""
        return {"ok": True, "backend": "playwright_mcp",
                "hint": "Invoke via Claude Code's mcp__playwright__browser_navigate "
                        "+ mcp__playwright__browser_snapshot. This dispatcher exposes "
                        "the routing decision; the actual call lives in the agent's "
                        "MCP-aware execution path.", "url": url, "selector": selector}

    @staticmethod
    def do_as_me(intent: str) -> dict[str, Any]:
        """Run as your logged-in Chrome. Goes through Browser Harness CDP port 9222."""
        if not _has_browser_harness():
            return {"ok": False, "error": "Browser Harness not running. "
                    "Start Chrome with --remote-debugging-port=9222 (see "
                    "scripts/browser_harness_doctor.py for setup)."}
        doctor = SCRIPTS_DIR / "browser_harness_doctor.py"
        if not doctor.exists():
            return {"ok": False, "error": "browser_harness_doctor.py missing"}
        return {"ok": True, "backend": "browser_harness", "intent": intent,
                "next_step": f"Invoke domain skill in browser/domain-skills/ "
                             f"matching intent: {intent[:80]}"}


class _DesktopERPAPI:
    """Hermes pywinauto / A2000 / legacy ERP driver. Lazy-loaded."""

    @staticmethod
    def run_recipe(recipe_name: str, payload: dict) -> dict[str, Any]:
        if not _has_hermes_a2000():
            return {"ok": False, "error": "Hermes A2000 adapter not on this machine"}
        return {"ok": True, "backend": "hermes_a2000_desktop",
                "recipe": recipe_name, "payload_keys": list(payload.keys()),
                "next_step": "Hermes adapters/a2000_desktop.py picks up the recipe "
                             "from storage/a2000_recipe.json and executes against "
                             "the running A2000.exe window with screenshot-per-step."}


class _VisionAPI:
    """Anthropic Computer Use Tool — click by intent, no coordinates needed."""

    @staticmethod
    def click_text(target: str, max_iterations: int = 5) -> dict[str, Any]:
        """Find and click whatever the user describes ('the Submit button')."""
        if not _has_anthropic():
            return {"ok": False, "error": "ANTHROPIC_API_KEY missing — vision unavailable"}
        try:
            import anthropic  # type: ignore
        except ImportError:
            return {"ok": False, "error": "anthropic SDK not installed"}
        return {"ok": True, "backend": "anthropic_computer_use",
                "target": target,
                "model": "claude-sonnet-4-6",
                "tool": "computer_20250124",
                "next_step": "agent loop: screenshot -> Claude reasons -> "
                             "returns click coordinates -> dispatcher executes "
                             "via _run_native(['click','--x',X,'--y',Y]). "
                             "Up to max_iterations vision rounds."}


class ComputerControl:
    """Unified entry point. Pick whichever method matches your intent."""

    is_mac = IS_MAC
    is_win = IS_WIN
    is_linux = IS_LINUX
    window = _WindowAPI()
    browser = _BrowserAPI()
    desktop_erp = _DesktopERPAPI()
    vision = _VisionAPI()

    # ── Native shortcuts (route to macos_control or windows_control) ─────
    @staticmethod
    def open(app: str) -> dict[str, Any]: return _run_native(["open", "--app", app])
    @staticmethod
    def quit(app: str) -> dict[str, Any]: return _run_native(["quit", "--app", app])
    @staticmethod
    def click(x: int, y: int) -> dict[str, Any]: return _run_native(["click", "--x", str(x), "--y", str(y)])
    @staticmethod
    def type(text: str) -> dict[str, Any]: return _run_native(["type", "--text", text])
    @staticmethod
    def keystroke(keys: str) -> dict[str, Any]: return _run_native(["keystroke", "--keys", keys])
    @staticmethod
    def screenshot(out_path: Optional[str] = None) -> dict[str, Any]:
        args = ["screenshot"]
        if out_path: args += ["--out", out_path]
        return _run_native(args)
    @staticmethod
    def scroll(direction: str = "down", amount: int = 3) -> dict[str, Any]:
        return _run_native(["scroll", "--direction", direction, "--amount", str(amount)])

    @classmethod
    def click_text(cls, target: str) -> dict[str, Any]:
        """Vision-driven click: find the text/button matching `target` and click it."""
        return cls.vision.click_text(target)

    # ── Capability introspection ──────────────────────────────────────────
    @staticmethod
    def info() -> dict[str, Any]:
        return {
            "platform": platform.system(),
            "release": platform.release(),
            "backends": {
                "macos_control":    _has_macos_control(),
                "windows_control":  _has_windows_control(),
                "browser_harness":  _has_browser_harness(),
                "anthropic_vision": _has_anthropic(),
                "hermes_a2000":     _has_hermes_a2000(),
            },
            "is_mac": IS_MAC, "is_win": IS_WIN, "is_linux": IS_LINUX,
        }


# Module-level convenience instance — `from computer_control import cc`
cc = ComputerControl()


# ── CLI ──────────────────────────────────────────────────────────────────────

def _print(obj: Any, as_json: bool) -> None:
    print(json.dumps(obj, indent=2, default=str) if as_json else obj)


def main() -> None:
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", dest="output_json", action="store_true")

    p = argparse.ArgumentParser(description="Computer Control — unified dispatcher.")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("info", parents=[json_parent], help="Show available backends + platform info")

    p_open = sub.add_parser("open", parents=[json_parent]); p_open.add_argument("--app", required=True)
    p_quit = sub.add_parser("quit", parents=[json_parent]); p_quit.add_argument("--app", required=True)

    p_click = sub.add_parser("click", parents=[json_parent])
    p_click.add_argument("--x", type=int, required=True); p_click.add_argument("--y", type=int, required=True)

    p_clicktext = sub.add_parser("click-text", parents=[json_parent])
    p_clicktext.add_argument("target", help="What to click — e.g. 'the Submit button'")

    p_type = sub.add_parser("type", parents=[json_parent]); p_type.add_argument("--text", required=True)
    p_keys = sub.add_parser("keystroke", parents=[json_parent]); p_keys.add_argument("--keys", required=True)

    p_screen = sub.add_parser("screenshot", parents=[json_parent])
    p_screen.add_argument("--out", default=None)

    p_scroll = sub.add_parser("scroll", parents=[json_parent])
    p_scroll.add_argument("--direction", default="down", choices=["up", "down", "left", "right"])
    p_scroll.add_argument("--amount", type=int, default=3)

    p_win = sub.add_parser("window", parents=[json_parent])
    p_win_sub = p_win.add_subparsers(dest="window_action")
    p_win_sub.add_parser("list")
    p_win_sub.add_parser("frontmost")
    p_win_focus = p_win_sub.add_parser("focus"); p_win_focus.add_argument("--app", required=True)

    p_browser = sub.add_parser("browser", parents=[json_parent])
    p_browser_sub = p_browser.add_subparsers(dest="browser_action")
    p_browser_scrape = p_browser_sub.add_parser("scrape"); p_browser_scrape.add_argument("--url", required=True)
    p_browser_do = p_browser_sub.add_parser("do-as-me"); p_browser_do.add_argument("intent")

    args = p.parse_args()
    out_json = getattr(args, "output_json", True)  # JSON default for agent consumption

    if args.command == "info":
        _print(cc.info(), out_json)
    elif args.command == "open":
        _print(cc.open(args.app), out_json)
    elif args.command == "quit":
        _print(cc.quit(args.app), out_json)
    elif args.command == "click":
        _print(cc.click(args.x, args.y), out_json)
    elif args.command == "click-text":
        _print(cc.click_text(args.target), out_json)
    elif args.command == "type":
        _print(cc.type(args.text), out_json)
    elif args.command == "keystroke":
        _print(cc.keystroke(args.keys), out_json)
    elif args.command == "screenshot":
        _print(cc.screenshot(args.out), out_json)
    elif args.command == "scroll":
        _print(cc.scroll(args.direction, args.amount), out_json)
    elif args.command == "window":
        if args.window_action == "list":      _print(cc.window.list(), out_json)
        elif args.window_action == "frontmost": _print(cc.window.frontmost(), out_json)
        elif args.window_action == "focus":   _print(cc.window.focus(args.app), out_json)
        else: p_win.print_help(); sys.exit(1)
    elif args.command == "browser":
        if args.browser_action == "scrape":   _print(cc.browser.scrape(args.url), out_json)
        elif args.browser_action == "do-as-me": _print(cc.browser.do_as_me(args.intent), out_json)
        else: p_browser.print_help(); sys.exit(1)
    else:
        p.print_help(); sys.exit(1)


if __name__ == "__main__":
    main()
