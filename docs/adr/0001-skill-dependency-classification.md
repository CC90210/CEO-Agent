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

We have 148 active skills under `skills/<name>/SKILL.md`. Several depend on infrastructure that may not be present in every session:

- `EMPIRE_V6_MODE=on` (state DB authoritative)
- Specific `.env.agents` keys (Stripe, Supabase, Late/Zernio, ElevenLabs, ...)
- Running PM2 daemons (`event-router`, `sequence-runner`, Telegram bridge)
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
     daemons: [event-router]
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

**Implemented in V6.8.1 (commit bec2fcc, 2026-05-16):**
- `scripts/capability_query.py check-deps <node_id>` — verifies declared `requires:` against current environment. Returns ok/missing/pointer report. Exit code 0 if all present, 1 otherwise. Checks: env vars via `os.environ`; PM2 daemons via `state/<name>.pid` mtime freshness (≤120s); state files via existence check.
- `scripts/register.py skill` — accepts `--requires-env`, `--requires-daemon`, `--requires-state` (CSV-each) and emits a `requires: [env:X, daemon:Y, state:Z]` line in the scaffolded frontmatter.
- `scripts/build_capability_graph.py` — surfaces `requires:` field on every skill node via `_parse_requires()` (lines 167-198). Result available in `CAPABILITY_GRAPH.json` for every skill.
- This ADR is referenced from [CONTEXT.md](../../CONTEXT.md) and [skills/skill-creator/SKILL.md](../../skills/skill-creator/SKILL.md). New skills declare dependencies at draft time via the wizard.

**Not yet done (follow-up):**
- Audit of the existing ~150 skills against their runtime dependencies. Most skills do not yet declare a `requires:` field. Tracked in [memory/ACTIVE_TASKS.md](../../memory/ACTIVE_TASKS.md). The dependency-classification rule applies to ALL skills, but the audit is incremental.
- Activation-time enforcement (resolver auto-runs `check-deps` before returning a skill in `resolve_intent`). Currently `check-deps` is opt-in via CLI; the resolver does not yet gate on it.

## References

- Source pattern: https://github.com/mattpocock/skills/blob/main/docs/adr/0001-explicit-setup-pointer-only-for-hard-dependencies.md
- Related: [ADR-0002 — CONTEXT.md canonical vocabulary](0002-context-md-canonical-vocabulary.md)
- Capability graph schema: [scripts/build_capability_graph.py](../../scripts/build_capability_graph.py)
