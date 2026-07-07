' ============================================================================
' Bravo PM2 Fleet Resurrect — durable reboot persistence
' ============================================================================
' Runs `pm2 resurrect` HIDDEN at user logon so the Bravo daemon fleet
' (bravo-scheduler, bravo-telegram, bravo-coord, claude-bridge,
' claude-bridge-ping, event-router) comes back automatically after any
' reboot — Windows Update, power loss, or manual restart.
'
' WHY logon (not a SYSTEM service): the daemons need CC's user profile —
' ~/.claude/.credentials.json (subscription OAuth, per the CLI-only rule),
' .env.agents, and .venv. A service running as SYSTEM/service-account would
' not see those. Running at logon in CC's own context guarantees access.
'
' Canonical copy is tracked here (scripts/bravo_pm2_resurrect.vbs). A copy is
' placed in the per-user Startup folder:
'   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Bravo PM2 Resurrect.vbs
' Re-run `pm2 save` whenever the fleet composition changes so dump.pm2 stays
' current. Created 2026-07-07 (Montreal turnkey reset).
'
' windowStyle 0 = hidden (no console flash). The 20s settle delay lets the
' user PATH / npm globals and the PM2 daemon initialize before resurrect.
' ============================================================================
Set WshShell = CreateObject("WScript.Shell")
WScript.Sleep 20000
' pm2.cmd resolves via the user's npm global PATH at logon. cmd /c keeps the
' window closed; the final "0, False" runs it hidden and non-blocking.
WshShell.Run "cmd /c pm2 resurrect", 0, False
