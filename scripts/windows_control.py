#!/usr/bin/env python3
"""
Windows Computer Control V2.1 — Full desktop automation for agent-driven control.
60+ commands covering apps, windows, browser, files, processes, input, system, network, power.
Uses pyautogui, pywin32, PowerShell, and Python stdlib.

Platform: Windows only. Exits with error on other platforms.
First run: python scripts/windows_control.py setup-permissions  (verifies all dependencies work)

All commands support --json flag for agent consumption.
Run: python scripts/windows_control.py --help  for full command list.
"""

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import time

# Windows-specific — conditional imports handled gracefully
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def guard_windows():
    if platform.system() != "Windows":
        print(json.dumps({"error": f"windows_control.py is Windows-only. Current platform: {platform.system()}"}))
        sys.exit(1)


def run_powershell(script, timeout=10):
    """Run a PowerShell script and return structured result."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_shell(cmd, timeout=10):
    """Run a shell command and return structured result."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---- SECURITY: Input sanitization ----

def sanitize_string(s):
    """Remove characters that could break shell interpolation."""
    return s.replace('"', '').replace('\\', '').replace('\n', ' ').replace('\r', '').replace('`', '').replace('$', '')


def sanitize_url(url):
    """Validate and sanitize a URL."""
    url = url.strip()
    if not url.startswith(('http://', 'https://', 'about:', 'file://')):
        url = 'https://' + url
    return sanitize_string(url)


# Paths that should never be read/written/deleted via file commands
SENSITIVE_PATHS = [
    '\\.ssh', '\\.aws', '\\.gnupg', '\\.env', '\\credentials',
    '\\id_rsa', '\\id_ed25519', '\\.npmrc', '\\.pypirc',
    '\\AppData\\Local\\Microsoft\\Credentials',
    '\\AppData\\Roaming\\Microsoft\\Credentials',
    '\\Windows\\System32\\config',
]

# Process names that should never be killed
PROTECTED_PROCESSES = [
    'explorer.exe', 'dwm.exe', 'csrss.exe', 'winlogon.exe',
    'services.exe', 'lsass.exe', 'svchost.exe', 'smss.exe',
    'wininit.exe', 'pm2', 'conhost.exe', 'System',
]


def is_sensitive_path(path):
    """Check if a path touches sensitive files/directories."""
    expanded = os.path.expanduser(path)
    for s in SENSITIVE_PATHS:
        if s.lower() in expanded.lower():
            return True
    return False


# ---- SCREEN SIZE HELPER ----

def get_screen_size():
    """Get primary display resolution."""
    try:
        user32 = ctypes.windll.user32
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        return w, h
    except Exception:
        return 1920, 1080  # safe default


# ---- CHROME DEVTOOLS PROTOCOL ----
CDP_PORT = 9222
CDP_TIMEOUT = 10

def _chrome_cdp_available():
    """Check if Chrome is running with DevTools Protocol."""
    try:
        import requests
        r = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

def _chrome_ensure_debug_mode():
    """Ensure Chrome is running with remote debugging enabled.
    Chrome on Windows requires a non-default data dir for CDP.
    We use CDP_Data which is junction-linked to the real profile
    (shares cookies, passwords, extensions, bookmarks).

    WARNING: This will restart Chrome. All tabs are restored but
    active sessions (video calls, etc.) will be interrupted.
    Returns True if CDP is available."""
    if _chrome_cdp_available():
        return True
    chrome = _chrome_path()
    # CDP_Data dir is junction-linked to real profile (set up by Bravo)
    cdp_data = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "CDP_Data")
    if not os.path.exists(os.path.join(cdp_data, "Default")):
        return False  # Junctions not set up — can't use CDP without losing profile
    # Must kill existing Chrome — only one instance per profile
    run_shell(["taskkill", "/IM", "chrome.exe", "/F"], timeout=10)
    time.sleep(2)
    try:
        subprocess.Popen(
            [chrome, f"--remote-debugging-port={CDP_PORT}",
             "--remote-allow-origins=*",
             f"--user-data-dir={cdp_data}", "--restore-last-session"],
            creationflags=CREATE_NO_WINDOW
        )
        time.sleep(4)
        return _chrome_cdp_available()
    except Exception:
        return False

def _chrome_get_tabs():
    """Get all Chrome tabs via CDP."""
    try:
        import requests
        r = requests.get(f"http://localhost:{CDP_PORT}/json", timeout=3)
        if r.status_code == 200:
            return [t for t in r.json() if t.get("type") == "page"]
    except Exception:
        pass
    return []

def _chrome_get_active_tab():
    """Get the most recently active tab."""
    tabs = _chrome_get_tabs()
    return tabs[0] if tabs else None

def _chrome_execute_js(js_code, tab=None, timeout=10):
    """Execute JavaScript in a Chrome tab via CDP WebSocket."""
    try:
        import websocket
        import requests
        if tab is None:
            tab = _chrome_get_active_tab()
        if not tab:
            return {"ok": False, "error": "No Chrome tab available"}

        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            return {"ok": False, "error": "No WebSocket URL for tab"}

        ws = websocket.create_connection(ws_url, timeout=timeout)
        msg = json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": js_code,
                "returnByValue": True,
                "awaitPromise": True,
            }
        })
        ws.send(msg)
        result = json.loads(ws.recv())
        ws.close()

        if "result" in result and "result" in result["result"]:
            val = result["result"]["result"]
            if val.get("type") == "string":
                return {"ok": True, "output": val["value"]}
            elif val.get("type") == "undefined":
                return {"ok": True, "output": "(undefined)"}
            elif "value" in val:
                return {"ok": True, "output": str(val["value"])}
            elif "description" in val:
                return {"ok": True, "output": val["description"]}
        if "result" in result and "exceptionDetails" in result["result"]:
            exc = result["result"]["exceptionDetails"]
            return {"ok": False, "error": exc.get("text", str(exc))}
        return {"ok": True, "output": str(result)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _chrome_navigate(url, tab=None, wait=True):
    """Navigate a Chrome tab to a URL via CDP."""
    try:
        import websocket
        if tab is None:
            tab = _chrome_get_active_tab()
        if not tab:
            return {"ok": False, "error": "No Chrome tab available"}

        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            return {"ok": False, "error": "No WebSocket URL for tab"}

        ws = websocket.create_connection(ws_url, timeout=CDP_TIMEOUT)
        msg = json.dumps({
            "id": 1,
            "method": "Page.navigate",
            "params": {"url": url}
        })
        ws.send(msg)
        ws.recv()  # Wait for response
        ws.close()

        if wait:
            time.sleep(2)  # Wait for page load

        return {"ok": True, "output": f"Navigated to {url}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---- RECORDING PID FILE ----
RECORD_PID_FILE = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "windows_control_recording.pid")

# FFmpeg path
FFMPEG = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Microsoft", "WinGet", "Packages",
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
    "ffmpeg-8.0.1-full_build", "bin", "ffmpeg.exe"
)
if not os.path.exists(FFMPEG):
    FFMPEG = "ffmpeg"  # Fallback to PATH


# ============================================================
# COMMANDS — App Control
# ============================================================

def cmd_open(args):
    """Open/activate an application."""
    app = args.app
    # Try to activate existing window first
    r = run_powershell(f'''
$proc = Get-Process -Name "{app}" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    if ($hwnd -ne 0) {{
        Add-Type @"
using System; using System.Runtime.InteropServices;
public class Win32 {{ [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd); [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow); }}
"@
        [Win32]::ShowWindow($hwnd, 9)
        [Win32]::SetForegroundWindow($hwnd)
        Write-Output "Activated: {app}"
    }} else {{
        Write-Output "Process running but no window: {app}"
    }}
}} else {{
    Start-Process "{app}" -ErrorAction Stop
    Write-Output "Started: {app}"
}}
''', timeout=10)
    return r


def cmd_quit(args):
    """Quit an application."""
    app = sanitize_string(args.app)
    return run_powershell(f'Stop-Process -Name "{app}" -Force -ErrorAction Stop; Write-Output "Quit: {app}"')


def cmd_type(args):
    """Type text into the frontmost application. Handles Unicode via clipboard fallback."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        if args.text.isascii():
            pyautogui.typewrite(args.text, interval=0.02)
        else:
            # Unicode text: copy to clipboard then Ctrl+V (pyautogui.typewrite is ASCII-only)
            import pyperclip
            old_clip = pyperclip.paste()
            pyperclip.copy(args.text)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.1)
            pyperclip.copy(old_clip)  # Restore clipboard
        return {"ok": True, "output": f"Typed {len(args.text)} chars"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_keystroke(args):
    """Send key combination (e.g., ctrl+c, alt+tab, win+d)."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        keys = args.keys.lower().split("+")
        key_char = keys[-1]
        modifiers = keys[:-1]

        # Map modifier names
        mod_map = {
            "cmd": "win", "command": "win", "super": "win", "win": "win",
            "ctrl": "ctrl", "control": "ctrl",
            "alt": "alt", "option": "alt",
            "shift": "shift",
        }
        # Map special key names
        key_map = {
            "return": "enter", "escape": "esc", "esc": "esc",
            "space": "space", "delete": "delete", "backspace": "backspace",
            "tab": "tab", "up": "up", "down": "down", "left": "left", "right": "right",
            "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4", "f5": "f5", "f6": "f6",
            "f7": "f7", "f8": "f8", "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
            "home": "home", "end": "end", "pageup": "pageup", "pagedown": "pagedown",
            "insert": "insert", "printscreen": "printscreen",
        }

        mapped_mods = [mod_map.get(m, m) for m in modifiers]
        mapped_key = key_map.get(key_char, key_char)

        if mapped_mods:
            pyautogui.hotkey(*mapped_mods, mapped_key)
        else:
            pyautogui.press(mapped_key)
        return {"ok": True, "output": f"Keystroke: {args.keys}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_click(args):
    """Click at screen coordinates using win32api (doesn't steal mouse focus)."""
    try:
        import ctypes
        # Use win32api SetCursorPos + mouse_event — faster and less glitchy than pyautogui
        ctypes.windll.user32.SetCursorPos(args.x, args.y)
        time.sleep(0.05)
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
        time.sleep(0.05)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
        return {"ok": True, "output": f"Clicked at {args.x},{args.y}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_list_windows(args):
    """List visible windows with position and size."""
    r = run_powershell('''
Get-Process | Where-Object {$_.MainWindowTitle -ne ""} | ForEach-Object {
    $name = $_.ProcessName
    $title = $_.MainWindowTitle
    Write-Output "$name | $title"
}
''', timeout=15)
    return r


def cmd_list_apps(args):
    """List running applications (with visible windows)."""
    r = run_powershell('''
Get-Process | Where-Object {$_.MainWindowTitle -ne ""} |
    Select-Object -Property ProcessName -Unique |
    ForEach-Object { Write-Output $_.ProcessName }
''')
    return r


def cmd_frontmost(args):
    """Get the foreground window title and process."""
    r = run_powershell('''
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public class FG {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
}
"@
$hwnd = [FG]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 256
[void][FG]::GetWindowText($hwnd, $sb, 256)
$pid = 0
[void][FG]::GetWindowThreadProcessId($hwnd, [ref]$pid)
$proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
Write-Output "$($proc.ProcessName) | $($sb.ToString())"
''')
    return r


def cmd_screenshot(args):
    """Take a full screenshot."""
    target = args.path or os.path.join(os.environ.get("TEMP", "."), "screenshot.png")
    try:
        import mss
        with mss.mss() as sct:
            sct.shot(output=target)
        return {"ok": True, "output": f"Screenshot saved to {target}", "file": target}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_url(args):
    """Open a URL in default browser."""
    return run_shell(["cmd", "/c", "start", "", args.url])


def cmd_say(args):
    """Speak text aloud using Windows SAPI."""
    return run_powershell(f'''
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Speak("{sanitize_string(args.text)}")
Write-Output "Spoke: {sanitize_string(args.text)[:50]}"
''', timeout=30)


def cmd_volume(args):
    """Set system volume (0-100)."""
    level = max(0, min(100, args.level))
    normalized = level / 100.0
    try:
        from pycaw.pycaw import AudioUtilities
        device = AudioUtilities.GetSpeakers()
        vol = device.EndpointVolume
        vol.SetMasterVolumeLevelScalar(normalized, None)
        return {"ok": True, "output": f"Volume set to {level}%"}
    except Exception as e:
        return {"ok": False, "error": f"Volume control failed: {str(e)[:100]}"}


def cmd_notify(args):
    """Send a Windows toast notification."""
    title = sanitize_string(args.title)
    message = sanitize_string(args.message)
    try:
        from plyer import notification as plyer_notify
        plyer_notify.notify(title=title, message=message, timeout=5)
        return {"ok": True, "output": f"Notification sent: {title}"}
    except Exception:
        # Fallback to PowerShell BurntToast or basic
        return run_powershell(f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
$template = @"
<toast><visual><binding template="ToastText02"><text id="1">{title}</text><text id="2">{message}</text></binding></visual></toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Bravo").Show($toast)
Write-Output "Notification sent: {title}"
''', timeout=10)


# ============================================================
# COMMANDS — Window Management
# ============================================================

def _get_window_handle(app_name):
    """Get the main window handle for a process by name."""
    r = run_powershell(f'''
$proc = Get-Process -Name "{app_name}" -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{ Write-Output $proc.MainWindowHandle }} else {{ Write-Output "0" }}
''')
    if r["ok"]:
        try:
            return int(r["output"].strip())
        except ValueError:
            return 0
    return 0


def cmd_window_move(args):
    """Move app window to x,y."""
    app = sanitize_string(args.app)
    return run_powershell(f'''
Add-Type @"
using System; using System.Runtime.InteropServices;
public class WinMove {{
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [StructLayout(LayoutKind.Sequential)] public struct RECT {{ public int Left; public int Top; public int Right; public int Bottom; }}
}}
"@
$proc = Get-Process -Name "{app}" -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    $rect = New-Object WinMove+RECT
    [WinMove]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
    $w = $rect.Right - $rect.Left
    $h = $rect.Bottom - $rect.Top
    [void][WinMove]::MoveWindow($hwnd, {args.x}, {args.y}, $w, $h, $true)
    Write-Output "Moved {app} to {args.x},{args.y}"
}} else {{ Write-Error "No window found for {app}" }}
''')


def cmd_window_resize(args):
    """Resize app window to w,h."""
    app = sanitize_string(args.app)
    return run_powershell(f'''
Add-Type @"
using System; using System.Runtime.InteropServices;
public class WinResize {{
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [StructLayout(LayoutKind.Sequential)] public struct RECT {{ public int Left; public int Top; public int Right; public int Bottom; }}
}}
"@
$proc = Get-Process -Name "{app}" -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    $rect = New-Object WinResize+RECT
    [WinResize]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
    [void][WinResize]::MoveWindow($hwnd, $rect.Left, $rect.Top, {args.w}, {args.h}, $true)
    Write-Output "Resized {app} to {args.w}x{args.h}"
}} else {{ Write-Error "No window found for {app}" }}
''')


def cmd_window_fullscreen(args):
    """Toggle fullscreen (maximize) for app."""
    app = sanitize_string(args.app)
    return run_powershell(f'''
Add-Type @"
using System; using System.Runtime.InteropServices;
public class WinFS {{
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}}
"@
$proc = Get-Process -Name "{app}" -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    [void][WinFS]::SetForegroundWindow($hwnd)
    if ([WinFS]::IsZoomed($hwnd)) {{
        [void][WinFS]::ShowWindow($hwnd, 9)  # SW_RESTORE
        Write-Output "Restored {app} from maximized"
    }} else {{
        [void][WinFS]::ShowWindow($hwnd, 3)  # SW_MAXIMIZE
        Write-Output "Maximized {app}"
    }}
}} else {{ Write-Error "No window found for {app}" }}
''')


def cmd_window_left(args):
    """Snap window to left half of screen."""
    app = sanitize_string(args.app)
    sw, sh = get_screen_size()
    half_w = sw // 2
    return run_powershell(f'''
Add-Type @"
using System; using System.Runtime.InteropServices;
public class WinSnap {{
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}}
"@
$proc = Get-Process -Name "{app}" -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    [void][WinSnap]::ShowWindow($hwnd, 9)
    [void][WinSnap]::SetForegroundWindow($hwnd)
    [void][WinSnap]::MoveWindow($hwnd, 0, 0, {half_w}, {sh}, $true)
    Write-Output "Snapped {app} to left half"
}} else {{ Write-Error "No window found for {app}" }}
''')


def cmd_window_right(args):
    """Snap window to right half of screen."""
    app = sanitize_string(args.app)
    sw, sh = get_screen_size()
    half_w = sw // 2
    return run_powershell(f'''
Add-Type @"
using System; using System.Runtime.InteropServices;
public class WinSnapR {{
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}}
"@
$proc = Get-Process -Name "{app}" -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    [void][WinSnapR]::ShowWindow($hwnd, 9)
    [void][WinSnapR]::SetForegroundWindow($hwnd)
    [void][WinSnapR]::MoveWindow($hwnd, {half_w}, 0, {half_w}, {sh}, $true)
    Write-Output "Snapped {app} to right half"
}} else {{ Write-Error "No window found for {app}" }}
''')


def cmd_window_center(args):
    """Center window on screen."""
    app = sanitize_string(args.app)
    sw, sh = get_screen_size()
    return run_powershell(f'''
Add-Type @"
using System; using System.Runtime.InteropServices;
public class WinCtr {{
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [StructLayout(LayoutKind.Sequential)] public struct RECT {{ public int Left; public int Top; public int Right; public int Bottom; }}
}}
"@
$proc = Get-Process -Name "{app}" -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    $rect = New-Object WinCtr+RECT
    [WinCtr]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
    $w = $rect.Right - $rect.Left
    $h = $rect.Bottom - $rect.Top
    $cx = ({sw} - $w) / 2
    $cy = ({sh} - $h) / 2
    [void][WinCtr]::SetForegroundWindow($hwnd)
    [void][WinCtr]::MoveWindow($hwnd, [int]$cx, [int]$cy, $w, $h, $true)
    Write-Output "Centered {app}"
}} else {{ Write-Error "No window found for {app}" }}
''')


def cmd_window_minimize(args):
    """Minimize app window."""
    app = sanitize_string(args.app)
    return run_powershell(f'''
Add-Type @"
using System; using System.Runtime.InteropServices;
public class WinMin {{ [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow); }}
"@
$proc = Get-Process -Name "{app}" -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{
    [void][WinMin]::ShowWindow($proc.MainWindowHandle, 6)  # SW_MINIMIZE
    Write-Output "Minimized {app}"
}} else {{ Write-Error "No window found for {app}" }}
''')


def cmd_window_restore(args):
    """Restore/unminimize app window."""
    app = sanitize_string(args.app)
    return run_powershell(f'''
Add-Type @"
using System; using System.Runtime.InteropServices;
public class WinRst {{
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}}
"@
$proc = Get-Process -Name "{app}" -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    [void][WinRst]::ShowWindow($hwnd, 9)  # SW_RESTORE
    [void][WinRst]::SetForegroundWindow($hwnd)
    Write-Output "Restored {app}"
}} else {{ Write-Error "No window found for {app}" }}
''')


# ============================================================
# COMMANDS — Screenshot Variants
# ============================================================

def cmd_screenshot_window(args):
    """Screenshot of the foreground window only."""
    target = args.path or os.path.join(os.environ.get("TEMP", "."), "screenshot_window.png")
    try:
        import pyautogui
        import pygetwindow as gw
        active = gw.getActiveWindow()
        if active:
            region = (active.left, active.top, active.width, active.height)
            img = pyautogui.screenshot(region=region)
            img.save(target)
            return {"ok": True, "output": f"Window screenshot saved to {target}", "file": target}
        # Fallback to full screenshot
        img = pyautogui.screenshot()
        img.save(target)
        return {"ok": True, "output": f"Full screenshot saved to {target} (no active window detected)", "file": target}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# COMMANDS — Screen Recording
# ============================================================

def cmd_record_start(args):
    """Start screen recording using ffmpeg gdigrab."""
    target = args.path or os.path.join(os.environ.get("TEMP", "."), "recording.mp4")
    if os.path.exists(RECORD_PID_FILE):
        return {"ok": False, "error": "Recording already in progress. Use record-stop first."}
    try:
        proc = subprocess.Popen(
            [FFMPEG, "-f", "gdigrab", "-framerate", "30", "-i", "desktop",
             "-c:v", "libx264", "-preset", "ultrafast", "-y", target],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        )
        with open(RECORD_PID_FILE, "w", encoding="utf-8") as f:
            f.write(f"{proc.pid}\n{target}")
        return {"ok": True, "output": f"Recording started (PID {proc.pid}). Saving to {target}", "file": target}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_record_stop(args):
    """Stop active screen recording."""
    if not os.path.exists(RECORD_PID_FILE):
        return {"ok": False, "error": "No active recording found."}
    with open(RECORD_PID_FILE, encoding="utf-8") as f:
        lines = f.read().strip().split("\n")
    pid = int(lines[0])
    target = lines[1] if len(lines) > 1 else "recording.mp4"
    try:
        # Send 'q' to ffmpeg stdin or kill gracefully
        subprocess.run(["taskkill", "/pid", str(pid), "/T"], capture_output=True,
                       creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass
    try:
        os.remove(RECORD_PID_FILE)
    except Exception:
        pass
    return {"ok": True, "output": f"Recording stopped. File: {target}", "file": target}


# ============================================================
# COMMANDS — System Toggles
# ============================================================

def cmd_dark_mode(args):
    """Toggle/set dark mode via Registry."""
    if args.on:
        val = 0  # 0 = dark mode ON in Windows
    elif args.off:
        val = 1  # 1 = dark mode OFF (light)
    else:
        # Toggle: read current then flip
        r = run_powershell('(Get-ItemProperty -Path "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" -Name AppsUseLightTheme).AppsUseLightTheme')
        if r["ok"]:
            current = r["output"].strip()
            val = 0 if current == "1" else 1
        else:
            val = 0

    return run_powershell(f'''
Set-ItemProperty -Path "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" -Name AppsUseLightTheme -Value {val}
Set-ItemProperty -Path "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" -Name SystemUsesLightTheme -Value {val}
if ({val} -eq 0) {{ Write-Output "Dark mode: ON" }} else {{ Write-Output "Dark mode: OFF" }}
''')


def cmd_dnd(args):
    """Toggle Focus Assist (Do Not Disturb) via Registry."""
    if args.on:
        return run_powershell('''
Set-ItemProperty -Path "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Notifications\\Settings" -Name "NOC_GLOBAL_SETTING_TOASTS_ENABLED" -Value 0 -Type DWord
Write-Output "Focus Assist: ON (notifications silenced)"
''')
    else:
        return run_powershell('''
Set-ItemProperty -Path "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Notifications\\Settings" -Name "NOC_GLOBAL_SETTING_TOASTS_ENABLED" -Value 1 -Type DWord
Write-Output "Focus Assist: OFF (notifications enabled)"
''')


def cmd_wifi(args):
    """WiFi on/off."""
    action = "Enable" if args.on else "Disable"
    return run_powershell(f'''
$adapter = Get-NetAdapter -Name "Wi-Fi" -ErrorAction SilentlyContinue
if ($adapter) {{
    {action}-NetAdapter -Name "Wi-Fi" -Confirm:$false
    Write-Output "WiFi: {'ON' if args.on else 'OFF'}"
}} else {{
    # Try wildcard
    $adapter = Get-NetAdapter | Where-Object {{ $_.Name -like "*Wi*" -or $_.InterfaceDescription -like "*Wireless*" }} | Select-Object -First 1
    if ($adapter) {{
        {action}-NetAdapter -Name $adapter.Name -Confirm:$false
        Write-Output "WiFi ($($adapter.Name)): {'ON' if args.on else 'OFF'}"
    }} else {{
        Write-Error "No WiFi adapter found"
    }}
}}
''')


def cmd_bluetooth(args):
    """Bluetooth on/off via PowerShell."""
    action = "enable" if args.on else "disable"
    return run_powershell(f'''
$bt = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Where-Object {{ $_.FriendlyName -like "*Bluetooth*" }} | Select-Object -First 1
if ($bt) {{
    if ("{action}" -eq "enable") {{
        Enable-PnpDevice -InstanceId $bt.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
    }} else {{
        Disable-PnpDevice -InstanceId $bt.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
    }}
    Write-Output "Bluetooth: {'ON' if args.on else 'OFF'}"
}} else {{
    Write-Error "No Bluetooth adapter found"
}}
''')


def cmd_brightness(args):
    """Set display brightness (0-100) via WMI."""
    level = max(0, min(100, args.level))
    return run_powershell(f'''
$brightness = Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue
if ($brightness) {{
    $brightness.WmiSetBrightness(1, {level})
    Write-Output "Brightness set to {level}%"
}} else {{
    Write-Error "Brightness control not available (desktop monitor or unsupported driver)"
}}
''')


def cmd_mute(args):
    """Toggle/set system mute."""
    try:
        from pycaw.pycaw import AudioUtilities
        device = AudioUtilities.GetSpeakers()
        vol = device.EndpointVolume

        if args.on:
            vol.SetMute(1, None)
            return {"ok": True, "output": "Muted"}
        elif args.off:
            vol.SetMute(0, None)
            return {"ok": True, "output": "Unmuted"}
        else:
            current = vol.GetMute()
            vol.SetMute(0 if current else 1, None)
            return {"ok": True, "output": "Unmuted" if current else "Muted"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_sleep_display(args):
    """Put display to sleep."""
    try:
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        return {"ok": True, "output": "Display sleeping"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_lock_screen(args):
    """Lock the screen."""
    return run_shell(["rundll32.exe", "user32.dll,LockWorkStation"])


def cmd_trash_empty(args):
    """Empty the Recycle Bin."""
    return run_powershell('Clear-RecycleBin -Force -ErrorAction SilentlyContinue; Write-Output "Recycle Bin emptied"')


def cmd_battery(args):
    """Show battery status."""
    r = run_powershell('''
$batt = Get-WmiObject -Class Win32_Battery -ErrorAction SilentlyContinue
if ($batt) {
    $pct = $batt.EstimatedChargeRemaining
    $status = switch ($batt.BatteryStatus) {
        1 { "discharging" }; 2 { "AC connected" }; 3 { "fully charged" }
        4 { "low" }; 5 { "critical" }; default { "unknown" }
    }
    Write-Output "$pct% — $status"
} else {
    Write-Output "No battery detected (desktop)"
}
''')
    return r


# ============================================================
# COMMANDS — Clipboard
# ============================================================

def cmd_clipboard_read(args):
    """Read clipboard contents."""
    try:
        import pyperclip
        content = pyperclip.paste()
        if not content:
            return {"ok": True, "output": "(clipboard is empty)"}
        if len(content) > 5000:
            return {"ok": True, "output": content[:5000] + f"\n...(truncated, {len(content)} chars total)"}
        return {"ok": True, "output": content}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_clipboard_write(args):
    """Write text to clipboard."""
    try:
        import pyperclip
        pyperclip.copy(args.text)
        return {"ok": True, "output": f"Copied {len(args.text)} chars to clipboard."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# COMMANDS — System Info
# ============================================================

def cmd_sysinfo(args):
    """Comprehensive system info snapshot."""
    info = {}

    # Battery
    r = run_powershell('''
$b = Get-WmiObject -Class Win32_Battery -ErrorAction SilentlyContinue
if ($b) { Write-Output "$($b.EstimatedChargeRemaining)% — Status $($b.BatteryStatus)" }
else { Write-Output "No battery" }
''')
    if r["ok"]:
        info["battery"] = r["output"]

    # Disk
    r = run_powershell('$d = Get-PSDrive C; Write-Output "$([math]::Round($d.Free/1GB,1)) GB free of $([math]::Round(($d.Free+$d.Used)/1GB,1)) GB"')
    if r["ok"]:
        info["disk"] = r["output"]

    # Memory
    r = run_powershell('''
$os = Get-WmiObject Win32_OperatingSystem
$total = [math]::Round($os.TotalVisibleMemorySize/1MB, 1)
$free = [math]::Round($os.FreePhysicalMemory/1MB, 1)
$used = [math]::Round($total - $free, 1)
Write-Output "$used GB used of $total GB"
''')
    if r["ok"]:
        info["memory"] = r["output"]

    # CPU
    r = run_powershell('''
$cpu = Get-WmiObject Win32_Processor
Write-Output "$($cpu.Name) — $($cpu.LoadPercentage)% load"
''')
    if r["ok"]:
        info["cpu"] = r["output"]

    # Uptime
    r = run_powershell('$up = (Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime; Write-Output "$($up.Days)d $($up.Hours)h $($up.Minutes)m"')
    if r["ok"]:
        info["uptime"] = r["output"]

    # WiFi
    r = run_powershell('(netsh wlan show interfaces | Select-String "SSID" | Select-Object -First 1).ToString().Split(":")[1].Trim()')
    if r["ok"] and r["output"]:
        info["wifi"] = r["output"]

    # Display
    sw, sh = get_screen_size()
    info["display"] = f"{sw}x{sh}"

    lines = []
    labels = {
        "battery": "Battery", "disk": "Disk", "memory": "RAM",
        "cpu": "CPU", "uptime": "Uptime", "wifi": "WiFi", "display": "Display"
    }
    for key, label in labels.items():
        if key in info:
            lines.append(f"{label}: {info[key]}")

    return {"ok": True, "output": "\n".join(lines) if lines else "No system info available", "detail": info}


# ============================================================
# COMMANDS — File Operations (cross-platform — mostly stdlib)
# ============================================================

def cmd_list_files(args):
    """List files in a directory."""
    path = args.path or os.path.expanduser("~")
    try:
        entries = os.listdir(path)
        lines = []
        for entry in sorted(entries):
            full = os.path.join(path, entry)
            try:
                stat = os.stat(full)
                size = stat.st_size
                is_dir = os.path.isdir(full)
                prefix = "d" if is_dir else "-"
                lines.append(f"{prefix} {size:>10}  {entry}")
            except OSError:
                lines.append(f"? {entry}")
        if args.recursive:
            # Walk subdirectories too
            for root, dirs, files in os.walk(path):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), path)
                    lines.append(f"  {rel}")
                if len(lines) > 200:
                    lines.append(f"...(truncated)")
                    break
        output = "\n".join(lines[:200])
        if len(lines) > 200:
            output += f"\n...(truncated, {len(lines)} total entries)"
        return {"ok": True, "output": output}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_read_file(args):
    """Read contents of a text file (truncated at 10KB)."""
    path = os.path.expanduser(args.path)
    if not os.path.isfile(path):
        return {"ok": False, "error": f"File not found: {path}"}
    try:
        with open(path, "r", errors="replace", encoding="utf-8") as f:
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
        with open(path, "w", encoding="utf-8") as f:
            f.write(args.content)
        return {"ok": True, "output": f"Wrote {len(args.content)} chars to {path}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_move_file(args):
    """Move or rename a file/directory."""
    src = os.path.expanduser(args.src)
    dst = os.path.expanduser(args.dst)
    try:
        shutil.move(src, dst)
        return {"ok": True, "output": f"Moved {src} -> {dst}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_copy_file(args):
    """Copy a file or directory."""
    src = os.path.expanduser(args.src)
    dst = os.path.expanduser(args.dst)
    try:
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return {"ok": True, "output": f"Copied {src} -> {dst}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_delete_file(args):
    """Delete a file (not directories unless --force)."""
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
    """Search files by name using PowerShell."""
    query = args.query
    search_dir = args.dir or os.path.expanduser("~")
    search_dir = search_dir.replace("/", "\\")
    r = run_powershell(f'''
Get-ChildItem -Path "{search_dir}" -Recurse -Filter "*{query}*" -ErrorAction SilentlyContinue |
    Select-Object -First 50 |
    ForEach-Object {{ Write-Output $_.FullName }}
''', timeout=20)
    if r["ok"]:
        lines = [l for l in r["output"].split("\n") if l.strip()]
        if not lines:
            r["output"] = "No files found."
    return r


def cmd_reveal_in_explorer(args):
    """Reveal a file/folder in Explorer."""
    path = os.path.expanduser(args.path)
    if os.path.isfile(path):
        return run_shell(["explorer.exe", "/select,", path])
    elif os.path.isdir(path):
        return run_shell(["explorer.exe", path])
    return {"ok": False, "error": f"Path not found: {path}"}


# ============================================================
# COMMANDS — Process Management
# ============================================================

def cmd_list_processes(args):
    """List running processes, sorted by CPU or memory."""
    sort_col = "WS" if args.sort == "mem" else "CPU"
    limit_clause = f"| Select-Object -First {args.limit}" if args.limit else ""
    r = run_powershell(f'''
Get-Process | Sort-Object {sort_col} -Descending {limit_clause} |
    Format-Table -Property Name, Id, CPU, @{{n="Mem(MB)";e={{[math]::Round($_.WS/1MB,1)}}}} -AutoSize |
    Out-String -Width 200
''', timeout=15)
    return r


def cmd_kill_process(args):
    """Kill a process by name or PID."""
    if args.pid:
        r = run_shell(["taskkill", "/PID", str(args.pid), "/F"])
        if r["ok"]:
            r["output"] = f"Killed PID {args.pid}"
        return r
    if args.name:
        # Check protected list
        if args.name.lower() in [p.lower() for p in PROTECTED_PROCESSES]:
            return {"ok": False, "error": f"BLOCKED: Cannot kill protected process '{args.name}'"}
        r = run_shell(["taskkill", "/IM", args.name, "/F"])
        if r["ok"]:
            r["output"] = f"Killed processes matching '{args.name}'"
        return r
    return {"ok": False, "error": "Specify --pid or --name"}


# ============================================================
# COMMANDS — Advanced Input
# ============================================================

def cmd_right_click(args):
    """Right-click at screen coordinates using win32api."""
    try:
        ctypes.windll.user32.SetCursorPos(args.x, args.y)
        time.sleep(0.05)
        ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)  # MOUSEEVENTF_RIGHTDOWN
        time.sleep(0.05)
        ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)  # MOUSEEVENTF_RIGHTUP
        return {"ok": True, "output": f"Right-clicked at {args.x},{args.y}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_double_click(args):
    """Double-click at screen coordinates using win32api."""
    try:
        ctypes.windll.user32.SetCursorPos(args.x, args.y)
        time.sleep(0.05)
        for _ in range(2):
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.03)
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.05)
        return {"ok": True, "output": f"Double-clicked at {args.x},{args.y}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_scroll(args):
    """Scroll up/down by amount using win32api."""
    try:
        # MOUSEEVENTF_WHEEL = 0x0800, WHEEL_DELTA = 120
        direction = 1 if args.direction == "up" else -1
        amount = abs(args.amount) * 120 * direction
        ctypes.windll.user32.mouse_event(0x0800, 0, 0, amount, 0)
        return {"ok": True, "output": f"Scrolled {args.direction} by {abs(args.amount)}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_mouse_move(args):
    """Move mouse cursor to coordinates using win32api."""
    try:
        ctypes.windll.user32.SetCursorPos(args.x, args.y)
        return {"ok": True, "output": f"Mouse moved to {args.x},{args.y}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# COMMANDS — Audio Devices
# ============================================================

def cmd_list_audio(args):
    """List audio devices."""
    r = run_powershell('''
Get-WmiObject Win32_SoundDevice | ForEach-Object {
    Write-Output "$($_.Name) — Status: $($_.Status)"
}
''')
    return r


def cmd_switch_audio(args):
    """Switch audio output device (requires pycaw or nircmd)."""
    # This is complex on Windows — provide info
    return {"ok": False, "error": f"Audio device switching requires nircmd or AudioDeviceCmdlets. Target device: {args.device}. Install: Install-Module AudioDeviceCmdlets; Set-AudioDevice -PlaybackDevice '{args.device}'"}


# ============================================================
# COMMANDS — Network
# ============================================================

def cmd_get_ip(args):
    """Get local and public IP addresses."""
    info = {}
    r = run_powershell('(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.*" } | Select-Object -First 1).IPAddress')
    if r["ok"]:
        info["local"] = r["output"].strip()
    r = run_shell(["curl", "-s", "https://api.ipify.org"], timeout=10)
    if r["ok"]:
        info["public"] = r["output"].strip()
    if info:
        parts = [f"Local: {info.get('local', '?')}", f"Public: {info.get('public', '?')}"]
        return {"ok": True, "output": " | ".join(parts), "detail": info}
    return {"ok": False, "error": "Could not determine IP"}


def cmd_ping(args):
    """Ping a host."""
    count = str(args.count or 3)
    r = run_shell(["ping", "-n", count, args.host], timeout=30)
    return r


# ============================================================
# COMMANDS — Power (Destructive — requires --confirm)
# ============================================================

def cmd_shutdown(args):
    """Shut down the PC. Requires --confirm."""
    if not args.confirm:
        return {"ok": False, "error": "Destructive action. Add --confirm to proceed."}
    return run_shell(["shutdown", "/s", "/t", "5", "/c", "Bravo initiated shutdown"])


def cmd_restart(args):
    """Restart the PC. Requires --confirm."""
    if not args.confirm:
        return {"ok": False, "error": "Destructive action. Add --confirm to proceed."}
    return run_shell(["shutdown", "/r", "/t", "5", "/c", "Bravo initiated restart"])


def cmd_logout(args):
    """Log out the current user. Requires --confirm."""
    if not args.confirm:
        return {"ok": False, "error": "Destructive action. Add --confirm to proceed."}
    return run_shell(["shutdown", "/l"])


# ============================================================
# COMMANDS — Permissions/Setup Check
# ============================================================

def cmd_setup_permissions(args):
    """Verify all dependencies and capabilities work on this Windows machine."""
    results = []

    # 1. pyautogui
    try:
        import pyautogui
        pos = pyautogui.position()
        results.append(f"pyautogui: PASS (mouse at {pos.x},{pos.y})")
    except Exception as e:
        results.append(f"pyautogui: FAIL ({e})")

    # 2. pywin32
    try:
        import win32gui
        fg = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(fg)
        results.append(f"pywin32: PASS (foreground: {title[:40]})")
    except Exception as e:
        results.append(f"pywin32: FAIL ({e})")

    # 3. screenshot (mss)
    try:
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            results.append(f"mss/screenshot: PASS ({monitor['width']}x{monitor['height']})")
    except Exception as e:
        results.append(f"mss/screenshot: FAIL ({e})")

    # 4. clipboard
    try:
        import pyperclip
        pyperclip.paste()  # just test it works
        results.append("clipboard: PASS")
    except Exception as e:
        results.append(f"clipboard: FAIL ({e})")

    # 5. audio (pycaw)
    try:
        from pycaw.pycaw import AudioUtilities
        AudioUtilities.GetSpeakers()
        results.append("pycaw/audio: PASS")
    except Exception as e:
        results.append(f"pycaw/audio: FAIL ({e})")

    # 6. notifications (plyer)
    try:
        from plyer import notification as plyer_notify
        plyer_notify.notify(title="Bravo", message="Setup check complete", timeout=3)
        results.append("plyer/notifications: PASS")
    except Exception as e:
        results.append(f"plyer/notifications: FAIL ({e})")

    # 7. PowerShell
    r = run_powershell('Write-Output "PowerShell OK"')
    results.append(f"PowerShell: {'PASS' if r['ok'] else 'FAIL'}")

    # 8. FFmpeg
    r = run_shell([FFMPEG, "-version"], timeout=5)
    results.append(f"FFmpeg: {'PASS' if r['ok'] else 'FAIL (screen recording unavailable)'}")

    # 9. Screen size
    sw, sh = get_screen_size()
    results.append(f"Display: {sw}x{sh}")

    summary = "\n".join(results)
    all_pass = all("PASS" in r for r in results)
    return {
        "ok": True,
        "output": f"{'All capabilities verified!' if all_pass else 'Some capabilities need attention.'}\n\n{summary}"
    }


# ============================================================
# BROWSER CONTROL (Chrome via DevTools Protocol or PowerShell)
# ============================================================

def _chrome_path():
    """Find Chrome executable."""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "chrome.exe"  # hope it's on PATH


def cmd_browser_open(args):
    """Open URL in Chrome, wait for page to load."""
    url = args.url
    if _chrome_cdp_available():
        tab = _chrome_get_active_tab()
        if tab:
            r = _chrome_navigate(url, tab, wait=True)
            if r["ok"]:
                # Get page title
                title_r = _chrome_execute_js("document.title", tab)
                title = title_r.get("output", url) if title_r.get("ok") else url
                return {"ok": True, "output": f"Opened {url} — {title}"}
            return r
    # Fallback: launch Chrome with URL + CDP
    chrome = _chrome_path()
    cdp_data = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "CDP_Data")
    os.makedirs(cdp_data, exist_ok=True)
    try:
        subprocess.Popen(
            [chrome, f"--remote-debugging-port={CDP_PORT}",
             "--remote-allow-origins=*",
             f"--user-data-dir={cdp_data}", url],
            creationflags=CREATE_NO_WINDOW
        )
        time.sleep(3)
        # Try to get title via CDP now
        if _chrome_cdp_available():
            tab = _chrome_get_active_tab()
            if tab:
                title_r = _chrome_execute_js("document.title", tab)
                title = title_r.get("output", url) if title_r.get("ok") else url
                return {"ok": True, "output": f"Opened {url} — {title}"}
        return {"ok": True, "output": f"Opened {url} in Chrome"}
    except Exception as e:
        # Last resort: default browser
        run_shell(["cmd", "/c", "start", "", url])
        return {"ok": True, "output": f"Opened {url} in default browser"}


def cmd_browser_js(args):
    """Execute JavaScript in Chrome's active tab via DevTools Protocol."""
    if not _chrome_ensure_debug_mode():
        return {"ok": False, "error": "Chrome DevTools not available. Restart Chrome with: chrome.exe --remote-debugging-port=9222"}
    r = _chrome_execute_js(args.script)
    return r


def cmd_browser_tab_url(args):
    """Get the URL of Chrome's active tab."""
    if _chrome_cdp_available():
        tab = _chrome_get_active_tab()
        if tab:
            return {"ok": True, "output": tab.get("url", "unknown")}
    # Fallback: process title
    r = run_powershell('''
$chrome = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -ne "" } | Select-Object -First 1
if ($chrome) { Write-Output $chrome.MainWindowTitle } else { Write-Error "Chrome not running" }
''')
    return r


def cmd_browser_tab_title(args):
    """Get the title of Chrome's active tab."""
    if _chrome_cdp_available():
        tab = _chrome_get_active_tab()
        if tab:
            return {"ok": True, "output": tab.get("title", "unknown")}
    r = run_powershell('''
$chrome = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -ne "" } | Select-Object -First 1
if ($chrome) { Write-Output $chrome.MainWindowTitle } else { Write-Error "Chrome not running" }
''')
    return r


def cmd_browser_new_tab(args):
    """Open a new tab in Chrome with URL."""
    url = getattr(args, 'url', 'about:blank')
    if _chrome_cdp_available():
        try:
            import requests
            r = requests.put(
                f"http://localhost:{CDP_PORT}/json/new?{url}", timeout=5
            )
            if r.status_code == 200:
                tab_info = r.json()
                time.sleep(1)
                title_r = _chrome_execute_js("document.title", tab_info)
                title = title_r.get("output", url) if title_r.get("ok") else url
                return {"ok": True, "output": f"New tab: {title} ({url})"}
        except Exception:
            pass
    # Fallback: launch Chrome with new-tab flag
    chrome = _chrome_path()
    try:
        subprocess.Popen([chrome, "--new-tab", url], creationflags=CREATE_NO_WINDOW)
        time.sleep(1)
        return {"ok": True, "output": f"New tab: {url}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_browser_close_tab(args):
    """Close the active Chrome tab."""
    if _chrome_cdp_available():
        tab = _chrome_get_active_tab()
        if tab:
            try:
                import requests
                tab_id = tab.get("id")
                requests.get(f"http://localhost:{CDP_PORT}/json/close/{tab_id}", timeout=3)
                return {"ok": True, "output": "Tab closed"}
            except Exception:
                pass
    # Fallback: Ctrl+W via keybd_event
    try:
        VK_CONTROL = 0x11
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x57, 0, 0, 0)  # W
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(0x57, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)
        return {"ok": True, "output": "Sent Ctrl+W to close tab"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_browser_list_tabs(args):
    """List all open Chrome tabs with URLs and titles."""
    if _chrome_cdp_available():
        tabs = _chrome_get_tabs()
        if tabs:
            lines = []
            for i, t in enumerate(tabs, 1):
                title = t.get("title", "?")[:60]
                url = t.get("url", "?")
                lines.append(f"{i}. {title} | {url}")
            return {"ok": True, "output": "\n".join(lines)}
    # Fallback: process titles
    r = run_powershell('''
Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -ne "" } |
    ForEach-Object { Write-Output "$($_.Id) | $($_.MainWindowTitle)" }
''')
    if r["ok"] and not r["output"]:
        return {"ok": True, "output": "No Chrome windows found"}
    return r


def cmd_browser_switch_tab(args):
    """Switch to a specific Chrome tab by number."""
    tab_num = args.tab
    if _chrome_cdp_available():
        tabs = _chrome_get_tabs()
        if tabs and 1 <= tab_num <= len(tabs):
            tab = tabs[tab_num - 1]
            try:
                import websocket
                ws_url = tab.get("webSocketDebuggerUrl")
                if ws_url:
                    ws = websocket.create_connection(ws_url, timeout=5)
                    ws.send(json.dumps({"id": 1, "method": "Page.bringToFront"}))
                    ws.recv()
                    ws.close()
                    return {"ok": True, "output": f"Switched to tab {tab_num}: {tab.get('title', '?')}"}
            except Exception:
                pass
    # Fallback: Ctrl+number via keybd_event
    if tab_num < 1 or tab_num > 9:
        return {"ok": False, "error": "Tab number must be 1-9"}
    try:
        VK_CONTROL = 0x11
        vk_num = 0x30 + tab_num  # VK_0 = 0x30, so VK_1 = 0x31 etc.
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_num, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(vk_num, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)
        return {"ok": True, "output": f"Switched to tab {tab_num}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_browser_back(args):
    """Go back in browser history."""
    if _chrome_cdp_available():
        r = _chrome_execute_js("history.back(); 'navigated back'")
        if r.get("ok"):
            return r
    try:
        VK_MENU = 0x12
        VK_LEFT = 0x25
        ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_LEFT, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(VK_LEFT, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_MENU, 0, 2, 0)
        return {"ok": True, "output": "Navigated back"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_browser_forward(args):
    """Go forward in browser history."""
    if _chrome_cdp_available():
        r = _chrome_execute_js("history.forward(); 'navigated forward'")
        if r.get("ok"):
            return r
    try:
        VK_MENU = 0x12
        VK_RIGHT = 0x27
        ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_RIGHT, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(VK_RIGHT, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_MENU, 0, 2, 0)
        return {"ok": True, "output": "Navigated forward"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_browser_reload(args):
    """Reload the current page."""
    if _chrome_cdp_available():
        tab = _chrome_get_active_tab()
        if tab:
            try:
                import websocket
                ws_url = tab.get("webSocketDebuggerUrl")
                if ws_url:
                    ws = websocket.create_connection(ws_url, timeout=5)
                    ws.send(json.dumps({"id": 1, "method": "Page.reload"}))
                    ws.recv()
                    ws.close()
                    return {"ok": True, "output": "Page reloaded"}
            except Exception:
                pass
    try:
        VK_CONTROL = 0x11
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x52, 0, 0, 0)  # R
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(0x52, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)
        return {"ok": True, "output": "Page reloaded"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_browser_screenshot(args):
    """Take a screenshot of the browser page via CDP."""
    target = args.path or os.path.join(os.environ.get("TEMP", "."), "browser_screenshot.png")
    if _chrome_cdp_available():
        tab = _chrome_get_active_tab()
        if tab:
            try:
                import websocket
                import base64
                ws_url = tab.get("webSocketDebuggerUrl")
                if ws_url:
                    ws = websocket.create_connection(ws_url, timeout=15)
                    ws.send(json.dumps({"id": 1, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
                    result = json.loads(ws.recv())
                    ws.close()
                    if "result" in result and "data" in result["result"]:
                        img_data = base64.b64decode(result["result"]["data"])
                        with open(target, "wb") as f:
                            f.write(img_data)
                        return {"ok": True, "output": f"Browser screenshot saved to {target}", "file": target}
            except Exception as e:
                return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "Chrome DevTools not available for browser screenshot. Use 'screenshot' for full screen."}


def cmd_browser_get_text(args):
    """Get the visible text content of the current page."""
    if not _chrome_cdp_available():
        return {"ok": False, "error": "Chrome DevTools not available"}
    r = _chrome_execute_js("document.body.innerText.substring(0, 5000)")
    if r.get("ok"):
        text = r["output"]
        if len(text) > 3000:
            text = text[:3000] + "\n...(truncated)"
        r["output"] = text
    return r


def cmd_browser_click_element(args):
    """Click an element by CSS selector."""
    if not _chrome_cdp_available():
        return {"ok": False, "error": "Chrome DevTools not available"}
    selector = args.selector.replace("'", "\\'")
    return _chrome_execute_js(f"""
(function() {{
    var el = document.querySelector('{selector}');
    if (el) {{ el.click(); return 'Clicked: {selector}'; }}
    return 'Element not found: {selector}';
}})()
""")


def cmd_browser_fill(args):
    """Fill an input field by CSS selector."""
    if not _chrome_cdp_available():
        return {"ok": False, "error": "Chrome DevTools not available"}
    selector = args.selector.replace("'", "\\'")
    value = args.value.replace("'", "\\'")
    return _chrome_execute_js(f"""
(function() {{
    var el = document.querySelector('{selector}');
    if (el) {{
        el.focus();
        el.value = '{value}';
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'Filled: {selector}';
    }}
    return 'Element not found: {selector}';
}})()
""")


# ============================================================
# COMMANDS — Browser CDP Setup
# ============================================================

def cmd_browser_enable_cdp(args):
    """Enable Chrome DevTools Protocol (restarts Chrome with CDP flag).
    This kills Chrome and relaunches with --remote-debugging-port=9222.
    Uses junction-linked profile so all passwords/cookies/extensions are preserved.
    WARNING: This restarts Chrome — active calls/meets will be interrupted."""
    if _chrome_cdp_available():
        return {"ok": True, "output": "CDP already active on port 9222"}
    # Check if junctions are set up
    cdp_data = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "CDP_Data")
    if not os.path.exists(os.path.join(cdp_data, "Default")):
        return {"ok": False, "error": "CDP profile junctions not set up. Run setup-permissions to configure."}
    ok = _chrome_ensure_debug_mode()
    if ok:
        tabs = _chrome_get_tabs()
        return {"ok": True, "output": f"CDP enabled on port {CDP_PORT}. {len(tabs)} tab(s) open. Profile: GoldStorm (junction-linked)."}
    return {"ok": False, "error": "Failed to enable CDP. Chrome may need manual restart."}


def cmd_browser_cdp_status(args):
    """Check if Chrome DevTools Protocol is available."""
    if _chrome_cdp_available():
        tabs = _chrome_get_tabs()
        try:
            import requests
            r = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
            browser = r.json().get("Browser", "Chrome")
            return {"ok": True, "output": f"CDP active: {browser}, {len(tabs)} tab(s)", "detail": {"port": CDP_PORT, "tabs": len(tabs), "browser": browser}}
        except Exception:
            return {"ok": True, "output": f"CDP active, {len(tabs)} tab(s)"}
    return {"ok": False, "error": f"CDP not available on port {CDP_PORT}. Run browser-enable-cdp to activate."}


# ============================================================
# COMMANDS — Windows-Specific Extras
# ============================================================

def cmd_installed_apps(args):
    """List installed applications."""
    r = run_powershell('''
Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* |
    Where-Object { $_.DisplayName } |
    Select-Object DisplayName, DisplayVersion |
    Sort-Object DisplayName |
    ForEach-Object { Write-Output "$($_.DisplayName) ($($_.DisplayVersion))" }
''', timeout=15)
    if r["ok"]:
        lines = r["output"].split("\n")
        if len(lines) > 100:
            r["output"] = "\n".join(lines[:100]) + f"\n...(truncated, {len(lines)} total)"
    return r


def cmd_startup_apps(args):
    """List startup applications."""
    r = run_powershell('''
Get-CimInstance Win32_StartupCommand | ForEach-Object {
    Write-Output "$($_.Name) | $($_.Command) | $($_.Location)"
}
''')
    return r


def cmd_disk_usage(args):
    """Disk usage for all drives."""
    r = run_powershell('''
Get-PSDrive -PSProvider FileSystem | ForEach-Object {
    $free = [math]::Round($_.Free/1GB, 1)
    $used = [math]::Round($_.Used/1GB, 1)
    $total = [math]::Round(($_.Free + $_.Used)/1GB, 1)
    $pct = if ($total -gt 0) { [math]::Round(($used/$total)*100, 0) } else { 0 }
    Write-Output "$($_.Name): $used GB used / $total GB total ($pct%) — $free GB free"
}
''')
    return r


def cmd_open_settings(args):
    """Open Windows Settings page."""
    page_map = {
        "": "ms-settings:",
        "display": "ms-settings:display",
        "sound": "ms-settings:sound",
        "network": "ms-settings:network",
        "wifi": "ms-settings:network-wifi",
        "bluetooth": "ms-settings:bluetooth",
        "apps": "ms-settings:appsfeatures",
        "privacy": "ms-settings:privacy",
        "update": "ms-settings:windowsupdate",
        "storage": "ms-settings:storagesense",
        "about": "ms-settings:about",
        "personalization": "ms-settings:personalization",
        "background": "ms-settings:personalization-background",
        "colors": "ms-settings:colors",
        "notifications": "ms-settings:notifications",
        "power": "ms-settings:powersleep",
        "battery": "ms-settings:batterysaver",
        "mouse": "ms-settings:mousetouchpad",
        "keyboard": "ms-settings:keyboard",
        "accounts": "ms-settings:yourinfo",
        "time": "ms-settings:dateandtime",
        "language": "ms-settings:regionlanguage",
        "defaultapps": "ms-settings:defaultapps",
    }
    page = args.page.lower().strip() if args.page else ""
    uri = page_map.get(page, f"ms-settings:{page}" if page else "ms-settings:")
    return run_shell(["cmd", "/c", "start", uri])


def cmd_open_with(args):
    """Open file with specific application."""
    filepath = os.path.expanduser(args.file)
    app = args.app
    try:
        subprocess.Popen([app, filepath], creationflags=CREATE_NO_WINDOW)
        return {"ok": True, "output": f"Opened {filepath} with {app}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_drag(args):
    """Drag from one point to another using win32api."""
    try:
        ctypes.windll.user32.SetCursorPos(args.x1, args.y1)
        time.sleep(0.1)
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
        time.sleep(0.1)
        # Move in steps for smooth drag
        steps = 20
        for i in range(1, steps + 1):
            x = args.x1 + (args.x2 - args.x1) * i // steps
            y = args.y1 + (args.y2 - args.y1) * i // steps
            ctypes.windll.user32.SetCursorPos(x, y)
            time.sleep(0.02)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
        return {"ok": True, "output": f"Dragged from ({args.x1},{args.y1}) to ({args.x2},{args.y2})"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_task_switcher(args):
    """Open Alt+Tab task switcher using keybd_event."""
    try:
        VK_MENU = 0x12  # Alt
        VK_TAB = 0x09
        ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)  # Alt down
        ctypes.windll.user32.keybd_event(VK_TAB, 0, 0, 0)    # Tab down
        time.sleep(0.1)
        ctypes.windll.user32.keybd_event(VK_TAB, 0, 2, 0)    # Tab up
        ctypes.windll.user32.keybd_event(VK_MENU, 0, 2, 0)   # Alt up
        return {"ok": True, "output": "Task switcher opened"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_focus_window(args):
    """Focus a window by title substring."""
    title_search = sanitize_string(args.title)
    return run_powershell(f'''
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public class WinFocus {{
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}}
"@
$procs = Get-Process | Where-Object {{ $_.MainWindowTitle -like "*{title_search}*" }} | Select-Object -First 1
if ($procs) {{
    $hwnd = $procs.MainWindowHandle
    if ([WinFocus]::IsIconic($hwnd)) {{ [void][WinFocus]::ShowWindow($hwnd, 9) }}
    [void][WinFocus]::SetForegroundWindow($hwnd)
    Write-Output "Focused: $($procs.MainWindowTitle)"
}} else {{
    Write-Error "No window found matching: {title_search}"
}}
''')


# ============================================================
# ============================================================
# COMMANDS — Advanced Utilities
# ============================================================

def cmd_download_file(args):
    """Download a file from URL to path."""
    url = args.url
    target = args.path or os.path.join(os.environ.get("USERPROFILE", "."), "Downloads", os.path.basename(url.split("?")[0]))
    try:
        import requests
        r = requests.get(url, timeout=60, stream=True)
        r.raise_for_status()
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        size = os.path.getsize(target)
        return {"ok": True, "output": f"Downloaded {size} bytes to {target}", "file": target}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_open_folder(args):
    """Open a folder in Explorer."""
    path = os.path.expanduser(args.path)
    if os.path.isdir(path):
        return run_shell(["explorer.exe", path])
    return {"ok": False, "error": f"Not a directory: {path}"}


def cmd_set_wallpaper(args):
    """Set desktop wallpaper."""
    path = os.path.expanduser(args.path)
    if not os.path.isfile(path):
        return {"ok": False, "error": f"File not found: {path}"}
    try:
        SPI_SETDESKWALLPAPER = 0x0014
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDCHANGE = 0x02
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, path,
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )
        return {"ok": True, "output": f"Wallpaper set to {path}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_screen_resolution(args):
    """Get or set screen resolution."""
    if args.width and args.height:
        return run_powershell(f'''
Add-Type @"
using System; using System.Runtime.InteropServices;
[StructLayout(LayoutKind.Sequential)] public struct DEVMODE {{
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string dmDeviceName;
    public short dmSpecVersion; public short dmDriverVersion; public short dmSize;
    public short dmDriverExtra; public int dmFields; public int dmPositionX;
    public int dmPositionY; public int dmDisplayOrientation; public int dmDisplayFixedOutput;
    public short dmColor; public short dmDuplex; public short dmYResolution;
    public short dmTTOption; public short dmCollate;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string dmFormName;
    public short dmLogPixels; public int dmBitsPerPel; public int dmPelsWidth;
    public int dmPelsHeight; public int dmDisplayFlags; public int dmDisplayFrequency;
}}
public class Display {{
    [DllImport("user32.dll")] public static extern int ChangeDisplaySettings(ref DEVMODE devMode, int flags);
}}
"@
$dm = New-Object DEVMODE
$dm.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($dm)
$dm.dmPelsWidth = {args.width}
$dm.dmPelsHeight = {args.height}
$dm.dmFields = 0x180000
$result = [Display]::ChangeDisplaySettings([ref]$dm, 0)
if ($result -eq 0) {{ Write-Output "Resolution set to {args.width}x{args.height}" }}
else {{ Write-Error "Failed to change resolution (code: $result)" }}
''')
    else:
        sw, sh = get_screen_size()
        return {"ok": True, "output": f"Current resolution: {sw}x{sh}"}


def cmd_open_task_manager(args):
    """Open Task Manager."""
    return run_shell(["taskmgr.exe"])


def cmd_virtual_desktop_new(args):
    """Create a new virtual desktop (Win+Ctrl+D)."""
    try:
        VK_LWIN = 0x5B
        VK_CONTROL = 0x11
        ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)  # D
        time.sleep(0.1)
        ctypes.windll.user32.keybd_event(0x44, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_LWIN, 0, 2, 0)
        return {"ok": True, "output": "New virtual desktop created"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_virtual_desktop_switch(args):
    """Switch virtual desktop left or right (Win+Ctrl+Arrow)."""
    direction = args.direction
    try:
        VK_LWIN = 0x5B
        VK_CONTROL = 0x11
        VK_ARROW = 0x25 if direction == "left" else 0x27  # LEFT or RIGHT
        ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_ARROW, 0, 0, 0)
        time.sleep(0.1)
        ctypes.windll.user32.keybd_event(VK_ARROW, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_LWIN, 0, 2, 0)
        return {"ok": True, "output": f"Switched to {direction} virtual desktop"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_virtual_desktop_close(args):
    """Close current virtual desktop (Win+Ctrl+F4)."""
    try:
        VK_LWIN = 0x5B
        VK_CONTROL = 0x11
        VK_F4 = 0x73
        ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_F4, 0, 0, 0)
        time.sleep(0.1)
        ctypes.windll.user32.keybd_event(VK_F4, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)
        ctypes.windll.user32.keybd_event(VK_LWIN, 0, 2, 0)
        return {"ok": True, "output": "Virtual desktop closed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cmd_headless_browse(args):
    """Browse a URL in headless mode (background — no GUI, no mouse).
    Returns page text, title, or screenshot without touching your screen."""
    url = args.url
    action = args.action or "text"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            if action == "text":
                text = page.inner_text("body")[:5000]
                title = page.title()
                result = {"ok": True, "output": f"Title: {title}\n\n{text}"}
            elif action == "screenshot":
                target = args.path or os.path.join(os.environ.get("TEMP", "."), "headless_screenshot.png")
                page.screenshot(path=target, full_page=True)
                result = {"ok": True, "output": f"Screenshot saved to {target}", "file": target}
            elif action == "links":
                links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href + ' | ' + e.innerText.trim()).slice(0, 50)")
                result = {"ok": True, "output": "\n".join(links) if links else "No links found"}
            elif action == "title":
                result = {"ok": True, "output": page.title()}
            elif action == "html":
                result = {"ok": True, "output": page.content()[:10000]}
            else:
                result = {"ok": False, "error": f"Unknown action: {action}"}

            browser.close()
            return result
    except ImportError:
        return {"ok": False, "error": "Playwright not installed. Run: pip install playwright && playwright install chromium"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# MAIN
# ============================================================

def main():
    guard_windows()

    # Handle --json flag in any position
    json_output = "--json" in sys.argv
    if json_output:
        sys.argv.remove("--json")

    parser = argparse.ArgumentParser(description="Windows Computer Control V2.1")
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- App control ----
    p = sub.add_parser("open", help="Open/activate an application")
    p.add_argument("--app", required=True)

    p = sub.add_parser("quit", help="Quit an application")
    p.add_argument("--app", required=True)

    p = sub.add_parser("type", help="Type text into frontmost app")
    p.add_argument("--text", required=True)

    p = sub.add_parser("keystroke", help="Send key combo (e.g., ctrl+c, win+d)")
    p.add_argument("--keys", required=True)

    p = sub.add_parser("click", help="Click at screen coordinates")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)

    sub.add_parser("list-windows", help="List visible windows")
    sub.add_parser("list-apps", help="List running applications")
    sub.add_parser("frontmost", help="Get foreground window")

    p = sub.add_parser("screenshot", help="Take a screenshot")
    p.add_argument("--path", help="Save path")

    p = sub.add_parser("url", help="Open a URL in default browser")
    p.add_argument("--url", required=True)

    p = sub.add_parser("say", help="Speak text aloud")
    p.add_argument("--text", required=True)

    p = sub.add_parser("volume", help="Set system volume (0-100)")
    p.add_argument("--level", type=int, required=True)

    p = sub.add_parser("notify", help="Send a Windows notification")
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

    p = sub.add_parser("window-fullscreen", help="Toggle maximize for app")
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
    p = sub.add_parser("screenshot-window", help="Screenshot foreground window only")
    p.add_argument("--path", help="Save path")

    # ---- Screen recording ----
    p = sub.add_parser("record-start", help="Start screen recording (ffmpeg)")
    p.add_argument("--path", help="Save path")

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
    sub.add_parser("trash-empty", help="Empty the Recycle Bin")
    sub.add_parser("battery", help="Show battery status")

    # ---- Clipboard ----
    sub.add_parser("clipboard-read", help="Read clipboard contents")

    p = sub.add_parser("clipboard-write", help="Write text to clipboard")
    p.add_argument("--text", required=True)

    # ---- System info ----
    sub.add_parser("sysinfo", help="Full system info snapshot")

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

    p = sub.add_parser("search-files", help="Search files by name")
    p.add_argument("--query", required=True)
    p.add_argument("--dir", help="Limit search to directory")

    p = sub.add_parser("reveal-in-explorer", help="Show file in Explorer")
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

    p = sub.add_parser("mouse-move", help="Move mouse to coordinates")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)

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
    p = sub.add_parser("shutdown", help="Shut down the PC (needs --confirm)")
    p.add_argument("--confirm", action="store_true")

    p = sub.add_parser("restart", help="Restart the PC (needs --confirm)")
    p.add_argument("--confirm", action="store_true")

    p = sub.add_parser("logout", help="Log out (needs --confirm)")
    p.add_argument("--confirm", action="store_true")

    # ---- Setup/permissions check ----
    sub.add_parser("setup-permissions", help="Verify all dependencies work (run once)")

    # ---- Browser control (Chrome via DevTools Protocol) ----
    p = sub.add_parser("browser-open", help="Open URL in Chrome, wait for load")
    p.add_argument("--url", required=True)

    p = sub.add_parser("browser-js", help="Execute JavaScript in Chrome tab")
    p.add_argument("--script", required=True)

    sub.add_parser("browser-tab-url", help="Get current Chrome tab URL")
    sub.add_parser("browser-tab-title", help="Get current Chrome tab title")

    p = sub.add_parser("browser-new-tab", help="Open new Chrome tab with URL")
    p.add_argument("--url", default="about:blank")

    sub.add_parser("browser-close-tab", help="Close active Chrome tab")
    sub.add_parser("browser-list-tabs", help="List all Chrome tabs with URLs")

    p = sub.add_parser("browser-switch-tab", help="Switch to Chrome tab by number")
    p.add_argument("--tab", type=int, required=True)

    sub.add_parser("browser-back", help="Go back in browser history")
    sub.add_parser("browser-forward", help="Go forward in browser history")
    sub.add_parser("browser-reload", help="Reload the current page")

    p = sub.add_parser("browser-screenshot", help="Screenshot the browser page via CDP")
    p.add_argument("--path", help="Save path")

    sub.add_parser("browser-get-text", help="Get visible text from current page")

    p = sub.add_parser("browser-click-element", help="Click element by CSS selector")
    p.add_argument("--selector", required=True)

    p = sub.add_parser("browser-fill", help="Fill input field by CSS selector")
    p.add_argument("--selector", required=True)
    p.add_argument("--value", required=True)

    # ---- Windows-specific extras ----
    sub.add_parser("installed-apps", help="List installed applications")
    sub.add_parser("startup-apps", help="List startup applications")
    sub.add_parser("disk-usage", help="Disk usage for all drives")

    p = sub.add_parser("open-settings", help="Open Windows Settings page")
    p.add_argument("--page", default="", help="Settings page (e.g., display, sound, network, bluetooth)")

    p = sub.add_parser("open-with", help="Open file with specific application")
    p.add_argument("--file", required=True)
    p.add_argument("--app", required=True)

    p = sub.add_parser("drag", help="Drag from one point to another")
    p.add_argument("--x1", type=int, required=True)
    p.add_argument("--y1", type=int, required=True)
    p.add_argument("--x2", type=int, required=True)
    p.add_argument("--y2", type=int, required=True)

    sub.add_parser("task-switcher", help="Open Alt+Tab task switcher")

    p = sub.add_parser("focus-window", help="Focus window by title substring")
    p.add_argument("--title", required=True)

    # ---- Browser CDP management ----
    sub.add_parser("browser-enable-cdp", help="Enable Chrome DevTools Protocol (restarts Chrome)")
    sub.add_parser("browser-cdp-status", help="Check Chrome DevTools Protocol status")

    # ---- Advanced utilities ----
    p = sub.add_parser("download-file", help="Download file from URL")
    p.add_argument("--url", required=True)
    p.add_argument("--path", help="Save path (default: Downloads)")

    p = sub.add_parser("open-folder", help="Open folder in Explorer")
    p.add_argument("--path", required=True)

    p = sub.add_parser("set-wallpaper", help="Set desktop wallpaper")
    p.add_argument("--path", required=True)

    p = sub.add_parser("screen-resolution", help="Get/set screen resolution")
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)

    sub.add_parser("open-task-manager", help="Open Task Manager")

    # ---- Virtual desktops ----
    sub.add_parser("virtual-desktop-new", help="Create new virtual desktop")

    p = sub.add_parser("virtual-desktop-switch", help="Switch virtual desktop")
    p.add_argument("--direction", choices=["left", "right"], required=True)

    sub.add_parser("virtual-desktop-close", help="Close current virtual desktop")

    # ---- Headless browser (background — no GUI) ----
    p = sub.add_parser("headless-browse", help="Browse URL in background (no GUI)")
    p.add_argument("--url", required=True)
    p.add_argument("--action", choices=["text", "screenshot", "links", "title", "html"], default="text")
    p.add_argument("--path", help="Save path for screenshot")

    args = parser.parse_args()

    # SECURITY: Sanitize string arguments
    if hasattr(args, 'app') and args.app:
        args.app = sanitize_string(args.app)
    if hasattr(args, 'url') and args.url:
        args.url = sanitize_url(args.url)
    if hasattr(args, 'title') and args.title:
        args.title = sanitize_string(args.title)
    if hasattr(args, 'message') and args.message:
        args.message = sanitize_string(args.message)

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
        # App control
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
        # File operations
        "list-files": cmd_list_files, "read-file": cmd_read_file,
        "write-file": cmd_write_file, "move-file": cmd_move_file,
        "copy-file": cmd_copy_file, "delete-file": cmd_delete_file,
        "search-files": cmd_search_files, "reveal-in-explorer": cmd_reveal_in_explorer,
        # Process management
        "list-processes": cmd_list_processes, "kill-process": cmd_kill_process,
        # Advanced input
        "right-click": cmd_right_click, "double-click": cmd_double_click,
        "scroll": cmd_scroll, "mouse-move": cmd_mouse_move,
        # Audio devices
        "list-audio": cmd_list_audio, "switch-audio": cmd_switch_audio,
        # Network
        "get-ip": cmd_get_ip, "ping": cmd_ping,
        # Power (destructive)
        "shutdown": cmd_shutdown, "restart": cmd_restart, "logout": cmd_logout,
        # Setup check
        "setup-permissions": cmd_setup_permissions,
        # Browser control (Chrome)
        "browser-open": cmd_browser_open, "browser-js": cmd_browser_js,
        "browser-tab-url": cmd_browser_tab_url, "browser-tab-title": cmd_browser_tab_title,
        "browser-new-tab": cmd_browser_new_tab, "browser-close-tab": cmd_browser_close_tab,
        "browser-list-tabs": cmd_browser_list_tabs, "browser-switch-tab": cmd_browser_switch_tab,
        "browser-back": cmd_browser_back, "browser-forward": cmd_browser_forward,
        "browser-reload": cmd_browser_reload, "browser-screenshot": cmd_browser_screenshot,
        "browser-get-text": cmd_browser_get_text,
        "browser-click-element": cmd_browser_click_element, "browser-fill": cmd_browser_fill,
        # Windows-specific extras
        "installed-apps": cmd_installed_apps, "startup-apps": cmd_startup_apps,
        "disk-usage": cmd_disk_usage, "open-settings": cmd_open_settings,
        "open-with": cmd_open_with, "drag": cmd_drag,
        "task-switcher": cmd_task_switcher, "focus-window": cmd_focus_window,
        # Browser CDP management
        "browser-enable-cdp": cmd_browser_enable_cdp, "browser-cdp-status": cmd_browser_cdp_status,
        # Advanced utilities
        "download-file": cmd_download_file, "open-folder": cmd_open_folder,
        "set-wallpaper": cmd_set_wallpaper, "screen-resolution": cmd_screen_resolution,
        "open-task-manager": cmd_open_task_manager,
        # Virtual desktops
        "virtual-desktop-new": cmd_virtual_desktop_new,
        "virtual-desktop-switch": cmd_virtual_desktop_switch,
        "virtual-desktop-close": cmd_virtual_desktop_close,
        # Headless browser
        "headless-browse": cmd_headless_browse,
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
