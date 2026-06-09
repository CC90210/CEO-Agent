---
tags: [multi-machine, pairing, antigravity, paste-ready, cross-platform, command-center]
purpose: Generalized N-machine pairing prompt — covers Mac (launchd), Linux (systemd user unit), and Windows-as-secondary. Replaces the old MAC_COMMAND_CENTER_PROMPT.md (which is now a thin pointer at this doc).
last_updated: 2026-05-09
verified: |
  Mac path stress-tested end-to-end on 2026-05-09 (commit 1aec806 + 894585b).
  Linux + Windows-as-secondary paths use the same `bravo bridge install`
  code path that already supports systemd / Startup-folder fallback —
  shipped behaviour, no new install code needed. Pair endpoint is
  fingerprint-idempotent via migration 030 + commit d0e15e0.
---

# MULTI-MACHINE PAIRING — Antigravity Setup Prompt

> Paste the block below into Antigravity (or Claude Code) on the SECOND
> (or Nth) machine you want paired to an existing dashboard tenant.
> Works on macOS, Linux, and Windows-as-secondary. The agent there
> will: pull latest, install OS-appropriate deps, set up the local
> bridge chat-server, pair with the dashboard, and verify end-to-end.
>
> Hard architectural rule from [[brain/CROSS_MACHINE_SYNC]]: **only
> ONE machine runs scheduler / skool / telegram daemons.** The second
> machine runs ONLY the chat-server. The dashboard is shared.

## Prerequisites (operator does once, by hand)

1. Repo cloned to a local path. Recommended:
   - **macOS:** `~/CEO-Agent` (canonical as of 2026-05-19; older clones may live at `~/APPS/Business-Empire-Agent` or `~/Downloads/business-empire-agent`)
   - **Linux:** `~/Business-Empire-Agent`
   - **Windows-as-secondary:** `C:\Users\<user>\Business-Empire-Agent`
2. `.env.agents` populated. The two **mandatory keys for pairing**:
   - `OASIS_PROFILE_ID` (same as primary machine)
   - `OASIS_OUTBOUND_HMAC_SECRET` (same as primary machine)
   Without these, the chat-server runs but can't pair.
3. Python 3.11+ available on the OS:
   - macOS: `brew install python@3.12`
   - Linux: `sudo apt install python3.12 python3.12-venv` (Debian/Ubuntu) or distro equivalent
   - Windows: official installer from python.org, ensure pythonw.exe is included
4. Git installed.

## The Prompt — Paste This

```
You are Claude Code (or Antigravity) on a machine that needs to pair
to an existing Agent Command Center dashboard tenant. Goal: add this
machine as an additional paired bridge alongside the existing primary
machine. Each machine pairs independently — both can be online; they
don't conflict. After this completes, the operator will see this
machine listed in /operations under "Paired machines".

Hard constraints (non-negotiable, see brain/CROSS_MACHINE_SYNC.md):
- This machine must NOT start scheduler.py, skool_engine.py daemon,
  telegram_agent.js, or local_bridge.py _loop. Those are PRIMARY-only
  — running them on a secondary machine corrupts shared state
  (Supabase cron_jobs, Skool browser session, Telegram long-poll).
  If `pm2 list` shows ANY actively-running `bravo-*` process, stop
  and report — don't kill anything without operator approval.
- This machine IS allowed to run `bravo bridge serve` (the chat-server
  on :9100). This is the ONLY bridge daemon allowed.
- Do NOT push code or modify .env.agents without operator approval.
- Do NOT pip install / npm install of new packages without approval.

STEP 0 — Detect the OS.
  Run: uname -s   (Linux/macOS) OR ver   (Windows)
  Report which OS this is. Subsequent steps branch on that.

STEP 1 — Sync repo.
  cd to the repo (try the recommended path for this OS, fall back to
  whatever exists). Run: bash scripts/sync-from-github.sh (or on
  Windows: powershell .\scripts\sync-from-github.ps1 if it exists,
  else: git fetch origin main && git pull --ff-only origin main).
  Report: current commit hash + how many commits pulled.

STEP 2 — Read the canonical rules.
  Read these in full so you understand the multi-machine model:
    brain/CROSS_MACHINE_SYNC.md
    docs/deploy/MULTI_MACHINE_PAIRING_PROMPT.md (this file — for context)
  Confirm understanding: this machine runs ONLY the chat-server.

STEP 3 — Verify Python venv.
  ls .venv/bin/python (Unix) OR .venv\Scripts\python.exe (Windows)
  If missing:
    Unix:    python3.12 -m venv .venv && source .venv/bin/activate && pip install -e .
    Windows: python -m venv .venv && .venv\Scripts\activate && pip install -e .
  Verify: .venv/bin/python --version (or .venv\Scripts\python.exe --version)
  Should be 3.11+.

STEP 4 — Verify .env.agents has the two mandatory pairing keys.
  Run this audit (does NOT print secret values, just presence):
    .venv/bin/python -c "
    from pathlib import Path
    needed = ['OASIS_PROFILE_ID', 'OASIS_OUTBOUND_HMAC_SECRET']
    env = {}
    for line in Path('.env.agents').read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k = line.split('=', 1)[0].strip()
            v = line.split('=', 1)[1].strip()
            env[k] = bool(v)
    for k in needed:
        print(f'  {k}: {\"PRESENT\" if env.get(k) else \"MISSING\"}')"
  If either is MISSING, STOP. Report back — operator needs to copy
  them from the primary machine's .env.agents.

STEP 5 — Install OS dependencies for the bridge probes (optional).
  The chat-server's heartbeat probes for ffmpeg/whisper/playwright
  every 60s. Missing tools = "down" status in /integrations on the
  dashboard. Each is opt-in:
    macOS:   brew install ffmpeg
             .venv/bin/pip install openai-whisper
             .venv/bin/pip install playwright && .venv/bin/playwright install chromium
    Linux:   sudo apt install ffmpeg (Debian/Ubuntu) or equivalent
             .venv/bin/pip install openai-whisper
             .venv/bin/pip install playwright && .venv/bin/playwright install chromium
    Windows: choco install ffmpeg -y (or scoop install ffmpeg)
             .venv\Scripts\pip install openai-whisper
             .venv\Scripts\pip install playwright; .venv\Scripts\playwright install chromium
  Report what was installed vs already present. Skip any tools the
  operator doesn't need.

STEP 6 — Pair this machine with the dashboard.
  One-time handshake. PYTHONUNBUFFERED=1 makes the [bridge] log appear
  immediately rather than after stdio flush:
    Unix:    PYTHONUNBUFFERED=1 .venv/bin/python -m bravo_cli.bridge_chat_server > /tmp/bravo_pair.log 2>&1 &
    Windows: $env:PYTHONUNBUFFERED='1'; Start-Process -FilePath .venv\Scripts\pythonw.exe -ArgumentList '-m','bravo_cli.bridge_chat_server' -RedirectStandardOutput tmp\bravo_pair.log -WindowStyle Hidden
  Wait 8 seconds, then verify:
    Unix:    cat ~/.oasis/bridge_token  (should print 60+ char token)
             cat /tmp/bravo_pair.log    (should show "[bridge] paired with...")
    Windows: type "$env:USERPROFILE\.oasis\bridge_token"
             type tmp\bravo_pair.log
  If ~/.oasis/bridge_token is non-empty, pairing succeeded. Common
  failure modes:
    - "no OASIS_PROFILE_ID / OASIS_OUTBOUND_HMAC_SECRET" → STEP 4 missed
    - "self-pair failed: ... 401" → HMAC secret doesn't match dashboard
    - "self-pair failed: ... timeout" → dashboard unreachable
  IMPORTANT: the pair endpoint is now idempotent by machine_fingerprint
  (commit d0e15e0 + migration 030). Re-running pair from the same
  machine ROTATES the token on the existing bridge_pairings row instead
  of creating duplicates. Safe to re-run.
  After verifying, kill the foreground server before STEP 7:
    Unix:    kill %1   OR   pkill -f bridge_chat_server
    Windows: Stop-Process -Name pythonw -Force (only if no other pythonw running!)

STEP 7 — Install OS-native auto-start so the bridge survives reboot.
  Run: .venv/bin/python -m bravo_cli bridge install (Unix)
   or: .venv\Scripts\python.exe -m bravo_cli bridge install (Windows)
  Branch by OS:
    macOS:   writes ~/Library/LaunchAgents/work.oasisai.bravo-bridge.plist
             with KeepAlive=true. Verify with `launchctl list | grep bravo-bridge`.
             The plist contains <key>WorkingDirectory</key> pointing at
             the repo root — without it launchd starts with cwd=/ and
             python -m bravo_cli.local_bridge hits ModuleNotFoundError.
             (Was a real bug on first ship; fixed in commit 894585b.)
    Linux:   writes ~/.config/systemd/user/bravo-bridge.service.
             Verify with `systemctl --user status bravo-bridge`.
    Windows: writes either a schtasks ONLOGON entry OR drops a .vbs
             in the Startup folder (fallback when schtasks denies).
             Verify with `schtasks /Query /TN OASIS-Bravo-Bridge` OR
             `dir "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"`.
  Re-running `bridge install` is idempotent — it removes the prior
  registration before creating the new one. Safe to re-run after
  pulling code changes.

STEP 8 — Confirm chat-server is responsive.
  curl -s http://127.0.0.1:9100/warm-status
  Expect: {"ok": true, "size": 0, "max_size": 8, "idle_timeout_s": 900,
           "processes": []}
  If you get connection refused, the auto-start hasn't kicked in yet:
    macOS:   launchctl load -w ~/Library/LaunchAgents/work.oasisai.bravo-bridge.plist
    Linux:   systemctl --user restart bravo-bridge
    Windows: schtasks /Run /TN OASIS-Bravo-Bridge  OR  start the .vbs

STEP 9 — Verify both machines are visible in the dashboard.
  Open https://agent-dashboard-cc90210.vercel.app/operations in a
  browser on this machine. Under "Paired machines", you should see
  AT LEAST TWO entries:
    - The primary machine (already paired)
    - This machine (newly paired, label like "<hostname> (<OS>)")
  If only one shows, the heartbeat hasn't fired yet — wait 60s and
  refresh. If duplicates appear for THIS machine's fingerprint, the
  fingerprint-idempotent fix didn't propagate (migration 030 must be
  applied on the dashboard's Supabase project — verify with
  scripts/integrations/supabase_tool.py select bridge_pairings).

STEP 10 — Daemon-leak check (mandatory).
  Anchored to the Bravo repo path so sibling Maven / Atlas processes
  (which run by design from their own repos) don't trigger false
  positives. Adapt commands by OS:
    Unix:
      REPO=$(git -C "$(pwd)" rev-parse --show-toplevel)
      ps aux | grep -E "$REPO/(scripts/scheduler\.py|skool_engine|telegram_agent\.js)|local_bridge\.py.*_loop" | grep -v grep
      pm2 list 2>/dev/null | awk '/bravo-/ && $0 !~ /stopped/ && $0 !~ /errored/'
    Windows (PowerShell):
      $REPO = (git -C (Get-Location) rev-parse --show-toplevel)
      Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "$REPO.*scheduler\.py|skool_engine|telegram_agent\.js|local_bridge\.py.*_loop" } | Select-Object ProcessId, Name, CommandLine
      pm2 list 2>$null | Select-String "bravo-" | Where-Object { $_ -notmatch "stopped|errored" }
  Both should produce ZERO output. If either does, STOP — those are
  state-mutating daemons that must NEVER actively run on a secondary
  machine. Report the full output, do not kill anything yourself.

STEP 11 — Report back in this exact format:

  ## OS
  <macOS / Linux / Windows>

  ## Sync
  - commit: <hash> (pulled <N> commits)
  - venv: present / created / repaired

  ## Pairing
  - .env.agents OASIS_PROFILE_ID: PRESENT / MISSING
  - .env.agents OASIS_OUTBOUND_HMAC_SECRET: PRESENT / MISSING
  - bridge_token at ~/.oasis/bridge_token: PRESENT (paired) / MISSING (failed)
  - dashboard /operations shows this machine: YES / NO
  - duplicate rows for this fingerprint: NONE / <count>

  ## Auto-start
  - launchctl / systemctl / schtasks: LOADED / NOT LOADED
  - chat-server on :9100: RESPONDING (warm-status OK) / DOWN

  ## Optional integrations
  - ffmpeg: installed / skipped
  - whisper: installed / skipped
  - playwright: installed / skipped

  ## Daemon-leak check
  - scheduler / skool / telegram processes: NONE (clean) / FOUND <details>
  - pm2 actively-running bravo-*: NONE (clean) / FOUND <details>

  ## Ready-to-work status
  <one sentence: "This machine is fully paired with Command Center
   and ready" — or what's still blocking>

STEP 12 — Session end.
  bash scripts/hooks/bravo-session-end.sh "<machine name> pairing complete"
  This commits SESSION_LOG.md + HANDOFF.md and pushes. The primary
  machine will see it on next session-start.
```

---

## After the secondary machine reports back

Expected outcome: 11/11 green. The new machine shows up in `/operations`
under "Paired machines", the chat widget on the dashboard offers a
`localhost:9100` chat path when the operator opens it from this
machine, and the primary keeps running production daemons untouched.

If anything is yellow/red:
- **Pairing failed (401)** → HMAC secret mismatch. Copy
  `OASIS_OUTBOUND_HMAC_SECRET` from primary's `.env.agents` to
  secondary's `.env.agents` and re-run STEP 6.
- **Dashboard doesn't show this machine in /operations** → heartbeat
  hasn't fired yet (60s interval). Wait, refresh.
- **Duplicate rows for this fingerprint** → migration 030 not applied
  on the dashboard's Supabase. Apply it via:
  `python scripts/apply_migration.py database/030_bridge_pairings_unique_fingerprint.sql`
- **Daemon leak found** → STOP, paste the output. Likely a stale PM2
  entry; verify it's not the active production daemon before killing.
- **launchd not loading on Mac** → check that `WorkingDirectory` is
  set in the plist; sometimes macOS Security & Privacy needs to grant
  permission to the plist.
- **systemd not loading on Linux** → verify
  `loginctl enable-linger $USER` is set so user services persist past
  logout.

## What this multi-machine setup gives the operator

- **N paired bridges visible** in the dashboard `/operations` page.
- **Chat with file access from any machine** — when the operator opens
  the dashboard on a paired machine, the chat widget detects
  `localhost:9100` and gets full file-system access for that session.
  Each machine sees only its own files.
- **No daemon conflicts** — scheduler / skool / telegram still run on
  the designated primary, untouched. Secondary chat-servers are
  operator-driven (only fire when the operator sends a message), not
  on a timer, so they don't compete.
- **Survives reboot** — OS-native auto-start keeps the chat-server
  running after every login.
- **Production-machine flexibility** — the "primary" designation is
  configurable. CC's setup is Windows-primary + Mac-secondary; a
  client could flip that (Linux server primary, laptop secondary) by
  simply running scheduler / skool / telegram on the desired
  primary and only `bravo bridge serve` everywhere else.

## Obsidian Links
- [[brain/CROSS_MACHINE_SYNC]] (the rules — daemons stay primary, chat-server allowed everywhere)
- [[docs/deploy/MAC_COMMAND_CENTER_PROMPT]] (legacy pointer — body moved here)
- [[docs/deploy/MAC_ANTIGRAVITY_PROMPT]] (general Mac sync — env audit)
- [[docs/deploy/MAC_SYNC_PROMPT]] (env audit + Mac-specific overrides like GWS_PATH)
- [[brain/SECURITY_MODEL]] (how pairing + tokens + tenant isolation actually work)
