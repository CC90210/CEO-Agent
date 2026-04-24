---
tags: [sync, mac, setup, environment]
purpose: The one prompt CC pastes into Mac Claude Code to get the MacBook fully synced with the Windows production box. Covers git pull, env var audit, Mac-specific overrides, daemon setup.
owner: CC (Conaugh McKenna)
last_updated: 2026-04-11
---

# MAC SYNC PROMPT — Paste into Mac Claude Code

> CC: open Claude Code on your MacBook inside `~/APPS/Business-Empire-Agent` (or wherever the repo lives on Mac) and paste the block below verbatim.
>
> If the repo isn't cloned on Mac yet, run this first in Terminal:
> ```bash
> mkdir -p ~/APPS && cd ~/APPS && git clone https://github.com/CC90210/CEO-Agent.git && cd business-empire-agent
> ```

---

## The Prompt (copy everything between the triple-dashes)

```
You are Claude Code running on CC's MacBook. Full task: sync this Mac clone of
Business-Empire-Agent to match the Windows production box and make sure
nothing is missing. Do not ask for permission on read-only steps. Do not
push to GitHub. Do not restart any daemons without my explicit OK.

STEP 1 — Pull latest from origin/main.
Run: bash scripts/sync-from-github.sh
If it fails, fall back to: git fetch origin main && git pull --ff-only origin main
Report: which commit we're now on and a one-line summary of incoming changes.

STEP 2 — Audit .env.agents against what the code needs.
Read brain/CREDENTIALS_SCAFFOLD.md for the master list.
Then run this audit so I know exactly what's missing:

  python3 -c "
  import re, pathlib
  keys_in_code = set()
  pat = re.compile(r'(?:os\.environ|env|env_vars|_env)\.get\([\"\x27]([A-Z][A-Z0-9_]*)[\"\x27]')
  pat2 = re.compile(r'(?:os\.environ|env|env_vars|_env)\[[\"\x27]([A-Z][A-Z0-9_]*)[\"\x27]\]')
  for p in pathlib.Path('scripts').rglob('*.py'):
      try: t = p.read_text(encoding='utf-8', errors='ignore')
      except: continue
      for m in pat.finditer(t): keys_in_code.add(m.group(1))
      for m in pat2.finditer(t): keys_in_code.add(m.group(1))
  noise = {'PATH','HOME','USER','USERNAME','APPDATA','LOCALAPPDATA','TEMP','TMP','COMSPEC','PYTHONPATH','PYTHONUNBUFFERED','WINDIR','SYSTEMROOT','CLAUDE_PLUGIN_ROOT','NO_COLOR','TERM','OSTYPE','PWD','SHLVL','LANG','LC_ALL','LOGNAME','SHELL','PROGRAMFILES','PROGRAMDATA','EDITOR','CLAUDE_CODE_TASK_LIST_ID','CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS','CLAUDE_CODE_NO_FLICKER','CLAUDE_CODE_SUBPROCESS_ENV_SCRUB','HF_HUB_DISABLE_SYMLINKS_WARNING','USERPROFILE'}
  keys_in_code = {k for k in keys_in_code if k not in noise}
  env_keys = set()
  p = pathlib.Path('.env.agents')
  if p.exists():
      for line in p.read_text(encoding='utf-8').splitlines():
          line = line.strip()
          if line and not line.startswith('#') and '=' in line:
              env_keys.add(line.split('=',1)[0].strip())
  missing = sorted(keys_in_code - env_keys)
  present = sorted(keys_in_code & env_keys)
  print(f'=== {len(present)} present, {len(missing)} missing ===')
  print()
  print('MISSING FROM .env.agents (code needs these):')
  for k in missing: print(f'  - {k}')
  "

Classify each missing key into: (a) REQUIRED (daemon won't run without it),
(b) CORE (major capability lost), (c) OPTIONAL (edge case only), (d) HAS
FALLBACK (code falls back to another key that's already set). Use the
classification list in brain/MAC_SYNC_PROMPT.md as reference.

STEP 3 — Apply the Mac-specific overrides I'm about to give you.
The biggest one: GWS_PATH must be set to the Mac path, not Windows. Also
FFmpeg must be brew-installed. Report which overrides are needed.

STEP 4 — Verify core integrations WITHOUT modifying anything:
  python3 scripts/supabase_tool.py select leads --limit 1
  python3 scripts/stripe_tool.py balance
  python3 scripts/funnel_sync.py stats
  python3 scripts/revenue_engine.py --json mrr
For each: report OK or the specific error. Don't try to fix credential errors
— just tell me what's missing.

STEP 5 — Read the 3 state files and tell me what's happening:
  brain/STATE.md
  memory/ACTIVE_TASKS.md
  memory/SESSION_LOG.md (top 100 lines only)

STEP 6 — Report back in this exact format:
  ## Git: <commit hash, N commits behind origin (or "up to date"), one-line summary>
  ## Env audit: <present>/<total> keys, <N> missing, list the missing
  ## Mac overrides needed: <GWS_PATH, FFmpeg, anything else>
  ## Integration checks: <tool: OK or error, one per line>
  ## State: <what's in ACTIVE_TASKS.md P0 items, one line each>
  ## Next actions: <what I need to do before I can actually use the Mac box>

DO NOT: push code, restart daemons, modify .env.agents, run any pm2 start
commands, or install anything without my OK.
```

---

## Environment Variable Delta (new keys since Mac last synced)

Your Windows `.env.agents` currently has **53 keys**. The code only uses **39 of them** actively (the rest are for other services like Notion, Turso, Gritly that may be set but unused). Here are the **keys your Mac needs**, ranked by priority:

### [REQUIRED] — Mac daemon/scheduler won't run without these
```
ANTHROPIC_API_KEY=<same as Windows>
BRAVO_SUPABASE_URL=<same as Windows>
BRAVO_SUPABASE_SERVICE_ROLE_KEY=<same as Windows>
BRAVO_SUPABASE_ANON_KEY=<same as Windows>
TELEGRAM_BOT_TOKEN=<same as Windows>
TELEGRAM_ALLOWED_USERS=<same as Windows>
```

### [CORE] — Major capability lost if missing
```
# Revenue
STRIPE_SECRET_KEY=<same as Windows>
STRIPE_ORG_KEY=<same as Windows>
STRIPE_OASIS_ACCT_ID=<same as Windows>

# Content distribution
LATE_API_KEY=<same as Windows>

# Scraping / OSINT
FIRECRAWL_API_KEY=<same as Windows>

# Email (Gmail SMTP + IMAP)
GMAIL_USER=oasisaisolutions@gmail.com
GMAIL_APP_PASSWORD=<same as Windows>

# n8n workflow automation
N8N_API_URL=<same as Windows>
N8N_API_KEY=<same as Windows>
```

### [CORE — MAC OVERRIDE REQUIRED]
These have Windows-specific values. **DO NOT copy the Windows value — use the Mac path.**
```
# GWS CLI path — Windows: C:\Users\User\AppData\Roaming\npm\gws.cmd
# Mac: wherever `which gws` prints after you install it via npm
GWS_PATH=/opt/homebrew/bin/gws
# If `which gws` gives a different path, use that instead.
```

### [OPTIONAL but recommended] — New keys I may have added since last Mac sync
These are referenced by scripts but fall back to defaults or alternate keys. Adding them explicitly avoids silent degraded behavior:
```
# Email alias — code checks both GMAIL_USER and GMAIL_ADDRESS. Set both to be safe.
GMAIL_ADDRESS=oasisaisolutions@gmail.com

# Claude model override — defaults to claude-sonnet-4 if unset. Override if you want Opus.
CLAUDE_MODEL=claude-sonnet-4-20250514

# Booking link for funnel nurture Day-2 emails — falls back to mailto: if unset
# Authoritative value lives in .env.agents BOOKING_LINK and brain/USER.md Critical Links.
# Current canonical link: https://calendar.app.google/tpfvJYBGircnGu8G8
BOOKING_MEET_LINK=https://calendar.app.google/tpfvJYBGircnGu8G8

# Notify category filter — blocks spam categories. Default is fine.
NOTIFY_BLOCKED_CATEGORIES=content,instagram,system

# Stripe aliases — code tolerates either name, but set the aliases so ceo_dashboard.py works
STRIPE_API_KEY=<same value as STRIPE_SECRET_KEY>
STRIPE_ACCOUNT_OASIS_ID=<same value as STRIPE_OASIS_ACCT_ID>
STRIPE_ACCOUNT_PROPFLOW_ID=<same value as STRIPE_PROPFLOW_ACCT_ID>
STRIPE_ACCOUNT_NOSTALGIC_ID=<same value as STRIPE_NOSTALGIC_ACCT_ID>

# CASL compliance (for Canadian email outreach — legal requirement)
CASL_BUSINESS_NAME=OASIS AI Solutions
CASL_BUSINESS_ADDRESS=Collingwood, ON, Canada
CASL_SENDER_NAME=Conaugh McKenna
CASL_UNSUBSCRIBE_URL=https://oasisai.work/unsubscribe

# Session/agent identity (for cross-AI observability — totally optional)
BRAVO_AGENT_LABEL=mac
BRAVO_SESSION_ID=mac-$(date +%s)
```

### [SKIP ON MAC] — Windows-specific or other-app keys
These are in your Windows `.env.agents` but you don't need them on Mac:
- `GRITLY_TURSO_*` — Gritly app credentials, only used in `C:\Users\User\APPS\gritly`
- `NOSTALGIC_SUPABASE_*` / `OASIS_SUPABASE_*` — Nostalgic/OASIS app creds, only used in those app repos
- `NOTION_*` — personal productivity, not used by BEA scripts
- `TURSO_API_KEY` / `TURSO_DATA_BASE_URL` — only if you run Turso CLI on Mac
- `GWS_CLIENT_ID` / `GWS_CLIENT_SECRET` / `GWS_GCP_PROJECT` — OAuth setup, handled by `gws auth login` keyring on Mac
- `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` — IG automation, Playwright-based, Windows-only for now
- `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD` — LinkedIn automation, same deal
- `SKOOL_EMAIL` / `SKOOL_PASSWORD` — the Skool daemon runs on Windows and you don't want TWO instances fighting the same Chromium profile

---

## Mac-specific tooling checklist

Install these on Mac BEFORE trying to run any daemons:

```bash
# Python 3.12 (if not already)
brew install python@3.12

# FFmpeg (content pipeline needs this — auto-fallback to PATH, so just install)
brew install ffmpeg

# Node 20+ (for telegram-bot, MCP wrappers, n8n-mcp, late_tool.py subprocesses)
brew install node@20

# GitHub CLI (for gh commands in sync script)
brew install gh

# PM2 for process orchestration
npm install -g pm2

# Google Workspace CLI
npm install -g @wstgdev/gws-cli
gws auth login   # one-time OAuth, uses macOS keyring

# Playwright for Skool / IG automation (optional — see note below)
python3 -m pip install playwright
python3 -m playwright install chromium
```

**Critical:** Do NOT run the Skool daemon on Mac. The Windows box (PID 11176 as of 2026-04-11) has an exclusive lock and an active Chromium profile at `tmp/skool-browser/`. Running a second instance will **fight the same Skool account** and cause double-replies in your live community. One instance only, on Windows.

---

## What's changed in the repo since your last Mac sync

Commits you're pulling (newest first):
1. `2bf7293` — V2.1 final: skool crash-safe state + IMAP poison UID + lead_followup fail-closed
2. `687f039` — V2.1 hardening: skip_phrase substring bug, retry-on-error, n8n argparse, skool is_cc
3. `abc7d12` — Notification pipeline V2: fail-closed parsing, double-notify fix, fast-poll mode, argparse root cause
4. `b0bbd11` — Skool Engine V2.1: comment-tier engagement + coach escalation
5. `1993014` — CLIENT_READY scorecard + sync script + credentials scaffold + STATE dedup
6. `c1c7525` — Hyperthink protocol + production hardening + CASL compliance

**New files you'll see on Mac after pull:**
- [scripts/sync-from-github.sh](scripts/sync-from-github.sh) — the script at the top of this document
- [brain/CLIENT_READY.md](brain/CLIENT_READY.md) — the honest 15/100 scorecard
- [brain/CREDENTIALS_SCAFFOLD.md](brain/CREDENTIALS_SCAFFOLD.md) — master env var documentation
- [brain/MAC_SYNC_PROMPT.md](brain/MAC_SYNC_PROMPT.md) — this file
- [skills/ethical-hacking/SKILL.md](skills/ethical-hacking/SKILL.md)
- [skills/sales-closing/SKILL.md](skills/sales-closing/SKILL.md)
- [.agents/workflows/close-review.md](.agents/workflows/close-review.md)

**Scripts with significant new behavior:**
- [scripts/skool_engine.py](scripts/skool_engine.py) — V2.1 comment-tier, coach escalation, crash-safe state, tightened is_cc matching, Playwright page health check
- [scripts/scheduler.py](scripts/scheduler.py) — fail-closed handlers, retry-on-error (5 attempts, 5-min backoff), prefix-based skip matching (fixed substring bug), periodic re-init of new jobs, lead_followup fail-closed
- [scripts/funnel_sync.py](scripts/funnel_sync.py) — fast-poll mode (60s cadence, 120s window, race-safe insert, consolidated digest)
- [scripts/funnel_nurture.py](scripts/funnel_nurture.py) — Day2/Day5 window fix (dead zone closed), migrated to notify.py
- [scripts/revenue_engine.py](scripts/revenue_engine.py) — argparse --json flag fix (root cause of weeks of Telegram spam)
- [scripts/n8n_tool.py](scripts/n8n_tool.py) — same argparse fix
- [scripts/email_engine.py](scripts/email_engine.py) — IMAP poison UID quarantine
- [scripts/notify.py](scripts/notify.py) — 5s Telegram timeout, stderr error logging, guarded chat_id parsing

**New cron job active on Windows (will also need to be seeded if Mac ever runs its own scheduler):**
- `Funnel Fast-Poll` — `*/1 * * * *`, checks funnel_leads last 2 minutes, fires high-priority Telegram digest when new CC Funnel form submissions land

---

## Post-sync verification checklist

After pasting the prompt above and getting Claude's report, verify:

- [ ] Git pull succeeded, on commit `2bf7293` or newer
- [ ] `.env.agents` audit shows 0 REQUIRED missing, 0 CORE missing
- [ ] `GWS_PATH` is a Mac path, not a Windows path
- [ ] `python3 scripts/supabase_tool.py select leads --limit 1` returns JSON (not an error)
- [ ] `python3 scripts/stripe_tool.py balance` returns balance data
- [ ] `python3 scripts/funnel_sync.py stats` shows `1 total` (John)
- [ ] `python3 scripts/revenue_engine.py --json mrr` returns `{"mrr": 3322.0, ...}`
- [ ] FFmpeg installed (`ffmpeg -version`)
- [ ] Node installed (`node --version`)
- [ ] Skool daemon is NOT running on Mac (one instance, Windows only)

If any of those fail, share the error back and I'll triage from Windows.

---

## One-liner to test everything after sync

```bash
bash scripts/sync-from-github.sh --verify-only && \
python3 scripts/supabase_tool.py select leads --limit 1 && \
python3 scripts/stripe_tool.py balance && \
python3 scripts/revenue_engine.py --json mrr && \
echo "ALL GREEN"
```

If that prints "ALL GREEN" at the end, the Mac is fully synced and operational as a read/analyze/edit node. (It's NOT a second production execution node — only Windows runs daemons.)

## Obsidian Links
- [[brain/CREDENTIALS_SCAFFOLD]]
- sync-from-github
- [[brain/STATE]]
- [[brain/CLIENT_READY]]
