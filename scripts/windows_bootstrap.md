# Windows Computer Control — Bootstrap Prompt

> Paste the SYSTEM PROMPT section below into Claude Code on your Windows desktop.
> Make sure you're in the `business-empire-agent` repo first (`cd C:\Users\User\Downloads\business-empire-agent` or wherever you cloned it).

## Pre-requisites (do these manually first)

1. **Pull the latest repo:**
   ```
   cd C:\Users\User\Downloads\business-empire-agent
   git pull origin main
   ```

2. **Install Python dependencies:**
   ```
   pip install pyautogui pyperclip pywin32 pillow pycaw plyer mss comtypes pynput
   ```

3. **Install Node dependencies (if not already):**
   ```
   npm install
   ```

4. **Verify `.env.agents` exists** with your `TELEGRAM_BOT_TOKEN` and `ANTHROPIC_API_KEY`.

5. **Open Claude Code in the repo directory**, then paste the system prompt below.

---

## SYSTEM PROMPT (copy everything between the dashes)

---

You are building `scripts/windows_control.py` — the Windows equivalent of `scripts/macos_control.py`. This is for the Bravo Telegram Bridge, which gives full remote desktop control from Telegram.

### YOUR TASK

Build `scripts/windows_control.py` that mirrors the EXACT same CLI interface as `scripts/macos_control.py`. Same commands, same argparse structure, same `--json` output format. The Telegram bridge (`telegram_agent.js`) already detects Windows and routes to `python` instead of `python3` — it expects `windows_control.py` to exist with identical command names.

### STEP 1: Read these files first

1. `scripts/macos_control.py` — this is the reference. Every command in here needs a Windows equivalent.
2. `skills/computer-control/SKILL.md` — scroll to "Windows Implementation Path" for the command mapping table.
3. `telegram_agent.js` — search for `IS_WIN` and `windows_control` to understand how the bridge calls it.
4. `scripts/music_control.py` — SoundCloud music control, also needs Windows Chrome automation.

### STEP 2: Build `scripts/windows_control.py`

Requirements:
- Same argparse CLI: `python scripts/windows_control.py <command> [--args] [--json]`
- Same JSON output: `{"ok": true, "output": "..."}` or `{"ok": false, "error": "..."}`
- Same command names (all 60+): open, quit, type, keystroke, click, list-windows, list-apps, frontmost, screenshot, url, say, volume, notify, window-move, window-resize, window-fullscreen, window-left, window-right, window-center, window-minimize, window-restore, screenshot-window, record-start, record-stop, dark-mode, dnd, wifi, bluetooth, brightness, mute, sleep-display, lock-screen, trash-empty, battery, clipboard-read, clipboard-write, sysinfo, list-files, read-file, write-file, move-file, copy-file, delete-file, search-files, reveal-in-finder (reveal-in-explorer on Windows), list-processes, kill-process, right-click, double-click, scroll, mouse-move, list-audio, switch-audio, get-ip, ping, shutdown, restart, logout, setup-permissions, browser-open, browser-js, browser-tab-url, browser-tab-title, browser-new-tab, browser-close-tab, browser-list-tabs, browser-switch-tab

Windows-specific implementations:
- **App control**: `subprocess.Popen` for open, `taskkill` for quit, PowerShell `Get-Process` for list
- **Window management**: `pywin32` — `win32gui.FindWindow`, `win32gui.MoveWindow`, `win32gui.SetForegroundWindow`
- **Input simulation**: `pyautogui` — click, type, hotkey, scroll, moveTo
- **Screenshots**: `mss` or `Pillow` ImageGrab
- **Screen recording**: `ffmpeg -f gdigrab` (check if ffmpeg is available)
- **System toggles**: PowerShell commands, Registry edits, `nircmd` (optional fallback)
- **Dark mode**: `reg add "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize" /v AppsUseLightTheme /t REG_DWORD /d 0 /f`
- **Volume/mute**: `pycaw` (Python Core Audio Windows) or `nircmd`
- **Brightness**: WMI `WmiMonitorBrightnessMethods`
- **Clipboard**: `pyperclip` (cross-platform)
- **Files**: Python stdlib `os`, `shutil`, `pathlib` (already cross-platform)
- **Processes**: `tasklist`, `taskkill`, or `psutil` if available
- **Network**: `ipconfig` for local IP, `ipify.org` for public
- **Browser (Chrome)**: Chrome DevTools Protocol — launch Chrome with `--remote-debugging-port=9222`, use `requests` to send commands via CDP JSON API. Alternative: PowerShell COM automation.
- **Notifications**: `plyer` library or PowerShell BurntToast module
- **Power**: `shutdown /s /t 0` (shutdown), `shutdown /r /t 0` (restart), `shutdown /l` (logoff)
- **Audio devices**: `pycaw` or PowerShell `Get-AudioDevice`
- **Lock screen**: `rundll32.exe user32.dll,LockWorkStation`
- **Text-to-speech**: PowerShell `Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("text")`

### STEP 3: Security (copy from macOS)

Copy these EXACT security patterns from `macos_control.py`:
- `sanitize_applescript_string()` → rename to `sanitize_shell_string()` — strip `"`, `\`, `\n`, `\r`, backticks, `$(`
- `SENSITIVE_PATHS` — adapt to Windows: `C:\Users\*\.ssh`, `C:\Users\*\.aws`, `.env`, credentials, etc.
- `PROTECTED_PROCESSES` — adapt: `explorer.exe`, `dwm.exe`, `csrss.exe`, `wininit.exe`, `lsass.exe`, `services.exe`, `svchost.exe`, `pm2`
- `is_sensitive_path()` — same logic, Windows path separators
- Centralized args sanitization in `main()` — same pattern
- `--confirm` flag required for shutdown, restart, logout

### STEP 4: Update `telegram_agent.js` routing

The bridge file already has `IS_WIN` detection. Check that it routes to `windows_control.py` correctly:
- Search for any hardcoded `macos_control.py` references — they should be conditional on `IS_MAC`
- The `PYTHON` constant is already set to `'python'` on Windows

### STEP 5: Test everything

Run these commands and verify JSON output:
```
python scripts/windows_control.py frontmost --json
python scripts/windows_control.py list-apps --json
python scripts/windows_control.py volume --level 50 --json
python scripts/windows_control.py screenshot --json
python scripts/windows_control.py clipboard-write --text "test" --json
python scripts/windows_control.py clipboard-read --json
python scripts/windows_control.py sysinfo --json
python scripts/windows_control.py battery --json
python scripts/windows_control.py get-ip --json
python scripts/windows_control.py list-processes --sort cpu --limit 5 --json
python scripts/windows_control.py dark-mode --toggle --json
python scripts/windows_control.py brightness --level 80 --json
python scripts/windows_control.py open --app notepad --json
python scripts/windows_control.py type --text "Hello from Bravo" --json
python scripts/windows_control.py screenshot --json
python scripts/windows_control.py quit --app notepad --json
```

Also test security blocks:
```
python scripts/windows_control.py read-file --path C:\Users\User\.ssh\id_rsa --json
python scripts/windows_control.py kill-process --name explorer.exe --json
python scripts/windows_control.py shutdown --json
```
All three should return `{"ok": false, "error": "BLOCKED: ..."}`.

### STEP 6: Start PM2

```
pm2 start ecosystem.config.js
pm2 logs bravo-telegram --lines 10
```

Verify it shows `Bridge V15.3 ready. Platform: Windows. Computer control: FULL CONTROL (60+ cmds).`

### STEP 7: Commit and push

```
git add scripts/windows_control.py
git commit -m "bravo: feat — Windows computer control (60+ commands) mirroring macOS"
git push origin main
```

### IMPORTANT RULES

- Do NOT modify `macos_control.py` — it's done and tested on macOS.
- Do NOT modify the Telegram bridge security gates — they're already hardened in V15.3.
- Same `--json` output contract. The bridge parses JSON — if the format differs, it breaks.
- Test each category before moving on. Don't build all 60 commands and test at the end.
- If a dependency fails to install (`pywin32`, `pycaw`, etc.), implement a fallback using PowerShell subprocess calls. Never leave a command unimplemented.

---

## Obsidian Links
- [[brain/CAPABILITIES]] | [[brain/AGENTS]]
- [[skills/cli-anything/SKILL]] | [[skills/python-daemon-automation/SKILL]]
