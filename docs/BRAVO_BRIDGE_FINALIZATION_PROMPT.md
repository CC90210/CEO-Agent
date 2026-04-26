# Bravo Telegram Bridge Finalization (Mac + Windows)

> **STATUS: ACTIVE — paste into Bravo on the MacBook 2026-04-26+.**
>
> **Why:** A Telegram-bridge audit on 2026-04-26 found 3 real issues from CC's screenshot:
> 1. Bravo said "Atlas is at `C:\Users\User\APPS\trading-agent`" — that path is stale (Atlas moved to `CFO-Agent` ~3 months ago)
> 2. Bravo said "Maven I don't have in my context" — Maven is documented but only loads at T3 (architecture queries), not on simple identity questions
> 3. Bridge tool list still pointed to `scripts/late_tool.py` which Bravo deleted on 2026-04-26 (transferred to Maven)
>
> **The Windows bridge has been partially fixed already in commit (current session):** stale `late_tool.py` references rewired to `../CMO-Agent/scripts/late_tool.py`, and a C-Suite snapshot (Bravo/Atlas/Maven/Aura with locations + domains) now loads at every tier ≥ T1. The Mac bridge needs the same treatment + a sync-pull from the Windows version.

---

You are Bravo on CC's MacBook. The `telegram_agent.js` file in this repo
powers the Bravo Telegram chat. CC ran a Telegram conversation on
2026-04-26 04:08 AM and found two functional bugs and a knowledge gap.
Fix all three.

═══ KNOWN ISSUES ═══

1. C-SUITE AWARENESS GAP: The bridge's `loadContext` function only loads
   `brain/APP_REGISTRY.md` and `brain/AGENTS.md` at Tier 3 (architecture
   queries). Simple identity questions like "do you know about Atlas and
   Maven?" classify as T2, so the bridge has no Maven context loaded.

   FIX: Open `telegram_agent.js`, find `loadContext`. Insert a hardcoded
   C-Suite snapshot BEFORE the T2 CLAUDE.md load. Use this exact block
   (the Windows side already has it — sync-pull from the Windows
   commit on origin/main once CC pushes):

   ```
   chunks.push(`=== C-SUITE (CC's 4-agent team — always load) ===
   - BRAVO (CEO, you) — C:\\Users\\User\\Business-Empire-Agent — strategy, clients, revenue, cold outreach, primary retainer/Skool, calendar
   - ATLAS (CFO) — C:\\Users\\User\\APPS\\CFO-Agent — tax, accounting, runway, research, portfolio advisory; writes cfo_pulse.json
   - MAVEN (CMO) — C:\\Users\\User\\CMO-Agent — paid ads (Meta+Google), social (Late/Zernio), Instagram, content pipeline, brand voice
   - AURA (Life/Home) — C:\\Users\\User\\AURA — smart home, habits, presence, life context
   Cross-agent messaging: \${PYTHON} scripts/agent_inbox.py post --from bravo --to <atlas|maven|aura> --subject "..." --body "..."
   Pulse files (read-only): data/pulse/ceo_pulse.json (yours), ../CMO-Agent/data/pulse/cmo_pulse.json (Maven), ../APPS/CFO-Agent/data/pulse/cfo_pulse.json (Atlas)`);
   ```

   On the MacBook: replace `C:\\Users\\User\\` with `/Users/conaugh/` in
   the snapshot since the Mac uses different paths. Also replace
   `../APPS/CFO-Agent/` and `../CMO-Agent/` with the actual Mac paths
   if the sibling repos live somewhere different on the MacBook.

2. STALE PATH REFERENCES: The bridge mentioned `scripts/late_tool.py` for
   social posting but that file was transferred to Maven on 2026-04-26
   (Bravo commit `3eb5b13`). All references should now point to
   `../CMO-Agent/scripts/late_tool.py` with a "(Maven cross-repo)" note.
   Same pattern for `instagram_engine.py` and `codex_image_gen.py`.

   FIX: grep `telegram_agent.js` for `late_tool.py`, `instagram_engine.py`,
   `late_publisher.py`, `codex_image_gen.py`. Each occurrence outside an
   archive comment must be rewritten with the cross-repo path.

3. PERSISTENCE OF STALE PATHS IN BRAIN: The `trading-agent` path appears
   5 times across Bravo's docs (mostly in old session-log entries). Atlas
   moved to `CFO-Agent` ~3 months ago. Most refs are historical and OK
   to leave, but verify `brain/APP_REGISTRY.md` + `brain/AGENTS.md` use
   the current path (they should — verify by grep).

═══ VERIFICATION ═══

After the fix, restart the bridge and ask via Telegram:
  - "Do you know about Atlas and Maven?" → must answer with both,
    correct paths, correct domains
  - "What's Maven for?" → must explain CMO domain (ads, social, content)
  - "Where does Atlas live?" → C:/Users/User/APPS/CFO-Agent (Win) or
    /Users/conaugh/.../CFO-Agent (Mac)
  - "Post a tweet for me" → bridge should know to use Maven's late_tool
    cross-repo, not Bravo's (which no longer exists)

═══ COMMIT ═══

After verification:
  git add telegram_agent.js
  git commit -m "bravo bridge: C-Suite snapshot at T1+ + Maven cross-repo paths"
  Do NOT push. Tell CC it's ready and wait for authorization.

═══ CROSS-AGENT FOLLOW-UP ═══

After Bravo's bridge is fixed, Maven still has NO Telegram bridge — CC
will paste a separate prompt at MAVEN_BRIDGE_BUILD_PROMPT.md to build
that. Atlas's bridge needs a similar C-Suite parity update — that's at
ATLAS_BRIDGE_FINALIZATION_PROMPT.md.

Begin.

---

## What CC does after pasting

1. Watch the bridge restart cleanly (no PM2/node errors)
2. Ask "Do you know about Atlas and Maven?" via the Telegram chat — verify both come back with correct paths + domains
3. Run all 4 verification questions from the prompt
4. If all pass: bridge is fixed. Move on to building Maven's bridge.
