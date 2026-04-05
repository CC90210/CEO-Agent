#!/usr/bin/env python3
"""
macOS Computer Control — AppleScript wrapper for agent-driven desktop automation.
Uses osascript (built-in macOS) for application control, keystrokes, and window management.
No external dependencies — stdlib only.

Platform: macOS only. Exits with error on other platforms.

Usage:
  python3 scripts/macos_control.py open --app Safari
  python3 scripts/macos_control.py type --text "Hello world"
  python3 scripts/macos_control.py keystroke --keys "cmd+c"
  python3 scripts/macos_control.py click --x 500 --y 300
  python3 scripts/macos_control.py list-windows
  python3 scripts/macos_control.py list-apps
  python3 scripts/macos_control.py frontmost
  python3 scripts/macos_control.py screenshot [--path /tmp/screen.png]
  python3 scripts/macos_control.py url --open "https://example.com"
  python3 scripts/macos_control.py say --text "Hello CC"
  python3 scripts/macos_control.py volume --level 50
  python3 scripts/macos_control.py notify --title "Alert" --message "Task complete"

All commands support --json flag for agent consumption.
"""

import argparse
import json
import platform
import subprocess
import sys


def guard_macos():
    if platform.system() != "Darwin":
        print(json.dumps({"error": f"macos_control.py is macOS-only. Current platform: {platform.system()}"}))
        sys.exit(1)


def run_osascript(script, timeout=10):
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_shell(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---- KEY CODE MAP ----

SPECIAL_KEY_CODES = {
    "return": 36, "enter": 36, "tab": 48,
    "escape": 53, "esc": 53, "space": 49,
    "delete": 51, "backspace": 51,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}

MODIFIER_MAP = {
    "cmd": "command down", "command": "command down",
    "shift": "shift down",
    "alt": "option down", "option": "option down",
    "ctrl": "control down", "control": "control down",
}


# ---- COMMANDS ----

def cmd_open(args):
    return run_osascript(f'tell application "{args.app}" to activate')


def cmd_type(args):
    escaped = args.text.replace('\\', '\\\\').replace('"', '\\"')
    return run_osascript(f'''
tell application "System Events"
    keystroke "{escaped}"
end tell''')


def cmd_keystroke(args):
    keys = args.keys.lower().split("+")
    key_char = keys[-1]
    modifiers = keys[:-1]

    modifier_list = [MODIFIER_MAP[m] for m in modifiers if m in MODIFIER_MAP]
    using_clause = f" using {{{', '.join(modifier_list)}}}" if modifier_list else ""

    if key_char in SPECIAL_KEY_CODES:
        code = SPECIAL_KEY_CODES[key_char]
        return run_osascript(f'''
tell application "System Events"
    key code {code}{using_clause}
end tell''')
    else:
        return run_osascript(f'''
tell application "System Events"
    keystroke "{key_char}"{using_clause}
end tell''')


def cmd_click(args):
    # Use Python + Quartz framework for mouse clicks (built into macOS)
    py_script = f"""
import Quartz
point = Quartz.CGPointMake({args.x}, {args.y})
down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, 0)
up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, 0)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
print("clicked at {args.x},{args.y}")
"""
    result = run_shell(["python3", "-c", py_script])
    if not result["ok"] and "No module named" in result.get("error", ""):
        # Fallback: try cliclick if Quartz not available
        fallback = run_shell(["cliclick", f"c:{args.x},{args.y}"])
        if not fallback["ok"]:
            return {"ok": False, "error": "Quartz framework unavailable and cliclick not installed. Install via: brew install cliclick"}
        return fallback
    return result


def cmd_list_windows(args):
    return run_osascript('''
tell application "System Events"
    set windowList to ""
    repeat with proc in (every process whose visible is true)
        set procName to name of proc
        try
            repeat with win in (every window of proc)
                set winName to name of win
                set winPos to position of win
                set winSize to size of win
                set windowList to windowList & procName & " | " & winName & " | pos:" & (item 1 of winPos as text) & "," & (item 2 of winPos as text) & " | size:" & (item 1 of winSize as text) & "x" & (item 2 of winSize as text) & linefeed
            end repeat
        end try
    end repeat
    return windowList
end tell''', timeout=15)


def cmd_list_apps(args):
    return run_osascript('''
tell application "System Events"
    set appList to ""
    repeat with proc in (every process whose background only is false)
        set appList to appList & name of proc & linefeed
    end repeat
    return appList
end tell''')


def cmd_frontmost(args):
    result = run_osascript('''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    return frontApp
end tell''', timeout=15)
    if not result["ok"] and "Timed out" in result.get("error", ""):
        result["error"] += ". Grant Accessibility permissions: System Settings > Privacy & Security > Accessibility > enable your terminal app."
    return result


def cmd_screenshot(args):
    target = args.path or "/tmp/screenshot.png"
    result = run_shell(["screencapture", "-x", target])
    if result["ok"]:
        result["output"] = f"Screenshot saved to {target}"
    return result


def cmd_url(args):
    return run_shell(["open", args.url])


def cmd_say(args):
    return run_shell(["say", args.text])


def cmd_volume(args):
    level = max(0, min(100, args.level))
    return run_osascript(f"set volume output volume {level}")


def cmd_notify(args):
    script = f'display notification "{args.message}" with title "{args.title}"'
    return run_osascript(script)


# ---- MAIN ----

def main():
    guard_macos()

    # Handle --json flag in any position (before or after subcommand)
    json_output = "--json" in sys.argv
    if json_output:
        sys.argv.remove("--json")

    parser = argparse.ArgumentParser(description="macOS Computer Control")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("open", help="Open/activate an application")
    p.add_argument("--app", required=True)

    p = sub.add_parser("type", help="Type text into frontmost app")
    p.add_argument("--text", required=True)

    p = sub.add_parser("keystroke", help="Send key combo (e.g., cmd+c)")
    p.add_argument("--keys", required=True)

    p = sub.add_parser("click", help="Click at screen coordinates")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)

    sub.add_parser("list-windows", help="List visible windows")
    sub.add_parser("list-apps", help="List running applications")
    sub.add_parser("frontmost", help="Get frontmost app name")

    p = sub.add_parser("screenshot", help="Take a screenshot")
    p.add_argument("--path", help="Save path (default: /tmp/screenshot.png)")

    p = sub.add_parser("url", help="Open a URL in default browser")
    p.add_argument("--url", required=True)

    p = sub.add_parser("say", help="Speak text aloud")
    p.add_argument("--text", required=True)

    p = sub.add_parser("volume", help="Set system volume (0-100)")
    p.add_argument("--level", type=int, required=True)

    p = sub.add_parser("notify", help="Send a macOS notification")
    p.add_argument("--title", required=True)
    p.add_argument("--message", required=True)

    args = parser.parse_args()

    commands = {
        "open": cmd_open, "type": cmd_type, "keystroke": cmd_keystroke,
        "click": cmd_click, "list-windows": cmd_list_windows,
        "list-apps": cmd_list_apps, "frontmost": cmd_frontmost,
        "screenshot": cmd_screenshot, "url": cmd_url, "say": cmd_say,
        "volume": cmd_volume, "notify": cmd_notify,
    }

    result = commands[args.command](args)

    if json_output:
        print(json.dumps(result))
    else:
        if result.get("ok"):
            print(result.get("output", "Done."))
        else:
            print(f"ERROR: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
