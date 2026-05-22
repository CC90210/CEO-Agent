# Claude Code Mobile Terminal — Access From Anywhere

## Overview

Claude Code supports remote terminal access via SSH tunneling. With the Claude Max plan, you can connect to your Claude Code session from any device — including your phone — using a terminal app.

## Setup Methods

### Method 1: Claude Code SSH (Built-in)

Claude Code has built-in remote access. From your main terminal:

```bash
# Start Claude Code with remote access enabled
claude --remote

# This generates a URL and QR code you can scan
# The QR code links to a web-based terminal connected to your session
```

If `--remote` is not available in your version, upgrade:
```bash
npm update -g @anthropic-ai/claude-code
```

### Method 2: VS Code Remote Tunnel (Recommended for Mobile)

VS Code's tunnel feature works with Antigravity IDE and gives you full editor + terminal access:

```bash
# From your Windows machine
code tunnel

# This outputs:
# - A URL: https://vscode.dev/tunnel/<machine-name>
# - A QR code to scan
# Open the URL on your phone's browser — full VS Code + terminal access
```

Steps:
1. Run `code tunnel` on your Windows machine
2. Authenticate with your GitHub account when prompted
3. Scan the QR code or open the URL on your phone
4. You now have full terminal access — run `claude` to start Claude Code

### Method 3: Tailscale + Termux (Android) or a-Shell (iOS)

For direct SSH access from a mobile terminal app:

1. **Install Tailscale** on both your Windows machine and phone
2. **Enable SSH on Windows:**
   ```powershell
   # In PowerShell as Admin
   Add-WindowsCapability -Online -Name OpenSSH.Server
   Start-Service sshd
   Set-Service -Name sshd -StartupType Automatic
   ```
3. **Connect from phone:**
   - Android: Install Termux, then `ssh User@<tailscale-ip>`
   - iOS: Install a-Shell or Blink Shell, then SSH to your machine
4. **Run Claude Code:** `cd /c/Users/User/Business-Empire-Agent && claude`

### Method 4: Telegram Bridge (Already Configured)

The existing Telegram bot (`telegram_agent.js`) bridges messages to Gemini/Claude CLI:

```bash
# Start the bridge
npm run telegram
```

This routes through Gemini by default. For Claude Code specifically, Methods 1-3 provide direct access.

## Recommended Setup

**For quick access:** Method 2 (VS Code tunnel) — one command, QR code, works on any phone browser.

**For full terminal power:** Method 3 (Tailscale + SSH) — persistent connection, works with any terminal app.

**For casual queries:** Method 4 (Telegram) — already set up, no new infrastructure.

## Mobile Workflow Tips

- Keep sessions short on mobile — complex multi-file work is better on desktop
- Use `/prime` to load context quickly when starting a mobile session
- Use voice-to-text for long prompts — faster than typing on phone
- The Telegram bridge is best for quick questions and status checks
- VS Code tunnel is best for actual code work from a tablet

## Obsidian Links
- [[docs/INDEX]] | [[brain/DASHBOARD]]


## Related (graph)

- [[docs/INDEX]]
- [[docs/AGENT_RUNNER_DESIGN]]
- [[docs/AI_WORKSTATION_ROADMAP]]
