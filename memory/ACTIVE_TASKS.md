---
tags: [tasks, active]
---
# ACTIVE TASKS
> [[brain/DASHBOARD]] | [[brain/STATE]] | [[memory/SESSION_LOG]]

## Target: $5,000 USD Net MRR by May 15, 2026
- **Current:** ~$2,982 USD/mo | **Gap:** ~$2,018 USD/mo (~4-5 new clients)
- **Risk:** 94% revenue from primary retainer — diversification is #1 priority

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
- [ ] Ship 1 Kona Makana long-form video end-to-end through Remotion pipeline (CC records, Bravo edits via `content_pipeline.py`)
- [ ] Daily content cascade: 1 long-form → 5 cross-posts (X, LinkedIn, IG, TikTok, Threads) via `content_engine` skill repurposing workflow
- [ ] Import 47 stale leads to CRM — `python scripts/lead_engine.py bulk-import`
- [ ] Semi-auto outreach loop live: 20 cold emails/day minimum, `outreach_batch.py` → Telegram approve → send
- [ ] Study `skills/sales-methodology` (NEPQ) + `skills/sales-closing` nightly — 30 min/day
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
- [x] Sync `ANTIGRAVITY.md` with `CLAUDE.md` (MCP 4→8, skills 55→150, agents 16→17, workflows 15→34, Hyperthink/Codex/Self-improvement rules)
- [x] **Skool Engine V2.1** — comment-tier engagement + coach-attention escalation. Bravo now replies to comments on posts (not just post bodies), tone-adjusts when CC already top-level commented (brief + complementary, ≤180 chars), and Telegram-escalates posts/comments that need CC's personal voice (crisis, hot leads, @-mentions, direct coaching asks). 38 escalation keywords, 9/9 unit tests pass. Graceful degradation on Skool DOM drift. Daemon PID 2196 picks up changes on next restart.
- [ ] CC: restart skool daemon to activate V2.1 — `taskkill //PID 2196 //F && python scripts/skool_engine.py daemon --interval 5 &` (or via PM2 restart). NO auto-restart by Bravo — requires CC authorization.
- [ ] CC: install eJPT study materials (see ethical-hacking skill, $200)
- [ ] CC: first TryHackMe session (30 min) this week
- [ ] Bravo: after 3 real deals, update sales-closing with observed objections

*Last updated: 2026-04-11*
