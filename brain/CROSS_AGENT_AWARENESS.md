---
tags: [c-suite, protocol, awareness]
---

# CROSS-AGENT AWARENESS — How the 4 Agents Stay in Sync

> The 4-agent operating system (Bravo + Atlas + Maven + Aura) only works if each agent knows what the others are doing. This document defines the awareness protocol.

## The 4 Agents at a Glance

| Agent | Scope | Lives At | Pulse |
|-------|-------|----------|-------|
| **Bravo** (CEO) | Business strategy, clients, revenue | `C:\Users\User\Business-Empire-Agent` | `ceo_pulse.json` |
| **Atlas** (CFO) | Money, tax, runway, research | `C:\Users\User\APPS\CFO-Agent` | `cfo_pulse.json` |
| **Maven** (CMO) | Brand, content, ads, funnels | `C:\Users\User\CMO-Agent` | `cmo_pulse.json` |
| **Aura** (Life) | Apartment, habits, accountability | `C:\Users\User\AURA` | `aura_pulse.json` |

## The Problem

CC talks to one agent at a time. If CC tells Maven about a campaign idea, then 3 hours later asks Bravo "what's my strategy?", Bravo must know Maven just discussed that campaign — otherwise the four agents contradict each other and CC loses trust.

Same with Aura: if CC is in a lean week per Atlas, Aura should know not to recommend ordering takeout. If CC just closed a deal per Bravo, Aura should reflect that in the morning briefing.

## The Solution: Pulse Files Carry a Session Summary

Each agent's pulse file contains a `session_note` field with a 1-2 sentence summary of what happened in the agent's most recent session. Other agents read this first on their own boot.

```json
{
  "agent": "bravo",
  "updated_at": "2026-04-18T06:30:00Z",
  "session_note": "Completed C-Suite reorg. Maven split into CMO-Agent. PULSE booking funnel shipped. Focus: pulse-lead-gen campaign launch pending Atlas spend approval.",
  ...
}
```

## Mandatory Reads on Session Start

Every agent's `CLAUDE.md` already includes a Session Start protocol. The cross-agent part looks like:

```
1. Read MY OWN brain/STATE.md and memory/ACTIVE_TASKS.md
2. Read SIBLING pulse files:
   - The other two agents' data/pulse/*.json
   - Specifically check `session_note` + `updated_at` age
3. If a sibling's pulse is > 24h old, flag it — that agent may need a session
4. Surface anything relevant from sibling pulses in your response to CC
```

## Write Protocol at Session End

Every agent MUST update its OWN pulse with:

| Field | What to write |
|-------|---------------|
| `updated_at` | ISO-8601 timestamp (UTC preferred) |
| `session_note` | 1-3 sentence summary of what happened this session |
| `recent_shipped` | Array of bullet-point deliverables (keep last ~5) |
| `blockers` | Array of things waiting on another agent or on CC |
| Domain-specific fields | Each agent's own schema — see individual pulse files |

## V6.0 Substrate (added 2026-05-10 — Bravo first)

Bravo is the first agent on V6.0. The cross-agent contract is unchanged: pulses still drive sibling awareness, Supabase is still the deep record. V6.0 adds two optional enrichments siblings can pick up when ready:

1. **Bravo's pulse now carries a `v6` block** — `state_db` row counts, `fts5` index size, `hook_modes` (enforce/report/off), and `mode` (off/shadow/on). Sibling agents reading `ceo_pulse.json` can use `pulse.v6.state_db.last_heartbeat` for sub-second liveness instead of the day-precision markdown frontmatter. JSON additive — old siblings ignore the field.

2. **Mandatory reads still hit `memory/SESSION_LOG.md` and `brain/STATE.md`** — same paths as V5.5. In V6.0 those files are auto-generated mirrors of `state/empire_state.db`, so reads return canonical DB data. No code change required on the sibling side.

3. **When you adopt V6.0 in your own repo:** read `brain/CAPABILITIES.md` "V6.0 Architecture" + "V6.0 Phase 2 — Productized Deployment" sections in this Bravo repo. The patterns (single-writer SQLite/WAL, FTS5 retrieval, three guards, scoped env files) port directly. The cross-agent inbox + pulse contract stays identical.

4. **Push-mode coordination (V6 BUILD 3, 2026-05-10):** the Supabase `agent_events` table is now the canonical low-latency broadcast layer. Producers call `scripts/event_bus.publish(event_type, payload, source, target)` — INSERT fires a `pg_notify` trigger; subscribers running `await event_bus.subscribe(agent, handlers={...})` wake on the notification and atomically dequeue via `claim_events()` (uses `FOR UPDATE SKIP LOCKED` — multiple workers of the same agent never claim the same row). Standard event-type registry: `brain/EVENT_BUS_CONTRACT.md`. Bravo emits `BRAVO_SESSION_LOG_APPENDED`, `BRAVO_PULSE_REFRESHED`, `BRAVO_CHAT_INTERACTION` today; siblings can subscribe to any of them. Pulse files remain the canonical "current state" snapshot — the bus broadcasts changes; the file is the authoritative read.

## Shared Supabase as the Deep Record

Pulses are the "what's happening now" layer. Supabase (`phctllmtsogkovoilwos`) is the "what happened over time" layer.

- **Every material action** each agent takes should log to Supabase's `agent_traces` table with `agent`, `action`, `payload`
- When CC asks "what happened in marketing last week," the answering agent queries `agent_traces WHERE agent = 'maven' AND created_at > now() - interval '7 days'`
- This is the only way to know cross-session, cross-agent history

## When CC Talks to Agent A About Agent B's Domain

If CC starts discussing (for example) paid ads with Bravo:
1. Bravo answers the conversational part (general strategy, business fit)
2. Bravo writes a note to its own `ceo_pulse.json` → `directives_to_cmo` field capturing the intent
3. Bravo tells CC: "This is Maven's execution. When you open Maven next, it'll read my directive and know what we discussed."
4. When Maven opens, it reads the directive and acts on it

This is the **pass-the-baton** pattern. No agent ever reaches across and writes to another agent's file — they write to their OWN pulse and count on the other to read it.

## Multi-Resident Privacy (Aura-specific)

Aura serves a household with 2+ residents (CC + Adon currently; possibly more over time). Each resident has private life data. Agents must respect resident boundaries:

- **CC's agents** (Bravo, Atlas, Maven) may read `aura_pulse.json`'s
  `apartment_shared` + `residents.cc.*` sections. The `residents.adon.*`
  section is opaque by default.
- **Adon's agent(s)** (his AIOS stack, when he connects) may read
  `apartment_shared` + `residents.adon.*`. CC's section is opaque to
  them by default.
- Only fields each resident explicitly opts into sharing (listed in
  `aura_pulse.json` under `*_shared_fields`) cross the boundary.
- **Never ask Aura about the other resident's habits, health, mood,
  spending, or schedule.** If a question requires that data, tell CC
  and let CC decide whether to include Adon in the loop.
- Cross-resident data reads are logged to Supabase `agent_traces` for
  transparency.

When Adon's AIOS agent joins the shared Supabase DB, its rows will carry
`resident: 'adon'` alongside `agent: 'adon_<name>'`. CC's agents continue
tagging `resident: 'cc'`. Rows tagged `resident: 'shared'` are readable
by any agent (apartment status, utilities, etc.).

## Conflict Resolution (if two agents hold contradictory state)

Order of precedence:
1. **Atlas on money** — if Atlas says "no budget for that," Maven cannot override
2. **Bravo on strategy** — if Bravo says "that's not our target ICP," Maven reframes
3. **Maven on execution** — Bravo + Atlas defer to Maven on HOW to run an ad campaign once the WHY and the BUDGET are set
4. **Aura on CC's physical/health domain** — business agents can't override Aura's guest mode, roommate-sensitive timing, or sleep protection
5. **CC on everything** — final tiebreaker, always

See `C_SUITE_ARCHITECTURE.md` Decision Rights Matrix for the full map.

## Diagnostic: How to Verify Awareness Is Working

Run the 3-way pulse stress test:
```bash
python scripts/test_csuite_pulse_flow.py
```

A passing run (15/15) proves:
- All 3 pulse files exist at sovereign paths
- Each is cross-readable from any agent's project
- Spend-gate round-trip works (Maven request → Atlas approval → Maven readback)
- Sovereignty enforced (no agent writes to another's pulse)

If any test fails, fix it before starting the next session.

## Related Docs
- `brain/C_SUITE_ARCHITECTURE.md` — governance + decision rights + spend gate
- `../CMO-Agent/brain/SHARED_DB.md` — shared Supabase schema
- Each agent's own pulse at `data/pulse/{ceo,cfo,cmo}_pulse.json`
