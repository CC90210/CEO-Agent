---
tags: [tasks, active]
---
# ACTIVE TASKS
> [[brain/DASHBOARD]] | [[brain/STATE]] | [[memory/SESSION_LOG]]

## Target: $5,000 USD Net MRR by May 15, 2026
- **Current:** ~$2,982 USD/mo | **Gap:** ~$2,018 USD/mo (~4-5 new clients)
- **Risk:** 94% revenue from primary retainer — diversification is #1 priority

## 🏗 V6.0 FINALIZATION (2026-04-22)
- **Status:** Scaffolds shipped (dormant), send_gateway hardening in progress via Codex, V6 architecture doc signed-off.
- **Owner:** Bravo (scaffold) + CC (sign-off on 4 open questions in docs/V6_ARCHITECTURE.md)
- **Shipped this session:**
  - `docs/V6_ARCHITECTURE.md` — Principal-Architect design doc (~450 lines)
  - `database/014_v6_pgvector_memory.sql` — pgvector + memory_chunks + search_memory_chunks RPC
  - `database/015_v6_event_bus_extensions.sql` — LISTEN/NOTIFY + claim/ack/fail RPCs, FOR UPDATE SKIP LOCKED
  - `scripts/event_bus.py`, `scripts/memory_chunker.py`, `scripts/memory_ingest.py`, `scripts/memory_query.py`, `scripts/pii_scrubber.py`
  - `infra/Dockerfile`, `infra/docker-compose.yml`, `infra/Caddyfile`, `infra/README.md`, `infra/.dockerignore`
  - `.github/workflows/deploy-vps.yml`
  - Codex-delivered send_gateway hardening: bounce circuit breaker + HOURLY_CAPS + per-domain cooldown + draft_critic wired + dns_reputation.py doctor
- **CC decision points (blocking activation):**
  1. VPS region — Hetzner Germany (€6.90/mo, recommended) or OVH Canada
  2. Dedicated GPU VPS for self-hosted LLM — recommend: defer until first regulated client
  3. SOC 2 timeline — recommend: defer until $30k+/yr deal ROI-justifies
  4. Obsidian sync model — recommend: keep local, git-sync to VPS
- **Activation sequence (after CC sign-off):** apply migration 015 (event bus ext) Week 1 → provision VPS Week 2 → migration 014 (pgvector) + ingest Week 3 → cutover Week 4.
- **Full context:** [[docs/V6_ARCHITECTURE]] | [[infra/README]] | [[memory/project_v6_architecture]] | [[memory/project_send_gateway_audit]]

## 🎯 CONSULTING RETAINER PITCH — Alejandro Andrade (2026-04-21)
- **Owner:** CC
- **Status:** 3 texts sent post-call (Apr 21) — delivered but unread/no response for ~24h. **NO MORE TEXTS.** Next action is a **phone call Wed Apr 23 or Thu Apr 24** — casual follow-up, not chasing.
- **Scope:** Associate / consultant access — Google Meets when he needs, async availability, repo + cloud reviews. NOT agency-retainer, NOT weekly-guaranteed deliverables.
- **Pricing:** **$450/mo minimum** · non-negotiable
- **Context:** $1,500 one-off already paid — that covered the Tool Shed + AIOS Roadmap (his to keep forever). Retainer is separate, for ongoing access.
- **Call script:** "Hey Alejandro, just following up on those texts. Wanted to see where your head's at — any questions on the retainer?" → then listen.
- **On YES:** Stripe subscription link for $450/mo within 1 hour. First Google Meet scheduled when he asks.
- **On NO / silent after call:** 30-day watch. **Re-check 2026-05-21.** Do NOT chase. Hold price line if he counter-offers below $450.
- **Pending blocker:** CC to send me Alejandro's email so I can share the 3 Google Docs (Tool Shed, Client Playbook, Benchmark/AIOS Roadmap) via `google_tool.py drive share`.
- **Full context:** [[memory/project_alejandro_andrade]] (auto-memory)
- **Risk flag:** He framed Claude Code as "leaked info from Anthropic enterprise" in the meeting. If retainer signs, early check-in to align tech framing so it doesn't reflect on CC.

## 🎯 HIGH-PRIORITY WARM LEAD — Basque Landscaping (2026-04-20)
- **Owner:** Jonathan Hutton · `(705) 539-0547`
- **Status:** `qualified` · **Score:** 75
- **Deal shape:** **Custom software build** (Gritly-style — he owns the software, tailored to his use cases). Not a retainer — one-time + maintenance.
- **Angle that landed:** 15-year exit value — custom software asset makes the business sell for significantly more when he exits.
- **Timeline:** He said "3 weeks busy" — CC shortened to 1 week follow-up. **next_followup_at = 2026-04-26**
- **Next action:** CC rings back 2026-04-26 (or sooner if an opening appears). Goal: book the 15-min Zoom walkthrough. Compress the pitch.
- **Keep him warm meantime:** one-touch LinkedIn view + maybe one content piece about custom-software-as-asset if CC wants to subtly land it in his feed.
- **Why it matters:** First real qualified lead outside primary retainer in weeks. This is the diversification play.

## CC Manual Action Required

## CC Manual Action Required
- [x] **Deploy command center to Vercel** — DONE 2026-04-20. Live at https://agent-dashboard-cc90210.vercel.app (Vercel SSO-gated — CC logs in once, dashboard loads). Deploy playbook saved to memory/reference_vercel_deploy.md.

## 🔨 N8N Inbound Qualifier V10 Refinement — roadmap (2026-04-20 PM)
> CC's direction: move all inbound + follow-up reminders OFF Python (machine isn't 24/7) and ONTO N8N (Hostinger cloud, 24/7). Already done: disabled `Lead Follow-up Check` + `Email Inbox Monitor` crons. All future inbound work lives in N8N.

**Full 8-step click-by-click plan at:** `docs/N8N_v10_REFINEMENT.md` (~15 min of clicks in the N8N UI)

Pending CC execution in N8N:
- [ ] Step 1: delete Shopify branch (Oasis Chat Agent + 8 tool nodes)
- [ ] Step 2: paste new Classifier system prompt (6 categories now, Products dropped, Unsubscribe added)
- [ ] Step 3: paste new OASIS Email Agent prompt (production-grade tech support)
- [ ] Step 4: paste new Business Opportunities Agent prompt (lead convo + booking link)
- [x] Step 5: SENTINEL cleanup (remove Research Agent + Perplexity + Google Sheets; add Gmail "Business Expenses" / "Legal" / "Atlas/Review" labels)
- [ ] Step 6: add ONE Supabase `Log to Bravo Ledger` node (calls `record_inbound_from_n8n` RPC → dashboard sees every classified email)
- [ ] Step 7: add 4-node Unsubscribe chain (STOP replies auto-suppress via Supabase)
- [ ] Step 8: delete Internal & Operations Agent (unused — no team members)

Bravo-side pending:
- [ ] Create `add_email_suppression` Supabase RPC + `email_suppressions` table (needed for Step 7) — ready to ship on CC's say-so
- [ ] **(Optional) Wire N8N Supabase node** into workflow `OASIS Inbound Qualifier (Bravo Aware)` (ID `1cGIN32alM8sf8OV`) — NO LONGER REQUIRED as of 2026-04-20. The Python path (`email_engine.py check-inbox` now calls `inbound_classifier` + `record_inbound_from_n8n` RPC automatically via scheduler's 5-min IMAP poll) closes the blind spot. Wiring the N8N node would add redundancy; skip unless CC wants dual-path coverage. Paste-in config preserved at [docs/N8N_INBOUND_INTEGRATION.md](../docs/N8N_INBOUND_INTEGRATION.md).

## P0 — Revenue
- [ ] **Content Engine daily** — Kona Makana inbound funnel. 1 long-form/day through Remotion pipeline + 5 cross-posts. Zernio free plan limit (20/mo) hit — upgrade or cut.
- [ ] **Cold outreach volume** — 20+ touches/day via semi-auto loop. Deploy `skills/sales-closing` on every reply.
- [ ] **4 OASIS retainers by Apr 30** — Stretch goal. Drop primary retainer concentration below 70%.
- [ ] **Import 47+ leads to CRM** — Only 4 in pipeline. `python scripts/lead_engine.py bulk-import`

## P2 — Deferred
- [ ] **primary retainer Coaching $10K** — DEFERRED. primary retainer currently overcommitted to his own clients. Revisit Q3 2026. Not a Week-1 lever.

## P1 — Operations
- [ ] Upgrade Zernio plan or reduce posting to 20/mo — 12 posts stuck in scheduled
- [ ] Grade Q2 OKRs weekly (Mondays) | Review R-001 + R-010 weekly
- [ ] Run first client health report — `python scripts/client_health.py report`
- [ ] Populate competitor intelligence — `data/competitors.json`
- [ ] Create CLAUDE.md for 3 apps (Grape Vine, Mindset, On The Hill)
- [ ] Fix SkoolWatchdog scheduled task — run `scripts/fix_watchdog_task.ps1` as admin
- [x] Codex dual-AI integration — Done 2026-04-02
- [x] Terminal popup fix — Done 2026-04-04 (silent VBS launchers, CREATE_NO_WINDOW)
- [x] Skool agent V2 — Done 2026-04-04 (research-enhanced, DuckDuckGo)

## P2 — Blocked
| Task | Blocked By | Since |
|------|-----------|-------|
| TIKTIK Camera | Midas network spec | 2026-03-17 |
| On The Bay | Client not ready | 2026-03-16 |

## 5-Week Sprint Roadmap — $5K MRR by May 15, 2026 (STRETCH: 4 RETAINERS BY APR 30)
> Current: $3,322 Net MRR. Gap to $5K: $1,678. True goal = 4 retainers by end of month to drop primary retainer concentration below 70%.
> primary retainer $10K coaching is DEFERRED — primary retainer is overcommitted to his own clients right now. Revisit Q3.
> **The real play: stack legitimate agency retainers through content + cold outreach.** No coaching crutch.

### Week 1 (Apr 12–18) — CONTENT ENGINE DAILY + COLD OUTREACH VOLUME
- [ ] Ship 1 Kona Makana long-form video through Remotion pipeline (CC records, Bravo edits via `content_pipeline.py`)
- [ ] Daily content cascade: 1 long-form → 5 cross-posts via `content_engine` repurposing workflow
- [ ] Import 47 stale leads to CRM — `python scripts/lead_engine.py bulk-import`
- [ ] Semi-auto outreach: 20 cold emails/day — `outreach_batch.py` → Telegram approve → send
- [ ] Decide: Zernio upgrade ($29/mo) or frequency cut to 20/mo
- **Target:** 3 discovery calls booked, 50+ cold touches made, 1 long-form shipped

### Week 2 (Apr 19–25) — DISCOVERY CALLS + FIRST CLOSE
- [ ] 5 discovery calls on calendar
- [ ] Deploy `skills/sales-closing` framework on every call
- [ ] Publish 1 "how I closed my first client" proof piece (content flywheel)
- [ ] First OASIS retainer closed (any size — the first one breaks the drought)
- **Close target:** 1 retainer signed

### Week 3 (Apr 26–May 2) — DIVERSIFY + CYBERSECURITY TEST
- [ ] Second OASIS retainer closed
- [ ] Ship first "Security Posture Assessment" offer on Kona Makana ($2,500 flat, 5-day engagement)
- [ ] Start TryHackMe "Complete Beginner" path (CC personal skill-up, 30 min/day)
- [ ] Client health report run — `python scripts/client_health.py report`
- **Close target:** 2 retainers signed (MRR gap closing)

### Week 4 (May 3–9) — SCALE + SALES TRAINING
- [ ] Third OASIS retainer closed
- [ ] Log every close/loss to `memory/SESSION_LOG.md` with LAER breakdown
- [ ] Codify 3 new objection-handling patterns from real deals → feed back to sales-closing SKILL
- [ ] First security assessment delivered end-to-end (even if internal test run)
- **Close target:** 3 retainers signed, trajectory to $5K confirmed

### Week 5 (May 10–15) — LOCK IN
- [ ] Final push: $5K MRR hit, verified in `revenue_engine.py mrr`
- [ ] primary retainer concentration dropped below 75% (from 93%)
- [ ] Public announcement on Kona Makana (proof → more inbound)
- [ ] Retro — `/retro` workflow, log lessons to `memory/SELF_REFLECTIONS.md`
- [ ] Plan Q3 OKRs from position of strength

## Self-Improvement Tasks (2026-04-11 — from hyperthink self-upgrade)
- [x] Create `skills/ethical-hacking/SKILL.md` — authorized offensive security playbook + secure-by-default coding
- [x] Create `skills/sales-closing/SKILL.md` — NEPQ extension into closing
- [x] Verify Antigravity MCP config (.vscode/mcp.json, 8 servers healthy)
- [x] Build `/close-review` workflow — paste transcript, get NEPQ+LAER scoring, auto-log patterns
- [x] Sync `ANTIGRAVITY.md` with `CLAUDE.md` (MCP 4→8, skills 55→150, agents 16→17, workflows 15→34)
- [x] **Skool Engine V2.1** — comment-tier + coach-attention escalation + crash-safe state + is_cc tightening
- [x] Skool daemon restarted on V2.1 (PID 11176, cycle 41+, HEALTHY)
- [x] **Notification pipeline V2.1** — fail-closed parsing, double-notify fix, fast-poll, retry-on-error, IMAP poison UID, argparse root-cause
- [x] **Cross-machine sync** — SSH control plane, session scripts, ACTIVE_SESSION.json, HANDOFF.md protocol
- [x] **Mac synchronized** — Python 3.12.13, all integration tests passing, telegram cold-standby in PM2
- [x] **PM2 name mismatch fixed** — Windows now uses `bravo-scheduler` + `bravo-telegram` (matches ecosystem.config.js)
- [x] **CRLF debt cleared** — 39 Python files normalized to LF + .gitattributes enforcing LF on *.py/*.sh/*.js
- [x] **requirements.txt generated** — 17 core packages, committed for reproducible installs
- [ ] CC: install eJPT study materials (see ethical-hacking skill, $200)
- [ ] CC: first TryHackMe session (30 min) this week
- [ ] Bravo: after 3 real deals, update sales-closing with observed objections

## C-Suite Architecture Buildout (2026-04-18)
> CC's vision: Full AI C-Suite — Atlas (CFO) + Bravo (CEO) + Maven (CMO) as personal board of directors.
> Architecture doc: [[brain/C_SUITE_ARCHITECTURE]]

### Phase 1: Architecture ✅ COMPLETE
- [x] Fix stale Atlas reference in AGENTS.md (trading-agent → CFO-Agent)
- [x] Add Maven (CMO) to AGENTS.md + decision matrix
- [x] Create 3-way pulse protocol (ceo_pulse.json + cmo_pulse.json)
- [x] Create C_SUITE_ARCHITECTURE.md

### Phase 2: Maven Identity (IN CMO-Agent/ repo) ✅ COMPLETE
- [x] Rewrite SOUL.md — AdVantage V2.0 → Maven V1.0
- [x] Rewrite CLAUDE.md — multi-client, pulse protocol, CC's brands
- [x] Create GEMINI.md + ANTIGRAVITY.md entry points
- [x] Add pulse read/write logic

### Phase 3: Skill Migration (CC approval required)
- [ ] Copy 10 marketing skills from Bravo → Maven (content-engine, email-marketing, funnel-management, brand-guidelines, growth-engine, competitive-intelligence, elite-video-production, lead-management, linkedin-outreach, persona-content-creator)
- [ ] Move ../CMO-Agent/content-studio/ to Maven
- [ ] Update both agents' CAPABILITIES.md

### Phase 4: Multi-Client Expansion
- [ ] Add OASIS AI, PropFlow, Nostalgic Requests client profiles to Maven
- [ ] Add CC personal brand profile
- [ ] Client routing in Maven's CLAUDE.md

### Phase 5: Integration Testing
- [ ] 3-way pulse read/write verification
- [ ] Spend gate flow end-to-end test
- [ ] Routing test: marketing → Maven, not Bravo

*Last updated: 2026-04-20*

## Sentient Autonomy Buildout (2026-04-20)
> From intelligence audit: 8 critical gaps preventing autonomous agent intelligence.
> Audit artifact: `artifacts/bravo_intelligence_audit.md`

### Phase 1: Action Awareness — **BUILT + REARCHITECTED 2026-04-20**
Decision: extended the existing `lead_interactions` table instead of creating a new `agent_actions` table (three engines already wrote there — adding a second ledger would deepen fragmentation). `scripts/send_gateway.py` replaces the proposed `action_guard.py` and enforces idempotency **architecturally** — callers can't bypass it because the smtplib call lives inside the gateway and nowhere else.

- [x] SQL migration 003 `database/003_unified_interaction_ledger.sql` — adds cooldown_until, agent_source, metadata + 4 indexes to lead_interactions
- [x] `scripts/send_gateway.py` — single outbound chokepoint (CASL + cooldown + daily cap + multi-brand + .ics attachments + 3-way logging)
- [x] `scripts/context_builder.py` — relationship stage + sentiment + prompt composition for persona engine
- [x] `scripts/apply_migration.py` — Management API migration runner
- [x] Rewire outreach_engine → gateway
- [x] Rewire outreach_batch → gateway
- [x] Rewire email_engine (cmd_send + cmd_send_template + cmd_sequence_run) → gateway
- [x] Rewire funnel_nurture → gateway
- [x] Rewire booking_engine (confirmation + reminder, transactional intent) → gateway
- [x] CASL bypass closed in email_engine.cmd_send + funnel_nurture.send_email + booking_engine paths
- [x] 17 tests green (golden, suppression, transactional bypass, cooldown, daily cap, dry-run, validation, SMTP failure, brand, auto-create, stage inference, sentiment, prompt composition)
- [x] Per-channel cooldown config (email 72h, IG 48h, LinkedIn 72h, phone 168h)
- [x] Daily caps (email 50, IG 30, LinkedIn 20, phone 15)
- [x] Multi-brand identity (oasis, kona_makana, nostalgic) — drives CASL footer
- [x] `skills/send-gateway/SKILL.md` — full caller contract
- [x] CAPABILITIES.md + QUICK_REFERENCE.md + ARCHITECTURE.md updated to V5.6
- [ ] **Apply migration 003** — requires CC to rotate SUPABASE_ACCESS_TOKEN (current token expired) OR paste the SQL into Supabase Dashboard SQL editor. Migration is purely additive, safe to apply mid-traffic. Until applied, gateway runs in degraded-compatibility mode (falls back to legacy schema, logs a warning).

### Phase 2: Interaction Intelligence — partially unlocked by Phase 1
- [x] Unified interaction ledger (replaces the proposed interaction_timeline)
- [ ] Wire email inbox check (IMAP) to lead_interactions with type=email_received
- [ ] Build reply classifier (Claude Haiku sentiment/intent) — replaces context_builder's keyword classifier
- [ ] Build persona engine skill files (cold/contacted/warm/engaged/dormant/active_client)
- [ ] Wire persona prompt composer into outreach_batch Claude Haiku draft call

### Phase 3: Autonomous Reasoning — PLANNED
- [ ] Build daemon brain loop (`scripts/autonomous_agent.py tick`) — portable state machine cron + Telegram both invoke
- [ ] Wire Telegram `/tick` command to autonomous reasoning loop
- [ ] Add N8N Supabase-write node to OASIS Inbound Qualifier (closes the fifth-writer blind spot)
- [ ] Build autonomous decision engine ("should I contact this lead?") consuming context_builder output

