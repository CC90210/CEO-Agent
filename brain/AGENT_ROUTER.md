---
name: AGENT ROUTER
description: The chat agent's routing-by-intent table. Loaded after CLAUDE.md as the second-stage boot file. Tells the agent which deeper file to read for each kind of operator request.
mutability: SEMI-MUTABLE
tags: [brain, router, rag-entry, agent-only]
last_updated: 2026-05-06
---

# AGENT ROUTER — How to Decide What to Read

> Loaded by the chat agent after `CLAUDE.md`. Everything else is lazy-loaded
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

The operator's profile (name, brand, north-star MRR target, manifesto) lives in `brain/USER.md`. **Read it once on the first operator turn** of a session — it's small and high-value. After that, trust your prompt unless the operator says something changed.

The operator also has a profile row in Supabase `user_profiles` keyed by `auth_user_id`. Use `python scripts/integrations/supabase_tool.py select user_profiles --eq '{"id":"<id>"}'` if you need the live values (mrr_current_usd, mrr_target_usd, primary_agent, agents_enabled).

## Where you run

On the operator's machine via `bravo bridge serve`. You have full read access to this repo's tree, scoped by `under_root()` to prevent path traversal.

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
| Operator's profile | `brain/USER.md` | — |
| What CLI tools you have | `brain/CAPABILITIES.md` | `brain/QUICK_REFERENCE.md` |
| Which sub-agent owns a task | `brain/AGENTS.md` | `brain/AGENT_ORCHESTRATION.md` |
| Today's plan / current focus | `memory/ACTIVE_TASKS.md` | `brain/STATE.md` |
| Recent context / what just happened | `memory/SESSION_LOG.md` | `memory/DECISIONS.md` |
| Past mistakes to avoid | `memory/MISTAKES.md` | — |
| Validated patterns to reuse | `memory/PATTERNS.md` | — |
| Send an email or DM | `skills/outreach-send/SKILL.md` | `brain/QUICK_REFERENCE.md` |
| What's deployed / live | `memory/OPERATIONAL_STATE.md` (7d threshold) | `brain/STATE.md` (stable arch), `brain/CHANGELOG.md` |
| Pricing / offers / deal shape | `brain/DEAL_ARCHITECTURE.md` | `brain/CLIENT_PLAYBOOK.md` |
| OKRs / strategy | `brain/OKRs.md` | `brain/CEO_OPERATING_SYSTEM.md` |
| Risk / what could go wrong | `brain/RISK_REGISTER.md` | — |
| When to use which skill | `brain/WHEN_TO_USE_SKILLS.md` | `skills/<name>/SKILL.md` |
| Specific intent verb | `brain/INTENTS.md` | — |
| What you may write / mutate | `brain/EXECUTION_RULES.md` | — |
| App-specific work (PropFlow, OASIS, etc.) | `brain/APP_REGISTRY.md` | `APPS_CONTEXT/<app>_CLAUDE.md` |
| Code review / pre-ship | `skills/code-review/SKILL.md` | `skills/ship/SKILL.md` |
| Debugging | `skills/systematic-debugging/SKILL.md` | `memory/MISTAKES.md` |
| Cron / background workers | `skills/background-workers/SKILL.md` | `oasis-command-center:vercel.json` |
| Dashboard structure | `oasis-command-center:lib/agent-roots.ts` | the relevant `oasis-command-center:app/<route>/page.tsx` |
| **Audit the system / health check** | (run `python scripts/core/self_audit.py`) | `brain/ORCHESTRATION.md` |
| **Clean up the repo / delete junk** | (run `python scripts/core/system_cleanup.py` — dry-run by default) | `brain/EXECUTION_RULES.md` Rule 9 |
| **Current date / day-of-week / time** | (run the date snippet in `brain/EXECUTION_RULES.md` Rule 11 — never quote from prompt) | `brain/STATE.md` |
| **Create a new skill / agent / workflow** | `skills/agent-forge/SKILL.md` | `skills/<name>/SKILL.md` after `python scripts/register_skill.py create` |
| **Diagnose why you made a mistake** | `memory/MISTAKES.md` | `brain/BRAIN_LOOP.md` (Reflexion section) |
| **Check whether memories are stale** | (run `python scripts/core/memory_aging.py stale --days 7 --json`) | `brain/EXECUTION_RULES.md` Rule 11 |
| **Update memory** | `brain/EXECUTION_RULES.md` Rule 0 | (write to `memory/<file>.md`, then `python scripts/state/state_sync.py --note "<summary>"`) |

---

## Intent → which TOOL to call (when you should act, not just read)

**In the dashboard chat (bridge mode), you have a `run_script` tool.** Allowlisted scripts execute with their stdout returned to you. Mutating scripts require `confirm: true` AND the operator must have asked for the action in the same turn. Off-list scripts fall back to surfacing the command for the operator to run.

| Operator wants... | run_script key (or how to act) | Consult first |
|---|---|---|
| Get current MRR | `revenue_engine_mrr` | `brain/STATE.md` |
| CEO daily briefing | `ceo_dashboard` | — |
| Read a Supabase table | `supabase_select` (args: table, --eq, --limit) | `brain/CAPABILITIES.md` |
| Write to Supabase | `supabase_insert` / `supabase_update` (mutating; needs `confirm: true`) | `brain/CAPABILITIES.md` |
| List leads | `lead_engine_list` (args: --status, --limit) | `brain/STATE.md` |
| Score a lead | `lead_engine_score` (args: --lead-id) | — |
| Add a lead | `lead_engine_add` (mutating; needs `confirm: true`) | `skills/outreach-send/SKILL.md` |
| Pre-flight a send | `send_gateway_can_act` (args: --lead-id, --channel) | `skills/outreach-send/SKILL.md` |
| Send an email | `send_gateway_send` (mutating; needs `confirm: true`; passes 8 safety gates) | `skills/outreach-send/SKILL.md` |
| Send-gateway state | `send_gateway_status` | — |
| Search the web | `firecrawl_search` (args: "query") | — |
| **Fetch a URL (DEFAULT — auto-escalates Firecrawl→Cloak + remembers per-domain)** | `research_fetch_fetch` (args: "url" "--json") · also: `research_fetch_reputation`, `research_fetch_reputation_clear` | `skills/research-fetch/SKILL.md` |
| Scrape a public unprotected page (when you want Firecrawl-specific features like extract/map/crawl) | `firecrawl_scrape` (args: "url") | — |
| Scrape a bot-protected page directly (interactive goto/screenshot or force-tier) | `cloak_browser_tool_scrape` (args: "url" "--json") · also: `cloak_browser_tool_check_stealth`, `cloak_browser_tool_goto` | `skills/cloak-browser/SKILL.md` |
| Read sibling-agent inbox | `agent_inbox_list` (args: --to bravo|atlas|maven|aura|hermes) | — |
| Post to sibling agent | `agent_inbox_post` (mutating; needs `confirm: true`) | `brain/AGENTS.md` |
| Update operator dashboard data | emit `<dashboard-action type="…">{…}</dashboard-action>` marker (separate path; not run_script) | `oasis-command-center:lib/agent-actions.ts` |
| Apply a SQL migration | (off run_script allowlist; surface `python scripts/apply_migration.py <path>` for operator approval) | `database/` for next migration number |
| Push to Vercel | (off allowlist; `git push` auto-deploys; verify with `npx vercel ls`) | — |
| Set a Vercel env var | (off allowlist; surface `npx vercel env add NAME production`) | `oasis-command-center:ENV_SETUP.md` |

To add a new script to the allowlist: edit `SCRIPT_ALLOWLIST` in `bravo_cli/bridge_chat_server.py`. Format: friendly key → `{path, subcmd, mutating, help}`. Run-only scripts run freely; mutating require `confirm: true` from the operator.

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
