---
tags: [handoff, oasis-command-center, overhaul]
date: 2026-05-20
agent: bravo
last_updated: 2026-05-21
freshness_threshold_days: 14
---

# OASIS Command Centre — Complete Overhaul (2026-05-20)

Full-session overhaul triggered by CC's "Goal mode" system message.
All work landed on `oasis-command-center` `main` and Vercel auto-deployed.
Production probed live: every overhauled route returns HTTP 200.

## Commits shipped (9, all on main)

| SHA | Phase | Title |
|---|---|---|
| `cd808a9` | 1.1 | `fix(cmd-center): remove erroneous /playbook → /settings redirect` |
| `ce4468b` | 1.2 | `fix(operations): resolve lead UUIDs to business names in activity tape` |
| `10caa7e` | 1.3 | `fix(health): scope failed-automation list to the last 24 hours` |
| `22587d8` | 3.1 / 1.4 | `feat(oasis): 11-stage lead lifecycle + stage metadata` |
| `2075618` | 3.2 | `feat(oasis): chevron-bar pipeline UI matching Sun Biz pattern` |
| `4f0631e` | 3.3 | `feat(oasis): Pipeline nav group with Leads + Proposals routes` |
| `887622e` | 2.1 | `feat(agents): persistent Active CLI selector on Local AI CLIs card` |
| `66cfc53` | 1.5 / 4.2 | `feat(automations): real feedback on cron toggle clicks` |
| `d847241` | 5.1 | `chore(overrides): plain-English explainer banner` |

## What changed, in operator language

- **Playbook tab works again.** Middleware had a hardcoded `/playbook → /settings` redirect left over from a Phase-2 reshuffle that was never actually completed. Deleted.
- **Operations Activity Tape shows real names.** Email-opened / outbound events now resolve `lead_id=ff7dcd…` to "Bennett Agency" (or whatever the row's `business_name` / `company` / `name` says). Implemented as a server-side batch resolver fired once per page render; falls back to a short UUID prefix on miss.
- **Health page is clean.** The "Atlas Pulse Refresh failed 54m ago" phantom went away because (a) the empire-failed-cron query is now scoped to the last 24h and (b) the underlying `bravo_cli/cron_runner.py` was double-prefixing `scripts/scripts/pulse_publish.py` — patched (see flag below).
- **Bennett Agency lives in the right column.** DB migration mapped `won → active_client` so the Pipeline shows it correctly.
- **OASIS pipeline matches Sun Biz's gold-standard layout.** Horizontal chevron-bar of 11 stages across the top, click a stage to filter the table below, table is now the default view, Kanban is opt-in via `?view=kanban`.
- **New sidebar group "Pipeline".** OASIS sidebar now has Operations / Pipeline / System. Pipeline contains: Pipeline · Leads · Proposals.
- **Proposals route exists.** Clone of the Sun Biz application pattern but adapted for AI-agency proposal lifecycle. Renders `OASIS_SEED.data_model.proposal` via the shared `ManifestTable`.
- **Settings → Local AI CLIs has an Active CLI radio.** Click Claude / Codex / Gemini once; the choice persists (same `oasis.chat.cliRuntime.v1` localStorage key the chat header reads). Disabled options point to their Install/Sign-in button on the card below.
- **Automation toggles feel alive.** Click flips immediately (optimistic), spinner shows while the PATCH is in flight, "Takes effect within ~60 seconds (next bridge poll)" hint appears after a successful flip and fades after 6s, error toast on failure with the actual server message.
- **Overrides page has an explainer card.** Plain-English description of what `exec_guard.py` blocks are and what Approve / Deny actually do.

## Stage migration (OASIS lead lifecycle, 7 → 11)

Old → new mapping, applied directly via supabase-py across three OASIS tenants (only the primary tenant `oasis-ai-cc` had rows):

| Old key | New key | Rows migrated |
|---|---|---|
| `new` | `new_contact` | 27 |
| `contacted` | `outreach` | 41 |
| `won` | `active_client` | 1 (Bennett Agency) |
| `qualified`, `proposal`, `negotiation`, `lost` | unchanged | n/a |

SQL spec preserved at `database/062_oasis_lead_lifecycle_v2.sql` for replay against staging environments.

## Files created / modified

### New files
- `lib/oasis-stage-meta.ts` — 11-stage colour + label metadata, mirrors `lib/sunbiz-stage-meta.ts`
- `app/proposals/page.tsx` — OASIS proposal list (tenant-gated)
- `database/062_oasis_lead_lifecycle_v2.sql` — stage migration spec (Business-Empire-Agent)

### Modified
- `middleware.ts` — drop `/playbook` from REDIRECT_MAP
- `lib/nav-config.ts` — split CC_NAV into Operations / Pipeline / System groups
- `lib/manifest/seeds.ts` — extend OASIS_SEED.data_model.lead.stage enum to 11 values
- `lib/event-projection.ts` — add `RecordResolver` + `buildRecordResolver()`, thread through projectEvent
- `app/operations/page.tsx` — batch-resolve lead IDs before rendering Activity Tape
- `app/health/page.tsx` — 24h staleness filter on empire-failed query
- `app/pipeline/page.tsx` — chevron-bar + filterable table layout, table default
- `app/leads/page.tsx` — tenant-aware stages prop
- `components/leads/LeadsTableClient.tsx` — accepts optional `stages` prop, SunBiz default
- `components/manifest/ManifestKanban.tsx` — accepts optional `where` prop
- `components/manifest/ManifestTable.tsx` — accepts optional `where` prop
- `components/settings/LocalCliProvidersCard.tsx` — Active CLI radio at top
- `components/automations/CronJobsManager.tsx` — toggle UX hardening
- `app/overrides/page.tsx` — operator explainer banner
- `bravo_cli/cron_runner.py` (Business-Empire-Agent) — script-path double-prefix fix

## Outstanding flags for CC

1. **`bravo_cli/cron_runner.py` fix is uncommitted in Business-Empire-Agent.** The fix is on disk and takes effect on next bridge daemon restart. The pre-commit `_bridge_manifest.json` hook blocks commits in this repo right now because there's a large uncommitted reorganization from a prior session (lots of scripts moved into `integrations/`, `core/`, `hooks/`, `state/` subdirs) that the manifest doesn't reflect. Recommended: sort the reorg first, run `python scripts/build_bridge_manifest.py`, then include `bravo_cli/cron_runner.py` in that consolidated commit.

2. **`scripts/integrations/supabase_tool.py` and `scripts/integrations/supabase_admin.py` have an off-by-one env path bug.** Both compute `Path(__file__).resolve().parent.parent / ".env.agents"` which from `scripts/integrations/` resolves to `scripts/.env.agents` (which doesn't exist) instead of the project root. I worked around this with inline `dotenv.load_dotenv(PROJECT_ROOT / ".env.agents")` in the migration scripts, but the shared tools need a one-line fix (`parent.parent.parent`) to work for the next agent that reaches for them.

3. **Phase 2.2 deferred polish.** The Connect / Replace / Disconnect provider-key flow already validates keys at save-time (via `/api/agent-config/bulk-provider`), so the existing UI is functional. An explicit "Test connection" button for already-saved keys (ping the provider, show last-verified timestamp) wasn't shipped — would be a small follow-up adding `app/api/agent-config/test-connection/route.ts` plus a button on each connected provider card.

4. **`memory/SESSION_LOG.md` is malformed.** Multiple stacked `AUTO-GENERATED-BEGIN` markers, no clean closure. `scripts/state/state_manager.py log` itself errors with `ModuleNotFoundError: lib.override_crypto` — same reorg fallout. That's why this handoff is a standalone file instead of an entry inside SESSION_LOG.md.

## Verification snapshot

- `npx tsc --noEmit` → 0 errors after every commit
- `npm run build` → succeeded (final build, before push of `c65cc5a`)
- Production HTTP probes return 200 for every overhauled route (`/playbook`, `/leads`, `/proposals`, `/agents`, `/operations`, `/health`, `/automations`, `/overrides`, `/settings`) — but note that 200 means "the redirect chain to /login resolved cleanly," not "the authenticated page rendered correctly."

**Behavioural verification CC still needs to do** (Playwright MCP couldn't authenticate as your session):

- Open `/pipeline` while signed in — confirm the horizontal chevron bar renders the 11 stages, clicking a stage filters the table below, row click opens the lead detail.
- Open `/leads` — confirm the 11-stage tab strip across the top, search + sort work, page-size pagination works at scale.
- Open `/proposals` — confirm the proposal table renders (will be empty if no proposal rows exist yet; the EmptyState should explain that).
- Open `/agents` → Settings → "Local AI CLIs" — confirm the new Active CLI radio shows at the top with the three options, and selecting one persists across page reload.
- Open `/automations` → flip a toggle — confirm spinner shows during PATCH + "Takes effect within ~60 seconds" hint appears after.
- Open `/overrides` — confirm the new explainer banner reads correctly above the existing list.
- Sun Biz: switch to the SunBiz tenant and open `/leads` / `/applications` / catch-all routes — confirm zero regression (the only shared changes are optional, backward-compatible props on ManifestKanban / ManifestTable / LeadsTableClient).

If any of those surfaces an issue, the dev-server path is `npm run dev` in `oasis-command-center` (auto-loads `.env.local` for service-role bypass), or I can drive Playwright through a manual login if you paste a session cookie.

## Nav structure correction

The nav layout I shipped (in commit `4f0631e`) deviated from the brief by lifting `/pipeline` out of the Operations group into a new Pipeline group. The brief had `/pipeline` staying under Operations. Corrected in commit `c65cc5a` — `/pipeline` is back in Operations, Pipeline group contains only `/leads` + `/proposals`. Final CC_NAV matches the brief's spec exactly.
