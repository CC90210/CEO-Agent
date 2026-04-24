---
tags: [mac, sync, antigravity, paste-ready]
purpose: One self-contained prompt CC pastes into Antigravity on the MacBook to sync with Windows and verify zero missing keys + zero false spam. No network prerequisites.
last_updated: 2026-04-11
---

# MAC ANTIGRAVITY PROMPT — Paste This

> CC: Open Antigravity IDE (or Claude Code) on your MacBook. Make sure the BEA repo is open at `~/APPS/Business-Empire-Agent` (or wherever you cloned it). Paste the block below verbatim into the chat. It's fully self-contained — no manual steps, no copy-paste from other files.

---

```
You are Claude Code on CC's MacBook. Full task: sync this Mac clone of
Business-Empire-Agent to match the Windows production box, verify the
environment is coherent, and report back in a fixed format. Do NOT push
code, restart daemons, or modify .env.agents without my OK.

STEP 1 — Session start.
Run: bash scripts/bravo-session-start.sh
If the script doesn't exist yet (first run on this Mac), fall back to:
  git fetch origin main && git pull --ff-only origin main
Then re-run the session-start script — it will exist after pull.
Report: the commit hash, how many commits you pulled, what's new.

STEP 2 — Read the sync protocol.
Read brain/CROSS_MACHINE_SYNC.md in full. This is the canonical rulebook
for how Windows and Mac stay coherent. Most important rules:
  1. Only Windows runs production daemons (scheduler, skool, telegram-bot)
  2. Never push without bravo-session-end.sh
  3. Mac reads/edits/analyzes — never starts cron workers

STEP 3 — Env var audit.
Run this Python one-liner (Mac python3):

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
  present_count = len(keys_in_code & env_keys)
  print(f'Env audit: {present_count} present, {len(missing)} missing out of {len(keys_in_code)} referenced')
  if missing:
      print('Missing (but most have fallbacks — see classification below):')
      for k in missing: print(f'  {k}')
  "

Classify the missing keys (if any) into one of these buckets based on
brain/MAC_SYNC_PROMPT.md and brain/CREDENTIALS_SCAFFOLD.md:
  (a) HARD BLOCKER — daemon/script actually fails without it
  (b) ALIAS — code falls back to another name you already have
  (c) CODE DEFAULT — Python has a hardcoded default if unset
  (d) OPT-IN FEATURE — unset = feature disabled gracefully

The ONLY key that matters for Mac is GWS_PATH. On Windows the default is
r"C:\Users\User\AppData\Roaming\npm\gws.cmd" which breaks on Mac. If gws
is installed, set:
  GWS_PATH=$(which gws)
in .env.agents. If gws is not installed, skip it — google_tool.py will
simply error out if called, which is fine.

STEP 4 — Integration smoke test. For each, report OK or specific error:
  python3 scripts/supabase_tool.py select leads --limit 1
  python3 scripts/stripe_tool.py balance
  python3 scripts/funnel_sync.py stats
  python3 scripts/revenue_engine.py --json mrr
  python3 scripts/funnel_nurture.py --json run
  python3 scripts/revenue_engine.py --json sync-stripe

If any of those produce Telegram notifications while running, that means
scheduler classification is wrong. Report the output of every command in
full (they are safe — all read-only except sync-stripe which is idempotent).

STEP 5 — State read. Print:
  brain/STATE.md (full)
  memory/ACTIVE_TASKS.md (full)
  memory/SESSION_LOG.md (top 100 lines)
  memory/ACTIVE_SESSION.json

STEP 6 — Verify no running daemons on Mac.
Run: ps aux | grep -E "(scheduler|skool|telegram)" | grep -v grep
If you see any matches, STOP and tell me immediately — something is running
that shouldn't be. Do not kill anything yourself; I will decide.

STEP 7 — Report back in this exact format:

  ## Git
  commit <hash>, pulled <N> commits, <one-line summary of new files>

  ## Env audit
  <X>/<Y> keys present. <Z> missing.
  HARD BLOCKERS: <list or "none">
  Aliases / defaults / opt-ins: <count>

  ## Mac-specific overrides
  GWS_PATH: <present with mac path / needs override / skipped>

  ## Integration smoke test
  supabase_tool.py select leads: OK / <error>
  stripe_tool.py balance: OK / <error>
  funnel_sync.py stats: <result>
  revenue_engine.py mrr: $<value>
  funnel_nurture.py run: <day2/day5 counts>
  revenue_engine.py sync-stripe: <inserted/skipped/errors>

  ## Daemon check
  No daemons running on Mac: PASS / FAIL (details)

  ## Current state (from files)
  MRR: $<value>
  Open P0 tasks: <N>
  Last session log entry: <date, one-line>
  Active session claim: <machine, age>

  ## Ready-to-work status
  <one sentence: is Mac fully synced, or what's blocking>

STEP 8 — Run session end.
bash scripts/bravo-session-end.sh "mac sync verification — no spam, all clear"

This will commit memory/SESSION_LOG.md with the Mac session entry, write
HANDOFF.md, and push to origin/main. Windows will pick it up on next
bravo-session-start.

Hard rules for this session:
- DO NOT modify .env.agents (I will do it manually if needed)
- DO NOT install any packages without my OK
- DO NOT restart any processes
- DO NOT push code changes — only the session-end commit
- DO NOT run the Skool daemon (Windows has exclusive lock)
- DO NOT run bravo-scheduler (Windows has exclusive lock)
```

---

## After Mac Reports Back

Based on what Mac Claude reports, come back to me on Windows and I'll:
- Diagnose any HARD BLOCKER missing keys (unlikely — all known ones have fallbacks)
- Fix any integration test failures
- Confirm the system is fully coherent across both machines
- Walk you through enabling cross-machine SSH so I can drive Mac directly from Windows

## If Mac Claude Finds Nothing Wrong

Expected outcome: zero hard blockers, zero integration failures, zero false Telegram spam. The env audit should show ~16 missing keys — same as Windows — and ALL should classify as alias/default/opt-in. None should be hard blockers.

If that's what Mac reports, you're done. Both machines are in sync.

## If Mac Claude Finds Something Unexpected

Paste the full report back to me here. I'll triage from the Windows side without needing SSH access.

## Obsidian Links
- [[brain/CROSS_MACHINE_SYNC]]
- [[brain/MAC_SYNC_PROMPT]]
- [[brain/CREDENTIALS_SCAFFOLD]]
- [[memory/HANDOFF]]
