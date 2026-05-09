---
tags: [mac, sync, antigravity, paste-ready, command-center, bridge]
purpose: One self-contained prompt CC pastes into Antigravity on the MacBook to connect the Mac to the Agent Command Center. Mac becomes a paired bridge — operator can chat with agents from the dashboard with Mac-side file access — without stepping on the Windows production daemons.
last_updated: 2026-05-09
---

# MAC AGENT COMMAND CENTER — Antigravity Setup Prompt

> Paste the block below into Antigravity (or Claude Code) on CC's MacBook.
> The agent there will: pull latest, install macOS dependencies, set up
> the local bridge chat-server, pair the Mac with the dashboard, and verify
> end-to-end. Mac will NOT run scheduler/skool/telegram daemons (Windows
> exclusive — see [[brain/CROSS_MACHINE_SYNC]]).

## Prerequisites (CC does once, by hand)

1. Repo cloned at `~/APPS/Business-Empire-Agent` (or `~/Downloads/business-empire-agent` — both paths are tolerated).
2. `.env.agents` already populated — copy from Windows OR run the wizard. The two **mandatory keys for pairing** are:
   - `OASIS_PROFILE_ID` (same as Windows)
   - `OASIS_OUTBOUND_HMAC_SECRET` (same as Windows)
   Without these, the Mac chat-server runs but can't pair with the dashboard.
3. Homebrew installed (`/opt/homebrew/bin/brew` — Apple Silicon, or `/usr/local/bin/brew` — Intel).
4. Python 3.12 available (`brew install python@3.12` if missing).

## The Prompt — Paste This

```
You are Claude Code (or Antigravity) on CC's MacBook. Goal: connect this
Mac to the Agent Command Center as a SECOND paired bridge alongside the
Windows production box. Each machine pairs independently — both can be
online; they don't conflict. After this completes, CC will see two
machines in /devices on the dashboard, and chat from the Mac will have
access to this machine's local file structure.

Hard constraints (non-negotiable, see brain/CROSS_MACHINE_SYNC.md):
- Mac must NOT start scheduler.py, skool_engine.py daemon, telegram_agent.js,
  or local_bridge.py _loop. Those are Windows-exclusive — running them on
  Mac corrupts shared state (Supabase cron_jobs, Skool browser session,
  Telegram long-poll). If `pm2 list` shows ANY `bravo-*` process, stop
  and report — don't kill it without my OK.
- Mac IS allowed to run `bravo bridge serve` (the chat-server on :9100).
  This is the ONLY bridge daemon allowed on Mac.
- Do NOT push code or modify .env.agents without my OK.
- Do NOT run npm install / pip install of new packages without my OK.

STEP 1 — Sync repo.
  cd to the repo (try ~/APPS/Business-Empire-Agent first, then
  ~/Downloads/business-empire-agent — whichever exists).
  Run: bash scripts/sync-from-github.sh
  If that script doesn't exist yet, fall back to:
    git fetch origin main && git pull --ff-only origin main
  Report: current commit hash + how many commits pulled.

STEP 2 — Read the canonical rules.
  Read these in full so you understand the multi-machine model:
    brain/CROSS_MACHINE_SYNC.md
    brain/MAC_COMMAND_CENTER_PROMPT.md (this file — for context)
  Confirm you understand: Mac runs ONLY the chat-server, nothing else.

STEP 3 — Verify Python venv.
  ls .venv/bin/python  # should exist
  If missing: python3.12 -m venv .venv && source .venv/bin/activate && \
              pip install -e .
  If exists, just verify: .venv/bin/python --version  (should be 3.11+)

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
  If either is MISSING, STOP. Report back to CC — Windows side has them
  and CC needs to copy/paste them into the Mac's .env.agents.

STEP 5 — Install macOS dependencies for the bridge probes.
  The bridge heartbeat probes for ffmpeg/whisper/playwright every 60s.
  Missing tools = "down" status in /integrations on the dashboard. Each
  is opt-in — install whichever apply:
    brew install ffmpeg                     # for video pipeline
    .venv/bin/pip install openai-whisper    # for voice transcription
    .venv/bin/pip install playwright && \
    .venv/bin/playwright install chromium   # for browser automation
  If any are already installed, skip. Report which were installed vs
  already present.

STEP 6 — Pair the Mac with the dashboard.
  This is a one-time handshake. Run:
    .venv/bin/python -m bravo_cli.bridge_chat_server &
    sleep 8
    cat ~/.oasis/bridge_token  # should print a JWT-looking string
  If ~/.oasis/bridge_token exists with content, pairing succeeded.
  If not, look at ~/.oasis/bridge.log for [bridge] messages — likely
  causes:
    - "no OASIS_PROFILE_ID / OASIS_OUTBOUND_HMAC_SECRET" → STEP 4 missed
    - "self-pair failed: ... 401" → HMAC secret doesn't match dashboard
    - "self-pair failed: ... timeout" → dashboard unreachable / network
  Kill the foreground server after pairing succeeds:
    kill %1   # or: pkill -f bridge_chat_server

STEP 7 — Install launchd auto-start so the bridge survives reboot/login.
  .venv/bin/python -m bravo_cli bridge install
  Verify:
    launchctl list | grep bravo-bridge
    cat ~/Library/LaunchAgents/work.oasisai.bravo-bridge.plist
  Should report "OK — installed launchd plist at ...".
  Note: this auto-start runs `bravo bridge serve` (chat-server on :9100),
  NOT the heartbeat-only `_loop` daemon — exactly what we want on Mac.

STEP 8 — Confirm chat-server is responsive.
  curl -s http://127.0.0.1:9100/warm-status
  Expect: {"ok": true, "size": 0, "max_size": 8, "idle_timeout_s": 900,
           "processes": []}
  If you get connection refused, the launchd plist hasn't kicked in yet.
  Run: launchctl load -w ~/Library/LaunchAgents/work.oasisai.bravo-bridge.plist
  Then retry the curl.

STEP 9 — Verify both machines are visible in the dashboard.
  Open https://agent-dashboard-cc90210.vercel.app/operations in a browser
  on the Mac. You should see TWO entries under "Paired machines":
    - The Windows host (existing)
    - This Mac (newly paired, label like "MacBook (Conaughs-MacBook-Air)")
  If only one shows, the heartbeat hasn't fired yet — wait 60s and refresh.

STEP 10 — Daemon-leak check (mandatory).
  ps aux | grep -E "(scheduler\.py|skool_engine|telegram_agent\.js)" | \
    grep -v grep
  pm2 list 2>/dev/null | grep bravo
  Both should produce ZERO output. If either does, STOP — those are
  state-mutating daemons that must NEVER run on Mac. Report the full
  output, do not kill anything yourself.

STEP 11 — Report back in this exact format:

  ## Sync
  - commit: <hash> (pulled <N> commits)
  - venv: present / created / repaired

  ## Pairing
  - .env.agents OASIS_PROFILE_ID: PRESENT / MISSING
  - .env.agents OASIS_OUTBOUND_HMAC_SECRET: PRESENT / MISSING
  - bridge_token at ~/.oasis/bridge_token: PRESENT (paired) / MISSING (failed)
  - dashboard /devices shows this Mac: YES / NO

  ## Auto-start
  - launchctl: bravo-bridge LOADED / NOT LOADED
  - chat-server on :9100: RESPONDING (warm-status OK) / DOWN

  ## Optional integrations
  - ffmpeg: installed / skipped
  - whisper: installed / skipped
  - playwright: installed / skipped

  ## Daemon-leak check
  - scheduler / skool / telegram on Mac: NONE (clean) / FOUND <details>
  - pm2 bravo-* on Mac: NONE (clean) / FOUND <details>

  ## Ready-to-work status
  <one sentence: "Mac is fully paired with Command Center and ready" — or
   what's still blocking>

STEP 12 — Session end.
  bash scripts/bravo-session-end.sh "mac command-center pairing complete"
  This commits SESSION_LOG.md + HANDOFF.md and pushes. Windows will see
  it on next session-start.
```

---

## After the Mac Reports Back

Expected outcome: 11/11 green. The Mac shows up as a second paired bridge
in `/devices`, the chat widget on the dashboard now offers a `localhost:9100`
chat path when CC opens it from the Mac, and Windows continues running the
production daemons untouched.

If anything is yellow/red:
- **Pairing failed (401)** → HMAC secret mismatch. Copy `OASIS_OUTBOUND_HMAC_SECRET` from Windows `.env.agents` to Mac `.env.agents` and re-run STEP 6.
- **Dashboard doesn't show Mac in /devices** → heartbeat hasn't fired yet (60s interval). Wait, refresh.
- **Daemon leak found** → STOP, paste the output back to me on Windows. Likely a stale PM2 entry from the 2026-04-11 incident — I'll triage from Windows side.
- **launchd not loading** → check that `OnDemand=false` is set; sometimes macOS Security & Privacy needs to grant permission to the plist.

## What This Setup Gives CC

- **Two paired bridges visible** in the dashboard `/operations` and `/devices` pages.
- **Chat with file access from the Mac** — when CC opens the dashboard on the Mac, the chat widget detects `localhost:9100` and gets full Mac file-system access for that session. Same thing on Windows. Each machine sees its own files.
- **No daemon conflicts** — scheduler / skool / telegram still Windows-only, untouched. The Mac chat-server is operator-driven (only fires when CC sends a message), not on a timer.
- **Survives reboot** — launchd starts the chat-server on every login.

## Obsidian Links
- [[brain/CROSS_MACHINE_SYNC]] (the rules — daemons stay Windows, chat-server allowed on Mac)
- [[brain/MAC_ANTIGRAVITY_PROMPT]] (general Mac sync — pairs with this Command Center prompt)
- [[brain/MAC_SYNC_PROMPT]] (env audit + Mac-specific overrides like GWS_PATH)
