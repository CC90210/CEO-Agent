---
adr: 0001
title: Skill dependency classification — hard vs soft
status: accepted
date: 2026-05-16
deciders: [bravo, cc]
supersedes: null
superseded_by: null
---

# ADR-0001 — Skill dependency classification: hard vs soft

## Context

We have 150+ skills under `skills/<name>/SKILL.md`. Several depend on infrastructure that may not be present in every session:

- `EMPIRE_V6_MODE=on` (state DB authoritative)
- Specific `.env.agents` keys (Stripe, Supabase, Late/Zernio, ElevenLabs, ...)
- Running PM2 daemons (`event-router`, `override-consumer`, Telegram bridge)
- Initialized state DB (`state/empire_state.db` exists + has tables)
- Browser Harness session (`~/.browser_harness/edge_profile/`)

Today, none of our skills declare these dependencies. When a session is launched in a degraded environment, skills fail silently with cryptic errors (no Stripe key → `KeyError: 'STRIPE_SECRET_KEY'`; daemon not running → events queued to `tmp/events_offline.jsonl` and nobody notices for a week).

Pattern observed at [mattpocock/skills ADR-0001](https://github.com/mattpocock/skills/blob/main/docs/adr/0001-explicit-setup-pointer-only-for-hard-dependencies.md): classify skills as **hard-dependency** (must check prerequisite, must point user at setup) vs **soft-dependency** (degrade gracefully, do NOT add explicit pointer to avoid noise).

## Decision

Every skill is classified as **hard** or **soft** with respect to each of its runtime dependencies.

### Hard-dependency skills

A skill is hard-dependency on resource R if it **cannot produce a useful result without R** (it will fail, return garbage, or skip its core action).

Hard-dependency skills MUST:

1. Declare the dependency in frontmatter:
   ```yaml
   requires:
     env: [STRIPE_SECRET_KEY]
     daemons: [override-consumer]
     state: [empire_state.db]
   ```
2. Check the prerequisite in the body, before any work:
   > **Prerequisite:** This skill requires `STRIPE_SECRET_KEY` in `.env.agents`. If missing, run `scripts/audit_mcp_secrets.py` and add the key before invoking.
3. Fail loudly on missing dependency (raise with a setup pointer, not silently no-op).

### Soft-dependency skills

A skill is soft-dependency on resource R if it **has a fallback path** when R is absent (degrade to local-only mode, skip the optional enrichment, etc.).

Soft-dependency skills MUST NOT include the explicit prerequisite pointer in the body — that adds noise to skills that already handle the absence gracefully. They MAY mention the optional enrichment in a "How it works" section, but the skill must remain functional without it.

### Examples

| Skill | Resource | Classification | Behavior |
|-------|----------|----------------|----------|
| `outreach-send` | `STRIPE_SECRET_KEY` | soft | Sends email without payment-link; logs warning |
| `outreach-send` | `send_gateway.py` running | hard | Blocks if gateway unreachable; raises with setup pointer |
| `memory-retriever` | LanceDB index built | soft | Falls back to FTS5-only mode (`--lexical-only`) |
| `state-sync` | `empire_state.db` exists | hard | Aborts with `state_manager.py init` pointer |
| `pulse-publish` | Telegram bot online | hard | Queues to retry; doesn't pretend it sent |
| `morning-brief` | LanceDB index built | soft | Uses FTS5 snippets only; result is shorter but valid |
| `hyperthink` | None | n/a | Pure-reasoning skill, no resource deps |

## Consequences

**Positive:**
- Skill failures become diagnostic in <60 seconds (the skill itself points at setup).
- New environment onboarding (CC's other machines, client harnesses) gets a deterministic prerequisite checklist.
- Reduces "why did this skill silently no-op?" debugging.

**Negative:**
- One-time audit of 150 skills against their dependencies. ~30 min via grep for `os.environ`, `.env.agents`, daemon names. Tracked as task in `memory/ACTIVE_TASKS.md`.
- Frontmatter `requires:` adds a new field to the capability graph schema. `scripts/build_capability_graph.py` must surface it in the entry shape.

**Neutral:**
- Skills with NO external dependencies (`hyperthink`, `retro`, `writing-plans`) need no annotation.

## Enforcement

Today (initial accept, 2026-05-16):
- This ADR is referenced from [CONTEXT.md](../../CONTEXT.md) and [skills/skill-creator/SKILL.md](../../skills/skill-creator/SKILL.md). New skills are expected to declare dependencies at draft time.
- Audit of the existing ~150 skills against their dependencies is tracked as a follow-up item in [memory/ACTIVE_TASKS.md](../../memory/ACTIVE_TASKS.md); not done in this PR.

Proposed future tooling (not implemented in this ADR, will be added in a follow-up):
- `scripts/capability_query.py check-deps <skill_id>` — verifies declared `requires:` against current environment. Returns 0 if all present, 1 with a setup pointer otherwise.
- `scripts/register.py skill` — prompt for hard/soft classification per declared dependency at scaffold time.
- `brain/CAPABILITY_GRAPH.json` — surface `requires:` field on each skill node so the runtime resolver can warn before activation.

The ADR is accepted on its rule (classify hard vs soft, declare in frontmatter, body pointer only for hard). The tooling is the natural next step but not blocking this acceptance.

## References

- Source pattern: https://github.com/mattpocock/skills/blob/main/docs/adr/0001-explicit-setup-pointer-only-for-hard-dependencies.md
- Related: [ADR-0002 — CONTEXT.md canonical vocabulary](0002-context-md-canonical-vocabulary.md)
- Capability graph schema: [scripts/build_capability_graph.py](../../scripts/build_capability_graph.py)
