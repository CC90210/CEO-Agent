#!/usr/bin/env python3
"""
macOS Computer Control V2.1 — Full desktop automation for agent-driven control.
60+ commands covering apps, windows, browser, files, processes, input, system, network, power.
Uses osascript (built-in macOS). No external dependencies — stdlib only.

Platform: macOS only. Exits with error on other platforms.
First run: python3 scripts/macos_control.py setup-permissions  (click Allow on each popup, then no more popups)

All commands support --json flag for agent consumption.
Run: python3 scripts/macos_control.py --help  for full command list.
"""

import argparse
import json
import os
import platform
import signal
import subprocess
import sys


def guard_macos():
    if platform.system() != "Darwin":
        print(json.dumps({"error": f"macos_control.py is macOS-only. Current platform: {platform.system()}"}))
        sys.exit(1)


def run_osascript(script, timeout=30):
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


def run_shell(cmd, timeout=30):
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


# ---- SECURITY: Input sanitization ----

def sanitize_applescript_string(s):
    """Remove characters that could break out of AppleScript string interpolation."""
    return s.replace('"', '').replace('\\', '').replace('\n', ' ').replace('\r', '')


def sanitize_url(url):
    """Validate and sanitize a URL for use in AppleScript."""
    url = url.strip()
    if not url.startswith(('http://', 'https://', 'about:', 'file://')):
        url = 'https://' + url
    return sanitize_applescript_string(url)


# Paths that should never be read/written/deleted via file commands
SENSITIVE_PATHS = [
    '/.ssh', '/.aws', '/.gnupg', '/.env', '/credentials',
    '/id_rsa', '/id_ed25519', '/.npmrc', '/.pypirc',
    '/keychain', '/Keychains', '/.config/gcloud',
]

# Process names that should never be killed
PROTECTED_PROCESSES = [
    'loginwindow', 'WindowServer', 'kernel_task', 'launchd',
    'sshd', 'pm2', 'Dock', 'SystemUIServer', 'Finder',
]


def is_sensitive_path(path):
    """Check if a path touches sensitive files/directories."""
    expanded = os.path.expanduser(path)
    for s in SENSITIVE_PATHS:
        if s in expanded:
            return True
    return False


# ---- MOUSETOOL BINARY PATH ----
# Pre-compiled CoreGraphics binary for reliable mouse control (no pyobjc dependency needed).
# Built once via: clang -framework ApplicationServices scripts/mousetool.c -o scripts/mousetool
MOUSETOOL = os.path.join(os.path.dirname(__file__), "mousetool")

def run_mousetool(args_list, timeout=15):
    """Run the mousetool binary. Parses its JSON output directly."""
    if not os.path.isfile(MOUSETOOL):
        return {"ok": False, "error": "mousetool binary not found. Run: clang -framework ApplicationServices scripts/mousetool.c -o scripts/mousetool"}
    r = run_shell([MOUSETOOL] + [str(a) for a in args_list], timeout=timeout)
    if r["ok"]:
        try:
            # mousetool outputs JSON directly — parse it so we don't double-wrap
            return json.loads(r["output"])
        except (json.JSONDecodeError, ValueError):
            pass
    return r


# ---- SCREEN SIZE HELPER ----

def get_screen_size():
    """Get main display resolution."""
    r = run_osascript('tell application "Finder" to get bounds of window of desktop')
    if r["ok"]:
        parts = r["output"].split(", ")
        if len(parts) == 4:
            return int(parts[2]), int(parts[3])
    # Fallback via system_profiler
    r2 = run_shell(["system_profiler", "SPDisplaysDataType"], timeout=5)
    if r2["ok"]:
        for line in r2["output"].split("\n"):
            if "Resolution" in line:
                # e.g., "Resolution: 2560 x 1600 Retina"
                parts = line.split(":")[-1].strip().split(" x ")
                if len(parts) >= 2:
                    return int(parts[0].strip()), int(parts[1].split()[0].strip())
    return 1440, 900  # safe default


# ---- RECORDING PID FILE ----
RECORD_PID_FILE = "/tmp/macos_control_recording.pid"


# ============================================================
# COMMANDS — Original (V1.0)
# ============================================================

def cmd_open(args):
    app = sanitize_applescript_string(args.app)
    wait = getattr(args, 'wait', False)
    if wait:
        script = f'''
tell application "{app}" to activate
delay 1
set maxWait to 20
set waited to 0
repeat while waited < maxWait
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
    end tell
    if frontApp contains "{app}" then
        return frontApp & " is active"
    end if
    delay 1
    set waited to waited + 1
end repeat
return "{app} launched (loading may continue)"
'''
        return run_osascript(script, timeout=25)
    return run_osascript(f'tell application "{app}" to activate')


def cmd_quit(args):
    app = sanitize_applescript_string(args.app)
    # Try graceful quit first; if it hangs (save dialog), dismiss and force-quit
    r = run_osascript(f'tell application "{app}" to quit saving no', timeout=5)
    if not r["ok"]:
        # Fall back to kill via pkill for stubborn apps
        r2 = run_shell(["pkill", "-f", app])
        if r2["ok"]:
            return {"ok": True, "output": f"Force-quit {app}"}
        # Last resort: standard quit (may show dialog)
        return run_osascript(f'tell application "{app}" to quit')
    return r


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
    return run_mousetool(["click", args.x, args.y])


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
        result["file"] = target
    return result


def cmd_url(args):
    return run_shell(["open", args.url])


def cmd_say(args):
    return run_shell(["say", args.text])


def cmd_volume(args):
    level = max(0, min(100, args.level))
    return run_osascript(f"set volume output volume {level}")


def cmd_notify(args):
    escaped_msg = args.message.replace('"', '\\"')
    escaped_title = args.title.replace('"', '\\"')
    script = f'display notification "{escaped_msg}" with title "{escaped_title}"'
    return run_osascript(script)


# ============================================================
# COMMANDS — Window Management (V2.0)
# ============================================================

def _window_guard(app):
    """Check that app has at least one window open. Returns error dict or None (ok)."""
    r = run_osascript(f'''
tell application "System Events"
    tell process "{app}"
        if (count of windows) = 0 then return "no_windows"
        return "ok"
    end tell
end tell''', timeout=5)
    if r["ok"] and r["output"] == "no_windows":
        return {"ok": False, "error": f"'{app}' has no open windows. Use `open --app \"{app}\" --wait` to launch it first, or open a document."}
    if not r["ok"]:
        return {"ok": False, "error": f"Cannot find process '{app}': {r.get('error', 'not running')}"}
    return None


def cmd_window_move(args):
    err = _window_guard(args.app)
    if err:
        return err
    return run_osascript(f'''
tell application "System Events"
    tell process "{args.app}"
        set position of window 1 to {{{args.x}, {args.y}}}
    end tell
end tell''')


def cmd_window_resize(args):
    err = _window_guard(args.app)
    if err:
        return err
    return run_osascript(f'''
tell application "System Events"
    tell process "{args.app}"
        set size of window 1 to {{{args.w}, {args.h}}}
    end tell
end tell''')


def cmd_window_fullscreen(args):
    # Activate app then toggle fullscreen via menu shortcut
    run_osascript(f'tell application "{args.app}" to activate')
    return run_osascript('''
tell application "System Events"
    keystroke "f" using {command down, control down}
end tell''')


def cmd_window_left(args):
    """Snap window to left half of screen."""
    err = _window_guard(args.app)
    if err:
        return err
    sw, sh = get_screen_size()
    half_w = sw // 2
    run_osascript(f'tell application "{args.app}" to activate')
    return run_osascript(f'''
tell application "System Events"
    tell process "{args.app}"
        set position of window 1 to {{0, 25}}
        set size of window 1 to {{{half_w}, {sh - 25}}}
    end tell
end tell''')


def cmd_window_right(args):
    """Snap window to right half of screen."""
    err = _window_guard(args.app)
    if err:
        return err
    sw, sh = get_screen_size()
    half_w = sw // 2
    run_osascript(f'tell application "{args.app}" to activate')
    return run_osascript(f'''
tell application "System Events"
    tell process "{args.app}"
        set position of window 1 to {{{half_w}, 25}}
        set size of window 1 to {{{half_w}, {sh - 25}}}
    end tell
end tell''')


def cmd_window_center(args):
    """Center window on screen."""
    err = _window_guard(args.app)
    if err:
        return err
    sw, sh = get_screen_size()
    r = run_osascript(f'''
tell application "System Events"
    tell process "{args.app}"
        set winSize to size of window 1
        return (item 1 of winSize as text) & "," & (item 2 of winSize as text)
    end tell
end tell''')
    if r["ok"]:
        parts = r["output"].split(",")
        ww, wh = int(parts[0]), int(parts[1])
        cx = (sw - ww) // 2
        cy = (sh - wh) // 2
        return run_osascript(f'''
tell application "System Events"
    tell process "{args.app}"
        set position of window 1 to {{{cx}, {cy}}}
    end tell
end tell''')
    return r


def cmd_window_minimize(args):
    err = _window_guard(args.app)
    if err:
        return err
    return run_osascript(f'''
tell application "System Events"
    tell process "{args.app}"
        click button 3 of window 1
    end tell
end tell''')


def cmd_window_restore(args):
    # Unminimize by activating
    return run_osascript(f'''
tell application "{args.app}" to activate''')


# ============================================================
# COMMANDS — Screenshot Variants (V2.0)
# ============================================================

def cmd_screenshot_window(args):
    """Screenshot of frontmost window only (non-interactive)."""
    target = args.path or "/tmp/screenshot_window.png"
    # Get frontmost window bounds via System Events — try multiple approaches
    r = run_osascript('''
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    try
        set winPos to position of window 1 of frontApp
        set winSize to size of window 1 of frontApp
        return (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "," & (item 1 of winSize as text) & "," & (item 2 of winSize as text)
    on error
        -- Try getting any visible window
        repeat with proc in (every process whose visible is true)
            try
                set winPos to position of window 1 of proc
                set winSize to size of window 1 of proc
                return (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "," & (item 1 of winSize as text) & "," & (item 2 of winSize as text)
            end try
        end repeat
        return "none"
    end try
end tell''', timeout=30)
    if r["ok"] and r["output"] != "none":
        parts = r["output"].split(",")
        if len(parts) == 4:
            x, y, w, h = [p.strip() for p in parts]
            result = run_shell(["screencapture", "-x", "-R", f"{x},{y},{w},{h}", target])
            if result["ok"]:
                result["output"] = f"Window screenshot saved to {target}"
                result["file"] = target
            return result
    # Fallback to full screenshot
    result = run_shell(["screencapture", "-x", target])
    if result["ok"]:
        result["output"] = f"Full screenshot saved to {target} (no visible window found)"
        result["file"] = target
    return result


# ============================================================
# COMMANDS — Screen Recording (V2.0)
# ============================================================

def cmd_record_start(args):
    """Start screen recording using screencapture."""
    target = args.path or "/tmp/recording.mov"
    if os.path.exists(RECORD_PID_FILE):
        return {"ok": False, "error": "Recording already in progress. Use record-stop first."}
    # Start screencapture in video mode as background process
    proc = subprocess.Popen(
        ["screencapture", "-v", "-x", target],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    with open(RECORD_PID_FILE, "w") as f:
        f.write(f"{proc.pid}\n{target}")
    return {"ok": True, "output": f"Recording started (PID {proc.pid}). Saving to {target}", "file": target}


def cmd_record_stop(args):
    """Stop active screen recording."""
    if not os.path.exists(RECORD_PID_FILE):
        return {"ok": False, "error": "No active recording found."}
    with open(RECORD_PID_FILE) as f:
        lines = f.read().strip().split("\n")
    pid = int(lines[0])
    target = lines[1] if len(lines) > 1 else "/tmp/recording.mov"
    try:
        os.kill(pid, signal.SIGINT)  # Graceful stop — finishes writing the file
    except ProcessLookupError:
        pass
    os.remove(RECORD_PID_FILE)
    return {"ok": True, "output": f"Recording stopped. File: {target}", "file": target}


# ============================================================
# COMMANDS — System Toggles (V2.0)
# ============================================================

def cmd_dark_mode(args):
    if args.toggle:
        return run_osascript('''
tell application "System Events"
    tell appearance preferences
        set dark mode to not dark mode
        if dark mode then
            return "Dark mode: ON"
        else
            return "Dark mode: OFF"
        end if
    end tell
end tell''')
    elif args.on:
        return run_osascript('tell application "System Events" to tell appearance preferences to set dark mode to true')
    elif args.off:
        return run_osascript('tell application "System Events" to tell appearance preferences to set dark mode to false')
    # Default: toggle
    return run_osascript('''
tell application "System Events"
    tell appearance preferences
        set dark mode to not dark mode
        if dark mode then
            return "Dark mode: ON"
        else
            return "Dark mode: OFF"
        end if
    end tell
end tell''')


def cmd_dnd(args):
    """Toggle Do Not Disturb (Focus mode)."""
    if args.on:
        # Use shortcuts — DND via Control Center simulation
        return run_shell(["shortcuts", "run", "Turn On Focus"], timeout=5) if _has_shortcut("Turn On Focus") else \
            run_osascript('''
do shell script "defaults -currentHost write com.apple.notificationcenterui doNotDisturb -boolean true && killall NotificationCenter 2>/dev/null; true"
''')
    else:
        return run_shell(["shortcuts", "run", "Turn Off Focus"], timeout=5) if _has_shortcut("Turn Off Focus") else \
            run_osascript('''
do shell script "defaults -currentHost write com.apple.notificationcenterui doNotDisturb -boolean false && killall NotificationCenter 2>/dev/null; true"
''')


def _has_shortcut(name):
    """Check if a Shortcuts.app shortcut exists."""
    r = run_shell(["shortcuts", "list"], timeout=5)
    return r["ok"] and name in r.get("output", "")


def cmd_wifi(args):
    # networksetup works on all macOS versions
    if args.on:
        return run_shell(["networksetup", "-setairportpower", "en0", "on"])
    else:
        return run_shell(["networksetup", "-setairportpower", "en0", "off"])


def cmd_bluetooth(args):
    # blueutil is common, fallback to defaults
    r = run_shell(["which", "blueutil"])
    if r["ok"]:
        flag = "1" if args.on else "0"
        return run_shell(["blueutil", "--power", flag])
    # Fallback: use defaults (less reliable)
    val = "1" if args.on else "0"
    return run_osascript(f'do shell script "defaults write /Library/Preferences/com.apple.Bluetooth ControllerPowerState -int {val} && killall -HUP blued 2>/dev/null; true" with administrator privileges')


def cmd_brightness(args):
    level = max(0, min(100, args.level))
    val = level / 100.0
    # Method 1: brightness CLI (if installed)
    r = run_shell(["which", "brightness"])
    if r["ok"]:
        return run_shell(["brightness", str(val)])
    # Method 2: DisplayServices private framework (works on macOS 10.14+)
    py_script = f"""
import ctypes, ctypes.util
try:
    lib = ctypes.cdll.LoadLibrary('/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices')
    lib.DisplayServicesSetBrightness.argtypes = [ctypes.c_int, ctypes.c_float]
    lib.DisplayServicesSetBrightness(0, ctypes.c_float({val}))
    print("Brightness set to {level}%")
except Exception as e:
    print(f"ERROR: {{e}}")
    raise
"""
    r2 = run_shell(["python3", "-c", py_script])
    if r2["ok"] and "ERROR" not in r2.get("output", ""):
        return {"ok": True, "output": f"Brightness set to {level}%"}
    return {"ok": False, "error": f"Brightness control failed. Install brightness CLI: brew install brightness"}


def cmd_mute(args):
    if args.toggle:
        return run_osascript('''
set curVol to output muted of (get volume settings)
if curVol then
    set volume without output muted
    return "Unmuted"
else
    set volume with output muted
    return "Muted"
end if''')
    elif args.on:
        return run_osascript("set volume with output muted")
    elif args.off:
        return run_osascript("set volume without output muted")
    # Default: toggle
    return run_osascript('''
set curVol to output muted of (get volume settings)
if curVol then
    set volume without output muted
    return "Unmuted"
else
    set volume with output muted
    return "Muted"
end if''')


def cmd_sleep_display(args):
    return run_shell(["pmset", "displaysleepnow"])


def cmd_lock_screen(args):
    return run_osascript('''
tell application "System Events" to keystroke "q" using {command down, control down}''')


def cmd_trash_empty(args):
    return run_osascript('''
tell application "Finder"
    empty trash
end tell''')


def cmd_battery(args):
    r = run_shell(["pmset", "-g", "batt"])
    if r["ok"]:
        output = r["output"]
        # Parse: "Now drawing from 'Battery Power'" and percentage
        info = {}
        for line in output.split("\n"):
            if "%" in line:
                # e.g., "-InternalBattery-0 (id=...)	78%; charging; 1:23 remaining"
                parts = line.split("\t")
                if len(parts) >= 2:
                    detail = parts[1].strip()
                    pct = detail.split(";")[0].strip()
                    info["percentage"] = pct
                    info["status"] = detail
            if "drawing from" in line.lower():
                info["source"] = line.strip()
        r["output"] = f"{info.get('percentage', '?')} — {info.get('status', output)}"
        r["detail"] = info
    return r


# ============================================================
# COMMANDS — Clipboard (V2.0)
# ============================================================

def cmd_clipboard_read(args):
    r = run_shell(["pbpaste"])
    if r["ok"]:
        content = r["output"]
        if not content:
            return {"ok": True, "output": "(clipboard is empty)"}
        # Truncate for safety
        if len(content) > 5000:
            return {"ok": True, "output": content[:5000] + f"\n...(truncated, {len(content)} chars total)"}
    return r


def cmd_clipboard_write(args):
    try:
        proc = subprocess.run(
            ["pbcopy"],
            input=args.text, text=True, timeout=5
        )
        if proc.returncode == 0:
            return {"ok": True, "output": f"Copied {len(args.text)} chars to clipboard."}
        return {"ok": False, "error": "pbcopy failed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# COMMANDS — System Info (V2.0)
# ============================================================

def cmd_sysinfo(args):
    """Comprehensive system info snapshot."""
    info = {}

    # Battery
    r = run_shell(["pmset", "-g", "batt"])
    if r["ok"]:
        for line in r["output"].split("\n"):
            if "%" in line:
                parts = line.split("\t")
                if len(parts) >= 2:
                    info["battery"] = parts[1].strip()

    # Disk space
    r = run_shell(["df", "-h", "/"])
    if r["ok"]:
        lines = r["output"].strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 5:
                info["disk"] = f"{parts[3]} free of {parts[1]} ({parts[4]} used)"

    # Memory
    r = run_shell(["vm_stat"])
    if r["ok"]:
        pages = {}
        for line in r["output"].split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                val = val.strip().rstrip(".")
                try:
                    pages[key.strip()] = int(val)
                except ValueError:
                    pass
        page_size = 16384  # Apple Silicon default
        free = pages.get("Pages free", 0) * page_size
        active = pages.get("Pages active", 0) * page_size
        inactive = pages.get("Pages inactive", 0) * page_size
        wired = pages.get("Pages wired down", 0) * page_size
        used_gb = (active + wired) / (1024 ** 3)
        total_gb = (free + active + inactive + wired) / (1024 ** 3)
        info["memory"] = f"{used_gb:.1f} GB used of ~{total_gb:.1f} GB"

    # CPU load
    r = run_shell(["sysctl", "-n", "vm.loadavg"])
    if r["ok"]:
        info["cpu_load"] = r["output"].strip("{ }")

    # Uptime
    r = run_shell(["uptime"])
    if r["ok"]:
        info["uptime"] = r["output"].strip()

    # WiFi network
    r = run_shell(["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"], timeout=5)
    if r["ok"]:
        for line in r["output"].split("\n"):
            if "SSID" in line and "BSSID" not in line:
                info["wifi"] = line.split(":")[-1].strip()

    # Display
    r = run_shell(["system_profiler", "SPDisplaysDataType"], timeout=5)
    if r["ok"]:
        for line in r["output"].split("\n"):
            if "Resolution" in line:
                info["display"] = line.split(":")[-1].strip()
                break

    # Format output
    lines = []
    labels = {
        "battery": "Battery", "disk": "Disk", "memory": "RAM",
        "cpu_load": "CPU Load", "uptime": "Uptime", "wifi": "WiFi",
        "display": "Display"
    }
    for key, label in labels.items():
        if key in info:
            lines.append(f"{label}: {info[key]}")

    return {"ok": True, "output": "\n".join(lines) if lines else "No system info available", "detail": info}


# ============================================================
# COMMANDS — File Operations (V2.1)
# ============================================================

def cmd_list_files(args):
    """List files in a directory."""
    path = args.path or os.path.expanduser("~")
    flags = ["-la"]
    if args.recursive:
        flags = ["-laR"]
    r = run_shell(["ls"] + flags + [path])
    if r["ok"]:
        lines = r["output"].split("\n")
        if len(lines) > 100:
            r["output"] = "\n".join(lines[:100]) + f"\n...(truncated, {len(lines)} total lines)"
    return r


def cmd_read_file(args):
    """Read contents of a file (text only, truncated at 10KB)."""
    path = os.path.expanduser(args.path)
    if not os.path.isfile(path):
        return {"ok": False, "error": f"File not found: {path}"}
    try:
        with open(path, "r", errors="replace") as f:
            content = f.read(10240)
        truncated = os.path.getsize(path) > 10240
        return {"ok": True, "output": content + ("\n...(truncated)" if truncated else "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_write_file(args):
    """Write text content to a file."""
    path = os.path.expanduser(args.path)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(args.content)
        return {"ok": True, "output": f"Wrote {len(args.content)} chars to {path}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_move_file(args):
    """Move or rename a file/directory."""
    import shutil
    src = os.path.expanduser(args.src)
    dst = os.path.expanduser(args.dst)
    try:
        shutil.move(src, dst)
        return {"ok": True, "output": f"Moved {src} → {dst}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_copy_file(args):
    """Copy a file or directory."""
    import shutil
    src = os.path.expanduser(args.src)
    dst = os.path.expanduser(args.dst)
    try:
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return {"ok": True, "output": f"Copied {src} → {dst}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_delete_file(args):
    """Delete a file (not directories, for safety)."""
    import shutil
    path = os.path.expanduser(args.path)
    if not os.path.exists(path):
        return {"ok": False, "error": f"Path not found: {path}"}
    try:
        if os.path.isdir(path):
            if args.force:
                shutil.rmtree(path)
                return {"ok": True, "output": f"Deleted directory {path}"}
            return {"ok": False, "error": f"{path} is a directory. Use --force to delete recursively."}
        os.remove(path)
        return {"ok": True, "output": f"Deleted {path}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_search_files(args):
    """Search files using Spotlight (mdfind)."""
    cmd = ["mdfind"]
    if args.dir:
        cmd += ["-onlyin", os.path.expanduser(args.dir)]
    cmd.append(args.query)
    r = run_shell(cmd, timeout=15)
    if r["ok"]:
        lines = r["output"].split("\n")
        lines = [l for l in lines if l.strip()]
        if len(lines) > 50:
            r["output"] = "\n".join(lines[:50]) + f"\n...(truncated, {len(lines)} total results)"
        elif not lines:
            r["output"] = "No files found."
    return r


def cmd_reveal_in_finder(args):
    """Reveal a file/folder in Finder."""
    p = os.path.expanduser(args.path)
    # Escape path for AppleScript (handle spaces, special chars)
    safe_path = p.replace('\\', '\\\\').replace('"', '\\"')
    return run_osascript(f'''
tell application "Finder"
    reveal POSIX file "{safe_path}"
    activate
end tell''')


# ============================================================
# COMMANDS — Process Management (V2.1)
# ============================================================

def cmd_list_processes(args):
    """List running processes, sorted by CPU or memory."""
    sort_flag = "-m" if args.sort == "mem" else "-r"
    r = run_shell(["ps", "aux", "--sort", sort_flag] if sys.platform == "linux" else ["ps", "aux"])
    if not r["ok"]:
        return r
    lines = r["output"].split("\n")
    # Sort by CPU% (column 3) descending on macOS
    if args.sort == "cpu" and len(lines) > 1:
        header = lines[0]
        procs = sorted(lines[1:], key=lambda l: float(l.split()[2]) if len(l.split()) > 2 else 0, reverse=True)
        lines = [header] + procs
    if args.limit:
        lines = lines[:args.limit + 1]  # +1 for header
    r["output"] = "\n".join(lines)
    return r


def cmd_kill_process(args):
    """Kill a process by name or PID."""
    if args.pid:
        r = run_shell(["kill", "-9", str(args.pid)])
        if r["ok"]:
            r["output"] = f"Killed PID {args.pid}"
        return r
    if args.name:
        r = run_shell(["pkill", "-f", args.name])
        if r["ok"]:
            r["output"] = f"Killed processes matching '{args.name}'"
        return r
    return {"ok": False, "error": "Specify --pid or --name"}


# ============================================================
# COMMANDS — Advanced Input (V2.1)
# ============================================================

def cmd_right_click(args):
    """Right-click at screen coordinates."""
    return run_mousetool(["rclick", args.x, args.y])


def cmd_double_click(args):
    """Double-click at screen coordinates."""
    return run_mousetool(["dclick", args.x, args.y])


def cmd_scroll(args):
    """Scroll up/down by amount."""
    return run_mousetool(["scroll", args.direction, args.amount])


def cmd_mouse_move(args):
    """Move mouse cursor to coordinates (instant)."""
    return run_mousetool(["move", args.x, args.y])


def cmd_mouse_animate(args):
    """Smoothly animate the mouse cursor to target coordinates with ease-in-out.
    Visually shows the cursor traveling across the screen — great for demonstrations."""
    duration = max(0.1, min(5.0, float(args.duration)))
    duration_ms = int(duration * 1000)
    timeout = max(10, int(duration) + 5)
    return run_mousetool(["animate", args.x, args.y, duration_ms], timeout=timeout)


def cmd_drag(args):
    """Click and drag from (x1,y1) to (x2,y2) with smooth animated movement."""
    duration = max(0.1, min(5.0, float(args.duration)))
    duration_ms = int(duration * 1000)
    timeout = max(10, int(duration) + 5)
    return run_mousetool(["drag", args.x1, args.y1, args.x2, args.y2, duration_ms], timeout=timeout)


# ============================================================
# COMMANDS — Audio Devices (V2.1)
# ============================================================

def cmd_list_audio(args):
    """List audio input/output devices."""
    r = run_shell(["system_profiler", "SPAudioDataType"], timeout=30)
    if not r["ok"]:
        return r
    # Parse into cleaner format
    devices = []
    current = {}
    for line in r["output"].split("\n"):
        line = line.strip()
        if not line:
            if current:
                devices.append(current)
                current = {}
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            current[key.strip()] = val.strip()
    if current:
        devices.append(current)
    names = [d.get("Default Output Device", d.get("Default Input Device", str(d))) for d in devices if d]
    r["output"] = "\n".join(names) if names else r["output"]
    return r


def cmd_switch_audio(args):
    """Switch audio output device using SwitchAudioSource (if installed)."""
    r = run_shell(["which", "SwitchAudioSource"])
    if r["ok"]:
        return run_shell(["SwitchAudioSource", "-s", args.device])
    return {"ok": False, "error": "Install SwitchAudioSource: brew install switchaudio-osx"}


# ============================================================
# COMMANDS — Network (V2.1)
# ============================================================

def cmd_get_ip(args):
    """Get local and public IP addresses."""
    info = {}
    r = run_shell(["ipconfig", "getifaddr", "en0"])
    if r["ok"]:
        info["local_wifi"] = r["output"].strip()
    r = run_shell(["curl", "-s", "https://api.ipify.org"], timeout=30)
    if r["ok"]:
        info["public"] = r["output"].strip()
    if info:
        parts = [f"Local: {info.get('local_wifi', '?')}", f"Public: {info.get('public', '?')}"]
        return {"ok": True, "output": " | ".join(parts), "detail": info}
    return {"ok": False, "error": "Could not determine IP"}


def cmd_ping(args):
    """Ping a host."""
    count = str(args.count or 3)
    r = run_shell(["ping", "-c", count, args.host], timeout=30)
    return r


# ============================================================
# COMMANDS — Power (V2.1 — Destructive, use with confirmation)
# ============================================================

def cmd_shutdown(args):
    """Shut down the Mac. Requires confirmation flag."""
    if not args.confirm:
        return {"ok": False, "error": "Destructive action. Add --confirm to proceed."}
    return run_osascript('tell application "System Events" to shut down')


def cmd_restart(args):
    """Restart the Mac. Requires confirmation flag."""
    if not args.confirm:
        return {"ok": False, "error": "Destructive action. Add --confirm to proceed."}
    return run_osascript('tell application "System Events" to restart')


def cmd_logout(args):
    """Log out the current user. Requires confirmation flag."""
    if not args.confirm:
        return {"ok": False, "error": "Destructive action. Add --confirm to proceed."}
    return run_osascript('tell application "System Events" to log out')


# ============================================================
# COMMANDS — Permissions Setup (V2.1)
# ============================================================

def cmd_setup_permissions(args):
    """Trigger all common permission prompts at once so macOS remembers them.
    Run this once — click Allow on each popup. After that, no more popups."""
    results = []

    # 1. Accessibility (System Events — keystrokes, clicks)
    r = run_osascript('''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    return "Accessibility: OK — frontmost app is " & frontApp
end tell''', timeout=30)
    results.append(f"Accessibility: {'PASS' if r['ok'] else 'NEEDS PERMISSION — click Allow'}")

    # 2. Automation — Chrome
    r = run_osascript('''
tell application "Google Chrome"
    return "Chrome automation: OK — " & (count of windows) & " windows"
end tell''', timeout=30)
    results.append(f"Chrome control: {'PASS' if r['ok'] else 'NEEDS PERMISSION — click Allow'}")

    # 3. Automation — Finder
    r = run_osascript('''
tell application "Finder"
    return "Finder automation: OK"
end tell''', timeout=30)
    results.append(f"Finder control: {'PASS' if r['ok'] else 'NEEDS PERMISSION — click Allow'}")

    # 4. Automation — Safari
    r = run_osascript('''
tell application "Safari"
    return "Safari automation: OK"
end tell''', timeout=30)
    results.append(f"Safari control: {'PASS' if r['ok'] else 'NEEDS PERMISSION — click Allow'}")

    # 5. Automation — Mail
    r = run_osascript('''
tell application "Mail"
    return "Mail automation: OK"
end tell''', timeout=30)
    results.append(f"Mail control: {'PASS' if r['ok'] else 'NEEDS PERMISSION — click Allow'}")

    # 6. Automation — System Preferences/Settings
    r = run_osascript('''
tell application "System Settings"
    return "Settings automation: OK"
end tell''', timeout=30)
    results.append(f"System Settings: {'PASS' if r['ok'] else 'NEEDS PERMISSION — click Allow'}")

    # 7. Automation — Notes
    r = run_osascript('''
tell application "Notes"
    return "Notes automation: OK"
end tell''', timeout=30)
    results.append(f"Notes control: {'PASS' if r['ok'] else 'NEEDS PERMISSION — click Allow'}")

    # 8. Automation — Calendar
    r = run_osascript('''
tell application "Calendar"
    return "Calendar automation: OK"
end tell''', timeout=30)
    results.append(f"Calendar control: {'PASS' if r['ok'] else 'NEEDS PERMISSION — click Allow'}")

    # 9. Automation — Messages (if CC wants)
    r = run_osascript('''
tell application "Messages"
    return "Messages automation: OK"
end tell''', timeout=30)
    results.append(f"Messages control: {'PASS' if r['ok'] else 'NEEDS PERMISSION — click Allow'}")

    # 10. Screen recording permission test
    r = run_shell(["screencapture", "-x", "/tmp/_perm_test.png"])
    if r["ok"] and os.path.exists("/tmp/_perm_test.png"):
        sz = os.path.getsize("/tmp/_perm_test.png")
        results.append(f"Screen capture: {'PASS' if sz > 1000 else 'BLANK — grant Screen Recording permission'}")
        os.remove("/tmp/_perm_test.png")
    else:
        results.append("Screen capture: NEEDS PERMISSION")

    # 11. Notification
    r = run_osascript('display notification "Permissions setup complete" with title "Bravo"')
    results.append(f"Notifications: {'PASS' if r['ok'] else 'NEEDS PERMISSION'}")

    summary = "\n".join(results)
    all_pass = all("PASS" in r for r in results)
    return {
        "ok": True,
        "output": f"{'All permissions granted!' if all_pass else 'Some permissions need approval — click Allow on any popups that appeared, then run again.'}\n\n{summary}"
    }


# ============================================================
# BROWSER CONTROL (Chrome via AppleScript + JavaScript)
# ============================================================

def _ensure_chrome_running():
    """Launch Chrome with the correct profile if not already running. Dismisses profile picker."""
    import subprocess as _sp
    # Check if Chrome is running
    r = _sp.run(['pgrep', '-x', 'Google Chrome'], capture_output=True)
    if r.returncode != 0:
        # Chrome not running — launch with the right profile to skip profile picker
        _sp.Popen(['open', '-a', 'Google Chrome', '--args', '--profile-directory=Profile 1'],
                   stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        import time; time.sleep(3)


def cmd_browser_open(args):
    """Open URL in Chrome and wait for page to load. Auto-launches with correct profile."""
    url = args.url
    _ensure_chrome_running()
    script = f'''
tell application "Google Chrome"
    activate
end tell

-- Dismiss profile picker popup if it somehow appears
delay 0.3
tell application "Google Chrome"
    repeat with w in every window
        try
            if title of w contains "using Chrome" or title of w contains "Choose a profile" then
                close w
            end if
        end try
    end repeat
end tell

tell application "Google Chrome"
    if (count of windows) = 0 then
        make new window
    end if
    set URL of active tab of window 1 to "{url}"
end tell

-- Wait for page to load (up to 20 seconds)
delay 1
set maxWait to 20
set waited to 0
repeat while waited < maxWait
    tell application "Google Chrome"
        set isLoading to loading of active tab of window 1
    end tell
    if not isLoading then exit repeat
    delay 1
    set waited to waited + 1
end repeat

tell application "Google Chrome"
    return title of active tab of window 1
end tell
'''
    return run_osascript(script, timeout=30)


def cmd_browser_js(args):
    """Execute JavaScript in Chrome's active tab. Requires: Chrome > View > Developer > Allow JavaScript from Apple Events."""
    js_code = args.script
    # Use json.dumps to safely escape the JS string for AppleScript embedding
    import json
    escaped = json.dumps(js_code)[1:-1]  # strip outer quotes, keep escaped internals
    script = f'''
tell application "Google Chrome"
    if (count of windows) = 0 then return "error: Chrome has no open windows"
    set jsResult to execute active tab of window 1 javascript "{escaped}"
    return jsResult
end tell
'''
    return run_osascript(script, timeout=15)


def cmd_browser_tab_url(args):
    """Get the URL of Chrome's active tab."""
    script = '''
tell application "Google Chrome"
    if (count of windows) = 0 then return "Chrome has no open windows"
    return URL of active tab of window 1
end tell
'''
    return run_osascript(script)


def cmd_browser_tab_title(args):
    """Get the title of Chrome's active tab."""
    script = '''
tell application "Google Chrome"
    if (count of windows) = 0 then return "Chrome has no open windows"
    return title of active tab of window 1
end tell
'''
    return run_osascript(script)


def cmd_browser_new_tab(args):
    """Open a new tab in Chrome with the given URL."""
    url = getattr(args, 'url', 'about:blank')
    script = f'''
tell application "Google Chrome"
    activate
    if (count of windows) = 0 then
        make new window
    else
        tell window 1
            make new tab with properties {{URL:"{url}"}}
        end tell
    end if
end tell

delay 1
set maxWait to 15
set waited to 0
repeat while waited < maxWait
    tell application "Google Chrome"
        set isLoading to loading of active tab of window 1
    end tell
    if not isLoading then exit repeat
    delay 1
    set waited to waited + 1
end repeat

tell application "Google Chrome"
    return title of active tab of window 1
end tell
'''
    return run_osascript(script, timeout=25)


def cmd_browser_close_tab(args):
    """Close the active tab in Chrome."""
    script = '''
tell application "Google Chrome"
    tell window 1
        close active tab
    end tell
    return "tab closed"
end tell
'''
    return run_osascript(script)


def cmd_browser_close_others(args):
    """Close all Chrome tabs and windows EXCEPT the active tab. Kills ad/popup tabs."""
    script = '''
tell application "Google Chrome"
    -- Close all windows except the first one
    set winCount to count of windows
    if winCount > 1 then
        repeat with i from winCount to 2 by -1
            close window i
        end repeat
    end if
    -- In the remaining window, close all tabs except the active one
    tell window 1
        set activeIdx to active tab index
        set tabCount to count of tabs
        repeat with i from tabCount to 1 by -1
            if i is not activeIdx then
                close tab i
            end if
        end repeat
    end tell
    return "closed all other tabs/windows"
end tell
'''
    return run_osascript(script, timeout=10)


def cmd_browser_list_tabs(args):
    """List all open tabs in Chrome."""
    script = '''
tell application "Google Chrome"
    set tabList to ""
    repeat with w in windows
        set tabIndex to 1
        repeat with t in tabs of w
            set tabList to tabList & tabIndex & ". " & title of t & " | " & URL of t & linefeed
            set tabIndex to tabIndex + 1
        end repeat
    end repeat
    return tabList
end tell
'''
    return run_osascript(script)


def cmd_browser_switch_tab(args):
    """Switch to a specific tab by number."""
    tab_num = args.tab
    script = f'''
tell application "Google Chrome"
    tell window 1
        set active tab index to {tab_num}
    end tell
    return title of active tab of window 1
end tell
'''
    return run_osascript(script)


# ============================================================
# COMMANDS — Workflow Helpers (V2.2)
# ============================================================

def cmd_screen_size(args):
    """Return the main display resolution (width x height)."""
    w, h = get_screen_size()
    return {"ok": True, "output": f"{w}x{h}", "width": w, "height": h}


def cmd_youtube_play(args):
    """Atomic: open YouTube, search the query, click the first result, and let it play.
    One command — no multi-turn orchestration needed."""
    query = sanitize_applescript_string(args.query)
    # Proper URL encoding (handles &, %, special chars, not just spaces)
    from urllib.parse import quote_plus
    encoded = quote_plus(query)
    search_url = f"https://www.youtube.com/results?search_query={encoded}"

    # Step 1 — navigate to search results
    r = run_osascript(f'''
tell application "Google Chrome"
    activate
    if (count of windows) = 0 then make new window
    set URL of active tab of window 1 to "{search_url}"
end tell
delay 1
tell application "Google Chrome"
    set maxWait to 20
    set waited to 0
    repeat while waited < maxWait
        if not (loading of active tab of window 1) then exit repeat
        delay 1
        set waited to waited + 1
    end repeat
end tell
return "search loaded"
''', timeout=30)

    if not r["ok"]:
        return r

    # Step 2 — click the first video result via JavaScript
    r2 = run_osascript('''
tell application "Google Chrome"
    set jsResult to execute active tab of window 1 javascript "
        var v = document.querySelector('ytd-video-renderer a#video-title');
        if (!v) v = document.querySelector('a#video-title');
        if (v) { var t = v.textContent.trim(); v.click(); t; } else { 'no_result'; }
    "
    return jsResult
end tell
''', timeout=30)

    if not r2["ok"]:
        return r2

    clicked_title = r2.get("output", "video")
    if clicked_title == "no_result":
        return {"ok": False, "error": f"No YouTube video results found for: {query}"}

    # Step 3 — wait for video page to load
    run_osascript('''
tell application "Google Chrome"
    delay 2
    set waited to 0
    repeat while waited < 15
        if not (loading of active tab of window 1) then exit repeat
        delay 1
        set waited to waited + 1
    end repeat
end tell
''', timeout=20)

    # Step 4 — dismiss any "Before you continue" or cookie dialogs, then ensure playback
    run_osascript('''
tell application "Google Chrome"
    execute active tab of window 1 javascript "
        var btn = document.querySelector('button[aria-label*=Accept], button[aria-label*=Agree], .yt-spec-button-shape-next--filled');
        if (btn) btn.click();
        var player = document.querySelector('video');
        if (player && player.paused) player.play();
    "
end tell
''', timeout=8)

    return {"ok": True, "output": f"YouTube playing: {clicked_title}\nSearch query: {query}"}


# ============================================================
# CONTACTS, FACETIME, MESSAGES — Native macOS APIs (no UI automation)
# ============================================================

def cmd_contacts_search(args):
    """Search macOS Contacts by name. Returns phone numbers and emails."""
    name = sanitize_applescript_string(args.name)
    # Launch Contacts quietly if not running
    run_shell(["open", "-gja", "Contacts"])
    import time; time.sleep(1)
    r = run_osascript(f'''
tell application "Contacts"
    set matchedPeople to every person whose name contains "{name}"
    if (count of matchedPeople) = 0 then return "NO_MATCHES"
    set results to ""
    repeat with p in matchedPeople
        set fn to first name of p
        set ln to last name of p
        if fn is missing value then set fn to ""
        if ln is missing value then set ln to ""
        set fullName to fn & " " & ln
        set phoneStr to ""
        repeat with ph in phones of p
            set phoneStr to phoneStr & (value of ph) & ", "
        end repeat
        set emailStr to ""
        repeat with em in emails of p
            set emailStr to emailStr & (value of em) & ", "
        end repeat
        set results to results & fullName & " | phone: " & phoneStr & " | email: " & emailStr & linefeed
    end repeat
    return results
end tell
''', timeout=30)
    if not r["ok"]:
        return r
    output = r.get("output", "").strip()
    if output == "NO_MATCHES":
        return {"ok": False, "error": f"No contacts found matching '{name}'"}
    contacts = []
    for line in output.strip().split("\n"):
        if "|" in line:
            parts = line.split("|")
            contact = {"name": parts[0].strip()}
            for part in parts[1:]:
                if "phone:" in part:
                    phones = [p.strip() for p in part.split("phone:")[1].split(",") if p.strip()]
                    contact["phones"] = phones
                if "email:" in part:
                    emails = [e.strip() for e in part.split("email:")[1].split(",") if e.strip()]
                    contact["emails"] = emails
            contacts.append(contact)
    r["contacts"] = contacts
    # Format for display
    lines = []
    for c in contacts:
        phones = ", ".join(c.get("phones", []))
        emails = ", ".join(c.get("emails", []))
        lines.append(f"{c['name']}: {phones} {emails}".strip())
    r["output"] = "\n".join(lines)
    return r


def cmd_facetime(args):
    """Initiate a FaceTime call. Pass a name, phone number, or email. Names auto-resolve via Contacts.
    Uses New FaceTime → type contact → select → click FaceTime button for a real call (not just the prompt)."""
    contact = args.contact.strip()
    audio_only = getattr(args, 'audio', False)
    # Resolve name to phone/email if needed (for the search field)
    search_term = contact
    resolved_name = contact
    if not contact.startswith("+") and "@" not in contact and not contact.replace("-","").replace(" ","").isdigit():
        # It's a name — we'll type it directly in the FaceTime search (it searches Contacts natively)
        search_term = contact
        resolved_name = contact
    # Use System Events to drive FaceTime UI — this actually initiates the call
    call_type = "Audio" if audio_only else "Video"
    safe_contact = sanitize_applescript_string(search_term)
    r = run_osascript(f'''
-- Launch FaceTime and wait for it to be fully ready
tell application "FaceTime" to activate
delay 2

-- Wait for window to appear (up to 10 seconds)
tell application "System Events"
    tell process "FaceTime"
        set maxWait to 10
        set waited to 0
        repeat while (count of windows) < 1 and waited < maxWait
            delay 1
            set waited to waited + 1
        end repeat
        if (count of windows) < 1 then return "error: FaceTime window did not appear"

        -- Click New FaceTime button (try multiple approaches)
        try
            click button "New FaceTime" of window 1
        on error
            -- Maybe the button has a different label — try all buttons
            set allBtns to buttons of window 1
            set found to false
            repeat with b in allBtns
                try
                    if name of b contains "New" or name of b contains "new" then
                        click b
                        set found to true
                        exit repeat
                    end if
                end try
            end repeat
            if not found then
                -- Last resort: Cmd+N for new call
                keystroke "n" using command down
            end if
        end try
    end tell
end tell

delay 1
-- Type the contact name/number
tell application "System Events"
    keystroke "{safe_contact}"
end tell

delay 2
-- Select first match from contact suggestions
tell application "System Events"
    key code 36
end tell

delay 1.5
-- Click the FaceTime call button (it's a radio button inside a radio group in the sheet)
tell application "System Events"
    tell process "FaceTime"
        try
            set s to sheet 1 of window 1
            set rg to radio group 1 of s
            click radio button 1 of rg
        on error
            -- Fallback: try clicking all radio buttons in the sheet
            try
                set allEls to entire contents of sheet 1 of window 1
                repeat with el in allEls
                    try
                        if class of el is radio button then
                            click el
                            exit repeat
                        end if
                    end try
                end repeat
            end try
        end try
    end tell
end tell

-- Wait for call to connect, then dismiss the "add people" dialog that appears
delay 2
tell application "System Events"
    key code 53 -- Escape to dismiss add-people dialog
end tell

return "Call initiated"
''', timeout=25)
    if r["ok"]:
        r["output"] = f"FaceTime {call_type.lower()} call initiated to {resolved_name}"
    return r


def cmd_imessage(args):
    """Send an iMessage via the Messages app. Pass a name, phone number, or email."""
    contact = args.contact.strip()
    text = args.text
    # If name given, look up in Contacts to get phone/email
    if not contact.startswith("+") and "@" not in contact and not contact.replace("-","").replace(" ","").isdigit():
        class FakeArgs:
            pass
        fa = FakeArgs()
        fa.name = contact
        cr = cmd_contacts_search(fa)
        if not cr.get("ok"):
            return {"ok": False, "error": f"Could not find '{contact}' in Contacts."}
        contacts = cr.get("contacts", [])
        if contacts and contacts[0].get("phones"):
            contact = contacts[0]["phones"][0]
        elif contacts and contacts[0].get("emails"):
            contact = contacts[0]["emails"][0]
        else:
            return {"ok": False, "error": f"No phone/email for '{contact}'"}
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    r = run_osascript(f'''
tell application "Messages"
    set targetService to (service 1 whose service type is iMessage)
    set targetBuddy to buddy "{contact}" of targetService
    send "{safe_text}" to targetBuddy
end tell
''', timeout=15)
    if r["ok"]:
        r["output"] = f"iMessage sent to {contact}: {text[:50]}"
    return r


# ============================================================
# NOTES — Create, search, read notes
# ============================================================

def cmd_notes_create(args):
    """Create a new note in Apple Notes."""
    title = sanitize_applescript_string(args.title)
    body = args.body.replace('\\', '\\\\').replace('"', '\\"') if args.body else ""
    folder = sanitize_applescript_string(getattr(args, 'folder', 'Notes') or 'Notes')
    r = run_osascript(f'''
tell application "Notes"
    tell account "iCloud"
        tell folder "{folder}"
            make new note with properties {{name:"{title}", body:"{body}"}}
        end tell
    end tell
end tell
''', timeout=30)
    if r["ok"]:
        r["output"] = f"Note created: {title}"
    return r


def cmd_notes_search(args):
    """Search Apple Notes by title."""
    query = sanitize_applescript_string(args.query)
    r = run_osascript(f'''
tell application "Notes"
    tell account "iCloud"
        tell folder "Notes"
            set matches to (every note whose name contains "{query}")
            set output to ""
            repeat with n in matches
                set output to output & (name of n) & " | " & (modification date of n as string) & linefeed
            end repeat
        end tell
    end tell
end tell
if output is "" then return "No notes found"
return output
''', timeout=30)
    return r


def cmd_notes_read(args):
    """Read the body of a note by title."""
    title = sanitize_applescript_string(args.title)
    r = run_osascript(f'''
tell application "Notes"
    tell account "iCloud"
        tell folder "Notes"
            set theNote to first note whose name is "{title}"
            return plaintext of theNote
        end tell
    end tell
end tell
''', timeout=30)
    return r


# ============================================================
# REMINDERS — Create, list, complete
# ============================================================

def cmd_reminder_create(args):
    """Create a reminder, optionally with a due date (e.g. 'tomorrow', '2026-04-15 9am')."""
    name = sanitize_applescript_string(args.name)
    body = sanitize_applescript_string(getattr(args, 'body', '') or '')
    list_name = sanitize_applescript_string(getattr(args, 'list', 'Reminders') or 'Reminders')
    due = getattr(args, 'due', None)
    due_script = ""
    if due:
        # Use Python to parse the date and pass it to AppleScript
        due_script = f'''
        set dueDate to current date
        try
            set dueDate to date "{sanitize_applescript_string(due)}"
        end try
        set due date of newReminder to dueDate
        set remind me date of newReminder to dueDate'''
    r = run_osascript(f'''
tell application "Reminders"
    set targetList to list 1
    tell targetList
        set newReminder to make new reminder with properties {{name:"{name}", body:"{body}"}}
        {due_script}
    end tell
end tell
return "Reminder created"
''', timeout=30)
    if r["ok"]:
        r["output"] = f"Reminder created: {name}" + (f" (due: {due})" if due else "")
    return r


def cmd_reminders_list(args):
    """List incomplete reminders."""
    list_name = sanitize_applescript_string(getattr(args, 'list', 'Reminders') or 'Reminders')
    r = run_osascript(f'''
tell application "Reminders"
    set targetList to list 1
    set incompleteItems to (every reminder in targetList whose completed is false)
    set output to ""
    repeat with r in incompleteItems
        set rName to name of r
        set rDue to ""
        try
            set rDue to due date of r as string
        end try
        set output to output & rName & " | due: " & rDue & linefeed
    end repeat
end tell
if output is "" then return "No incomplete reminders"
return output
''', timeout=30)
    return r


def cmd_reminder_complete(args):
    """Mark a reminder as complete by name."""
    name = sanitize_applescript_string(args.name)
    list_name = sanitize_applescript_string(getattr(args, 'list', 'Reminders') or 'Reminders')
    r = run_osascript(f'''
tell application "Reminders"
    set targetList to list 1
    set targetReminder to first reminder in targetList whose name is "{name}"
    set completed of targetReminder to true
end tell
return "Done"
''', timeout=30)
    if r["ok"]:
        r["output"] = f"Reminder completed: {name}"
    return r


# ============================================================
# MAPS — Search and directions via URL scheme
# ============================================================

def cmd_maps_search(args):
    """Search Apple Maps for a location."""
    from urllib.parse import quote_plus
    query = quote_plus(args.query)
    r = run_shell(["open", f"maps://?q={query}"])
    if r["ok"]:
        r["output"] = f"Maps opened: {args.query}"
    return r


def cmd_maps_directions(args):
    """Get directions in Apple Maps. Defaults to driving from current location."""
    from urllib.parse import quote_plus
    dest = quote_plus(args.to)
    mode = getattr(args, 'mode', 'd') or 'd'  # d=driving, w=walking, r=transit
    mode_flag = mode[0].lower() if mode else 'd'
    src = ""
    if getattr(args, 'from_addr', None):
        src = f"&saddr={quote_plus(args.from_addr)}"
    r = run_shell(["open", f"maps://?daddr={dest}{src}&dirflg={mode_flag}"])
    if r["ok"]:
        mode_name = {'d': 'driving', 'w': 'walking', 'r': 'transit'}.get(mode_flag, 'driving')
        r["output"] = f"Directions to {args.to} ({mode_name})"
    return r


# ============================================================
# MAIL — Compose, list unread, read
# ============================================================

def cmd_mail_send(args):
    """Compose and send an email via Apple Mail."""
    to_addr = sanitize_applescript_string(args.to)
    subject = sanitize_applescript_string(args.subject)
    body = args.body.replace('\\', '\\\\').replace('"', '\\"') if args.body else ""
    r = run_osascript(f'''
tell application "Mail"
    set theMessage to make new outgoing message with properties {{subject:"{subject}", content:"{body}", visible:false}}
    tell theMessage
        make new to recipient with properties {{address:"{to_addr}"}}
    end tell
    send theMessage
end tell
return "Email sent"
''', timeout=15)
    if r["ok"]:
        r["output"] = f"Email sent to {to_addr}: {subject}"
    return r


def cmd_mail_unread(args):
    """List unread emails."""
    limit = getattr(args, 'limit', 5) or 5
    r = run_osascript(f'''
tell application "Mail"
    set output to ""
    set unreadMsgs to (messages of inbox whose read status is false)
    set total to count of unreadMsgs
    set showing to {limit}
    if total < showing then set showing to total
    repeat with i from 1 to showing
        set msg to item i of unreadMsgs
        set output to output & (sender of msg) & " | " & (subject of msg) & linefeed
    end repeat
    return "(" & total & " unread total, showing " & showing & ")" & linefeed & output
end tell
''', timeout=45)
    return r


def cmd_mail_read(args):
    """Read the most recent unread email (or a specific one by subject)."""
    subject_filter = sanitize_applescript_string(getattr(args, 'subject', '') or '')
    if subject_filter:
        filter_clause = f'whose subject contains "{subject_filter}" and read status is false'
    else:
        filter_clause = 'whose read status is false'
    r = run_osascript(f'''
tell application "Mail"
    set inb to mailbox "INBOX" of account 1
    set msgs to (every message of inb {filter_clause})
    if (count of msgs) = 0 then return "No matching emails"
    set theMsg to item 1 of msgs
    set msgFrom to sender of theMsg
    set msgSubj to subject of theMsg
    set msgBody to content of theMsg
    if (length of msgBody) > 2000 then set msgBody to text 1 thru 2000 of msgBody & "... (truncated)"
    return msgFrom & linefeed & msgSubj & linefeed & linefeed & msgBody
end tell
''', timeout=15)
    return r


# ============================================================
# SHORTCUTS — Run macOS Shortcuts
# ============================================================

def cmd_shortcut_run(args):
    """Run a macOS Shortcut by name."""
    name = args.name
    input_text = getattr(args, 'input', None)
    if input_text:
        r = run_shell(["bash", "-c", f"echo {repr(input_text)} | shortcuts run {repr(name)}"], timeout=30)
    else:
        r = run_shell(["shortcuts", "run", name], timeout=30)
    if r["ok"]:
        r["output"] = r.get("output", "").strip() or f"Shortcut '{name}' executed"
    return r


def cmd_shortcut_list(args):
    """List all available macOS Shortcuts."""
    r = run_shell(["shortcuts", "list"])
    return r


# ============================================================
# SPOTIFY — Playback control
# ============================================================

def cmd_spotify(args):
    """Control Spotify playback: play, pause, next, previous, current, volume."""
    action = args.action
    if action == "play":
        query = getattr(args, 'query', None)
        if query:
            # Search and play via Spotify URI search
            from urllib.parse import quote
            r = run_osascript(f'''
tell application "Spotify"
    activate
    search for "{sanitize_applescript_string(query)}" with type "track"
end tell
''', timeout=30)
            # Fallback: just hit play
            if not r.get("ok"):
                r = run_osascript('tell application "Spotify" to play', timeout=5)
        else:
            r = run_osascript('tell application "Spotify" to play', timeout=5)
    elif action == "pause":
        r = run_osascript('tell application "Spotify" to pause', timeout=5)
    elif action == "next":
        r = run_osascript('tell application "Spotify" to next track', timeout=5)
    elif action == "previous":
        r = run_osascript('tell application "Spotify" to previous track', timeout=5)
    elif action == "current":
        r = run_osascript('''
tell application "Spotify"
    if player state is playing or player state is paused then
        set trackName to name of current track
        set artistName to artist of current track
        set albumName to album of current track
        return trackName & " by " & artistName & " (" & albumName & ")"
    else
        return "Nothing playing"
    end if
end tell
''', timeout=5)
    elif action == "volume":
        level = getattr(args, 'level', 50) or 50
        r = run_osascript(f'tell application "Spotify" to set sound volume to {level}', timeout=5)
        if r["ok"]:
            r["output"] = f"Spotify volume set to {level}"
    else:
        r = {"ok": False, "error": f"Unknown action: {action}"}
    return r


# ============================================================
# APPLE MUSIC — Playback control
# ============================================================

def cmd_music(args):
    """Control Apple Music: play, pause, next, previous, current, search, volume."""
    action = args.action
    if action == "play":
        query = getattr(args, 'query', None)
        if query:
            safe_q = sanitize_applescript_string(query)
            r = run_osascript(f'''
tell application "Music"
    set results to search playlist "Library" for "{safe_q}"
    if (count of results) > 0 then
        play item 1 of results
        return "Playing: " & (name of item 1 of results) & " by " & (artist of item 1 of results)
    else
        return "No results found for {safe_q}"
    end if
end tell
''', timeout=30)
        else:
            r = run_osascript('tell application "Music" to play', timeout=5)
    elif action == "pause":
        r = run_osascript('tell application "Music" to pause', timeout=5)
    elif action == "next":
        r = run_osascript('tell application "Music" to next track', timeout=5)
    elif action == "previous":
        r = run_osascript('tell application "Music" to previous track', timeout=5)
    elif action == "current":
        r = run_osascript('''
tell application "Music"
    if player state is playing or player state is paused then
        set trackName to name of current track
        set artistName to artist of current track
        return trackName & " by " & artistName
    else
        return "Nothing playing"
    end if
end tell
''', timeout=5)
    elif action == "volume":
        level = getattr(args, 'level', 50) or 50
        r = run_osascript(f'tell application "Music" to set sound volume to {level}', timeout=5)
        if r["ok"]:
            r["output"] = f"Music volume set to {level}"
    elif action == "search":
        safe_q = sanitize_applescript_string(getattr(args, 'query', ''))
        r = run_osascript(f'''
tell application "Music"
    set results to search playlist "Library" for "{safe_q}"
    set output to ""
    set i to 0
    repeat with t in results
        if i >= 10 then exit repeat
        set output to output & (name of t) & " by " & (artist of t) & linefeed
        set i to i + 1
    end repeat
end tell
if output is "" then return "No results"
return output
''', timeout=30)
    else:
        r = {"ok": False, "error": f"Unknown action: {action}"}
    return r


# ============================================================
# SYSTEM SETTINGS — Open specific pane
# ============================================================

def cmd_settings(args):
    """Open a specific System Settings pane."""
    pane_map = {
        "wifi": "com.apple.Wi-Fi-Settings.extension",
        "bluetooth": "com.apple.BluetoothSettings",
        "network": "com.apple.Network-Settings.extension",
        "notifications": "com.apple.Notifications-Settings.extension",
        "sound": "com.apple.Sound-Settings.extension",
        "display": "com.apple.Displays-Settings.extension",
        "displays": "com.apple.Displays-Settings.extension",
        "battery": "com.apple.Battery-Settings.extension",
        "privacy": "com.apple.settings.PrivacySecurity.extension",
        "security": "com.apple.settings.PrivacySecurity.extension",
        "keyboard": "com.apple.Keyboard-Settings.extension",
        "trackpad": "com.apple.Trackpad-Settings.extension",
        "appearance": "com.apple.Appearance-Settings.extension",
        "wallpaper": "com.apple.Wallpaper-Settings.extension",
        "dock": "com.apple.Desktop-Settings.extension",
        "desktop": "com.apple.Desktop-Settings.extension",
        "focus": "com.apple.Focus-Settings.extension",
        "accessibility": "com.apple.Accessibility-Settings.extension",
        "sharing": "com.apple.Sharing-Settings.extension",
        "update": "com.apple.Software-Update-Settings.extension",
        "software-update": "com.apple.Software-Update-Settings.extension",
        "apple-id": "com.apple.systempreferences.AppleIDSettings",
        "passwords": "com.apple.Passwords-Settings.extension",
        "login-items": "com.apple.LoginItems-Settings.extension",
        "airdrop": "com.apple.AirDrop-Handoff-Settings.extension",
        "spotlight": "com.apple.Spotlight-Settings.extension",
        "time-machine": "com.apple.Time-Machine-Settings.extension",
    }
    pane = args.pane.lower().strip()
    pane_id = pane_map.get(pane)
    if not pane_id:
        return {"ok": False, "error": f"Unknown pane '{pane}'. Available: {', '.join(sorted(pane_map.keys()))}"}
    r = run_shell(["open", f"x-apple.systempreferences:{pane_id}"])
    if r["ok"]:
        r["output"] = f"Opened Settings → {pane}"
    return r


# ============================================================
# MAIN
# ============================================================

def main():
    guard_macos()

    # Handle --json flag in any position (before or after subcommand)
    json_output = "--json" in sys.argv
    if json_output:
        sys.argv.remove("--json")

    parser = argparse.ArgumentParser(description="macOS Computer Control V2.0")
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- Original commands ----
    p = sub.add_parser("open", help="Open/activate an application")
    p.add_argument("--app", required=True)
    p.add_argument("--wait", action="store_true", help="Wait for app to become frontmost before returning")

    p = sub.add_parser("quit", help="Quit an application")
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

    # ---- Window management ----
    p = sub.add_parser("window-move", help="Move app window to x,y")
    p.add_argument("--app", required=True)
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)

    p = sub.add_parser("window-resize", help="Resize app window to w,h")
    p.add_argument("--app", required=True)
    p.add_argument("--w", type=int, required=True)
    p.add_argument("--h", type=int, required=True)

    p = sub.add_parser("window-fullscreen", help="Toggle fullscreen for app")
    p.add_argument("--app", required=True)

    p = sub.add_parser("window-left", help="Snap window to left half")
    p.add_argument("--app", required=True)

    p = sub.add_parser("window-right", help="Snap window to right half")
    p.add_argument("--app", required=True)

    p = sub.add_parser("window-center", help="Center window on screen")
    p.add_argument("--app", required=True)

    p = sub.add_parser("window-minimize", help="Minimize app window")
    p.add_argument("--app", required=True)

    p = sub.add_parser("window-restore", help="Restore/unminimize app window")
    p.add_argument("--app", required=True)

    # ---- Screenshot variants ----
    p = sub.add_parser("screenshot-window", help="Screenshot frontmost window only")
    p.add_argument("--path", help="Save path (default: /tmp/screenshot_window.png)")

    # ---- Screen recording ----
    p = sub.add_parser("record-start", help="Start screen recording")
    p.add_argument("--path", help="Save path (default: /tmp/recording.mov)")

    sub.add_parser("record-stop", help="Stop active screen recording")

    # ---- System toggles ----
    p = sub.add_parser("dark-mode", help="Toggle/set dark mode")
    p.add_argument("--on", action="store_true")
    p.add_argument("--off", action="store_true")
    p.add_argument("--toggle", action="store_true")

    p = sub.add_parser("dnd", help="Do Not Disturb on/off")
    p.add_argument("--on", action="store_true")
    p.add_argument("--off", action="store_true")

    p = sub.add_parser("wifi", help="WiFi on/off")
    p.add_argument("--on", action="store_true")
    p.add_argument("--off", action="store_true")

    p = sub.add_parser("bluetooth", help="Bluetooth on/off")
    p.add_argument("--on", action="store_true")
    p.add_argument("--off", action="store_true")

    p = sub.add_parser("brightness", help="Set display brightness (0-100)")
    p.add_argument("--level", type=int, required=True)

    p = sub.add_parser("mute", help="Toggle/set mute")
    p.add_argument("--on", action="store_true")
    p.add_argument("--off", action="store_true")
    p.add_argument("--toggle", action="store_true")

    sub.add_parser("sleep-display", help="Put display to sleep")
    sub.add_parser("lock-screen", help="Lock the screen")
    sub.add_parser("trash-empty", help="Empty the trash")
    sub.add_parser("battery", help="Show battery status")

    # ---- Clipboard ----
    sub.add_parser("clipboard-read", help="Read clipboard contents")

    p = sub.add_parser("clipboard-write", help="Write text to clipboard")
    p.add_argument("--text", required=True)

    # ---- System info ----
    sub.add_parser("sysinfo", help="Full system info snapshot")
    sub.add_parser("screen-size", help="Get main display resolution (width x height)")

    # ---- File operations ----
    p = sub.add_parser("list-files", help="List files in a directory")
    p.add_argument("--path", help="Directory path (default: home)")
    p.add_argument("--recursive", action="store_true", help="List recursively")

    p = sub.add_parser("read-file", help="Read text file contents")
    p.add_argument("--path", required=True)

    p = sub.add_parser("write-file", help="Write text to a file")
    p.add_argument("--path", required=True)
    p.add_argument("--content", required=True)

    p = sub.add_parser("move-file", help="Move/rename a file")
    p.add_argument("--src", required=True)
    p.add_argument("--dst", required=True)

    p = sub.add_parser("copy-file", help="Copy a file or directory")
    p.add_argument("--src", required=True)
    p.add_argument("--dst", required=True)

    p = sub.add_parser("delete-file", help="Delete a file")
    p.add_argument("--path", required=True)
    p.add_argument("--force", action="store_true", help="Force delete directories")

    p = sub.add_parser("search-files", help="Search files via Spotlight")
    p.add_argument("--query", required=True)
    p.add_argument("--dir", help="Limit search to directory")

    p = sub.add_parser("reveal-in-finder", help="Show file in Finder")
    p.add_argument("--path", required=True)

    # ---- Process management ----
    p = sub.add_parser("list-processes", help="List running processes")
    p.add_argument("--sort", choices=["cpu", "mem"], default="cpu")
    p.add_argument("--limit", type=int, help="Max processes to show")

    p = sub.add_parser("kill-process", help="Kill a process by name or PID")
    p.add_argument("--pid", type=int)
    p.add_argument("--name")

    # ---- Advanced input ----
    p = sub.add_parser("right-click", help="Right-click at coordinates")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)

    p = sub.add_parser("double-click", help="Double-click at coordinates")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)

    p = sub.add_parser("scroll", help="Scroll up or down")
    p.add_argument("--direction", choices=["up", "down"], required=True)
    p.add_argument("--amount", type=int, default=5, help="Scroll lines (default: 5)")

    p = sub.add_parser("mouse-move", help="Move mouse to coordinates (instant)")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)

    p = sub.add_parser("mouse-animate", help="Smoothly animate mouse to coordinates (visible movement)")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)
    p.add_argument("--duration", type=float, default=0.5, help="Animation duration in seconds (default: 0.5)")
    p.add_argument("--steps", type=int, default=30, help="Animation steps (default: 30, more=smoother)")

    p = sub.add_parser("drag", help="Click and drag from (x1,y1) to (x2,y2) with smooth animation")
    p.add_argument("--x1", type=int, required=True)
    p.add_argument("--y1", type=int, required=True)
    p.add_argument("--x2", type=int, required=True)
    p.add_argument("--y2", type=int, required=True)
    p.add_argument("--duration", type=float, default=0.5, help="Drag duration in seconds (default: 0.5)")

    # ---- Audio devices ----
    sub.add_parser("list-audio", help="List audio devices")

    p = sub.add_parser("switch-audio", help="Switch audio output device")
    p.add_argument("--device", required=True)

    # ---- Network ----
    sub.add_parser("get-ip", help="Get local and public IP")

    p = sub.add_parser("ping", help="Ping a host")
    p.add_argument("--host", required=True)
    p.add_argument("--count", type=int, default=3)

    # ---- Power (destructive) ----
    p = sub.add_parser("shutdown", help="Shut down the Mac (needs --confirm)")
    p.add_argument("--confirm", action="store_true")

    p = sub.add_parser("restart", help="Restart the Mac (needs --confirm)")
    p.add_argument("--confirm", action="store_true")

    p = sub.add_parser("logout", help="Log out (needs --confirm)")
    p.add_argument("--confirm", action="store_true")

    # ---- Permissions setup ----
    sub.add_parser("setup-permissions", help="Trigger all permission prompts (run once)")

    # ---- Browser control (Chrome) ----
    p = sub.add_parser("browser-open", help="Open URL in Chrome, wait for load")
    p.add_argument("--url", required=True)

    p = sub.add_parser("browser-js", help="Execute JavaScript in Chrome tab")
    p.add_argument("--script", required=True)

    sub.add_parser("browser-tab-url", help="Get current Chrome tab URL")
    sub.add_parser("browser-tab-title", help="Get current Chrome tab title")

    p = sub.add_parser("browser-new-tab", help="Open new Chrome tab with URL")
    p.add_argument("--url", default="about:blank")

    sub.add_parser("browser-close-tab", help="Close active Chrome tab")
    sub.add_parser("browser-close-others", help="Close all tabs/windows except active tab (kills ad popups)")
    sub.add_parser("browser-list-tabs", help="List all Chrome tabs")

    p = sub.add_parser("browser-switch-tab", help="Switch to Chrome tab by number")
    p.add_argument("--tab", type=int, required=True)

    # ---- Workflow helpers (V2.2) ----
    p = sub.add_parser("youtube-play", help="Search YouTube and auto-play the first result (atomic — no multi-turn needed)")
    p.add_argument("--query", required=True, help="Search query, e.g. 'lofi hip hop radio'")

    p = sub.add_parser("contacts-search", help="Search macOS Contacts by name — returns phone numbers and emails")
    p.add_argument("--name", required=True, help="Contact name to search for")

    p = sub.add_parser("facetime", help="FaceTime call — pass a name, phone, or email. Names auto-resolve via Contacts.")
    p.add_argument("--contact", required=True, help="Name, phone number, or email")
    p.add_argument("--audio", action="store_true", help="Audio-only call (no video)")

    p = sub.add_parser("imessage", help="Send an iMessage — pass a name, phone, or email. Names auto-resolve via Contacts.")
    p.add_argument("--contact", required=True, help="Name, phone number, or email")
    p.add_argument("--text", required=True, help="Message text to send")

    # Notes
    p = sub.add_parser("notes-create", help="Create a new Apple Note")
    p.add_argument("--title", required=True); p.add_argument("--body", default="")
    p.add_argument("--folder", default="Notes")

    p = sub.add_parser("notes-search", help="Search Apple Notes by title")
    p.add_argument("--query", required=True)

    p = sub.add_parser("notes-read", help="Read an Apple Note by title")
    p.add_argument("--title", required=True)

    # Reminders
    p = sub.add_parser("reminder-create", help="Create a reminder with optional due date")
    p.add_argument("--name", required=True); p.add_argument("--body", default="")
    p.add_argument("--due", default=None, help="Due date, e.g. 'April 15, 2026 9:00 AM'")
    p.add_argument("--list", default="Reminders")

    p = sub.add_parser("reminders-list", help="List incomplete reminders")
    p.add_argument("--list", default="Reminders")

    p = sub.add_parser("reminder-complete", help="Mark a reminder as complete")
    p.add_argument("--name", required=True); p.add_argument("--list", default="Reminders")

    # Maps
    p = sub.add_parser("maps-search", help="Search Apple Maps")
    p.add_argument("--query", required=True)

    p = sub.add_parser("maps-directions", help="Get directions in Apple Maps")
    p.add_argument("--to", required=True)
    p.add_argument("--from", dest="from_addr", default=None, help="Start address (defaults to current location)")
    p.add_argument("--mode", default="driving", choices=["driving", "walking", "transit"])

    # Mail
    p = sub.add_parser("mail-send", help="Send email via Apple Mail")
    p.add_argument("--to", required=True); p.add_argument("--subject", required=True)
    p.add_argument("--body", default="")

    p = sub.add_parser("mail-unread", help="List unread emails")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("mail-read", help="Read most recent unread email")
    p.add_argument("--subject", default=None, help="Filter by subject")

    # Shortcuts
    p = sub.add_parser("shortcut-run", help="Run a macOS Shortcut by name")
    p.add_argument("--name", required=True); p.add_argument("--input", default=None)

    p = sub.add_parser("shortcut-list", help="List available macOS Shortcuts")

    # Spotify
    p = sub.add_parser("spotify", help="Control Spotify: play, pause, next, previous, current, volume")
    p.add_argument("action", choices=["play", "pause", "next", "previous", "current", "volume"])
    p.add_argument("--query", default=None); p.add_argument("--level", type=int, default=None)

    # Apple Music
    p = sub.add_parser("music", help="Control Apple Music: play, pause, next, previous, current, search, volume")
    p.add_argument("action", choices=["play", "pause", "next", "previous", "current", "search", "volume"])
    p.add_argument("--query", default=None); p.add_argument("--level", type=int, default=None)

    # System Settings
    p = sub.add_parser("settings", help="Open a System Settings pane (wifi, bluetooth, display, privacy, etc.)")
    p.add_argument("--pane", required=True, help="Pane name: wifi, bluetooth, display, privacy, keyboard, etc.")

    args = parser.parse_args()

    # SECURITY: Sanitize string arguments that get interpolated into AppleScript
    if hasattr(args, 'app') and args.app:
        args.app = sanitize_applescript_string(args.app)
    if hasattr(args, 'url') and args.url:
        args.url = sanitize_url(args.url)
    if hasattr(args, 'title') and args.title:
        args.title = sanitize_applescript_string(args.title)
    if hasattr(args, 'message') and args.message:
        args.message = sanitize_applescript_string(args.message)
    if hasattr(args, 'query') and args.query:
        args.query = sanitize_applescript_string(args.query)

    # SECURITY: Block sensitive file paths
    for attr in ('path', 'src', 'dst'):
        val = getattr(args, attr, None)
        if val and args.command in ('read-file', 'write-file', 'delete-file', 'move-file', 'copy-file'):
            if is_sensitive_path(val):
                print(json.dumps({"ok": False, "error": f"BLOCKED: Path contains sensitive location. Cannot access {val}"}))
                sys.exit(1)

    # SECURITY: Block killing protected system processes
    if args.command == 'kill-process' and hasattr(args, 'name') and args.name:
        if args.name.lower() in [p.lower() for p in PROTECTED_PROCESSES]:
            print(json.dumps({"ok": False, "error": f"BLOCKED: Cannot kill protected process '{args.name}'"}))
            sys.exit(1)

    commands = {
        # Original
        "open": cmd_open, "quit": cmd_quit, "type": cmd_type,
        "keystroke": cmd_keystroke, "click": cmd_click,
        "list-windows": cmd_list_windows, "list-apps": cmd_list_apps,
        "frontmost": cmd_frontmost, "screenshot": cmd_screenshot,
        "url": cmd_url, "say": cmd_say, "volume": cmd_volume,
        "notify": cmd_notify,
        # Window management
        "window-move": cmd_window_move, "window-resize": cmd_window_resize,
        "window-fullscreen": cmd_window_fullscreen,
        "window-left": cmd_window_left, "window-right": cmd_window_right,
        "window-center": cmd_window_center,
        "window-minimize": cmd_window_minimize, "window-restore": cmd_window_restore,
        # Screenshot variants
        "screenshot-window": cmd_screenshot_window,
        # Recording
        "record-start": cmd_record_start, "record-stop": cmd_record_stop,
        # System toggles
        "dark-mode": cmd_dark_mode, "dnd": cmd_dnd, "wifi": cmd_wifi,
        "bluetooth": cmd_bluetooth, "brightness": cmd_brightness,
        "mute": cmd_mute, "sleep-display": cmd_sleep_display,
        "lock-screen": cmd_lock_screen, "trash-empty": cmd_trash_empty,
        "battery": cmd_battery,
        # Clipboard
        "clipboard-read": cmd_clipboard_read, "clipboard-write": cmd_clipboard_write,
        # System info
        "sysinfo": cmd_sysinfo, "screen-size": cmd_screen_size,
        # File operations
        "list-files": cmd_list_files, "read-file": cmd_read_file,
        "write-file": cmd_write_file, "move-file": cmd_move_file,
        "copy-file": cmd_copy_file, "delete-file": cmd_delete_file,
        "search-files": cmd_search_files, "reveal-in-finder": cmd_reveal_in_finder,
        # Process management
        "list-processes": cmd_list_processes, "kill-process": cmd_kill_process,
        # Advanced input
        "right-click": cmd_right_click, "double-click": cmd_double_click,
        "scroll": cmd_scroll, "mouse-move": cmd_mouse_move,
        "mouse-animate": cmd_mouse_animate, "drag": cmd_drag,
        # Audio devices
        "list-audio": cmd_list_audio, "switch-audio": cmd_switch_audio,
        # Network
        "get-ip": cmd_get_ip, "ping": cmd_ping,
        # Power (destructive)
        "shutdown": cmd_shutdown, "restart": cmd_restart, "logout": cmd_logout,
        # Permissions setup
        "setup-permissions": cmd_setup_permissions,
        # Browser control (Chrome)
        "browser-open": cmd_browser_open, "browser-js": cmd_browser_js,
        "browser-tab-url": cmd_browser_tab_url, "browser-tab-title": cmd_browser_tab_title,
        "browser-new-tab": cmd_browser_new_tab, "browser-close-tab": cmd_browser_close_tab,
        "browser-close-others": cmd_browser_close_others,
        "browser-list-tabs": cmd_browser_list_tabs, "browser-switch-tab": cmd_browser_switch_tab,
        # Workflow helpers (V2.2)
        "youtube-play": cmd_youtube_play,
        # Contacts, FaceTime, iMessage (V2.3 — native APIs)
        "contacts-search": cmd_contacts_search,
        "facetime": cmd_facetime,
        "imessage": cmd_imessage,
        # Notes, Reminders, Maps, Mail, Shortcuts, Spotify, Music, Settings (V2.4)
        "notes-create": cmd_notes_create, "notes-search": cmd_notes_search, "notes-read": cmd_notes_read,
        "reminder-create": cmd_reminder_create, "reminders-list": cmd_reminders_list, "reminder-complete": cmd_reminder_complete,
        "maps-search": cmd_maps_search, "maps-directions": cmd_maps_directions,
        "mail-send": cmd_mail_send, "mail-unread": cmd_mail_unread, "mail-read": cmd_mail_read,
        "shortcut-run": cmd_shortcut_run, "shortcut-list": cmd_shortcut_list,
        "spotify": cmd_spotify, "music": cmd_music,
        "settings": cmd_settings,
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
