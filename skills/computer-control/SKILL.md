---
name: computer-control
description: Full desktop autonomy via Telegram — 60+ commands for app control, windows, browser, files, mouse, audio, power. Routes to macOS AppleScript or Windows PowerShell based on platform. Triggered by natural-language intent ("open Chrome", "take a screenshot", "lock my computer").
tags: [skill]
triggers: ["computer control", "use computer control", "run computer control"]
---

# Computer Control V2.1 — Full Desktop Autonomy (60+ Commands)

## Overview

CC says anything implying computer control via Telegram. Claude translates intent into the correct command. On macOS: `scripts/macos_control.py` (60+ AppleScript commands). On Windows: native shell/PowerShell commands.

**Core principle:** Claude interprets intent and picks the right tool. The user never types commands.

**File relay:** Screenshots, recordings, and files are automatically sent back to the Telegram chat.

**First run:** `python3 scripts/macos_control.py setup-permissions` — triggers all macOS permission prompts at once. Click Allow on each. After that, no more popups.

## macOS Commands (via macos_control.py)

### App Control
| Command | What it does |
|---------|-------------|
| `open --app <name>` | Activate/launch app |
| `quit --app <name>` | Quit app |
| `list-apps` | Running applications |
| `frontmost` | Current foreground app |

### Input Simulation
| Command | What it does |
|---------|-------------|
| `type --text "..."` | Type into frontmost app |
| `keystroke --keys "cmd+c"` | Send key combination |
| `click --x <px> --y <px>` | Click at coordinates |
| `right-click --x <px> --y <px>` | Right-click at coordinates |
| `double-click --x <px> --y <px>` | Double-click at coordinates |
| `scroll --direction up\|down [--amount N]` | Scroll up/down |
| `mouse-move --x <px> --y <px>` | Move cursor to position |

### Window Management
| Command | What it does |
|---------|-------------|
| `window-move --app X --x N --y N` | Move window |
| `window-resize --app X --w N --h N` | Resize window |
| `window-fullscreen --app X` | Toggle fullscreen |
| `window-left --app X` | Snap to left half |
| `window-right --app X` | Snap to right half |
| `window-center --app X` | Center on screen |
| `window-minimize --app X` | Minimize |
| `window-restore --app X` | Unminimize |
| `list-windows` | All visible windows with positions |

### Screenshots & Recording
| Command | What it does |
|---------|-------------|
| `screenshot [--path /tmp/X.png]` | Full screen capture |
| `screenshot-window [--path /tmp/X.png]` | Frontmost window only |
| `record-start [--path /tmp/X.mov]` | Start screen recording |
| `record-stop` | Stop recording |

### System Toggles
| Command | What it does |
|---------|-------------|
| `dark-mode [--toggle\|--on\|--off]` | Dark mode |
| `dnd --on\|--off` | Do Not Disturb / Focus |
| `wifi --on\|--off` | WiFi toggle |
| `bluetooth --on\|--off` | Bluetooth toggle |
| `brightness --level <0-100>` | Display brightness |
| `volume --level <0-100>` | System volume |
| `mute [--toggle\|--on\|--off]` | Mute/unmute |
| `sleep-display` | Put display to sleep |
| `lock-screen` | Lock the screen |
| `trash-empty` | Empty the Trash |
| `battery` | Battery status & time remaining |
| `sysinfo` | Full system snapshot |

### Clipboard
| Command | What it does |
|---------|-------------|
| `clipboard-read` | Read clipboard contents |
| `clipboard-write --text "..."` | Write to clipboard |

### File Operations
| Command | What it does |
|---------|-------------|
| `list-files [--path X] [--recursive]` | List directory contents |
| `read-file --path X` | Read text file (10KB max) |
| `write-file --path X --content "..."` | Write text to file |
| `move-file --src X --dst Y` | Move/rename file |
| `copy-file --src X --dst Y` | Copy file or directory |
| `delete-file --path X [--force]` | Delete file (--force for dirs) |
| `search-files --query X [--dir Y]` | Spotlight search |
| `reveal-in-finder --path X` | Show in Finder |

### Process Management
| Command | What it does |
|---------|-------------|
| `list-processes [--sort cpu\|mem] [--limit N]` | Running processes |
| `kill-process --pid N` | Kill by PID |
| `kill-process --name X` | Kill by name |

### Network
| Command | What it does |
|---------|-------------|
| `get-ip` | Local and public IP |
| `ping --host X [--count N]` | Ping a host |

### Audio Devices
| Command | What it does |
|---------|-------------|
| `list-audio` | List audio I/O devices |
| `switch-audio --device X` | Switch output device |

### Power (Destructive — requires --confirm)
| Command | What it does |
|---------|-------------|
| `shutdown --confirm` | Shut down Mac |
| `restart --confirm` | Restart Mac |
| `logout --confirm` | Log out current user |

### Media & Utilities
| Command | What it does |
|---------|-------------|
| `say --text "..."` | Text-to-speech |
| `url --url "..."` | Open URL in default browser |
| `notify --title "..." --message "..."` | macOS notification |

### Browser Control (Chrome)
| Command | What it does |
|---------|-------------|
| `browser-open --url "..."` | Open URL in Chrome, wait for load |
| `browser-js --script "..."` | Execute JavaScript in active tab |
| `browser-tab-url` | Get current tab URL |
| `browser-tab-title` | Get current tab title |
| `browser-new-tab --url "..."` | Open new tab with URL |
| `browser-close-tab` | Close active tab |
| `browser-list-tabs` | List all open tabs |
| `browser-switch-tab --tab N` | Switch to tab by number |

**Prerequisite:** Chrome > View > Developer > Allow JavaScript from Apple Events (one-time toggle).

### Permissions Setup
| Command | What it does |
|---------|-------------|
| `setup-permissions` | Trigger ALL macOS permission prompts at once |

Run once — click Allow on each popup. Covers: Accessibility, Chrome, Finder, Safari, Mail, System Settings, Notes, Calendar, Messages, Screen Recording, Notifications.

### SoundCloud Music (via `scripts/music_control.py`)
| Command | What it does |
|---------|-------------|
| `play --query "..."` | Search and play a track |
| `pause` | Pause playback |
| `resume` | Resume playback |
| `skip` | Next track |
| `previous` | Previous track |
| `current` | Now playing info |
| `search --query "..."` | Search without playing |

Run music: `python3 scripts/music_control.py <command> [args] [--json]`

All macos_control commands: `python3 scripts/macos_control.py <command> [--json]`

## Natural Language Mapping

| CC says | Command(s) |
|---------|------------|
| "open my email" | `browser-open --url "https://gmail.com"` |
| "snap Safari to the left" | `window-left --app Safari` |
| "take a screenshot" | `screenshot` → auto-sent to Telegram |
| "start recording" | `record-start` |
| "toggle dark mode" | `dark-mode --toggle` |
| "what's on my clipboard?" | `clipboard-read` |
| "how's my battery?" | `battery` |
| "play 24 songs by Carti" | `music_control.py play --query "..."` |
| "open google.com" | `browser-open --url "https://google.com"` |
| "list my tabs" | `browser-list-tabs` |
| "what's my IP?" | `get-ip` |
| "list files on Desktop" | `list-files --path ~/Desktop` |
| "find invoices" | `search-files --query "invoice"` |
| "kill Chrome" | `kill-process --name Chrome` |
| "scroll down" | `scroll --direction down` |
| "ping google" | `ping --host google.com` |
| "restart my computer" | `restart --confirm` (with approval gate) |
| "show file in Finder" | `reveal-in-finder --path X` |
| "what processes are using CPU?" | `list-processes --sort cpu --limit 10` |

## Approval Gate

**Actions requiring confirmation** (output `⚠️ CONFIRM: [description]` and STOP):
- Deleting files or directories
- Sending emails or messages
- Running database mutations
- Publishing content
- Shutting down/restarting/logging out
- Emptying trash
- Turning off WiFi/Bluetooth
- Killing processes

**Actions NOT requiring confirmation:**
- Opening/closing apps or URLs
- Screenshots, recordings
- Window management
- Volume, brightness, mute, dark mode
- Reading clipboard or system info
- Typing, clicking, scrolling
- File listing, reading, searching
- Network diagnostics (ping, IP)

## Windows Implementation Path

When CC is back on the Windows desktop, create `scripts/windows_control.py` mirroring the macOS command set. The bridge already detects platform (`IS_MAC`/`IS_WIN`) and routes `python`/`python3` correctly.

### Command Mapping (macOS → Windows)

| Category | macOS (osascript) | Windows Equivalent |
|----------|------------------|--------------------|
| **App control** | AppleScript `activate` | PowerShell `Start-Process`, `Stop-Process` |
| **Window mgmt** | System Events AppleScript | `pywin32` (`win32gui.MoveWindow`, `SetWindowPos`) |
| **Input simulation** | Quartz CGEvents | `pyautogui` or `pynput` (pip install) |
| **Screenshots** | `screencapture` CLI | `Pillow` (`ImageGrab.grab()`) or `mss` |
| **Screen recording** | `screencapture -v` | `ffmpeg -f gdigrab` |
| **System toggles** | AppleScript / `defaults write` | PowerShell (`Set-WmiInstance`, Registry, `nircmd`) |
| **Dark mode** | System Events | `reg add "HKCU\...\Themes\Personalize"` |
| **Volume/mute** | osascript | `nircmd` or `pycaw` |
| **Brightness** | DisplayServices framework | `WmiMonitorBrightnessMethods` (WMI) |
| **Clipboard** | `pbcopy`/`pbpaste` | `pyperclip` or PowerShell `Get-Clipboard` |
| **Files** | Python stdlib (same) | Python stdlib (same — already cross-platform) |
| **Processes** | `ps aux` | `tasklist`, `taskkill`, `wmic process` |
| **Network** | `ifconfig`, `ipify.org` | `ipconfig`, `ipify.org` |
| **Browser** | Chrome AppleScript | Chrome DevTools Protocol via `--remote-debugging-port` |
| **Notifications** | osascript display notification | `plyer` or PowerShell `BurntToast` module |
| **Power** | AppleScript `shut down` | `shutdown /s /t 0`, `shutdown /r /t 0`, `logoff` |
| **Audio devices** | `system_profiler`, `SwitchAudioSource` | `pycaw` or `nircmd` |
| **DND/Focus** | `shortcuts run` | Focus Assist via Registry |
| **Lock screen** | `pmset displaysleepnow` | `rundll32 user32.dll,LockWorkStation` |

### Dependencies Needed on Windows
```
pip install pyautogui pyperclip pywin32 pillow pycaw plyer mss
```

### Architecture
- Same CLI interface: `python scripts/windows_control.py <command> --json`
- Same argparse structure, same JSON output format
- telegram_agent.js already routes `PYTHON` correctly per platform
- Same security gates (sensitive paths adapt to `C:\Users\...`, protected processes adapt to `explorer.exe`, `dwm.exe`, etc.)

### Effort Estimate
- Human team: ~3 days
- CC + Bravo: ~45 min (~100x leverage)
- File operations and network commands work as-is (Python stdlib)
- Main work: window management (pywin32), input simulation (pyautogui), system toggles (PowerShell/Registry)

## Obsidian Links
- [[brain/CAPABILITIES]] | [[brain/AGENTS]]
- [[skills/browser-automation/SKILL.md]] | [[skills/security-protocol/SKILL.md]]
