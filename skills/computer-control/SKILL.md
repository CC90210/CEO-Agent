---
tags: [skill]
---

# Computer Control V2.0 — Full Desktop Autonomy

## Overview

CC says "open my email", "snap Safari to the left", "toggle dark mode", or "what's on my clipboard?" via Telegram. Claude translates intent into the correct platform command. On macOS: `scripts/macos_control.py` (35+ AppleScript commands). On Windows: native shell/PowerShell commands.

**Core principle:** Claude interprets intent and picks the right tool. The user never types commands.

**File relay:** Screenshots, recordings, and files are automatically sent back to the Telegram chat as images/videos/documents.

## When to Use

- CC sends a message implying local computer control
- Opening/quitting apps, typing text, sending keystrokes
- Window management (move, resize, split, fullscreen)
- Screenshots, screen recording
- System toggles (dark mode, WiFi, Bluetooth, DND, brightness)
- Clipboard read/write
- Music playback via SoundCloud browser
- System diagnostics (battery, disk, RAM, CPU)

## macOS Commands (via macos_control.py)

### App Control
| Command | What it does |
|---------|-------------|
| `open --app <name>` | Activate/launch app |
| `quit --app <name>` | Quit app |
| `list-apps` | Running applications |
| `frontmost` | Current foreground app |

### Input
| Command | What it does |
|---------|-------------|
| `type --text "..."` | Type into frontmost app |
| `keystroke --keys "cmd+c"` | Send key combination |
| `click --x <px> --y <px>` | Click at coordinates |

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
| `sysinfo` | Full system snapshot (battery, disk, RAM, CPU, WiFi, display) |

### Clipboard
| Command | What it does |
|---------|-------------|
| `clipboard-read` | Read clipboard contents |
| `clipboard-write --text "..."` | Write to clipboard |

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
Without this, `browser-js` won't work — but all other browser commands work fine.

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

All macos_control commands support `--json` flag. Run from project root: `python3 scripts/macos_control.py <command>`

## Natural Language Mapping

| CC says | Command(s) |
|---------|------------|
| "open my email" | `url --url "https://gmail.com"` |
| "snap Safari to the left" | `window-left --app Safari` |
| "put Chrome on the right" | `window-right --app "Google Chrome"` |
| "make Terminal fullscreen" | `window-fullscreen --app Terminal` |
| "take a screenshot" | `screenshot` → auto-sent to Telegram |
| "start recording my screen" | `record-start` |
| "stop recording" | `record-stop` → video sent to Telegram |
| "toggle dark mode" | `dark-mode --toggle` |
| "turn off WiFi" | `wifi --off` |
| "what's on my clipboard?" | `clipboard-read` |
| "copy this to clipboard: ..." | `clipboard-write --text "..."` |
| "how's my battery?" | `battery` |
| "system info" | `sysinfo` |
| "mute" | `mute --on` |
| "play 24 songs by Playboy Carti" | `music_control.py play --query "24 songs playboy carti"` |
| "pause the music" | `music_control.py pause` |
| "skip this song" | `music_control.py skip` |
| "what's playing?" | `music_control.py current` |
| "open google.com" | `browser-open --url "https://google.com"` |
| "list my tabs" | `browser-list-tabs` |
| "close this tab" | `browser-close-tab` |
| "close Chrome" | `quit --app "Google Chrome"` |
| "what apps are running?" | `list-apps` |
| "lock my screen" | `lock-screen` |

## SoundCloud Music Control

Use `scripts/music_control.py` — atomic commands via Chrome (no manual browser steps):
- `python3 scripts/music_control.py play --query "artist or song"` — searches + navigates + plays in ONE call
- `python3 scripts/music_control.py pause` / `resume` / `skip` / `previous`
- `python3 scripts/music_control.py current` — what's playing now

## Approval Gate

**Actions requiring confirmation** (output `⚠️ CONFIRM: [description]` and STOP):
- Deleting files or directories
- Sending emails or messages
- Running database mutations
- Publishing content
- Shutting down/restarting/locking the screen
- Emptying trash
- Turning off WiFi/Bluetooth

**Actions NOT requiring confirmation:**
- Opening/closing apps or URLs
- Taking screenshots or recordings
- Window management (move, resize, split)
- Adjusting volume, brightness, mute
- Reading clipboard or system info
- Typing text or keystrokes (user explicitly asked)
- Toggling dark mode

## Prerequisites

### macOS Accessibility Permissions (One-Time)

`type`, `keystroke`, `click`, `list-windows`, `list-apps`, `frontmost`, and all window management commands require Accessibility permissions:
1. System Settings > Privacy & Security > Accessibility
2. Enable the terminal app (Terminal.app, iTerm2, or Node.js binary)

Without permissions, these still work: `open`, `quit`, `screenshot`, `url`, `say`, `volume`, `mute`, `notify`, `dark-mode`, `battery`, `sysinfo`, `clipboard-read`, `clipboard-write`, `record-start`, `record-stop`

## Obsidian Links
- [[brain/CAPABILITIES]] | [[brain/AGENTS]]
- [[skills/browser-automation/SKILL]] | [[skills/security-protocol/SKILL]]
