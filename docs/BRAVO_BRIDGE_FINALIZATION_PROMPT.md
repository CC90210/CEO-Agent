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

1. C-SUITE AWARENESS GAP: The bridge's `loadContext` function only loaded
   `brain/APP_REGISTRY.md` and `brain/AGENTS.md` at Tier 3 (architecture
   queries). Simple identity questions like "do you know about Atlas and
   Maven?" classify as T2, so the bridge had no Maven context loaded.

   FIX (already done on Windows in commit `d71520f`, REFACTORED in next
   commit): The Windows bridge now has a `loadCSuiteSnapshot()` helper
   that READS `brain/CROSS_AGENT_AWARENESS.md` at runtime — single
   source of truth, no hardcoded path duplication. If you change a
   path or domain in that one file, all 3 bridges (Bravo Win, Bravo
   Mac, Atlas, future Maven) pick it up automatically.

   The MacBook bridge needs the SAME refactor. Pull the latest
   `telegram_agent.js` from origin/main once CC pushes — both helpers
   (`loadCSuiteSnapshot` + the chunks.push call site) come down together.
   Verify on Mac:
     node --check telegram_agent.js  (must exit 0)
     node -e "const fs=require('fs');const path=require('path');
              const __dirname=process.cwd();
              <paste loadCSuiteSnapshot definition>; console.log(loadCSuiteSnapshot());"

   The output should include the 4-agent table from
   brain/CROSS_AGENT_AWARENESS.md. If it falls back to the hardcoded
   snapshot, that means the file is missing on the Mac — fix that
   first (git pull should bring it down).

   On the MacBook, paths in `brain/CROSS_AGENT_AWARENESS.md` itself
   are Windows-style (`C:\Users\User\...`). That's intentional — they're
   canonical references, used as identifiers across all 3 agents. The
   Mac bridge can use those identifiers verbatim; what matters
   functionally is whether each agent's local sibling-repo paths
   resolve. Verify the Mac has the 3 sibling repos at the equivalent
   Mac locations (`/Users/conaugh/...`) and that the bridge's
   subprocess calls use those Mac paths via env override or path
   resolution. Do NOT edit `brain/CROSS_AGENT_AWARENESS.md` to swap
   to Mac paths — that would corrupt the canonical doc for the
   Windows side.

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
