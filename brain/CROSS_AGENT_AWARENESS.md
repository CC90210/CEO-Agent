---
tags: [c-suite, protocol, awareness]
---

# CROSS-AGENT AWARENESS — How Agents Stay in Sync With Each Other

> The 3-agent C-Suite only works if each agent knows what the others are doing. This document defines the awareness protocol.

## The Problem

CC talks to one agent at a time. If CC tells Maven about a campaign idea, then 3 hours later asks Bravo "what's my strategy?", Bravo must know Maven just discussed that campaign — otherwise the three agents contradict each other and CC loses trust.

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

## Conflict Resolution (if two agents hold contradictory state)

Order of precedence:
1. **Atlas on money** — if Atlas says "no budget for that," Maven cannot override
2. **Bravo on strategy** — if Bravo says "that's not our target ICP," Maven reframes
3. **Maven on execution** — Bravo + Atlas defer to Maven on HOW to run an ad campaign once the WHY and the BUDGET are set
4. **CC on everything** — final tiebreaker, always

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
