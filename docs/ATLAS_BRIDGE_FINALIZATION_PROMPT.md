# Atlas Telegram Bridge Finalization — C-Suite Awareness Parity

> **STATUS: ACTIVE — paste into Atlas 2026-04-26+.**
>
> **Why:** A 2026-04-26 Telegram-bridge audit found that Bravo's bridge (and likely Atlas's too) didn't have a C-Suite snapshot loaded at low-tier queries. CC asked Bravo "do you know about Atlas and Maven?" and Bravo missed Maven. The same gap exists in Atlas's bridge — Atlas knows about Bravo (per its own CLAUDE.md) but doesn't know about Maven by default, and uses a stale path for "trading-agent" in some session-log fragments.
>
> Atlas's bridge is `telegram_bridge.py` (Python, 46KB). This prompt brings it to the same C-Suite awareness parity as the freshly-fixed Bravo bridge.

---

You are Atlas, AI Chief Financial Officer. CC has 3 separate Telegram
chats — one for Bravo (CEO), one for you (CFO), and soon one for Maven
(CMO). All three need to know about each other and stay in sync. CC
hit a knowledge gap on the Bravo chat where Bravo didn't know Maven
existed. Yours likely has the same gap. Fix it.

═══ KNOWN ISSUES ═══

1. C-SUITE AWARENESS MISSING IN BRIDGE: `telegram_bridge.py` builds
   prompt context from your brain/ files. Verify whether Maven is
   mentioned anywhere in the context-loading path. If Maven only shows
   up in `brain/AGENTS.md` or `docs/` (not loaded by default), the
   bridge has the same gap Bravo did.

   FIX: Add a hardcoded C-Suite snapshot to your bridge's prompt
   builder. Load it on EVERY query, not just architecture-tier ones.
   Snapshot text (under 350 chars, hardcoded — paths Windows-style for
   parity with how other agents reference each other):

   ```
   === C-SUITE (CC's 4-agent team — always load) ===
   - BRAVO (CEO) — C:\Users\User\Business-Empire-Agent — strategy, clients, revenue, cold outreach
   - ATLAS (CFO, you) — C:\Users\User\APPS\CFO-Agent — tax, runway, portfolio, research; you write cfo_pulse.json
   - MAVEN (CMO) — C:\Users\User\CMO-Agent — paid ads, social, Instagram, content, brand (reads your cfo_pulse to gate spend)
   - AURA (Life/Home) — C:\Users\User\AURA — smart home, habits, presence
   Cross-agent messaging: python scripts/agent_inbox.py post --from atlas --to <bravo|maven|aura> ...
   ```

2. STALE PATH IN OLD CONTEXT: Your repo's docs may still reference
   `C:\Users\User\APPS\trading-agent` (your old name before becoming
   the broader CFO-Agent). Search:
     grep -r "trading-agent" .
   Update any active references to `CFO-Agent`. Leave session-log
   archives alone — they're historical truth.

3. PULSE-CONTRACT VERIFICATION: Bravo's bridge now reads
   `data/pulse/cfo_pulse.json` (your file) before any spend decision.
   Maven's new bridge will too. If your pulse schema drifts, both
   downstream agents fail closed and CC's spend decisions stall.

   FIX (preventive, not reactive):
   - Read `cfo/pulse.py` — confirm the JSON schema.
   - Document the schema in `brain/CFO_PULSE_CONTRACT.md` (one page,
     example JSON + field list + freshness rules).
   - Cross-reference from `brain/SHARED_DB.md`.
   - When you eventually run the ATLAS_FINALIZATION_PROMPT.md
     (Lens 3 covers this), the pulse_schema.py validator will be
     written. For now, just document.

4. KILLSWITCH PARITY: Bravo's bridge supports `BRAVO_FORCE_DRY_RUN=1`.
   Maven's new bridge will support `MAVEN_FORCE_DRY_RUN=1`. Atlas
   should support `ATLAS_FORCE_DRY_RUN=1` so all 3 agents have a
   uniform safety pattern. If your bridge doesn't honor this env var,
   add a 3-line check at the top of every outbound action:
     if os.environ.get("ATLAS_FORCE_DRY_RUN") == "1":
         return {"status": "dry_run", "reason": "killswitch active"}

═══ VERIFICATION ═══

After the fix, restart the Atlas Telegram bridge and ask via Telegram:
  - "Who's on the team?" → must list Bravo + Atlas + Maven + Aura with
    correct paths and domains
  - "What's Maven for?" → must explain CMO domain (ads, social, content)
  - "Set ATLAS_FORCE_DRY_RUN=1 and try to send a tax alert" → must be
    blocked with killswitch reason
  - "What's Maven's path?" → C:\Users\User\CMO-Agent

═══ COMMIT ═══

After verification:
  git add telegram_bridge.py brain/CFO_PULSE_CONTRACT.md brain/SHARED_DB.md
  git commit -m "atlas bridge: C-Suite snapshot at every tier + killswitch + pulse contract doc"
  Do NOT push. Tell CC it's ready and wait for authorization.

═══ POST-COMPLETION ═══

Post to Bravo's inbox:
  python scripts/agent_inbox.py --json post --from atlas --to bravo \
    --priority normal --subject "Atlas bridge now has C-Suite parity" \
    --body "Bridge knows about Bravo + Maven + Aura. ATLAS_FORCE_DRY_RUN
            killswitch wired. cfo_pulse contract documented at
            brain/CFO_PULSE_CONTRACT.md so your read-side validator
            has a stable schema to test against."

And ping Maven (so Maven's bridge — when CC builds it — has a stable
contract to read):
  python scripts/agent_inbox.py --json post --from atlas --to maven \
    --priority high --subject "cfo_pulse contract documented" \
    --body "See brain/CFO_PULSE_CONTRACT.md in Atlas's repo for the
            exact schema. Don't drift from it without coordinating."

Begin.

---

## What CC does after pasting

1. Watch Atlas restart its bridge cleanly (no Python errors)
2. Ask "Who's on the team?" via the Atlas Telegram chat — verify all 4 agents come back with correct paths + domains
3. Ask "What's Maven for?" → must answer with marketing/ads/social, not "I don't know"
4. If both pass: Atlas bridge is at parity with Bravo. Move on to building Maven's bridge.
