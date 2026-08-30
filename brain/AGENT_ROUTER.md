---
name: AGENT ROUTER
description: Runtime-agnostic routing-by-intent table, loaded after the active entry point for operational requests.
mutability: SEMI-MUTABLE
tags: [brain, router, rag-entry, agent-only]
last_updated: 2026-08-19
freshness_threshold_days: 30
verified: 2026-07-19
---
# AGENT ROUTER — How to Decide What to Read

> Loaded after the active entry point (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`,
> `ANTIGRAVITY.md`, `OPENCODE.md`, or `ZCODE.md`) for operational turns. Everything else is lazy-loaded
> via `read_file` based on what the operator asks for.
> Stay under ~250 lines so it always fits in the boot prompt.

---

## How to use this file (instructions to YOU, the agent)

Every operator turn, do this in order:

1. **Read the message.** Identify intent — one of: build, debug, look up, decide, mutate state, schedule, draft, route to sibling agent.
2. **Match against the tables below.** Each row tells you which file(s) to `read_file(path)` for context, in priority order.
3. **Read only what the intent needs.** Token budget is real. Never bulk-load.
4. **Execute yourself if you have the tool.** Apply migrations, push code, write to Supabase, call APIs. Do NOT tell the operator to run commands. See `brain/EXECUTION_RULES.md`.
5. **Confirm what you did in chat.** State the change, the source, the next-action queued.

---

## Operator-specific facts

The operator's profile (name, brand, manifesto) lives in `brain/USER.md`. Read it when the request needs operator-specific context; casual and self-contained turns do not require it. (MRR / revenue targets are Atlas-owned — Bravo does not track or report them.)

The operator also has a profile row in Supabase `user_profiles` keyed by `auth_user_id`. Use `python scripts/integrations/supabase_tool.py select user_profiles --eq '{"id":"<id>"}'` if you need the live values (primary_agent, agents_enabled).

## Where you run

The runtime may be the guarded `bravo bridge serve` chat server or any of the six direct CLI/IDE entry points above. Bridge-launched script paths are scoped by `under_root()`; direct runtimes follow their own filesystem guardrails.

**Peer agents (the C-Suite + life — the canonical 4):**

- **Atlas** (CFO) at `~/APPS/CFO-Agent`
- **Maven** (CMO) at `~/CMO-Agent`
- **Aura** (life / home) at `~/AURA`

These three are the peer agents per [brain/C_SUITE_ARCHITECTURE.md](C_SUITE_ARCHITECTURE.md). Each owns its own `brain/`, `memory/`, and `data/pulse/<agent>_pulse.json`. You read theirs, never write.

**Client commerce product (NOT a peer):**

- **Hermes** at `~/hermes` — CC's commerce-agent product (Greek god of commerce, fits the family naming). It's a deliverable for clients (e.g. Emmanuel Lowinger), not a sibling C-Suite agent. Treat it like any other app in `brain/APP_REGISTRY.md`: `cd` into the repo before making changes, log the work in `memory/SESSION_LOG.md`. Don't read/write Hermes files when working business ops in this repo.

When the operator switches you in the chat picker, the bridge `cd`s to that repo and the new agent's `CLAUDE.md` becomes your boot file.

---

## Intent → which file to READ

| If the operator asks about... | Read first | Then if needed |
|---|---|---|
| Identity / voice / who you are | (already in your prompt) | `brain/SOUL.md` |
| **Editing a file APEX may also touch** | `skills/cross-agent-coordination/SKILL.md` | `brain/OWNERSHIP_MAP.yaml` |
| **A coord_guard block appeared** | the refusal names the peer, task, branch, machine | `coord_claim.py status --all-agents` |
| **Reviewing APEX's PR / it touches my surface** | `cross_agent_review.py scan` | `cross_agent_review.py review --pr <O/R#N>` |
| **CodeRabbit / Vercel / CI flagged something** | `review_harvest.py --pr <O/R#N>` | `review_fix.py` (applies, tests, pushes) |
| **Taking a migration number** | `check_migration_collision.py reserve <n>` | `database/turso_migrations/` |
| Operator's profile | `brain/USER.md` | — |
| What CLI tools you have | `brain/CAPABILITIES.md` | `brain/QUICK_REFERENCE.md` |
| Which sub-agent owns a task | `brain/WHEN_TO_USE_AGENTS.md` | run `python scripts/capability_query.py resolve "<intent>" --kind agent` |
| Today's plan / current focus | `memory/ACTIVE_TASKS.md` | `brain/STATE.md` |
| Recent context / what just happened | `memory/SESSION_LOG.md` | `memory/DECISIONS.md` |
| Past mistakes to avoid | `memory/MISTAKES.md` | — |
| Validated patterns to reuse | `memory/PATTERNS.md` | — |
| Send a cold/follow-up OUTREACH email (on-demand only — outbound is NOT the default motion) | `skills/outreach-send/SKILL.md` | `brain/QUICK_REFERENCE.md` |
| Inbound lead reply / nurture (the PRIMARY motion: funnel, DMs, social → nurture → book call) | `scripts/integrations/send_gateway.py` (same confirm-gated send steps as INTENTS.md, minus outreach framing) | `brain/QUICK_REFERENCE.md` |
| What's deployed / live | `memory/OPERATIONAL_STATE.md` (7d threshold) | `brain/STATE.md` (stable arch), `brain/CHANGELOG.md` |
| Pricing / offers / deal shape | `brain/DEAL_ARCHITECTURE.md` | `brain/CLIENT_PLAYBOOK.md` |
| OKRs / strategy | `brain/OKRs.md` | `brain/CEO_OPERATING_SYSTEM.md` |
| Risk / what could go wrong | `brain/RISK_REGISTER.md` | — |
| When to use which skill | `brain/WHEN_TO_USE_SKILLS.md` | `skills/<name>/SKILL.md` |
| **Resolve a skill by intent (live, preferred)** | run `python scripts/capability_query.py resolve "<intent>"` — semantic router over `brain/CAPABILITY_GRAPH.json`; gws-* CLI-refs are excluded so real skills win | `brain/WHEN_TO_USE_SKILLS.md` |
| Specific intent verb | `brain/INTENTS.md` | — |
| What you may write / mutate | `brain/EXECUTION_RULES.md` | — |
| App-specific work (PropFlow, OASIS, etc.) | `brain/APP_REGISTRY.md` | `APPS_CONTEXT/<app>_CLAUDE.md` |
| Code review / pre-ship | `skills/code-review/SKILL.md` | `skills/ship/SKILL.md` |
| Debugging | `skills/systematic-debugging/SKILL.md` | `memory/MISTAKES.md` |
| Cron / background workers | `skills/background-workers/SKILL.md` | `oasis-command-center:vercel.json` |
| Dashboard structure | `oasis-command-center:lib/agent-roots.ts` | the relevant `oasis-command-center:app/<route>/page.tsx` |
| **Audit the system / health check** | (run `python scripts/core/self_audit.py`) | `brain/ORCHESTRATION.md` |
| **Clean up the repo / delete junk** | (run `python scripts/core/system_cleanup.py` — dry-run by default) | `brain/EXECUTION_RULES.md` Rule 9 |
| **How long is X kept / adding a new store or log** | `brain/DATA_LIFECYCLE.md` | (schedule the sweep in the SAME commit — a retention tool nobody runs is not a policy) |
| **What automations run / is X scheduled / why did Y fire** | [[AUTOMATIONS]] — every job, daemon, hook and OS task with what it does and whether it is healthy | (regenerate with `python scripts/core/generate_automations.py`; it is auto-generated, never hand-edit) |
| **Current date / day-of-week / time** | (run the date snippet in `brain/EXECUTION_RULES.md` Rule 11 — never quote from prompt) | `brain/STATE.md` |
| **Create a new skill / agent / workflow** | `skills/agent-forge/SKILL.md` | use the matching `python scripts/register.py skill|agent|workflow ...` contract |
| **Diagnose why you made a mistake** | `memory/MISTAKES.md` | `brain/BRAIN_LOOP.md` (Reflexion section) |
| **Check whether memories are stale** | (run `python scripts/core/memory_aging.py stale --days 7 --json`) | `brain/EXECUTION_RULES.md` Rule 11 |
| **Update memory** | `brain/EXECUTION_RULES.md` Rule 0 | (write to `memory/<file>.md`, then `python scripts/state/state_sync.py --note "<summary>"`) |

---

## Intent → which TOOL to call (when you should act, not just read)

**In dashboard chat (bridge mode), you have a `run_script` tool.** Its generated manifest comes from static `CAPABILITY_META` declarations. Mutating entries require `confirm: true` and same-turn operator intent. Unreviewed legacy entries fail closed as confirmation-required; hidden/off-list scripts are not bridge-callable.

| Operator wants... | run_script key (or how to act) | Consult first |
|---|---|---|
| Get current MRR | ATLAS-OWNED — do not self-serve; defer to Atlas (read Atlas cfo_pulse/STATE.md READ-ONLY if CC insists) | `brain/C_SUITE_ARCHITECTURE.md` |
| CEO daily briefing | `ceo_dashboard` (legacy fail-closed; currently needs `confirm: true`) | — |
| Read a Supabase table | `supabase_select` (args: table, --eq, --limit) | `brain/CAPABILITIES.md` |
| Write to Database (legacy-ok Supabase) | `supabase_insert` / `supabase_update` (mutating; needs `confirm: true`) | `brain/CAPABILITIES.md` |
| List leads | `lead_engine_list` (args: --status, --limit; legacy fail-closed confirmation) | `brain/STATE.md` |
| Score a lead | `lead_engine_score` (positional lead UUID; legacy fail-closed confirmation) | — |
| Add a lead | `lead_engine_add` (mutating; needs `confirm: true`) | `skills/outreach-send/SKILL.md` |
| Pre-flight a send | `send_gateway_can_act` (args: --lead-id, --channel) | `skills/outreach-send/SKILL.md` |
| Send an email | `send_gateway_send` (mutating; needs `confirm: true`; passes 8 safety gates) | `skills/outreach-send/SKILL.md` |
| Send-gateway records / health | `send_gateway_history`, `send_gateway_stats`, or `send_gateway_doctor` | — |
| **Fetch/search a URL (DEFAULT — auto-escalates Firecrawl→Cloak + records domain reputation)** | `research_fetch_fetch` (positional URL, optional `--json`; currently confirmation-gated because it writes local reputation state) | `skills/research-fetch/SKILL.md` |
| Inspect or clear fetch reputation | `research_fetch_reputation` / `research_fetch_reputation_clear` (currently confirmation-gated pending metadata review) | `skills/research-fetch/SKILL.md` |
| Scrape a bot-protected page directly | `cloak_browser_scrape` (read-only unless `--screenshot`, which requires confirmation); `cloak_browser_check_stealth`; `cloak_browser_download` (confirmation) | `skills/cloak-browser/SKILL.md` |
| Read sibling-agent inbox | `agent_inbox_inbox` (args: --to bravo|atlas|maven|aura|hermes) | — |
| Post to / acknowledge sibling-agent inbox | `agent_inbox_send` / `agent_inbox_ack` (mutating; need `confirm: true`) | `brain/AGENTS.md` |
| Update operator dashboard data | emit `<dashboard-action type="…">{…}</dashboard-action>` marker (separate path; not run_script) | `oasis-command-center:lib/agent-actions.ts` |
| Apply a SQL migration | (off run_script allowlist; surface `python scripts/apply_migration.py <path>` for operator approval) | `database/` for next migration number |
| Push to Vercel | (off allowlist; `git push` auto-deploys; verify with `npx vercel ls`) | — |
| Set a Vercel env var | (off allowlist; surface `npx vercel env add NAME production`) | `oasis-command-center:ENV_SETUP.md` |

To expose or change a script, add or update its literal `CAPABILITY_META`, then regenerate with `python scripts/build_bridge_manifest.py`. Per-subcommand visibility, fixed arguments, denied arguments, and confirmation policy belong in that contract; do not hand-edit the generated manifest.

---

## Sibling-agent delegation (when work is in their lane)

| Agent | Repo | Hand off when |
|---|---|---|
| **Atlas** (CFO) | `~/APPS/CFO-Agent` | Capital, tax, trades, FIRE, cash-flow, broker reconcile |
| **Maven** (CMO) | `~/CMO-Agent` | Content production, paid ads, brand voice, funnels, video pipeline |
| **Aura** (life) | `~/AURA` | Smart home, habits, sleep, voice, daily routines |

When the operator switches agents in the chat picker, the bridge `cd`s to that repo and the new agent's `CLAUDE.md` becomes the entry. You don't reach into their files — they reach into theirs.

**Hermes is not a sibling.** It's CC's commerce-agent product (a deliverable for clients like Emmanuel Lowinger). Treat it like any other entry in `brain/APP_REGISTRY.md`: `cd` into `~/hermes` to make changes, log in `memory/SESSION_LOG.md`. Don't delegate business-ops work to Hermes.

---

## How to keep this router fresh

When a new high-traffic file or capability lands and the agent reaches for it repeatedly:

1. Add a row to the right table.
2. Keep descriptions to one line. Bodies live in their own files.
3. Bump `last_updated:`.
4. Remove obsolete rows.

If the table grows past ~250 lines, split intents into `brain/INTENTS.md` and keep this as the highest-frequency entries only.
