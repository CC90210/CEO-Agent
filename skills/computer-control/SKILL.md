---
tags: [skill]
---

# Computer Control — Natural Language Desktop Automation

## Overview

CC says "open my email" or "take a screenshot" via Telegram. Claude translates intent into the correct platform command. On macOS: `scripts/macos_control.py` (AppleScript wrapper). On Windows: native shell/PowerShell commands.

**Core principle:** Claude interprets intent and picks the right tool. The user never types commands.

## When to Use

- CC sends a message implying local computer control
- Opening apps, typing text, sending keystrokes, taking screenshots
- Checking running apps, frontmost window
- Opening URLs, adjusting volume, sending notifications

## macOS Commands (via macos_control.py)

| Command | What it does | Example |
|---------|-------------|---------|
| `open --app <name>` | Activate/launch app | `open --app Safari` |
| `type --text "..."` | Type into frontmost app | `type --text "Hello"` |
| `keystroke --keys "cmd+c"` | Send key combination | `keystroke --keys "cmd+v"` |
| `click --x <px> --y <px>` | Click at coordinates | `click --x 500 --y 300` |
| `list-windows` | All visible windows with positions | |
| `list-apps` | Running applications | |
| `frontmost` | Current foreground app | |
| `screenshot [--path ...]` | Capture screen | `screenshot --path /tmp/ss.png` |
| `url --url "..."` | Open URL in browser | `url --url "https://gmail.com"` |
| `say --text "..."` | Speak text aloud | `say --text "Task complete"` |
| `volume --level <0-100>` | Set system volume | `volume --level 50` |
| `notify --title "..." --message "..."` | macOS notification | |

All commands support `--json` flag. Run from project root: `python3 scripts/macos_control.py <command>`

## Natural Language Mapping

| CC says | Command |
|---------|---------|
| "open my email" | `open --app Mail` or `url --url "https://gmail.com"` |
| "check what's open" | `list-apps` then `frontmost` |
| "copy that" | `keystroke --keys "cmd+c"` |
| "paste it" | `keystroke --keys "cmd+v"` |
| "take a screenshot" | `screenshot` |
| "open YouTube" | `url --url "https://youtube.com"` |
| "mute" | `volume --level 0` |
| "switch to Chrome" | `open --app "Google Chrome"` |
| "play some music" | `open --app Spotify` |

## Direct Shell Alternative

Claude can also use raw `osascript` and macOS shell commands directly:
- `osascript -e 'tell application "Finder" to activate'`
- `open -a Safari https://gmail.com`
- `screencapture -x /tmp/screen.png`

Use `macos_control.py` when available. Fall back to raw commands if needed.

## Approval Gate

**Actions requiring confirmation** (output `⚠️ CONFIRM: [description]` and STOP):
- Deleting files or directories
- Sending emails or messages
- Running database mutations
- Publishing content
- Shutting down or restarting
- Any command modifying data permanently

**Actions NOT requiring confirmation:**
- Opening apps or URLs
- Taking screenshots
- Listing windows/apps
- Adjusting volume
- Typing text or keystrokes (user explicitly asked)

## Prerequisites

### macOS Accessibility Permissions (One-Time)

`type`, `keystroke`, `click`, `list-windows`, `list-apps`, `frontmost` require Accessibility permissions:
1. System Settings > Privacy & Security > Accessibility
2. Enable the terminal app (Terminal.app, iTerm2, or Node.js binary)

Without permissions, `open`, `screenshot`, `url`, `say`, `volume`, `notify` still work.

## Obsidian Links
- [[brain/CAPABILITIES]] | [[brain/AGENTS]]
- [[skills/browser-automation/SKILL]] | [[skills/security-protocol/SKILL]]
