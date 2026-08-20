# OASIS Command Center — Alignment Audit & Consolidation

## OBJECTIVE

Eliminate redundancy across the Command Center's Playbook, Prompts Library, Reasoning, and Operations surfaces — consolidate to a clean, methodical operator dashboard where every page earns its existence, every prompt is modern and deep, every metric is real, and content updates propagate from a single source of truth.

## CONTEXT

- **Repo:** `C:\Users\User\APPS\oasis-command-center` → GitHub `CC90210/oasis-command-center` → Vercel `oasisai.work`
- **Branch:** `main` (Vercel auto-deploys on push)
- **Stack:** Next.js 15.5, React 19, TypeScript, Tailwind, Supabase SSR
- **Canonical vocabulary:** "Playbook" = the `/playbook` index page with numbered cards + operating manual section. "Prompts Library" = `/playbook/prompts`, sourced from `lib/prompts-library.ts`. "Reasoning" = `/reasoning`, the page being deleted. "Quick Actions" = `lib/quick-actions.ts`, the click-to-chat grid currently on Reasoning. "Operations" = `/operations`, the live ops dashboard. "Automations" = `/automations`, the cron management surface. "Operating manual" = the bottom section of `/playbook` that renders markdown from `content/playbooks/*.md`.
- **Sibling agent repo (brain/memory/skills — NOT code):** `C:\Users\User\Business-Empire-Agent`
- **Key files already verified:**

| File | What it contains | Lines |
|------|-----------------|-------|
| `app/playbook/page.tsx` | 8 hardcoded `SECTIONS[]` cards + operating manual renderer | 316 |
| `lib/prompts-library.ts` | 41 prompts across 9 categories, `PROMPTS_LIBRARY[]` array | 771 |
| `lib/quick-actions.ts` | 33 quick actions across 7 agents, `QUICK_ACTIONS[]` array | 214 |
| `app/reasoning/page.tsx` | Quick Actions grid + Agent Decisions tape | 107 |
| `app/operations/page.tsx` | Error counter queries `agent_events` WHERE severity IN ('error','warn') | 497 |
| `app/playbook/prompts/page.tsx` | Prompts Library page, imports from `lib/prompts-library.ts` | 92 |
| `components/Sidebar.tsx` | Sidebar nav including Reasoning link | — |
| `content/playbooks/` | 9 `.md` files powering the operating manual section | — |
| `lib/playbooks.ts` | `listPlaybooks()` reads `content/playbooks/*.md` | 108 |

## CONTRACTS

### Track 1: Playbook Consolidation (8 → 5 cards)

**[VERIFIED: source read of `app/playbook/page.tsx` lines 23-80]** The `SECTIONS[]` array has 8 entries. CC's decision:

| # | Card | Action |
|---|------|--------|
| 01 | Deal Architecture | **KEEP** |
| 02 | Daily Drills | **DELETE** — redundant with prompts inside the library |
| 03 | Business Documentation | **KEEP** |
| 04 | Prompts Library | **KEEP** — navigation link to the sub-page |
| 05 | Client Deployment Runbook | **DELETE** — client deployment artifact, not daily ops |
| 06 | Operator Onboarding (V6.0) | **DELETE** — out of date, not useful for CC's current operations |
| 07 | Security Model | **KEEP** |
| 08 | 10 The OASIS Loop | **KEEP** — refine subtitle/body to match current state |

**Mutation:** Remove entries at indices 1, 4, 5 from the `SECTIONS[]` array in `app/playbook/page.tsx`. Renumber the remaining 5 cards (01–05). Do NOT delete the routes (`/playbook/drills`, `/playbook/client-deploy`, `/playbook/onboarding`) — leave them accessible by direct URL but remove them from the index. This preserves any external links or bookmarks.

**Operating manual section cleanup:** Delete any `content/playbooks/*.md` file that renders a "Vibe Translator" card in the operating manual. The Vibe Translator belongs EXCLUSIVELY in the Prompts Library (`lib/prompts-library.ts`). If a `vibe-translator.md` or similar file exists on the deployed version but not locally, check the git log for it and ensure it is removed. The operating manual should contain only genuinely distinct runbooks — NOT duplicates of prompts.

**Surviving operating manual files:** After SunBiz filtering, the remaining non-SunBiz files should be:
- `07-new-client-onboarding.md` → keep (canonical client onboarding runbook)
- `10-oasis-loop.md` → **evaluate**: if the OASIS Loop content is already covered by playbook card 08, delete this file to avoid duplication. If it contains deeper detail the card summary doesn't cover, keep it.
- Any other non-SunBiz file → evaluate for redundancy. If it duplicates a playbook card or a prompt, delete it.

### Track 2: Reasoning Tab — Complete Deletion

**[VERIFIED: CC Clarification]** "Completely remove the reasoning tab."

**Files to delete:**
- `app/reasoning/page.tsx` — the page itself
- `components/reasoning/QuickActionsGrid.tsx` — the Quick Actions grid component (verify no other consumer before deleting — check `components/manifest/ManifestReasoning.tsx` which also imports it)
- `components/manifest/ManifestReasoning.tsx` — the manifest-aware reasoning surface for `/t/<slug>/reasoning`

**Files to modify:**
- `components/Sidebar.tsx` — remove the "Reasoning" nav entry from the sidebar. Find the nav item with `href="/reasoning"` and delete it.
- `app/layout.tsx` — if it references `/reasoning` in any route list (public routes, etc.), remove it.
- `middleware.ts` — if it has routing logic for `/reasoning`, remove those branches.
- `lib/quick-actions.ts` — **DO NOT DELETE** yet. The Quick Actions data is still useful. See Track 2b.

**Track 2b: Quick Actions → Prompts Library merge.** The 33 Quick Actions in `lib/quick-actions.ts` should be evaluated against the 41 prompts in `lib/prompts-library.ts`. For every Quick Action that has no equivalent in the Prompts Library, create a new prompt entry. For every Quick Action that duplicates an existing prompt, discard it. After the merge, `lib/quick-actions.ts` may still be imported by the Prompts Library page if we want a "Quick Actions" click-to-chat grid there. **Alternatively**, if the Prompts Library already has an "Open in chat" button per prompt, the Quick Actions grid is redundant — delete `lib/quick-actions.ts` entirely.

**Decision rule:** If the Prompts Library page (`app/playbook/prompts/page.tsx`) already supports "Open in chat →" per prompt (check the `PromptsLibraryFilter` component), then the Quick Actions grid adds zero value — delete `lib/quick-actions.ts`. If it doesn't, port the click-to-chat UX into the Prompts Library cards as the "Open in chat" action.

**Agent Decisions tape:** The Agent Decisions section of the Reasoning page (`recentDecisions()` query) is unique data — autonomous loop decisions with confidence scores. This data currently has no other home. **Move it to the Operations page** (`app/operations/page.tsx`) as a new card section after the Activity Tape, titled "Agent decisions" with the same subtitle. This preserves the data surface without the redundant Reasoning tab.

### Track 3: Prompts Library Modernization

**[VERIFIED: source read of `lib/prompts-library.ts`]**

#### 3a. Remove client categories from operator view

The Prompts Library page (`app/playbook/prompts/page.tsx` lines 13-25) defines `OPERATOR_CATEGORIES` and `CLIENT_CATEGORIES`. **Remove `CLIENT_CATEGORIES` from the page render.** The prompts stay in the `PROMPTS_LIBRARY[]` array (available for client deployments), but the operator-facing page only shows:
- `ops_daily`
- `ops_review`
- `system_override`
- `system_health`
- `system_integration`
- `agent_tooling`

The 3 client categories (`client_setup`, `client_optimization`, `client_handoff`) are hidden from the operator page. A client deployment's tenant-scoped view can show them via the manifest system.

#### 3b. Fix morning briefing — remove MRR reference

**[VERIFIED: CC Clarification]** "MRR is more of an Atlas task. Bravo does not have real processes that include that. That shouldn't be the morning briefing."

**Mutation** in `lib/prompts-library.ts`:
- Prompt `ops-morning-briefing` (line 568-580): Remove "MRR" from description and prompt body. Replace with operational signals Bravo actually owns: pipeline status, client delivery health, inbound leads, scheduled meetings, top priority.
- **Also update** `lib/quick-actions.ts` (line 37-39): the "Run the daily briefing" Quick Action also references MRR. If this file survives Track 2b, update it too.

**New morning briefing prompt body** (write this, don't copy the old one):
The morning briefing should pull: pipeline movement (new leads, status changes), client delivery health (any blockers, deadlines today), inbound messages needing response, today's calendar/meetings, and the #1 priority. No MRR — that's Atlas's domain. Make the prompt body comprehensive and specific, not a one-liner.

#### 3c. Sync Vibe Translator to V9.1

**[VERIFIED: source read of `lib/prompts-library.ts` lines 88-178]** The Prompts Library has V8.0 of the Vibe Translator. The current working version is V9.1 (the one CC is using right now in `Business-Empire-Agent`).

**Mutation:** Replace the entire `prompt` field of the `vibe-to-execution-translator` entry with the V9.1 content. The canonical source is the skill file at `C:\Users\User\Business-Empire-Agent\skills\vibe-to-execution\SKILL.md` which should have the latest version. Verify the version number in the prompt text before writing. Also update the `description` field to reference V9.1, not V8.0. Update the comment block above the entry.

#### 3d. Modernize all remaining prompts

**[VERIFIED: CC Clarification]** "Some of these look a bit out of date and very basic and generic, like one-sentence prompts, and we can do better."

For EVERY prompt in `ops_daily`, `ops_review`, `system_health`, `system_integration`, and `agent_tooling`: review the `prompt` field. If it's a one-liner or a generic instruction, rewrite it to be:
- **Specific about what data to pull** — name the tables, the CLI tools, the scripts
- **Explicit about output format** — what the response should contain, in what structure
- **Aware of the current AOS** — reference the actual tools (supabase_tool, google_tool, n8n_tool, etc.)
- **Deep** — not a surface-level "give me a summary" but a structured multi-step workflow

The `system_override` prompts are already well-structured — leave them as-is unless they reference outdated paths.

### Track 4: Operations Error Counter Fix

**[VERIFIED: source read of `app/operations/page.tsx` lines 136-150]** The "Errors today" tile counts `agent_events` rows WHERE `severity IN ('error', 'warn')` in the last 24h. This inflates the count with routine warnings.

**Mutation:** Change line 143 from:
```typescript
.in("severity", ["error", "warn"])
```
to:
```typescript
.in("severity", ["error"])
```

The label stays "Errors today" — but now it only counts actual errors. Warnings are still visible in the Activity Tape and on the `/health` drill-down page.

### Track 5: Automations Functional Verification

**[VERIFIED: CC Clarification]** "I just want to make sure they're actually contributing to my AIOS accordingly."

After all code changes, run a verification sweep:
1. Query `cron_jobs` table for all active jobs: `python scripts/integrations/turso_tool.py select cron_jobs --limit 50`
2. For each active cron: check `last_result` and `last_run_at`. Flag any with `last_result` starting with "ERROR" or "FAILED" or `last_run_at` older than 2x their schedule interval.
3. Specifically check "Monthly inventory sync" — CC noted it hasn't run yet. If its `last_run_at` is NULL, that's expected for a monthly job added recently; flag it for CC but don't treat it as broken.
4. Report: for each automation, one line: name, schedule, last run, last result, status (contributing / stale / failed).

### Track 6: README Alignment Check

**[VERIFIED: source read of `C:\Users\User\Business-Empire-Agent\README.md`]** The README was last updated 2026-07-23. It references V7.3.3, 159 skills, 128 scripts, 27 sub-agents, 35 workflows — auto-maintained by `scripts/update_readme_stats.py`.

**Verification:** Run `python scripts/update_readme_stats.py --check` from the Business-Empire-Agent repo. If exit code 0, counts are current. If exit code 1, run without `--check` to update. Also verify the architecture version in the README matches `brain/STATE.md`'s `architecture_version` field.

### Track 7: Single Source of Truth Architecture Rule

**Root cause of the Vibe Translator drift:** The same content existed in two places — `lib/prompts-library.ts` (V8.0) and `content/playbooks/vibe-translator.md` (V9.1). When the prompt was updated, only one location was touched.

**Prevention:** After this audit, establish the rule: **every piece of operator knowledge lives in exactly one canonical location.**

| Content type | Canonical source | Consumers |
|---|---|---|
| Reusable prompts | `lib/prompts-library.ts` | Prompts Library page, chat composer |
| Operating runbooks | `content/playbooks/*.md` | Operating manual section of Playbook page |
| Playbook cards | `SECTIONS[]` in `app/playbook/page.tsx` | Playbook index page |
| Security model | `/playbook/security` route + `brain/SECURITY_MODEL.md` | Playbook card |

**Rule:** If content exists in `lib/prompts-library.ts`, it MUST NOT also exist as a `content/playbooks/*.md` file. If it does, the markdown file is deleted and the prompt entry is the single source.

## BUILD

Execute in this order — each step is independently deployable:

1. **`app/playbook/page.tsx`** — Remove 3 cards from `SECTIONS[]` (Daily Drills, Client Deployment Runbook, Operator Onboarding). Renumber remaining 5 (01–05). Refine OASIS Loop card subtitle/body if stale.

2. **`content/playbooks/`** — Delete any vibe-translator markdown file. Evaluate `10-oasis-loop.md` for redundancy with card 08. Clean up operating manual to contain only genuinely unique runbooks.

3. **`components/Sidebar.tsx`** — Remove "Reasoning" nav entry.

4. **`app/reasoning/page.tsx`** — Delete the file.

5. **`components/reasoning/QuickActionsGrid.tsx`** — Check all imports. If only consumed by `app/reasoning/page.tsx` and `components/manifest/ManifestReasoning.tsx`, delete both files. If consumed elsewhere, keep.

6. **`middleware.ts`** — Remove any `/reasoning` routing branches.

7. **`app/operations/page.tsx`** — (a) Change error counter query to errors-only (drop `warn`). (b) Add Agent Decisions card section (port from deleted reasoning page — import `recentDecisions` from `lib/queries`, render the same decisions list).

8. **`lib/prompts-library.ts`** — (a) Fix morning briefing: remove MRR, replace with pipeline/delivery/inbound/calendar/priority. (b) Sync Vibe Translator to V9.1. (c) Modernize all one-liner prompts in ops_daily, ops_review, system_health, system_integration, agent_tooling. (d) Every prompt body should be 5–15 lines minimum, specific, tool-aware.

9. **`app/playbook/prompts/page.tsx`** — Remove `CLIENT_CATEGORIES` from the render. Operator view shows only operator + universal prompts.

10. **`lib/quick-actions.ts`** — Evaluate against merged prompt library. If the Prompts Library page already has "Open in chat" buttons, delete this file. If not, port the click-to-chat UX into the Prompts Library page, then delete.

11. **`C:\Users\User\Business-Empire-Agent\README.md`** — Run `python scripts/update_readme_stats.py --check`. If stale, update.

12. **Visual QA** — After all changes, verify every modified page renders correctly. The Playbook should show exactly 5 clean cards + a minimal operating manual section. The Prompts Library should show only operator + universal prompts. Operations should show errors-only count + the new Agent Decisions section. The sidebar should have no Reasoning entry.

## GUARDRAILS

- **NEVER delete the `/playbook/drills`, `/playbook/client-deploy`, or `/playbook/onboarding` routes** — remove them from the index only. Direct URLs must still resolve.
- **NEVER modify `brain/SOUL.md`** — immutable, CC only.
- **NEVER modify `.env.agents`** — credentials, CC manages.
- **NEVER hardcode MRR numbers or financial data** into any prompt. MRR is Atlas's domain.
- **NEVER create duplicate content locations.** If a prompt exists in `lib/prompts-library.ts`, it must not also exist as a markdown file in `content/playbooks/`.
- **NEVER delete `lib/quick-actions.ts` data** before verifying the Prompts Library page has equivalent click-to-chat UX. Data loss with no replacement is worse than redundancy.
- **NEVER modify the SunBiz-specific sections** — client-tenant-scoped and outside this audit.
- **All Supabase queries must remain tenant-scoped.** Moving Agent Decisions to Operations must preserve existing tenant scoping.

## VERIFICATION

| Step | Command / Check | Expected output |
|------|----------------|-----------------|
| Playbook cards | Visit `/playbook` | Exactly 5 numbered cards (01–05) |
| Operating manual | Same page, scroll down | No "Vibe Translator" card |
| Reasoning tab gone | Click sidebar items | No "Reasoning" entry; `/reasoning` → 404 |
| Prompts Library | Visit `/playbook/prompts` | No client categories visible |
| Morning briefing | Find "Morning briefing" prompt | No "MRR" anywhere |
| Vibe Translator | Find "Prompt translator" prompt | Contains "V9.1" |
| Error counter | Visit `/operations` | Count matches `severity='error'` only |
| Agent Decisions | Ops page, scroll down | New "Agent decisions" card below Activity Tape |
| README stats | `python scripts/update_readme_stats.py --check` | Exit code 0 |
| Build passes | `npm run build` | No errors |

## OPEN QUESTIONS

| Gap | Default taken | Cost if wrong |
|-----|--------------|---------------|
| Whether `10-oasis-loop.md` duplicates playbook card 08 enough to delete | Keep unless near-exact copy | Minor redundancy — one edit |
| Whether `QuickActionsGrid.tsx` has consumers beyond Reasoning + ManifestReasoning | Delete both if only those two | Build breaks — caught by `npm run build` |
| Exact Vibe Translator version in skill file | Read and use whatever version it contains | One edit to fix |
| [ASSUMED] Error counter = errors-only, not errors+warnings | Changed to errors-only | One line revert |
| [ASSUMED] Client categories hidden from operator view, not deleted from code | Hidden from render, kept in array | Follow-up splice if needed |

---

## THE 7 PRODUCTION DEFENSES

1. **Probe credentials first.** Run `capability_probe check <service>` before claiming a credential gap. AVAILABLE = authorized. Never read an env file.
2. **No UI-only security.** Authorization re-checked server-side on EVERY endpoint. The Agent Decisions migration to Operations MUST preserve tenant scoping from `recentDecisions()`.
3. **Tenant data isolation.** Every multi-tenant query filters explicit tenant_id/user_id. Operations page uses `agentNamesForOps` — Agent Decisions must use the same scoping.
4. **Closed-loop error tracking.** No bare `except: pass`. The error counter fix removes `warn` from the count — it does NOT suppress warnings from logging.
5. **Verified restore point before schema change.** N/A — no schema changes.
6. **Server-side payment math.** N/A — no payment logic.
7. **Zero unrequested visual rewrites.** Remove items; do not redesign what remains.

## OPUS 5 EXECUTION CONTRACT

- **Zero stubs.** Complete every track end-to-end. No TODO comments.
- **Scope boundary.** Consolidation audit, not a redesign. Remove redundancy, modernize prompts, fix the error counter. Do not add new features.
- **Controlled delegation.** No subagents. 10-12 file edits, self-verify via `npm run build`.
- **Focused narration.** One sentence before the first tool call. Final report leads with the outcome.

## ANTI-SLOP CONSTRAINTS

1. **Probe, never assume access.** Run `capability_probe check <service>` before claiming a gap.
2. **No silent error swallowing.** Fail loud; log the full traceback.
3. **No mock data.** Every prompt references real tools and real tables.
4. **No generic UI.** Modernized prompts must be specific and deep — name the scripts, the tables, the output format.
5. **Surgical scope.** Touch only what the task requires.
6. **Empirical proof.** `npm run build` must pass. Every deleted import traced.
7. **Read the source.** Verify every path, column, and import before deleting.

## FIX-FIRST

Enter Fix-First Execution Mode. No permission-seeking, no architectural proposal, no brainstorm. Execute every track in order, verify after each, report at the end. Fix-First skips ceremony, not verification: `npm run build` and visual QA are never optional.
