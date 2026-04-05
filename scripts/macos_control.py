#!/usr/bin/env python3
"""
macOS Computer Control V2.0 — Full desktop automation for agent-driven control.
Uses osascript (built-in macOS) for application control, keystrokes, window management,
system toggles, clipboard, screen recording, and more.
No external dependencies — stdlib only.

Platform: macOS only. Exits with error on other platforms.

Usage:
  # App control
  python3 scripts/macos_control.py open --app Safari
  python3 scripts/macos_control.py quit --app Safari
  python3 scripts/macos_control.py type --text "Hello world"
  python3 scripts/macos_control.py keystroke --keys "cmd+c"
  python3 scripts/macos_control.py click --x 500 --y 300
  python3 scripts/macos_control.py list-windows
  python3 scripts/macos_control.py list-apps
  python3 scripts/macos_control.py frontmost

  # Window management
  python3 scripts/macos_control.py window-move --app Safari --x 0 --y 0
  python3 scripts/macos_control.py window-resize --app Safari --w 1280 --h 720
  python3 scripts/macos_control.py window-fullscreen --app Safari
  python3 scripts/macos_control.py window-left --app Safari
  python3 scripts/macos_control.py window-right --app Safari
  python3 scripts/macos_control.py window-center --app Safari
  python3 scripts/macos_control.py window-minimize --app Safari
  python3 scripts/macos_control.py window-restore --app Safari

  # Screenshots & recording
  python3 scripts/macos_control.py screenshot [--path /tmp/screen.png]
  python3 scripts/macos_control.py screenshot-window [--path /tmp/win.png]
  python3 scripts/macos_control.py record-start [--path /tmp/recording.mov]
  python3 scripts/macos_control.py record-stop

  # System toggles
  python3 scripts/macos_control.py dark-mode [--on | --off | --toggle]
  python3 scripts/macos_control.py dnd --on | --off
  python3 scripts/macos_control.py wifi --on | --off
  python3 scripts/macos_control.py bluetooth --on | --off
  python3 scripts/macos_control.py brightness --level 80
  python3 scripts/macos_control.py volume --level 50
  python3 scripts/macos_control.py mute [--on | --off | --toggle]
  python3 scripts/macos_control.py sleep-display
  python3 scripts/macos_control.py lock-screen
  python3 scripts/macos_control.py trash-empty
  python3 scripts/macos_control.py battery

  # Clipboard
  python3 scripts/macos_control.py clipboard-read
  python3 scripts/macos_control.py clipboard-write --text "Hello"

  # Media & audio
  python3 scripts/macos_control.py say --text "Hello CC"
  python3 scripts/macos_control.py url --url "https://example.com"
  python3 scripts/macos_control.py notify --title "Alert" --message "Task complete"

  # System info
  python3 scripts/macos_control.py sysinfo

  # Browser control (Safari)
  python3 scripts/macos_control.py browser-open --url "https://soundcloud.com"
  python3 scripts/macos_control.py browser-js --script "document.title"
  python3 scripts/macos_control.py browser-tab-url
  python3 scripts/macos_control.py browser-tab-title

All commands support --json flag for agent consumption.
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
    return run_osascript(f'tell application "{args.app}" to activate')


def cmd_quit(args):
    return run_osascript(f'tell application "{args.app}" to quit')


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

def cmd_window_move(args):
    return run_osascript(f'''
tell application "System Events"
    tell process "{args.app}"
        set position of window 1 to {{{args.x}, {args.y}}}
    end tell
end tell''')


def cmd_window_resize(args):
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
    sw, sh = get_screen_size()
    half_w = sw // 2
    # Menu bar is ~25px, so start at y=25
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
    sw, sh = get_screen_size()
    # Get current window size first
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
    """Screenshot of frontmost window only."""
    target = args.path or "/tmp/screenshot_window.png"
    result = run_shell(["screencapture", "-x", "-w", target])
    if result["ok"]:
        result["output"] = f"Window screenshot saved to {target}"
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
    # brightness CLI tool (brew install brightness)
    r = run_shell(["which", "brightness"])
    if r["ok"]:
        val = level / 100.0
        return run_shell(["brightness", str(val)])
    # Fallback: AppleScript via System Preferences (less smooth)
    return {"ok": False, "error": "Install brightness CLI: brew install brightness. Or use volume --level for audio."}


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
# BROWSER CONTROL (Chrome via AppleScript + JavaScript)
# ============================================================

def cmd_browser_open(args):
    """Open URL in Chrome and wait for page to load."""
    url = args.url
    script = f'''
tell application "Google Chrome"
    activate
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
    escaped = js_code.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "Google Chrome"
    set jsResult to execute active tab of window 1 javascript "{escaped}"
    return jsResult
end tell
'''
    return run_osascript(script, timeout=15)


def cmd_browser_tab_url(args):
    """Get the URL of Chrome's active tab."""
    script = '''
tell application "Google Chrome"
    return URL of active tab of window 1
end tell
'''
    return run_osascript(script)


def cmd_browser_tab_title(args):
    """Get the title of Chrome's active tab."""
    script = '''
tell application "Google Chrome"
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
    sub.add_parser("browser-list-tabs", help="List all Chrome tabs")

    p = sub.add_parser("browser-switch-tab", help="Switch to Chrome tab by number")
    p.add_argument("--tab", type=int, required=True)

    args = parser.parse_args()

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
        "sysinfo": cmd_sysinfo,
        # Browser control (Chrome)
        "browser-open": cmd_browser_open, "browser-js": cmd_browser_js,
        "browser-tab-url": cmd_browser_tab_url, "browser-tab-title": cmd_browser_tab_title,
        "browser-new-tab": cmd_browser_new_tab, "browser-close-tab": cmd_browser_close_tab,
        "browser-list-tabs": cmd_browser_list_tabs, "browser-switch-tab": cmd_browser_switch_tab,
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
