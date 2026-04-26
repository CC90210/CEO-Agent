# Maven Update Prompt — Capability Parity + Frontmatter Fix + Send-Safety

> **How to use:** Open Claude Code in `C:\Users\User\CMO-Agent`, paste the prompt below into the session, and let Maven execute it. This prompt is idempotent — if Maven already has a piece, it skips. Read-only against Bravo (`C:\Users\User\Business-Empire-Agent`); writes only inside CMO-Agent.

---

## Audit findings driving this prompt (so Maven understands the *why*)

A diagnostic from Bravo's repo on 2026-04-26 surfaced four production-grade gaps in Maven:

1. **0/16 of Maven's sub-agents have YAML frontmatter** — Claude Code cannot auto-discover them. Effectively invisible to the dispatch system.
2. **19/31 of Maven's skills are missing the `name:` / `description:` frontmatter fields** — same auto-discovery problem.
3. **No send-safety chokepoint.** Maven's `email_blast.py`, `meta_ads_engine.py`, `google_ads_engine.py`, and `jotform_tracker.py` send / spend without going through a `send_gateway`-style governor. Bravo had this exact gap and fixed it (V5.6 chokepoint architecture). Marketing email is *the* highest-blast-radius surface — must fail closed on placeholder names ("Hi Contact,"), CASL violations, daily caps, and draft-quality issues.
4. **Sub-agent role bleed.** Maven currently routes work to 16 marketing-specific agents but lacks the 8 cross-cutting agents Bravo uses for orchestration discipline (writer, reviewer, debugger, researcher, git-ops, codex-agent, chief-of-staff equivalent, meta-agent). Some of those overlap with Maven's existing agents — Maven needs the discipline patterns, not duplicate roles.

The prompt below addresses all four.

---

## THE PROMPT — paste this into Maven's Claude Code session verbatim

```
You are Maven (CMO Agent). I'm authorizing a structural upgrade pass — execute it
top to bottom. Read-only against Bravo at C:\Users\User\Business-Empire-Agent;
all writes happen inside CMO-Agent only.

GOAL: bring Maven up to production-grade parity with Bravo on the cross-cutting
disciplines (frontmatter, send-safety, skill coverage), without bloating Maven
with CEO-domain skills that aren't yours.

Do NOT use destructive operations. Do NOT modify .env.agents. Do NOT touch any
file under Business-Empire-Agent/. Stop and surface to CC if any step is
ambiguous.

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — FRONTMATTER REPAIR (15 min)
═══════════════════════════════════════════════════════════════════════════════

PROBLEM: 0/16 agents and 19/31 skills lack the YAML frontmatter Claude Code
needs to auto-discover them. Right now they're effectively invisible.

For every file in `agents/*.md` and `skills/*/SKILL.md` that doesn't already
start with a `---` block containing both `name:` and `description:`, prepend:

  ---
  name: <derived from filename, kebab-case>
  description: <one-line trigger sentence — when should Claude invoke this?>
  model: <sonnet for routine, opus for strategy/ambiguity>  # agents only
  tools: <comma-separated allow-list>  # agents only — be restrictive
  ---

Use Bravo's existing files as reference for the exact format:
- agents pattern:  C:\Users\User\Business-Empire-Agent\agents\writer.md
- skills pattern:  C:\Users\User\Business-Empire-Agent\skills\send-gateway\SKILL.md

For each agent's `description:`, write the sentence from Maven's perspective:
"Use this agent when CC asks to <X>." Don't pad. One concrete sentence.

After the pass, verify with:
  python -c "
  import pathlib
  ok=0; missing=[]
  for f in pathlib.Path('agents').glob('*.md'):
      txt=f.read_text(encoding='utf-8',errors='replace')
      if txt.startswith('---') and 'name:' in txt[:500] and 'description:' in txt[:500]:
          ok+=1
      else: missing.append(f.name)
  print(f'agents: {ok} valid, {len(missing)} missing: {missing}')
  ok=0; missing=[]
  for f in pathlib.Path('skills').glob('*/SKILL.md'):
      txt=f.read_text(encoding='utf-8',errors='replace')
      if txt.startswith('---') and 'name:' in txt[:500] and 'description:' in txt[:500]:
          ok+=1
      else: missing.append(f.parent.name)
  print(f'skills: {ok} valid, {len(missing)} missing: {missing}')
  "

Both lines must report 0 missing before moving to Phase 2.

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — IMPORT THE 12 CROSS-CUTTING SKILLS MAVEN IS MISSING (45 min)
═══════════════════════════════════════════════════════════════════════════════

These live in Bravo today but are general-purpose, not CEO-domain. Copy each
SKILL.md into Maven's skills/ directory verbatim, then add a `## Maven-specific
adaptation` section at the bottom describing how Maven uses it (ad campaign
context, not OASIS sales context).

CRITICAL — copy these 12:

1. send-gateway — Bravo: skills/send-gateway/SKILL.md
   The single chokepoint pattern. Maven's email_blast.py and meta/google ads
   engines MUST route through a Maven-owned send_gateway in Phase 3. This
   skill teaches the architecture.

2. email-safety — Bravo: skills/email-safety/SKILL.md
   The one-page rulebook for any AI driving email. Maven sends marketing
   emails to live recipients — this is non-negotiable.

3. security-protocol — Bravo: skills/security-protocol/SKILL.md
   Credential hygiene, .env.agents discipline, secret rotation.

4. codex-delegation — Bravo: skills/codex-delegation/SKILL.md
   When to delegate backend campaign work to OpenAI Codex (ad copy variants
   at scale, performance-data analysis, A/B test math). Pattern is the same
   for Maven; targets differ (campaigns, not API routes).

5. agent-inbox — Bravo: skills/agent-inbox/SKILL.md
   Async cross-agent messaging — Bravo, Atlas, Aura, Codex all post to
   `tmp/agent_inbox/`. Maven needs to read its inbox on session start
   ("--to maven") and post replies. Adapt the script if a Maven-side
   inbox script doesn't exist yet (Phase 3 will wire it).

6. mcp-operations — Bravo: skills/mcp-operations/SKILL.md
   MCP server routing, debugging, fallback rules.

7. task-routing — Bravo: skills/task-routing/SKILL.md
   The decision matrix: inline vs sub-agent vs Codex vs MCP.

8. anti-drift — Bravo: skills/anti-drift/SKILL.md
   How to stay on the user's actual ask instead of drive-by refactoring.

9. verification-before-completion — Bravo: skills/verification-before-completion/SKILL.md
   Domain-specific "done" definitions. Maven should NEVER mark a campaign
   "launched" without a read-back from the platform API.

10. writing-plans / executing-plans — Bravo: skills/writing-plans + skills/executing-plans
    The plan workflow. For multi-step campaign launches.

11. memory-management + memory-compression — Bravo: skills/memory-management/SKILL.md +
    skills/memory-compression/SKILL.md
    How to keep brain/, memory/, data/pulse/ healthy as the repo ages.

12. hyperthink — Bravo: skills/hyperthink/SKILL.md
    The 7-phase deep-reasoning protocol. Use for irreversible creative
    decisions (rebrand, major audience pivot, $5K+ ad spend reallocation).

ALSO COPY (lower priority, but valuable):
- ship — Bravo: skills/ship/SKILL.md (deployment discipline, adapt to Maven
  meaning "campaign launch" not "code deploy")
- python-daemon-automation — for cron-style campaign monitors
- subagent-driven-development — delegating creative work to sub-agents
- using-git-worktrees — parallel campaign branches
- web-scraping — competitive ad library scraping
- knowledge-management — the marketing canon discipline
- sop-breakdown — turning marketing playbooks into runnable steps
- retro — post-campaign retrospectives

For each copy:
  cp Bravo/skills/<name>/SKILL.md Maven/skills/<name>/SKILL.md
  Then: append `## Maven-specific adaptation` section. 5–10 lines max.

DO NOT COPY (Bravo-only, CEO/CFO domain, NOT Maven's responsibility):
  ceo-briefing, ceo-dashboard, client-success, proposal-generation,
  financial-modeling, crisis-response, scaling-playbook, investor-*,
  meeting-automation, sales-methodology, sales-closing, strategic-planning,
  team-management, skool-automation, booking-management, gws-* (Google
  Workspace email/calendar — Bravo's domain because Bravo owns CC's inbox).

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — MAVEN-OWNED SEND_GATEWAY (90 min) — HIGHEST PRIORITY
═══════════════════════════════════════════════════════════════════════════════

PROBLEM: marketing email is the highest-blast-radius surface in CC's empire.
Bravo got bitten by "Hi Contact," — a placeholder name leaked into 9 real
sends — and that was *cold outreach*. Maven sends *marketing email blasts*,
which is even higher volume. Without a chokepoint, the same failure mode is
inevitable.

Build `scripts/send_gateway.py` in Maven, modeled on Bravo's V5.6 chokepoint.
Read Bravo's at: C:\Users\User\Business-Empire-Agent\scripts\send_gateway.py

The Maven gateway should enforce:

A. NAME SANITIZATION — block placeholder names before render
   Copy `scripts/name_utils.py` from Bravo verbatim into Maven's scripts/
   directory. Then `from name_utils import safe_first_name, sanitize_template_vars`
   wherever Maven renders a recipient name.

   We choose copy-verbatim over runtime cross-repo import because (1) it
   keeps Maven independent of Bravo's filesystem layout, (2) the file is
   ~80 lines and changes rarely, (3) repos may live on different machines
   in the future. If the file ever changes in Bravo, both copies update —
   that's a known minor maintenance cost.

B. CASL COMPLIANCE — every commercial email needs:
   - Express or implied consent in `casl_consent` table
   - Identification of sender (Maven-mode: brand name + physical address)
   - Working unsubscribe mechanism
   - Bravo has `scripts/casl_compliance.py` — read it as reference.

C. DAILY/HOURLY CAPS — per-channel:
   - email: 200/day, 30/hr per brand
   - meta-ads spend: cap from cfo_pulse.json
   - google-ads spend: cap from cfo_pulse.json
   Maven's caps should be MORE conservative than Bravo's because marketing
   list sizes are larger.

D. DRAFT_CRITIC GATE — every commercial creative must pass adversarial
   review before send. Bravo's `scripts/draft_critic.py` is the reference.
   Fail-closed on:
   - Any verdict != "ship"
   - Any exception in the critic itself
   (Bravo had a bug here — fixed 2026-04-26 in db37263. Maven should ship
   with the fix in place from day one.)

E. SUPPRESSION LIST — never email a suppressed address. Maven shares the
   same Supabase project as Bravo (phctllmtsogkovoilwos), so use the same
   `casl_consent` table.

F. KILLSWITCH — `MAVEN_FORCE_DRY_RUN=1` env var must short-circuit ALL
   sends to dry-run mode. Bravo has BRAVO_FORCE_DRY_RUN — exact same pattern.

After the gateway exists, REWIRE:
- scripts/email_blast.py → routes through send_gateway, no direct SMTP
- scripts/meta_ads_engine.py → spend gate via send_gateway (channel="meta_ads")
- scripts/google_ads_engine.py → spend gate via send_gateway (channel="google_ads")
- scripts/jotform_tracker.py → if it sends, route through gateway

Write tests at `scripts/test_send_gateway.py`. Bravo's test file has 51 cases
— mirror the structure. Minimum coverage:
- Golden path send works
- Placeholder name → blocked or rewritten via name_utils
- Daily cap exceeded → blocked
- Hourly cap exceeded → blocked
- Suppressed address → blocked
- Critic verdict != ship → blocked
- Critic exception → blocked (fail-closed)
- MAVEN_FORCE_DRY_RUN=1 → all sends short-circuit to dry_run
- CASL violation → blocked

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — DELEGATION TOOLS — wire Maven into the multi-agent fabric (30 min)
═══════════════════════════════════════════════════════════════════════════════

A. Create `scripts/agent_inbox.py` — copy from Bravo verbatim. The script
   has built-in cross-repo routing via a `SIBLING_REPOS` map: posting
   `--to bravo` from Maven writes directly into Bravo's
   `Business-Empire-Agent/tmp/agent_inbox/inbox/`, and posting `--to maven`
   from Bravo writes into Maven's `CMO-Agent/tmp/agent_inbox/inbox/`. Each
   agent reads only its own local inbox; the writer resolves the recipient's
   repo path. (This was wired in Bravo on 2026-04-26 — verify the version
   you copy includes the `SIBLING_REPOS` dict and `_inbox_path_for()`
   helper.)

   Per-machine path overrides via env vars (set in `.env.agents`):
   `BRAVO_REPO`, `MAVEN_REPO`, `ATLAS_REPO`, `AURA_REPO`. Defaults are the
   Windows paths under `C:\Users\User\`.

   Smoke-test after copy:
     python scripts/agent_inbox.py --json post --from maven --to bravo \
       --subject "smoke-test" --body "verify cross-repo routing" --priority low
   The output must include `"_delivered_to": ".../Business-Empire-Agent/tmp/agent_inbox/inbox"`.
   Then ask CC to confirm the message landed in Bravo's inbox.

B. Create `scripts/codex_delegate.py` — wrapper to fire Codex tasks from
   Maven. Bravo's pattern lives at `~/.claude/codex-plugin/scripts/codex-companion.mjs`.
   Maven uses Codex for: ad-copy variant generation at scale (50+ variants
   per campaign), performance-data math (LTV/CAC, attribution), A/B test
   significance calculations, landing-page A/B copy variants.

C. Create `scripts/state_sync.py` — modeled on Bravo's. Updates STATE.md,
   ACTIVE_TASKS.md, SESSION_LOG.md, and writes `data/pulse/cmo_pulse.json`.
   This is the "memory sync" run at end of every session.

D. Create `scripts/self_audit.py` — Maven-flavored health check. Checks:
   - All agent + skill frontmatter valid (Phase 1 result is permanent)
   - All cron-equivalent scheduled tasks have run in the last 7 days
   - Meta + Google Ads tokens valid (don't print them — just status)
   - send_gateway tests pass
   - cmo_pulse.json fresh (< 24h old)
   - No orphaned files in brain/ or memory/
   Emit 0–100 score, JSON-output-flag-supported.

E. Update `brain/AGENTS.md` — add a "Cross-Cutting Agents (from Bravo
   parity)" section. Maven already has architect, debugger, documenter,
   explorer, workflow-builder. Add THESE three NEW agents (do not
   duplicate existing roles — `content-creator` is Maven's writer-
   equivalent for ad copy, so the new `writer` is for non-ad
   communications like memos, briefs, internal docs):

   - reviewer.md — adversarial pre-ship reviewer for campaigns + creative
     before launch. Source: `Business-Empire-Agent/agents/reviewer.md`.
     Adapt: review focus shifts from "is this code safe to ship?" to
     "is this campaign safe to launch? Does CASL pass? Does CFO budget
     gate clear? Is creative free of slop?"

   - researcher.md — deep market research, competitor ad-library scrapes,
     audience trend analysis. Source: `Business-Empire-Agent/agents/researcher.md`.
     Adapt: research targets are markets / competitors / platforms, not
     codebases / libraries.

   - writer.md — non-ad written communications: campaign briefs to CC,
     post-mortem reports, memos to Bravo via agent_inbox, RFCs for new
     marketing capabilities. Source: `Business-Empire-Agent/agents/writer.md`.
     Distinct from `content-creator` which owns ad copy + headlines.

   For all three, copy Bravo's frontmatter pattern (name/description/
   model/tools) and rewrite the body in Maven-flavored prose.

═══════════════════════════════════════════════════════════════════════════════
PHASE 5 — DIVISION-OF-RESPONSIBILITY DOC (15 min)
═══════════════════════════════════════════════════════════════════════════════

Write `brain/RESPONSIBILITY_BOUNDARIES.md` covering:

OWNED BY MAVEN (you):
- Ad creative (image, video, copy) for OASIS, PropFlow, Nostalgic, CC
  Personal Brand, SunBiz
- Paid campaigns (Meta, Google, TikTok, LinkedIn)
- Funnels, landing pages, lead magnets, tripwires
- Organic content distribution (Late/Zernio, Instagram, X, LinkedIn)
- Marketing email blasts (separate list from CC's cold outreach)
- SEO, AEO, content calendar
- Marketing attribution & ROAS reporting
- Brand voice & visual standards
- Competitive research / ad-library scraping
- A/B testing & creative iteration
- Marketing automations (n8n workflows for nurture sequences)

OWNED BY BRAVO (read-only access):
- B2B cold outreach (one-to-one sales emails to specific business owners)
- Client relationship management & success
- Sales calls, proposals, contracts
- CRM data integrity
- Bennett / Skool community operations
- Calendar / booking management
- Business strategy & OKRs
- Client delivery work

OWNED BY ATLAS (read-only access):
- All financial decisions: spend approvals, runway, tax, capital allocation
- The cfo_pulse.json spend gate is binding — Maven NEVER launches a paid
  campaign without verifying cfo_pulse.json approves the budget
- Trading, FIRE planning, wealth tracking

OWNED BY AURA (read-only access):
- CC's life context, energy, presence, home automation

GREY ZONES (resolve via agent_inbox):
- Lead generation (Bravo owns the closed list; Maven generates inbound via
  ads/funnels; both read the leads table). Rule: Maven posts new inbound
  leads to lead_interactions; Bravo handles outreach to those leads.
- Client win-back campaigns (Maven creative; Bravo identifies who; Atlas
  approves spend).
- Content that doubles as lead-gen (LinkedIn thought leadership, OASIS
  case studies). Bravo briefs strategy; Maven executes creative.

═══════════════════════════════════════════════════════════════════════════════
PHASE 6 — VERIFY EVERYTHING + COMMIT (15 min)
═══════════════════════════════════════════════════════════════════════════════

Run in order:
1. python scripts/self_audit.py --json    → must score >= 95/100
2. python scripts/test_send_gateway.py    → must pass 100%
3. python -m unittest discover scripts -p "test_*.py" → all pass
4. python scripts/state_sync.py --note "structural upgrade — frontmatter
   repair + 20 cross-cutting skills imported + send_gateway shipped +
   delegation tools wired + responsibility boundaries documented"
5. git add -A
6. git diff --stat (review the change surface)
7. git commit (use a 4-line message summarizing the 5 phases)

When done, post to Bravo's agent_inbox:
  python scripts/agent_inbox.py post \
    --from maven --to bravo \
    --subject "Maven structural upgrade complete (V1.0 → V1.1)" \
    --body "All 5 phases shipped. self_audit <score>/100. send_gateway
            online with <N> tests. Frontmatter 100% valid. Responsibility
            boundaries documented at brain/RESPONSIBILITY_BOUNDARIES.md.
            Ready for cross-agent work."

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA — what "done" looks like
═══════════════════════════════════════════════════════════════════════════════

- [ ] 16/16 agents have valid frontmatter
- [ ] 31/31 skills have valid frontmatter
- [ ] 20+ cross-cutting skills imported from Bravo (12 critical + ~8 valuable)
- [ ] Maven-owned send_gateway.py exists, has tests, passes them
- [ ] email_blast.py + meta_ads_engine.py + google_ads_engine.py rewired
  through the gateway
- [ ] agent_inbox.py + codex_delegate.py + state_sync.py + self_audit.py
  all in scripts/
- [ ] brain/RESPONSIBILITY_BOUNDARIES.md exists and is referenced from
  brain/INDEX.md and SOUL.md
- [ ] self_audit score >= 95/100
- [ ] Bravo notified via agent_inbox

If anything blocks you: stop, write what blocked, post to bravo via inbox,
do NOT push past it.
```

---

## What CC should do after Maven runs this

1. Watch Maven's progress — if it stalls on any phase, check `tmp/agent_inbox/` for the block reason.
2. Once Maven posts the completion message, Bravo will pick it up on its next session-start inbox check.
3. Manually inspect `brain/RESPONSIBILITY_BOUNDARIES.md` — that's the social contract; you may want to tweak phrasing.
4. Verify `data/pulse/cmo_pulse.json` is being updated — that's the spend-request channel that Atlas reads before approving budget.

---

## Why this prompt is "safe"

- **No destructive ops.** No `git reset --hard`, no `rm -rf`, no force-push.
- **No cross-repo writes.** Read-only against Bravo; writes only inside CMO-Agent.
- **No credential touches.** `.env.agents` is explicitly excluded.
- **Idempotent phases.** If Maven already has a piece, it skips.
- **Fail-closed gates.** Phase 3 (send_gateway) inherits Bravo's fail-closed pattern — any unknown state blocks rather than sends.
- **Verification at every phase boundary.** Maven won't move forward if the previous phase didn't succeed.
- **Self-reports completion via inbox.** No silent done — Bravo finds out programmatically.
