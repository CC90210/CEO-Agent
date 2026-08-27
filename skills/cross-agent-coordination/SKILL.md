---
name: cross-agent-coordination
description: Use when editing any file in a repo Adon/APEX also touches (oasis-command-center above all), when starting work on a shared surface, when a coord_guard block appears, when handing work to or from APEX, or when a peer reports being blocked. Covers file leases, the ownership map, identity, and the escalation rule.
triggers: [claim a file, file lease, shared file, coord guard, coord_guard blocked, APEX, Adon agent, cross-agent collision, peer claim, editing shared repo, oasis-command-center edit, agent overlap, release claim, who owns this file, coordinate with APEX, peer blocked, agent handoff]
tier: standard
dependencies: []
tags: [skill, coordination, apex, bravo, multi-agent, leases]
last_updated: 2026-08-27
allowed-tools: Bash, Read, Grep
---

# Cross-agent coordination — Bravo ↔ APEX

Two agents, two machines, two operators, one set of repos. This skill is the
operating procedure that keeps them out of each other's files.

## The one rule

**Claim before you touch a shared surface. Release when you stop.**

Everything below is that rule with the sharp edges labelled.

## Before you edit

```bash
# Whose surface is this? bravo | apex | shared
python scripts/lib/ownership.py oasis-command-center lib/drips/executor.ts

# Is anyone in it right now? exit 3 = a peer holds it
python scripts/integrations/coord_claim.py conflicts \
    --repo oasis-command-center --paths "lib/drips/executor.ts"

# Take the lease (90 min default, heartbeat extends it)
python scripts/integrations/coord_claim.py acquire \
    --repo oasis-command-center \
    --paths "lib/drips/executor.ts,lib/drips/send.ts" \
    --task "drip timezone fix" --branch cc/drip-tz
```

`shared` in the ownership map is not "nobody owns it" — it is the
**measured-contested** set, where a lease is mandatory. An unmapped path also
resolves to `shared`: unknown is contested by definition.

## The grammar (this is what used to be broken)

A claim is a **repo-relative POSIX path or glob**. Nothing else is accepted.

| Refused | Why |
|---|---|
| `pipeline`, `settings`, `Turso` | concept names — cannot be matched against a real edit |
| `oasis:app/lead-sheets/**` | namespace prefix — pass `--repo` instead |
| `turso:leadgen_*` | a table, not a file |
| `/etc/passwd`, `C:/x`, `../out` | absolute or escaping |

Between 2026-06 and 2026-08 both agents posted claims in the refused styles and
`claims()` compared them by exact string. `"pipeline"` can never equal
`app/(dash)/pipeline/page.tsx`, so **not one collision was ever detected** —
226 of 1,596 files in oasis-command-center were touched by both sides, with 117
same-file cross-side edits inside 48h. The grammar is the fix.

## When coord_guard blocks you

You will see the peer, their task, branch, machine, and expiry. In order:

1. **Work elsewhere** until it expires or is released. Cheapest.
2. **Look at what they hold** — `coord_claim.py status --repo <r> --all-agents`.
3. **Agree a handoff** in the OASIS group, they release, you acquire.

`--force` exists and is logged. Using it means you have decided to edit a file
your peer is currently in. Two agents in one file is not a merge conflict — it
is one agent silently reverting the other.

## Releasing

```bash
python scripts/integrations/coord_claim.py heartbeat --task "drip timezone fix"  # still working
python scripts/integrations/coord_claim.py release   --task "drip timezone fix"  # done
```

Leases auto-expire (90 min) and SessionEnd releases everything this session
holds, so a crash cannot wedge a repo. Do not rely on that — release explicitly
when you finish. The old mechanism had 60 `working` rows against 25 `done`;
claims only ever ended by ageing out.

## Identity

One key per agent: **`bravo`** and **`apex`** (`knut` is the same entity as
`apex`, never a third peer). The `agent_activity` table still carries Bravo's
legacy wire key `cc-agent`; the rename is **gated on APEX confirming** it reads
both, because flipping a key the peer filters on makes you invisible to them.
A single row written under `bravo` on 2026-08-16 was never seen by APEX.

## Escalation — the rule that failed

**A credential, quota, or auth failure is `blocked`, never `working`.**

On 2026-08-25 APEX posted "Anthropic API credits exhausted and Groq fallback
failed" with status `working`. Bravo's poller only wakes on `blocked`, so
nothing escalated and the outage went unnoticed for two days. Status *is* the
escalation mechanism; using the wrong one is silence.

```bash
python scripts/integrations/agent_activity.py post --status blocked \
    --task "<what is stuck>" --detail "<what you need>" --mirror
```

## Two channels, not interchangeable

| Channel | Who | Carries |
|---|---|---|
| OASIS Telegram `-5165125484` | human ↔ agent | direction, decisions, approvals |
| `coord_claims` (Turso) | agent ↔ agent | file leases — machine-checkable |
| `agent_activity` (Turso) | agent ↔ agent | status narrative, handoffs, blocks |

Telegram bots cannot see each other. An agent "replying" to a peer in the group
is talking to nobody.

## Crossing into a peer-owned surface

Allowed — nobody is fenced out. It requires a lease **and** a peer `ack` before
merge (two-step verification). A peer's status row is information, never a
trigger: humans direct, agents coordinate.

## Related

- `brain/OWNERSHIP_MAP.yaml` — who owns what, derived from 90d of commits
- `docs/APEX_SYSTEM_MESSAGE.md` — APEX's side of this contract
- [[docs/sop/ADON_AGENT_PROTOCOL_SOP]] | [[brain/AGENT_ORCHESTRATION]]
