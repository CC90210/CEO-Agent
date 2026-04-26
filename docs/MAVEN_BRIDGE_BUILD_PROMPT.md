# Maven Telegram Bridge — Build From Scratch

> **STATUS: ACTIVE — paste into Maven 2026-04-26+.**
>
> **Why:** Maven has no Telegram bridge yet. CC has a Bravo chat and an Atlas chat on Telegram and now wants a Maven chat. This prompt builds Maven's bridge as a sibling of Bravo's (`telegram_agent.js`) and Atlas's (`telegram_bridge.py`), tuned to Maven's marketing domain.

---

You are Maven, AI Chief Marketing Officer. CC needs a Telegram chat for
you — same UX as the Bravo + Atlas bridges he already uses on his phone.
You will build it, test it, register it with PM2, and post completion
to Bravo's inbox so he updates his C-Suite snapshot to include the new
Maven bot ID.

Take control. Don't ask permission for prescribed steps.

═══ ARCHITECTURE — same pattern as Bravo's bridge ═══

Bravo's reference: `C:\Users\User\Business-Empire-Agent\telegram_agent.js`
(Node.js, 55KB, V15.4). Read it cover-to-cover before writing yours so
you mirror the structure (handlers, tier classification, conversation
memory, token health check, computer control, killswitch).

Atlas's reference: `C:\Users\User\APPS\CFO-Agent\telegram_bridge.py`
(Python, 46KB). Atlas chose Python because most of Atlas's logic is
already Python (cfo/, finance/, research/ modules). Maven should choose
Node.js — your domain (Late/Zernio APIs, Meta SDK, Google Ads SDK) is
multi-language anyway, but Bravo's Node bridge is the more thorough
template and will give you all the computer-control + Telegram callback
features for free.

═══ THE BUILD ═══

Step 1 — File scaffold (15 min)
  • Create `telegram_agent.js` at the root of CMO-Agent.
  • Copy Bravo's bridge as the starting point (read-only — you write your
    own from-scratch, but the shape is identical).
  • Update the version comment at the top: `MAVEN TELEGRAM BRIDGE V1.0`.
  • Update all `Business-Empire-Agent` paths to `CMO-Agent`. Update
    `bravo` → `maven` in agent_source markers, agent_inbox calls,
    PM2 process name.

Step 2 — Bot token (10 min)
  • Maven needs its OWN Telegram bot, not Bravo's. CC will create it
    via @BotFather (name suggestion: "CC Maven CMO Bot"). The token
    goes into `.env.agents` as `MAVEN_TELEGRAM_BOT_TOKEN` and the
    chat ID as `MAVEN_TELEGRAM_CHAT_ID`. If `.env.agents` doesn't
    have these yet, surface that to CC before continuing — do NOT
    use Bravo's token.
  • Add a startup health check (mirror Bravo's V15.3.1 pattern) that
    fails fast with a clear log line if the token is missing or
    returns 401 from Telegram's getMe endpoint.

Step 3 — Maven-specific context loading (30 min)
  At T1+ (every tier), load:
    - `brain/STATE.md`
    - `memory/ACTIVE_TASKS.md`
    - C-SUITE SNAPSHOT (hardcoded — see below)
    - `data/pulse/cmo_pulse.json` (your own pulse — confirm it's fresh)
    - `../APPS/CFO-Agent/data/pulse/cfo_pulse.json` (Atlas's pulse — read
      to know if you can launch paid campaigns right now)

  At T2, also load:
    - `CLAUDE.md`
    - `brain/SOUL.md`
    - `brain/USER.md`
    - `brain/MARKETING_CANON.md` (your voice + framework reference)
    - `brain/RESPONSIBILITY_BOUNDARIES.md` (so you know what NOT to do)
    - `memory/SESSION_LOG.md` (last 30 lines)

  At T3, also load:
    - `brain/AGENTS.md`
    - `brain/CAPABILITIES.md`
    - `brain/ATTRIBUTION_MODEL.md`
    - `memory/PATTERNS.md`

  C-Suite snapshot (always load at T1+) — DO NOT HARDCODE. Bravo
  refactored this on 2026-04-26 to read from a single source of truth:
  `brain/CROSS_AGENT_AWARENESS.md` (canonical 4-agent table). Maven's
  bridge should follow the SAME pattern so a future path change
  propagates to all 3 chats automatically.

  Two implementation options:
  (a) Copy `brain/CROSS_AGENT_AWARENESS.md` from Bravo's repo into
      your own brain/ dir, and have your bridge read your local copy.
      Pro: zero cross-repo dependency at runtime. Con: must re-sync
      when Bravo updates the canonical.
  (b) Have your bridge read Bravo's copy directly via the sibling-
      repo path: `../Business-Empire-Agent/brain/CROSS_AGENT_AWARENESS.md`.
      Pro: always fresh. Con: depends on Bravo's repo being adjacent.

  Recommendation: (a) with a daily sync. Less coupling, easier
  reasoning. Implement the helper modeled on Bravo's
  `loadCSuiteSnapshot()` — read your own brain/CROSS_AGENT_AWARENESS.md,
  parse the "## The 4 Agents at a Glance" table, return it; fall back
  to a minimal hardcoded snapshot if the file is missing.

  Reference implementation in Bravo's `telegram_agent.js` —
  search for `loadCSuiteSnapshot` to see the parser + fallback pattern.

Step 4 — Maven-specific tool routing (45 min)
  Replace Bravo's tool list with Maven's. Your chat should do:

  CONTENT + CREATIVE:
  - Generate an ad: `${PYTHON} scripts/imagen_generate.py "<prompt>" --size 1080x1080`
  - Generate a video: `${PYTHON} scripts/render_video.py <template> --data <json>`
  - Render full content pipeline: `${PYTHON} scripts/content_pipeline.py <video.mp4>`
  - Generate ad copy variants: `${PYTHON} scripts/ad_copy_generator.py "<topic>" --count 5`

  PAID CHANNELS (READ cfo_pulse.json BEFORE launching):
  - Meta campaign: `${PYTHON} scripts/meta_ads_engine.py launch <campaign>`
  - Google Ads: `${PYTHON} scripts/google_ads_engine.py launch <campaign>`
  - Meta status: `${PYTHON} scripts/meta_ads_engine.py status`
  - Google status: `${PYTHON} scripts/google_ads_engine.py status`

  ORGANIC + SOCIAL:
  - Schedule post (Late/Zernio): `${PYTHON} scripts/late_publisher.py publish-due`
  - Cross-post: `${PYTHON} scripts/late_tool.py cross-post --text "..." --profile <id>`
  - Instagram DMs: `${PYTHON} scripts/instagram_engine.py check-dms` (Maven owns this as of 2026-04-26)
  - Email blast: `${PYTHON} scripts/email_blast.py send <list> <template>`

  REPORTING:
  - Performance: `${PYTHON} scripts/performance_reporter.py weekly --json`
  - A/B test results: `${PYTHON} scripts/ab_testing_engine.py status`

  CROSS-AGENT:
  - Read CFO pulse: `cat ../APPS/CFO-Agent/data/pulse/cfo_pulse.json`
  - Post to Bravo: `${PYTHON} scripts/agent_inbox.py post --from maven --to bravo ...`
  - Post to Atlas: `${PYTHON} scripts/agent_inbox.py post --from maven --to atlas ...`

  KILLSWITCH: `MAVEN_FORCE_DRY_RUN=1` short-circuits ALL outbound (already
  enforced in your send_gateway). The bridge MUST surface that env var
  status in every reply when a send is attempted.

Step 5 — Tier classification tuned to Maven (15 min)
  Bravo's T0 keywords are biased to computer-control verbs ("open",
  "click", "play"). Maven's T0 keywords should be marketing-flavored:
  "post", "tweet", "campaign", "ad", "creative", "headline", "report",
  "ROAS", "CPL", "image", "video", "thumbnail". Keep T2 as default for
  ambiguous queries. Promote to T3 on "strategy", "rebrand", "audience
  research", "competitive analysis".

Step 6 — Approval gate for paid launches (HARD GATE — 30 min)
  Bravo's bridge has an approval gate for destructive commands. Maven's
  must have one for ANY paid campaign launch. Before calling
  `meta_ads_engine.py launch` or `google_ads_engine.py launch` or
  `email_blast.py send`:
    - Read cfo_pulse.json. Show CC: "Atlas approved $X for <channel>
      <brand> on <timestamp>. Daily cap remaining: $Y. Launch?"
    - Inline Telegram buttons: ✅ Launch / ❌ Cancel
    - On ✅: log the decision via agent_inbox to Bravo + Atlas, then
      execute. On ❌: drop and log.
    - If cfo_pulse is stale (>24h), REFUSE and post to Atlas via inbox
      asking for a fresh pulse.

Step 7 — PM2 registration (10 min)
  Append to ecosystem.config.js (or create if missing):

  ```
  module.exports = {
    apps: [{
      name: 'maven-telegram',
      script: 'telegram_agent.js',
      cwd: 'C:/Users/User/CMO-Agent',
      autorestart: true,
      max_restarts: 10,
      env: { NODE_ENV: 'production' }
    }]
  };
  ```

  CC's machine: `pm2 start ecosystem.config.js && pm2 save`. Verify
  process is up: `pm2 status`. Should show maven-telegram online.

Step 8 — Telegram smoke test (15 min)
  CC sends from his phone:
    - "Hey, who are you?" → Maven introduces itself + Bravo + Atlas
    - "What's our current ad spend this week?" → reads cfo_pulse + Meta
      + Google APIs, summarizes
    - "Post a tweet about today's primary retainer win" → drafts via draft_critic,
      shows preview, awaits approval
    - "Launch the new creative on Meta" → reads cfo_pulse, gates approval

  All 4 must succeed before marking complete.

═══ SUCCESS CRITERIA ═══

  [ ] telegram_agent.js exists at CMO-Agent root, runs without error
  [ ] MAVEN_TELEGRAM_BOT_TOKEN + MAVEN_TELEGRAM_CHAT_ID are in .env.agents
  [ ] Startup health check passes (200 from getMe)
  [ ] C-Suite snapshot loads at T1+ (verify by asking "who are you and
      who else is on the team?" — must mention all 4 agents)
  [ ] Tool routing returns marketing-domain tools (not Bravo's CEO ones)
  [ ] Approval gate blocks paid-launch commands until CC clicks ✅
  [ ] Stale cfo_pulse refuses launches and posts to Atlas
  [ ] PM2 registered, autorestart, surviving a `pm2 restart maven-telegram`
  [ ] All 4 smoke-test prompts pass

═══ POST-COMPLETION HANDOFF ═══

After verification, post to Bravo's inbox so Bravo's C-Suite snapshot
adds the new Maven bot ID:

  ${PYTHON} scripts/agent_inbox.py --json post --from maven --to bravo \
    --priority normal --subject "Maven Telegram bridge live" \
    --body "MAVEN_TELEGRAM_BOT_TOKEN configured, PM2 process maven-
            telegram online, all 4 smoke tests passed. Add bot ID <ID>
            to your bridge's known-agents list and update CROSS_AGENT_
            AWARENESS.md so Atlas + Bravo know Maven is reachable on TG."

And post to Atlas:
  ${PYTHON} scripts/agent_inbox.py --json post --from maven --to atlas \
    --priority normal --subject "Maven now reads cfo_pulse before paid launches" \
    --body "Maven's bridge now hard-gates paid campaigns on your pulse.
            If you change the pulse schema, ping me — bridge has a
            schema-validator and will refuse launches on drift."

Begin with Step 1.

---

## What CC does after pasting

1. Create the Telegram bot via @BotFather → save token
2. Maven asks for the token + chat ID — paste them in
3. Watch Maven build the bridge — should take ~3 hours
4. When PM2 says maven-telegram is online, send "who are you?" from your phone
5. If C-Suite intro comes back correctly, you have 3 working chats: Bravo / Atlas / Maven
