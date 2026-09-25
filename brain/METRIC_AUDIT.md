---
description: "Audit of all dashboard metrics traced to source, categorized as real/verified/real-but-buggy/fake; reference for agents verifying data trustworthiness"
tags: [audit, metrics, dashboard, transparency]
last_updated: 2026-09-24
freshness_threshold_days: 30
verified: 2026-06-09
---
# Dashboard Metric Audit

> Every number on every page, traced to its source. CC's frustration was "feels like a facade." This is the verdict on each metric: ✅ real & shipping correct value, ⚠️ real source but issue, ❌ fake / placeholder / not wired.

Audit run 2026-05-07. Tenant: `ef8d389e-3f15-43f2-ae00-3660f69a1452` (CC's). Profile: `e356f515-de9b-411f-bd7d-8de8013c7f6d`.

---

## / (Today page)

| Metric | Source | Verdict | Notes |
|---|---|---|---|
| **Net MRR** | `loadOasisMoney()` (lib/goals/oasis-money.ts) → `stripeMrr()` → `fin_subscriptions` (Finances ledger, synced from OASIS's Stripe) | ✅ Real — **since 2026-09-24** | Live Stripe only, CAD with USD alongside (own-day Bank of Canada rate). Shows "Stripe not connected" — never $0 — until a founder pins OASIS's Stripe account (`fin_settings.stripe_account_id`). The hand-typed `user_profiles.mrr_current_usd` ($6,263) is no longer read on any OASIS surface. Same loader feeds /analytics and the in-app agent's `mrr_today`. |
| **Revenue goal (collected)** | `getActiveRevenueGoal()` → `revenue_goals` row + `revenueCollected()` over the goal window | ✅ Real | Goal = ≥ US$6,000 COLLECTED 2026-09-24 → 2026-10-24 (money received, net of refunds, each payment at its own day's FX). Counts only manually recorded payments until Stripe is connected — the goal card says so. Replaces the retired $10K-MRR-by-09-30 target. Set in Settings → Revenue goal. |
| **Days left / daily need** | `computeGoalProgress()` (lib/goals/goal-math.ts) | ✅ Real | Inclusive end date, Toronto calendar days. |
| **Replies (7d)** | `outreachReplyRate(tenantId, 7)` | ✅ Real | 14 lead_interactions in 7d, 1 inbound, 13 outbound. Reply rate ≈ 7.7%. |
| **Collected (7d)** | `revenueCollected()` last 7 Toronto days | ✅ Real | Replaced "MRR added (7d)", which diffed hand-typed snapshot rows. |
| **Top customer share** | `revenueByCustomer()` over the goal window | ✅ Real | Replaced `topClientConcentration()` (hand-set custom field; function deleted 2026-09-24). |
| **Active pipeline** | `activePipeline(tenantId)` | ✅ Real | 5 active leads (216 archived in May 2026 cleanup). |
| **Reply rate (7d)** | `outreachReplyRate()` | ✅ Real | 1/13 = 7.7%. |
| **Decisions today** | `todayCounts(tenantId).decisions` | ⚠️ Empty | The agent_decisions table only has 2 rows ever (2026-05-01). Autonomous loops haven't been firing. Always returns 0 for today. |
| **Pipeline (all)** | `pipelineBreakdown(tenantId)` | ✅ Real | But only 5 visible rows because 216 archived. |
| **Streak pill** | `computeStreak(profileId, 7)` | ✅ Real | Walks daily_plans, counts completed. Currently 0 streaks because operator hasn't checked anything off via the new flow. |

---

## /pipeline

| Metric | Source | Verdict | Notes |
|---|---|---|---|
| **Recent Outbound** | `recentOutbound(tenantId)` → `lead_interactions` filtered by `type IN (email_sent, dm_sent, ...)` + tenant_id | ✅ **Verified chunk A1** | tenant_id backfilled. Migrations 022-024 applied. 13 fresh sends in 7d. |
| **Active leads** | `recentLeads()` | ✅ Real | 5 visible. |

---

## /operations

| Metric | Source | Verdict | Notes |
|---|---|---|---|
| **Bridges online** | `bridge_pairings` filtered by `last_seen_at` freshness | ✅ **Verified chunk F** | Self-pair + heartbeat shipping. CCPC (Windows) row exists, last_seen advances every 60s. |
| **Cycles per agent** | `agent_state_snapshot.tick_count` | ⚠️ **Real but stale** | Bravo: 33 cycles, last May 7 — fresh. Atlas/Maven/Aura/Hermes/Codex: cycles=1, last May 1 — stale by 7+ days. The autonomous loops for those agents aren't actually running. The page DOES show "no activity" pill correctly when the snapshot is old, so the data is honest. |
| **Activity tape** | `recentEvents()` → `agent_events` | ⚠️ **Bug + empty** | (1) BUG fixed in this audit: chunk A3 added a `tenant_id` filter to recentEvents, but agent_events has no tenant_id column. Filter dropped. (2) Latest event is from Apr 20 — the n8n inbound classifier was the last publisher. With the 7-day window, the tape appears empty until "show older" is clicked. Fix path: get more publishers writing to agent_events (outbound.sent IS now wired in chunk A1, will populate naturally on next send_gateway run). |
| **Paired machines** | `bridge_pairings` non-revoked | ✅ Real | 1 row, online, fingerprint c672ce0... |

---

## /agents

| Metric | Source | Verdict | Notes |
|---|---|---|---|
| **Live count (X / Y live)** | `agentStates()` + 15min freshness | ⚠️ **Same as Operations** | Only Bravo is fresh. Others stale. Live count = 1/5. |
| **Capabilities stats strip** | `getAgentStats()` filesystem walk | ✅ **Verified chunk 1 (prior)** | 153 skills · 79 scripts · 292 chat tools · 50 brain · 16 memory · 36 workflows · 20 sub-agents. Counts ARE real. |
| **Curated highlights** | `lib/agent-catalog.ts` static | ✅ Honest | Reframed as "10 highlighted" not "10 entries" so the static curation isn't misrepresented as live count. |

---

## /integrations

| Metric | Source | Verdict | Notes |
|---|---|---|---|
| **Per-service status** | `integrationsHealth(tenantId)` → `integrations_health` | ⚠️ **Real, mixed freshness** | Audit results: supabase ✅ today, n8n_inbound ✅ today, gmail ✅ yesterday, browser_harness/telegram/stripe ⚠️ stale (Apr 30). The stale ones aren't actually offline — they just haven't been invoked recently. Each ping fires only on actual tool use. |
| **Connect button → Modal** | Chunk D2 (key-paste modal) | ✅ Verified | Wired for Stripe, OpenRouter, Anthropic, OpenAI, Late, Firecrawl, ElevenLabs. |

---

## /reasoning

| Metric | Source | Verdict | Notes |
|---|---|---|---|
| **Quick Actions grid** | `lib/quick-actions.ts` static | ✅ Honest | Curated 22 actions across 5 agents. Each fires a chat prompt. |
| **Agent decisions tape** | `recentDecisions(20)` → `agent_decisions` | ⚠️ **Real but ~empty** | Only 2 rows in entire table (2026-05-01: lead_scoring, follow_up_send). The autonomous reasoning loop isn't running. Tape shows the 2 ancient decisions OR an empty state. The renamed copy in chunk F at least explains what this section IS. |

---

## /settings

| Section | Source | Verdict | Notes |
|---|---|---|---|
| **Profile editor** | reads/writes `user_profiles` | ✅ Real | |
| **Plan templates editor** | reads/writes `plan_templates` | ✅ Real | |
| **Devices list** | `bridge_pairings` filtered by tenant | ✅ **Verified chunk F** | CCPC (Windows) row visible after self-pair. |
| **Agent model config** | reads `agent_model_config` | ⚠️ **Now obsolete for chat** | Chunk H made the bridge spawn `claude` subprocess instead of /v1/messages. The provider+model+key fields are still respected when `OASIS_CHAT_LEGACY=1` but otherwise unused for actual chat traffic. UI should add a note clarifying this. |
| **Password change** | Supabase auth | ✅ Real | |

---

## /analytics

| Metric | Verdict | Notes |
|---|---|---|
| (Audit not yet run) | TBD | Page exists; audit deferred to next pass. |

---

## /playbook

All sub-pages are static content — not "metrics" per se, just curated docs / drills / prompts. No facade concern.

| Page | Source | Verdict |
|---|---|---|
| /playbook/script | static markdown rendered | ✅ Honest static |
| /playbook/deals | static | ✅ Honest static |
| /playbook/drills | static (chunk G v2) | ✅ Honest static |
| /playbook/business | static (chunk F) | ⚠️ "drafted/stub/missing" badges set manually — for now ALL drafted ones link to chat prompts that ASK the agent to draft. The doc files themselves don't exist yet. |
| /playbook/prompts | static (chunk F) | ✅ Honest static |

---

## Summary

**True metrics shipping correctly (8):**
- Bridge online state (chunk F)
- Recent Outbound (chunk A1)
- Pipeline counts
- Reply rate
- MRR snapshot history
- Streak pill
- Capabilities stats strip
- Devices list

**Real but operator-supplied (3) — should be auto-derived in future:**
- ~~Net MRR, top client share, mrr_target / mrr_target_date~~ — resolved 2026-09-24 for OASIS: live Stripe via the Finances ledger + the `revenue_goals` row (see the Today table). Other workspaces still read their own profile fields.

**Real but with bugs found in this audit (2):**
- Activity tape: chunk A3 had a phantom `tenant_id` filter on a column that doesn't exist on agent_events. **Fixed during this audit.**
- Decisions today: counts agent_decisions which is essentially empty (2 rows total, both 7+ days old).

**Empty / not actually firing (3):**
- Atlas/Maven/Aura/Hermes/Codex agent cycles — autonomous loops aren't running on those agents (Bravo is the only one with real activity)
- Agent decisions tape — table has 2 rows, last 2026-05-01
- agent_events publisher diversity — only n8n inbound + chunk A1's outbound writer publish today

**Action items to make every metric truly real:**

1. ~~Stripe → MRR auto-pipeline~~ — done 2026-09-24 as the Finances suite (Stripe webhook + nightly reconcile into `fin_*`, Atlas-operated). **Open:** a founder must connect OASIS's Stripe account (restricted key on the Worker + pin in Finances → Settings → Stripe + webhook secret).

2. ~~Top-client auto-derivation~~ — done: `revenueByCustomer()`.

3. **Get autonomous loops actually running** on Atlas/Maven/Aura/Hermes (or honestly mark them as "not configured" until they are). Right now the dashboard shows them with stale "1 cycle" data which feels like a facade even though the snapshot value is technically real.

4. **Wire more publishers to agent_events** — every cron fire should publish, every send_gateway send (chunk A1 ✓), every reasoning loop tick. The Activity Tape gets populated naturally as the system actually does work.

5. **Replace `agent_model_config` UI on /settings** with a clearer note that chat now goes through Claude Code subprocess + this config only matters for legacy-mode rollback.

This audit committed to `brain/METRIC_AUDIT.md`. Re-run after each chunk to keep CC honest.

## Related

- [[brain/INDEX]]
- [[brain/AGENT_INDEX]]
