# MacBook Bravo Sync Prompt — Pull 12 Unpushed Commits + Verify

> **STATUS: ACTIVE — paste into Bravo on the MacBook 2026-04-26+.**
>
> **Why:** Windows Bravo shipped 12 commits between 2026-04-25 and 2026-04-26 covering placeholder-name disaster fixes, send_gateway safety holes, full system audit, marketing-tool transfer to Maven, two cross-agent finalization prompts (Maven + Atlas), three Telegram-bridge prompts, and the Telegram-bridge C-Suite-awareness fix + refactor. All commits are local on Windows; nothing pushed to `origin/main` yet. Mac side is stale.
>
> This prompt brings the MacBook current, verifies nothing broke locally, and runs the bridge fix so the Mac Telegram chat (the one in CC's screenshot) gets the same C-Suite snapshot fix as Windows.

---

You are Bravo on CC's MacBook. CC just shipped 12 commits on the
Windows side that haven't been pushed yet. Your job: pull them down,
verify nothing broke locally, restart the Telegram bridge with the new
C-Suite snapshot loader, and report status.

Don't ask permission for prescribed steps.

═══ THE 12 COMMITS YOU'RE PULLING ═══

(Newest first — git log oneline)
  20fe66b — telegram bridge: extract C-Suite snapshot to single source of truth
  d71520f — telegram bridge: fix C-Suite knowledge gap + 3 cross-bridge prompts
  0b8d57e — ship Maven + Atlas finalization prompts + retire stale V1.1 docs
  6649982 — self-review fixes: cron seed cleanup + sibling_repos consolidation
  3eb5b13 — transfer 4 marketing scripts to Maven + rewire 28 references
  c83b414 — finalize working tree: revert obsidian UI state + ignore stray download.html
  da76c13 — sync MAVEN_SYSTEM_MESSAGE.md with chat-pasted version
  f38afac — add paste-ready Maven system message that drives autonomous upgrade
  9885bfd — agent_inbox cross-repo routing + Maven-prompt accuracy fixes
  eb45bf1 — archive 3 completed one-shots + ship Maven structural-upgrade prompt
  db37263 — full system audit: fix 2 send_gateway safety holes + spread name sanitizer
  9af8c4c — extract name sanitizer to shared module + close outreach_engine gap

═══ THEMES (so you know what to look for) ═══

  1. NAME SANITIZER — `scripts/name_utils.py` (new). Single source of
     truth for blocking placeholder lead names ("Contact", "Owner",
     etc.) before they reach a real recipient. Used by email_engine,
     outreach_engine, funnel_nurture, autonomous_agent. Tests at
     scripts/test_name_utils.py (21 cases).

  2. SEND_GATEWAY SAFETY FIX — draft_critic gate now fail-closes on
     any non-`ship` verdict AND on critic exceptions. Was silently
     allowing `escalate`/`revise` verdicts to send. 51/51 tests pass.

  3. MARKETING TRANSFER — 4 scripts moved Bravo → Maven on 2026-04-26
     (commit 3eb5b13): late_tool.py, late_publisher.py,
     instagram_engine.py, codex_image_gen.py. Bravo's scheduler.py +
     ceo_dashboard.py + context_manager.py rewired (subprocess
     cross-repo for read-only stats). 21 docs updated.

  4. ONE-SHOT ARCHIVE — 3 completed scripts (_post_call_update,
     _tremont_email_and_updates, _warm_revival_batch2) moved from
     scripts/ to scratch/oneshots-2026-04/.

  5. CROSS-AGENT FINALIZATION PROMPTS — docs/MAVEN_FINALIZATION_PROMPT.md
     (V1.1→V1.2) and docs/ATLAS_FINALIZATION_PROMPT.md (V1.0
     foundation build). Stale V1.0→V1.1 Maven docs marked HISTORICAL.

  6. TELEGRAM BRIDGE FIX — telegram_agent.js now has
     loadCSuiteSnapshot() that reads brain/CROSS_AGENT_AWARENESS.md
     at runtime. Replaces the previous hardcoded snapshot. Single
     source of truth — when path drifts, all 3 bridges pick it up.

  7. SIBLING-REPO READS (NEW 2026-04-26) — telegram_agent.js now has
     SIBLING_REPOS map + readSiblingRepo() + loadSiblingPulses()
     helpers. Bridge can READ files from Maven, Atlas, Aura repos
     directly (env-overridable: MAVEN_REPO, ATLAS_REPO, AURA_REPO).
     loadSiblingPulses() injected into context at T1+ so Bravo always
     knows what Maven and Atlas are currently doing — not just that
     they exist. Stale-pulse warnings (>24h) get a ⚠ flag.

═══ EXECUTION ═══

Step 1 — Stash any local changes (5 min)
  cd ~/Downloads/business-empire-agent  (or wherever the repo lives on Mac)
  git status
  • If anything is uncommitted, ask CC if it should be stashed or
    committed first. Don't blow away local work.
  • If clean: proceed.

Step 2 — Pull (5 min)
  git fetch origin
  git log HEAD..origin/main --oneline   # confirm you see all 12 commits
  git pull --ff-only origin main
  • If fast-forward fails (Mac has commits Windows doesn't), STOP and
    surface to CC. Manual reconciliation required — do NOT force-push
    or rebase autonomously.

Step 3 — Smoke-test the Python side (10 min)
  python3 -m unittest scripts.test_name_utils scripts.test_send_gateway
  • Must show "Ran 72 tests in <X>s   OK" or close to it.
  • If any test fails, that's a Mac-specific environment issue (Python
    version, missing package). Document in tmp/agent_inbox/ outbox to
    bravo and fix locally — do NOT skip the test.

Step 4 — Verify the bridge (10 min)
  node --check telegram_agent.js
  • Must exit 0. If not, the pull picked up something that broke JS
    parse on Mac's Node version. Check Node version: node --version
    (need >= 18). Surface to CC if older.

  Verify loadCSuiteSnapshot returns the canonical table:
    node -e "const fs=require('fs'); const path=require('path');
             const PYTHON='python3'; const __dirname=process.cwd();
             eval(fs.readFileSync('telegram_agent.js','utf8')
               .match(/const readFileSafe[\s\S]*?^\};/m)[0]);
             eval(fs.readFileSync('telegram_agent.js','utf8')
               .match(/const loadCSuiteSnapshot[\s\S]*?^\};/m)[0]);
             console.log(loadCSuiteSnapshot());"
  • Output should include the 4-agent table from
    brain/CROSS_AGENT_AWARENESS.md (Bravo, Atlas, Maven, Aura).
  • If output shows the hardcoded fallback instead, that means
    brain/CROSS_AGENT_AWARENESS.md didn't pull (file missing). Fix.

Step 5 — Restart the Telegram bridge (5 min)
  pm2 restart telegram-agent  (or whatever PM2 process name CC uses
                               on the Mac — likely "bravo-telegram"
                               or "telegram-agent")
  pm2 logs telegram-agent --lines 30  # confirm clean boot, no errors

Step 6 — Telegram smoke test (5 min)
  Tell CC to send these from his phone in the Bravo Telegram chat:
    1. "Do you know about Atlas and Maven?" → must answer with both,
       correct paths (CFO-Agent, NOT trading-agent), correct domains
    2. "What's Maven for?" → must explain CMO domain (paid ads,
       social, Instagram, content, brand)
    3. "Where does Atlas live?" → C:\Users\User\APPS\CFO-Agent
       (canonical path; Mac local sibling path may differ but the
       canonical reference is what's in brain/CROSS_AGENT_AWARENESS.md)
    4. "Post a tweet for me" → bridge should know to use Maven's
       late_tool cross-repo, not Bravo's (which no longer exists)
    5. "What is Maven currently doing?" → bridge must answer with
       Maven's actual session_note from cmo_pulse.json, not "I don't
       know" (this verifies the new readSiblingRepo + loadSiblingPulses)
    6. "Is Atlas's pulse fresh?" → must report cfo_pulse age in hours
       and flag if >24h stale

  IMPORTANT for Mac: SIBLING_REPOS defaults assume Windows paths.
  Set env overrides in PM2 ecosystem.config.js or .env so the Mac
  bridge finds the sibling repos:
    MAVEN_REPO=/Users/conaugh/CMO-Agent  (or wherever it lives)
    ATLAS_REPO=/Users/conaugh/APPS/CFO-Agent
    AURA_REPO=/Users/conaugh/AURA
  Without these, the Mac bridge falls back to the Windows defaults
  and readSiblingRepo will return empty for all 3 siblings.

  All 6 must return correct answers before declaring done.

Step 7 — State sync (5 min)
  python3 scripts/state_sync.py --note "MacBook synced from Windows
    origin/main — 12 commits pulled (9af8c4c..20fe66b). Bridge restarted
    with loadCSuiteSnapshot. All 4 Telegram smoke tests passed."

═══ SUCCESS CRITERIA ═══

  [ ] git pull --ff-only succeeded; 12 commits visible in `git log`
  [ ] python3 -m unittest passed (72 tests)
  [ ] node --check passed
  [ ] loadCSuiteSnapshot returns the canonical 4-agent table at runtime
  [ ] PM2 bridge process online, no errors in logs
  [ ] All 4 Telegram smoke tests pass
  [ ] state_sync ran cleanly

═══ FAILURE PROTOCOL ═══

If ANY step fails:
  1. STOP. Do not proceed to subsequent steps.
  2. Document the exact failure (command + output + stack trace if any)
     in tmp/agent_inbox/outbox/ as a message to bravo (Windows side).
  3. Tell CC the failure mode in 1-2 sentences.
  4. Do NOT attempt destructive recovery (no git reset --hard, no
     force-push, no PM2 force-kill). Wait for CC's call.

═══ POST-COMPLETION ═══

Report status in 3-4 sentences:
  - Commits pulled: 12 (9af8c4c..20fe66b)
  - Tests: <N>/<M> pass
  - Bridge: online via PM2
  - Telegram smoke: 4/4 pass

Then ask CC: "All synced. Want me to git push origin main from Windows
later, or push from here?" (Both work — pick one to avoid divergent
remotes.)

Begin with Step 1.

---

## What CC does after pasting

1. Watch the bridge restart cleanly via PM2
2. Send the 4 smoke-test messages from your phone — verify Maven knowledge is now there
3. If all pass: Mac is current. The 3 cross-bridge prompts (Maven build, Atlas finalization, Bravo bridge fix on Mac is now obsolete) can move forward.
