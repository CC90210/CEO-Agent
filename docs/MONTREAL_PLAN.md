# Montreal Trip — Roadmap + Pre-Flight

> **2026-05-28 relocation note:** SunBiz daemons (`shop_out_sender.py`, `sequence_runner.py`, `lender_response_classifier.py`, `underwriting_orchestrator.py`, `renewal_reminder.py`, `follow_up_generator.py`, `cold_outreach_runner.py`, `daily_plan_generator.py`) and tools (`text_torrent_tool.py`, `kixie_tool.py`) now live in `~/SunBiz-Agent/scripts/`, not `~/CEO-Agent/scripts/`. PM2 entries for the daemons moved to `~/SunBiz-Agent/ecosystem.config.js` (run `pm2 start ecosystem.config.js` from each repo). Solara/Helios still invoke the same tools via the bridge's `run_script` — the bridge resolves the per-script `root` field automatically. Path-style references below mean "look in SunBiz-Agent" for the SunBiz tools/daemons.
>
> CC heading to Montreal 2026-05-26 to work on Sun Biz Funding in person with Ezra + team.
> Document built 2026-05-25 evening. Read once on the plane; reference on the ground.

---

## TL;DR — Are we ready?

**Yes, with three small caveats.** The full Sun Biz second-meeting expansion is live: Daily Plan, Cold Outreach, Underwriting tabs + Shopping Out severity-tier warnings + all 8 daemons + the entire V6.8 cognitive substrate for Solara. Migration 069 + 070 are applied to Supabase, RLS is green across all 45 tenant tables, 3 SunBiz cron jobs are seeded. Three things still need Ezra-the-human (not code):

1. Phone numbers for Jordan / Ethan / Ezra / Emily (lives at `~/SunBiz-Agent/memory/CLIENT_CONTEXT.md`)
2. The SunBiz "North Star" metric Ezra wants Solara watching (placeholder at `~/SunBiz-Agent/brain/SOUL.md`)
3. Incognito smoke-test of the new tabs against the live deployment

That's it. Show up, demo, fill in the placeholders, ship.

---

## What's actually live right now

**Dashboard (https://agent-dashboard-sigma-eight.vercel.app/t/sun)**
- 3 new tabs added to SunBiz sidebar: **Daily Plan** (Operations group), **Cold Outreach** (Outreach group), **Underwriting** (Pipeline group)
- Offers renamed to **Offers Board** (label tweak only)
- **Shopping Out severity-tier warnings**: replaces the prior hard-block. Operator gets Info / Warning / High Risk tiers per lender. Selecting a High Risk lender triggers a Proceed Anyway dialog that captures a required override note. Override persists to `shop_out_warnings` audit table with the rep's user_id + timestamp.
- **Lender narratives**: each lender in the recommender now gets a 1-3 sentence plain-English ranking explanation (Strong fit, Moderate, Long shot). No marketing fluff.
- **BankTab enhanced** in the lead drawer: underwriting status badge, sparkline metrics, re-run button, link to full Underwriting tab.
- **Import page split** for SunBiz: cold-list import goes to `cold_lead_lists` + `cold_leads` (separate storage from warm pipeline). Promote-to-warm is an explicit operator action with audit trail.
- **Forms page** restructured: three SunBiz template cards (Initial Lead Capture / Full Application / Bank Statement Upload) with "Create from template" buttons that pre-seed the form schema per Ezra's apply-now field list.

**Supabase (Bravo project)**
- Migration 069 applied — 14 new tables for the second-meeting expansion (application_underwriting, follow_up_tasks, daily_plan_items, cold_lead_lists, cold_leads, cold_outreach_campaigns, cold_outreach_recipients, shop_out_warnings, known_funding_companies, offer_sources, email_thread_monitors, lender_feedback, personalized_form_links, agent_memory_notes)
- Migration 070 applied — RLS policies on all 14 + service-role bypass + tenant-scoped auth gates. `audit_rls_coverage.py` returns 45/45 green.
- Known funding companies seeded: Forward Financing, OnDeck, Velocity, Kapitus, Yellowstone, Mantis, RCF, BlueVine, Kabbage, Funding Circle, CAN Capital, Square Capital, Stripe Capital, PayPal WC, Credibly, Fundbox, National Funding, Reliant.

**Bridge-side daemons (CEO-Agent, run from your Windows via PM2)**
- `shop_out_sender.py` — multi-lender outbound SMTP; substitutes `{{owner_phone}}` per assigned rep
- `sequence_runner.py` — drip campaign engine; now cancels in-flight drips on form-submission (Solara doesn't nag a lead who already did the thing)
- `lender_response_classifier.py` — Gmail label monitor + Claude classifier; now persists every outcome to `lender_feedback` for recommender bias
- `underwriting_orchestrator.py` — claims pending `application_underwriting` rows; runs statement_parser + debt_detector + sales_angle; writes metrics + risk flags + readiness score
- `daily_plan_generator.py` — daily 6:30am ET, six category passes
- `follow_up_generator.py` — daily 6am ET, generates stuck-lead tasks
- `renewal_reminder.py` — daily 9am ET, 40-50% term progress sweep + Telegram alert
- `cold_outreach_runner.py` — 30s tick, drains campaigns through send_gateway with daily cap

3 cron jobs seeded (first fires tomorrow morning). 2 PM2-loop-shaped daemons (cold_outreach_runner, underwriting_orchestrator) will need PM2 entries on the VPS when that comes up; meanwhile they're triggerable on-demand via CLI.

**SunBiz-Agent repo (your client-product fork)**
Forked from CEO-Agent's V6.8 cognitive substrate so Solara has full autonomous-agent parity with Bravo, scoped for funding-shop operations:
- 5 entry points: CLAUDE.md (174 lines), GEMINI.md, ANTIGRAVITY.md, AGENTS.md (new), OPENCODE.md (new)
- 16 brain/ files: SOUL, USER (Ezra), BRAIN_LOOP, STATE, INTERACTION_PROTOCOL, CAPABILITIES, GROWTH, HEARTBEAT, AGENTS, CHANGELOG, CLIENT, AGENT_ROUTER, EXECUTION_RULES, INTENTS, WHEN_TO_USE_SKILLS, _archive
- 21 active skills + 8 legacy archived
- 13 memory/ files
- CONTEXT.md at repo root (SunBiz vocabulary glossary)
- 6 operator-facing docs: SOLARA_QUICKSTART, HELIOS_QUICKSTART, ARCHITECTURE, DAEMON_PLAYBOOK, MIGRATION_HISTORY, CHANGELOG, plus VPS_BRINGUP from earlier

---

## Roadmap — what to do, in order

### Before you leave (tonight, 30 min)

- [ ] `git -C ~/SunBiz-Agent pull` — confirm you have the latest brain/ + skills (Solara's cognitive substrate)
- [ ] Open https://agent-dashboard-sigma-eight.vercel.app/t/sun in **incognito** as Ezra's user. Walk Daily Plan → Underwriting → Cold Outreach → Shopping Out. They'll render empty (no data seeded for those tables yet) but the chrome should look right. If anything 500s, it's an API-route bug; flag it.
- [ ] Pack laptop with these repos cloned + .env.agents present (you already have them on the work machine)

### Day 1 in Montreal — onboard Ezra (2-4 hours)

**Together at the laptop:**

- [ ] **Fill in `~/SunBiz-Agent/memory/CLIENT_CONTEXT.md`** — team phone numbers (Jordan / Ethan / Ezra / Emily), current lender book size, monthly deal volume, notable lender relationships. Solara uses this to draft outreach in Ezra's voice.
- [ ] **Confirm the SunBiz North Star** in `~/SunBiz-Agent/brain/SOUL.md` — what's the single number Ezra wants Solara watching? Likely "funded deals per month" or "monthly commission $". Replace the placeholder.
- [ ] **Walk through the dashboard's three new tabs** together. Daily Plan will be empty until tomorrow's 6:30am cron fires (or run `python ~/Business-Empire-Agent/scripts/daily_plan_generator.py once` to populate immediately). Underwriting is empty until someone uploads a bank statement. Cold Outreach is empty until a cold list is imported.
- [ ] **Demo Shopping Out** with the new severity-tier UI. Pick a real application, pick lenders, intentionally include a high_risk one, hit Send → walk through the Proceed Anyway dialog and the audit-log persistence.
- [ ] **Demo Cold Outreach end-to-end**: paste a small test cold list (5-10 rows), pick channel (start with email — lowest risk), compose, preview, send. Watch the campaign drainer in `scripts/cold_outreach_runner.py loop` mode.

### Day 2-3 — first real production usage

**With Ezra driving, you co-pilot:**

- [ ] Pick one real lead in the warm pipeline → run it through the Three-Step Application Funnel: send Initial Lead Capture form link → wait for submission → send Full Application form link → wait → send Bank Statement Upload form link → wait. Verify the drip cancellation hook fires (the sequence_runner should cancel its nag campaign when the form submits).
- [ ] Pick one real application with bank statements uploaded → run underwriting → review metrics + risk flags + sales angle → push to Lender Recommender → review the narrative + severity tiers → ship to lenders.
- [ ] Wait for first Daily Plan to render tomorrow morning at 6:30am ET. Review the 6 categories with Ezra. If any feel noisy (too many stuck-lead alerts, irrelevant priority calls), tune the thresholds in `scripts/daily_plan_generator.py`.
- [ ] Wait for first Renewal Reminder at 9am ET. If the Telegram alert noise is too much, dial back via `manifest.settings.renewal_eligibility_threshold_pct` (raise from 40 to 45 or 50 to reduce volume).

### Day 4-5 — VPS bring-up (only if Ezra wants Solara running independent of your Windows)

Runbook: `~/SunBiz-Agent/docs/VPS_BRINGUP.md` (8 steps, ~30 min once VPS exists).

- [ ] Provision a VPS (DigitalOcean droplet, Hetzner, Vultr — $20-40/month is fine for the daemon load)
- [ ] Clone both `CEO-Agent` (for PM2 ecosystem) + `SunBiz-Agent` (for Solara's substrate)
- [ ] Populate `.env.agents` from your password manager
- [ ] Run `python scripts/doctor.py --json` — must be all green
- [ ] Apply migrations 042-070 (idempotent; safe to re-run)
- [ ] `pm2 start ecosystem.config.js --only event-router,sequence-runner,lender-response-classifier,claude-bridge-ping`
- [ ] Pair the bridge with the dashboard (Settings → Devices → Install bridge)
- [ ] Migrate the 3 SunBiz crons from `cron_jobs` (empire scope, fires on your Windows) to `tenant_cron_jobs` (tenant scope, fires on the VPS) once the VPS is verified stable

### Week 2+ — the second wave (what Ezra will inevitably ask for)

Based on the second-meeting notes, here's what's likely next once the basics land:

1. **Email Offer Scanner daemon** — currently Planned. Polls the inbound lender mailbox via Gmail label, extracts offer terms via Claude, creates Offer records automatically. The `email_thread_monitors` table is ready; the daemon is the missing piece.
2. **Browser Offer Extractor** — currently Planned. Opens lender portal "View Offer" links from emails via CloakBrowser, extracts terms via Claude vision. Needs per-lender adapters (Velocity first, then Kapitus, then Forward Financing). The `cloak_browser_tool.py` infrastructure is ready.
3. **Document Parser** — currently Planned. Parse driver's license + voided check uploads for OCR (name match, account/routing for ACH, etc.). Thin wrapper around Anthropic vision.
4. **Commission projection rollout (Phase 6.6)** — currently a stubbed Phase note. When Solara captures funded amount + funded buy-rate + funded term days, project commissions per deal. Needs a `commissions_projection` field on `application_lender_threads` + a CLI to query rollups. Already documented in the brain/ playbooks as "Phase 6.6 — query path documented".
5. **Tenant CSS theming** — `manifest.brand.primary_color` exists in the schema but isn't wired to a CSS variable swap yet. Trivial fix; ~30 minutes when you decide colors matter.
6. **AI editor for manifests (Phase 2)** — let Ezra ask Solara "add a Lead Status column to the Leads board" and have Solara mutate the manifest via function calls. Schema is ready; the function-calling tool surface needs wiring.

---

## Critical things to verify when you land

Quick smoke test (5 min on hotel wifi):

```bash
# 1. Are the daemons + crons live on your Windows?
ssh cc-windows "pm2 status"
ssh cc-windows "python ~/Business-Empire-Agent/scripts/core/cron_engine.py list | grep -i sunbiz"
# Expect: bravo-scheduler running + 3 SunBiz cron jobs

# 2. Is RLS still green?
ssh cc-windows "cd ~/Business-Empire-Agent && python scripts/audit_rls_coverage.py --project bravo"
# Expect: "All tenant-scoped tables have RLS enabled"

# 3. Is the dashboard deploying clean?
# https://vercel.com/cc90210/agent-dashboard — check latest deploy is green

# 4. Did the morning crons actually fire?
# Open Telegram, look for the 9am Renewal Reminder ping (if any funded_deal hit the 40-50% window)
# Open dashboard /t/sun/daily-plan — there should be items in the 6 categories
```

If any of those four fail, that's the conversation to have with me before doing anything else.

---

## Where everything lives (cheat sheet)

| You want to... | Look here |
|---|---|
| See what Solara can do | `~/SunBiz-Agent/docs/SOLARA_QUICKSTART.md` |
| See what Helios can do | `~/SunBiz-Agent/docs/HELIOS_QUICKSTART.md` |
| Read the full system architecture | `~/SunBiz-Agent/docs/ARCHITECTURE.md` |
| Bring up a VPS | `~/SunBiz-Agent/docs/VPS_BRINGUP.md` |
| Diagnose a stuck daemon | `~/SunBiz-Agent/docs/DAEMON_PLAYBOOK.md` |
| Hand the project off to an external AI | `~/Business-Empire-Agent/docs/AGENT_COMMAND_CENTER_HANDOFF.md` |
| See what schema exists | `~/SunBiz-Agent/docs/MIGRATION_HISTORY.md` |
| See what's deployed where | `~/APPS/oasis-command-center/content/playbooks/08-sunbiz-production-pre-flight.md` § Section 10 |
| Solara's identity + values | `~/SunBiz-Agent/brain/SOUL.md` |
| Solara's playbooks (verb → action) | `~/SunBiz-Agent/brain/INTENTS.md` |
| Solara's daily monitoring rhythm | `~/SunBiz-Agent/brain/HEARTBEAT.md` |
| Ezra's profile + priorities | `~/SunBiz-Agent/brain/USER.md` |
| SunBiz business profile + ICP | `~/SunBiz-Agent/brain/CLIENT.md` |

---

## Honest gaps (so you're not surprised)

1. **Parallel V6.9.x work in flight** — there are uncommitted files in CEO-Agent (migration 071 staged, migration 073 untracked, ai-editor + workflow-steps + views-loader) and oasis-command-center (views + workflow-steps + tests). These are from a different agent's stream (V6.9.1 through V6.9.4 commits) shipping a workflow-engine substrate + manifest AI editor. **Not my work this session.** I left them alone. When you're back at the laptop, check if that stream is done; if so, commit it.

2. **Migration 071 + 072 + 073** are queued in CEO-Agent but I didn't apply them (not my stream). Check with whoever shipped V6.9.x.

3. **API routes for new tabs return 500 if the dashboard hits a table that's not yet been written to** — that's not a bug, that's empty-state behavior. Once Solara starts running (cron tomorrow morning), data populates and the UI fills in.

4. **The 4 P2 doc-fix sweeps** I did this evening completed the Codex audit closure. But Codex itself is still rate-limited and was unable to re-audit after the fixes — there could be other issues lurking that a fresh adversarial pass would catch. Re-run after 6:53 PM cutoff clears: `node ~/.claude/codex-plugin/scripts/codex-companion.mjs adversarial-review --wait "<focus>"`.

5. **The 2 PM2-loop-shaped daemons** (cold_outreach_runner, underwriting_orchestrator) aren't yet in `ecosystem.config.js` because they'd conflict with the cron-shaped versions on your Windows. They'll go into PM2 only on the VPS. Until then, trigger them on-demand via CLI when testing.

---

## What to bring to Montreal

- Laptop (obviously) with all 3 repos cloned + .env.agents populated
- Login credentials for Ezra's existing tooling (JotForm, Twilio, Gmail/Google Workspace) — so you can wire them into SunBiz-Agent's `.env.agents` together if needed
- The list of Ezra's team's phone numbers (or get them on-site for CLIENT_CONTEXT.md)
- A test cold list (5-10 fake/test rows) for the Cold Outreach demo so you don't blast real prospects on day 1
- A real application with bank statements uploaded (or one Ezra is willing to use as the live underwriting demo)
- Sleep. The build is done; the trip is execution.

---

## North Star reminder

Empire goal: **$5,000 USD Net MRR by 2026-06-18**. Sun Biz Funding is the first real client tenant — every funded deal Ezra closes via Solara is a marker that the multi-tenant Agent Command Center pattern actually works. Get one real funded deal traced end-to-end (lead → underwriting → shop-out → offer → funded → renewal eligible) during this trip and the architecture has earned the right to scale.

Safe travels.
