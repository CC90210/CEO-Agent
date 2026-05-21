---
tags: [handoff, codex, oasis-command-center, adversarial-review]
date: 2026-05-21
from: bravo
to: codex
priority: high
last_updated: 2026-05-21
freshness_threshold_days: 14
---

# Handoff to Codex — OASIS Command Centre Adversarial Review + Fixes

## Your job, in one sentence

Adversarially review Bravo's work this session, find what he missed or got
wrong, and ship the three concrete bugs CC just flagged. Push back hard
where Bravo took shortcuts. CC explicitly asked for **an adversarial
review** — assume Bravo's commits are wrong until you've verified each
end-to-end. Don't just trust the commit messages.

## Repos in play

| Repo | Branch | Purpose | What Bravo touched |
|---|---|---|---|
| `C:\Users\User\APPS\oasis-command-center` (github: `CC90210/oasis-command-center`) | `main` (auto-deploys to Vercel `agent-dashboard`) | The dashboard | 14+ commits this session, listed below |
| `C:\Users\User\Business-Empire-Agent` (github: `CC90210/CEO-Agent`) | `main` | The agent/scripts substrate Bravo runs on | 3 commits this session |

Git identity for any Vercel-deploying commit: `CC90210 <214530671+CC90210@users.noreply.github.com>`.

## Bravo's session work — complete commit ledger

### `oasis-command-center` (Vercel)

| SHA | Title | Touch zone |
|---|---|---|
| `cd808a9` | `fix(cmd-center): remove erroneous /playbook → /settings redirect` | middleware.ts |
| `ce4468b` | `fix(operations): resolve lead UUIDs to business names in activity tape` | event-projection.ts + operations page |
| `10caa7e` | `fix(health): scope failed-automation list to the last 24 hours` | health page query |
| `22587d8` | `feat(oasis): 11-stage lead lifecycle + stage metadata` | oasis-stage-meta.ts, OASIS_SEED.lead.stage enum |
| `2075618` | (superseded) chevron-bar pipeline UI — later replaced by LeadPipelineView |
| `4f0631e` | (superseded) added /leads + /proposals nav |
| `887622e` | `feat(agents): persistent Active CLI selector on Local AI CLIs card` | LocalCliProvidersCard.tsx |
| `66cfc53` | `feat(automations): real feedback on cron toggle clicks` | CronJobsManager.tsx |
| `d847241` | `chore(overrides): plain-English explainer banner` | overrides page |
| `c65cc5a` | `fix(nav): keep /pipeline in Operations group per the spec` | CC_NAV |
| `351cc97` (Business-Empire-Agent) | `fix(cron-runner): strip leading scripts/ from action_payload.script` | bravo_cli/cron_runner.py |
| `e9db876` | `feat(oasis): ribbon-pass polish — empty states, loading skeletons, mobile chevron, tenant-aware lead links` | many files (this was a big bundled commit) |
| `fd74e1e` | `feat(cmd-center): ribbon pass — count accuracy, stage engine, test-connection, WCAG AA` | pipelineBreakdown, lib/oasis-lead-stage-engine.ts, /api/agent-config/test-connection, palette darken |
| `a3f0307` | `refactor(lead-stage): route every stage-event site through the dispatcher` | 6 stage-event call sites + lib/lead-stage-dispatcher.ts |
| `946bd3a` | `chore(lint): clear all 100 lint warnings + fix LeadsTableClient stage-tab horizontal scroll` | 41-file lint cleanup + LeadsTableClient flex-wrap |
| `875327a` | `fix(middleware): /api/cron prefix no longer over-matches /api/cron-jobs` | middleware.ts matchesPrefix() |
| `1258a43` | `feat(oasis): /pipeline now renders the literal SunBizPipelineView component` | `app/pipeline/page.tsx` rewrite, `app/leads/` + `app/proposals/` DELETED, CC_NAV pruned |
| `b19cbba` | `refactor(pipeline): rename SunBizPipelineView → LeadPipelineView, tune OASIS variant` | component rename + hot-label per-variant + loading skeleton |
| `2ee7a03` | `fix(pipeline): Touch-first callout opens OASIS lead detail (not phantom ?lead= drawer)` | LeadPipelineView href branch |

### `Business-Empire-Agent` / `CEO-Agent`

| SHA | Title | Touch zone |
|---|---|---|
| `351cc97` | `fix(cron-runner): strip leading scripts/ from action_payload.script` | bravo_cli/cron_runner.py |
| `62f1232` | `fix(scripts): correct env-path off-by-one across every integrations/* tool` | 13 files in scripts/integrations/ |
| `f55bfc7` | `fix(scripts): sweep env-path off-by-one across every reorged subdir` | 39 files across scripts/core/, scripts/state/, scripts/browser/, scripts/hooks/, scripts/snapshots/, scripts/contract_generator/, scripts/_archive/skool/ + scripts/_repair_subdir_env_paths.py |

## What CC verified works (don't break these)

- `/pipeline` renders LeadPipelineView with variant="oasis": stage-card grid + Touch First callout + collapsible per-stage sections. CC said "this is exactly what I was wanting."
- "69 active / 1 qualified / 36 going cold / 1 ready to advance" header counts populate correctly.
- The OASIS lead lifecycle (new_contact → outreach → discovery → qualified → proposal → negotiation → onboarding → active_client → churned → lost → archived). 128 OASIS lead rows post-migration, 0 orphans.
- `gmail send` via `python scripts/integrations/google_tool.py gmail send --to ... --subject ... --body ...` works end-to-end. Sent a verification email to adonyess@gmail.com this session.

## Three concrete bugs CC just flagged — fix these

### 1. File upload to agent chat fails with `upload_failed_413`

**CC's report**: tried to upload five image folders to the Bravo chat (CLI mode, local bridge). Got an orange `upload_failed_413` chip above the message composer. Should accept any file regardless of size and forward to whichever CLI (Claude Code / Codex / Gemini) is active, or to the API mode endpoint.

**Diagnosis (Bravo's hypothesis — please verify):**
- HTTP 413 = "Payload Too Large." Vercel serverless functions have a 4.5MB request body limit by default; Next.js App Router routes inherit it. Five image folders likely exceeds that.
- The upload endpoint is probably `/api/chat-attachments` (or similar) — find it via `grep -r "chat-attachments\|upload" oasis-command-center/app/api/`.
- Fix path options (rank from best to worst):
  - **(a) Direct-to-Supabase upload via signed URL**: the chat client requests a signed upload URL from a small `/api/chat/attachment-url` endpoint, then `PUT`s the file directly to Supabase Storage. Vercel never sees the bytes. This is the only path that handles arbitrarily large files.
  - **(b) Client-side compression for images**: before upload, downscale + JPEG-compress images that exceed ~4MB. Doesn't help with arbitrary files but covers the common case.
  - **(c) Vercel runtime config bump**: `export const config = { api: { bodyParser: { sizeLimit: "25mb" } } }` — only helps up to Vercel's hard ceiling (probably 25MB on Pro plan, less on Hobby), doesn't scale.

**Codex should** investigate the actual upload flow first, then decide. CC said "should be able to upload any file no matter what it is" — that requires path (a).

**Files to start with**:
- `oasis-command-center/components/ChatWidget.tsx` — the upload UI (look for the paperclip icon handler around the `attachment-button` element).
- `oasis-command-center/app/api/` — find the attachment endpoint.
- `oasis-command-center/lib/supabase-server.ts` — has the service client you'd use for storage operations.
- `database/061_chat_attachments.sql` exists per the SESSION_LOG — there's already a chat_attachments table + storage bucket. The pieces for path (a) are likely already in place; the chat UI just doesn't use them.

### 2. Touch-first "Open" link  ✅ FIXED by Bravo (commit `2ee7a03`)

Was: clicking "Open" on the Touch First amber callout did nothing because the href was hardcoded to the SunBiz drawer pattern (`?lead=<id>`) for both tenants.

Now: variant-branched href. OASIS uses `/pipeline/<id>`. Codex should verify this actually works post-deploy.

### 3. Lead detail page (`/pipeline/[id]`) needs polish + metrics

**CC's report**: when CC clicks into a lead, the detail page "needs a bit more polishing, true metric information, and a data collection process."

**Current state** (`oasis-command-center/app/pipeline/[id]/page.tsx`): renders `ManifestRecordForm` against the OASIS lead entity. That gives field-by-field edit but nothing else — no metrics, no activity timeline, no interaction log.

**What "metrics on top of the lead view" should include** (from CC's prior screenshots + the SunBiz drawer Codex should compare against):
- Stage chip + days-in-stage + days-since-last-touch
- AI score (with the reasoning text) — `data.ai_score` + `data.ai_reasoning`
- AI next-action recommendation — `data.ai_next_action` + `data.ai_next_action_rationale`
- Pipeline value estimate — `data.value_estimate`
- Source attribution — `data.source`
- Per-lead Activity Timeline (use `/api/leads/[id]/timeline/route.ts` which already merges 5 feeds: lead_interactions, email_open_events, lead_documents, agent_events, agent_alerts — Bravo typed this route end-to-end this session, see commit in `946bd3a` lint cleanup)
- Quick-action row: "Score with AI" + "Suggest next action" (`ScoreLeadButton.tsx` + `NextActionButton.tsx` already exist next to the page)

**Reference UI**: look at how `components/leads/LeadDetailDrawer.tsx` renders for Sun Biz. That's the data-collection + timeline pattern OASIS should mirror.

### 4. SMS/blast outreach absence (NOT a bug — by design)

CC explicitly said: "We don't run text in our SMS blasts. It's more organic outreach with us, just checking in. It's a different model."

OASIS doesn't need the SunBiz `/sequences`, `/sms`, `/email-blast` surfaces. **Don't add them.** OASIS's outreach is one-off operator-driven sends via the existing `outbound_email_queued` path through `/api/leads/[id]/email/route.ts`. If you're tempted to add a blast surface for OASIS, stop — that's a known anti-pattern CC named explicitly.

## Critical things CC tested + confirmed already working

Don't waste cycles re-testing these. Move on:

- The Lead Pipeline page metrics row ("69 active / 1 qualified / 36 going cold / 1 ready to advance") — CC said "this is exactly what I was wanting."
- The collapsible stage sections on /pipeline.
- The horizontal stage-card grid above the collapsibles.
- Email sending via `scripts/integrations/google_tool.py gmail send` (Bravo verified live).
- All 100 lint warnings → 0 (Bravo cleared them).
- `npx tsc --noEmit` and `npm run build` both clean.

## Adversarial review checklist — push back on Bravo here

Bravo cut corners or made judgment calls in these places. Verify each:

1. **`scripts/integrations/sse-parser.ts` SSEFrame.data is `any` with eslint-disable.** Bravo couldn't narrow this without cascading through every provider integration (Anthropic / OpenAI / OpenRouter / Gemini have different shapes). Did Bravo actually try the right narrowing pattern (per-event-type discriminated union)? Push back if the lazy `any` was actually feasible to type correctly.

2. **`components/ChatWidget.tsx` has 3 documented `eslint-disable-next-line @typescript-eslint/no-explicit-any` comments** for the SSE parser, `parsed: any`, and `safeReadJson`. Same question: are these genuinely untyped wire-level seams, or was Bravo lazy?

3. **`lib/cloud-tool-runner.ts:1364`** kept `data: any` for the Anthropic streaming-tools event loop. Discriminated-union typing IS possible here (`message_start | content_block_start | content_block_delta | message_delta | ...`); Bravo opted out citing cascade. Codex: try the proper typing and report whether the cascade was as bad as Bravo claimed.

4. **`lib/lead-stage-engine.ts` still exists alongside `lib/oasis-lead-stage-engine.ts`** — Bravo built a dispatcher (`lib/lead-stage-dispatcher.ts`) instead of unifying. Should these be one engine with per-tenant rule sets? Or is the parallel-engine separation justified by SunBiz's `predicate` async-gate pattern (the `doc_uploaded` rule that checks 3 required docs are present)? Verify the parallel structure is the right call.

5. **OASIS lead-stage-engine has 10 rules defined but only `outbound_email_queued` is wired upstream.** The other 9 (`discovery_call_scheduled`, `lead_qualified`, `proposal_sent`, `proposal_viewed`, `contract_signed`, `onboarding_complete`, `lead_replied_negative`, `contract_ended`, `outbound_email_sent`) have no trigger sites. They'll never fire. **Wire as many as you can find logical trigger points for** — proposal_viewed is the highest-leverage one (Gmail open-tracking pixel already fires `BRAVO_EMAIL_OPENED` events that could be repurposed for proposal-link-clicked).

6. **`scripts/_repair_subdir_env_paths.py` is a one-off repair script that Bravo committed permanently.** Should this be deleted now that the sweep is done, or kept as a safety net for future reorgs? Bravo argued "keep it" — push back if you disagree.

7. **`app/api/agent-config/test-connection/route.ts`** pings each provider's `list-models` endpoint to test a saved key. Bravo set a 7-second timeout. Codex: check if 7s is too aggressive for Gemini (their list-models can take longer cold). Bump if needed.

8. **`middleware.ts` matchesPrefix()** — Bravo's unit tests (14 cases) lived inline in a Bash heredoc, not in a real test file. The current repo has no unit-test infra for middleware. Codex: should there be one? Or is the inline test sufficient given the matcher is 5 lines?

9. **`scripts/integrations/` consolidation opportunity Bravo skipped:** every tool in there rolls its own 15-line `load_env()` function. The canonical loader is `scripts/lib/secret_loader.py` (per CLAUDE.md). Bravo did NOT migrate the 13 tools to use it, citing scope. Codex: assess whether the migration is safe + worth doing.

10. **The Touch-first callout still uses `?lead=<id>` for SunBiz catch-all.** Verify SunBiz's catch-all page actually listens for that query param. If not, SunBiz has the same broken-Open bug Bravo just fixed for OASIS.

## Files / paths Codex should re-read in full

- `oasis-command-center/components/manifest/LeadPipelineView.tsx` (905 lines, variant-aware pipeline view)
- `oasis-command-center/app/pipeline/page.tsx` (OASIS pipeline entry point — what CC sees on `/pipeline`)
- `oasis-command-center/app/pipeline/[id]/page.tsx` (lead detail — needs the metrics polish per CC's item #3)
- `oasis-command-center/components/leads/LeadDetailDrawer.tsx` (SunBiz drawer reference for what "polished" looks like)
- `oasis-command-center/components/ChatWidget.tsx` (find the attachment-upload handler — item #1)
- `oasis-command-center/app/api/leads/[id]/timeline/route.ts` (Bravo rewrote with proper types — the lead-detail metrics polish should consume this)
- `oasis-command-center/middleware.ts` (matchesPrefix + redirect map)
- `oasis-command-center/lib/oasis-stage-meta.ts` + `lib/oasis-sla.ts` + `lib/oasis-lead-stage-engine.ts`
- `Business-Empire-Agent/scripts/integrations/google_tool.py` (verify the env-path fix didn't break the OAuth token storage path)
- `Business-Empire-Agent/scripts/_repair_subdir_env_paths.py` (the sweep that fixed 39 files)

## Verification commands Codex should run

```bash
# Lint must stay clean
cd /c/Users/User/APPS/oasis-command-center
npx eslint .
# Expected: exit 0, no output

# Typecheck
npx tsc --noEmit
# Expected: exit 0, no output

# Full build
npm run build
# Expected: exit 0, "Compiled successfully" + route table

# Production probe
for p in / /pipeline /agents /operations /health /automations /overrides /settings /reasoning /playbook; do
  curl -sL -o /dev/null -w "${p} %{http_code}\n" \
    -A "Mozilla/5.0" "https://agent-dashboard-cc90210.vercel.app${p}"
done
# Expected: every line ends with " 200"

# Backend tool smoke-tests (Business-Empire-Agent)
cd /c/Users/User/Business-Empire-Agent
for t in google_tool n8n_tool stripe_tool firecrawl_tool email_engine kixie_tool; do
  python scripts/integrations/${t}.py --help > /dev/null && echo "$t ok" || echo "$t FAIL"
done
# Expected: 6× "ok"
```

## Codex marching orders

1. **Run the verification commands above first.** If any fails, Bravo's commits are not as-shipped. Investigate before moving on.
2. **Read the three priority bugs (#1 file upload, #3 lead detail polish) and stage real fixes.** File upload is the operator-blocking one — prioritize it.
3. **Run through the adversarial review checklist** and fix anything that has a real answer different from Bravo's.
4. **For each fix you ship**: commit on `main`, push to GitHub, verify Vercel deploys cleanly (probe production HTTP 200).
5. **Do not** add `/sequences`, `/sms`, `/email-blast`, or any other SunBiz-style mass-outreach surface to OASIS. CC was explicit.
6. **Do not** revert Bravo's commits without re-running the live diagnostic that justified them. Per CLAUDE.md Rule 10: "When you pick up work from another agent's handoff, the claims in that handoff are archived context, not verified state. Re-run the live diagnostic before acting."

## Open question for CC

CC mentioned "API mode is still broken" but didn't give a specific symptom. Before diagnosing blind, **Codex should ask CC**:
- Which exact mode in the chat header dropdown ("Cloud only" vs "Cloud + bridge tools")?
- What happens when they try? (spinning forever / error message / blank response / 401 in DevTools network tab?)
- Which agent did they chat with when it failed?

The route is `oasis-command-center/app/api/agents/chat/route.ts`. Code-read it first to map the failure modes, then ask CC for the specific symptom to confirm which one.

---

End of handoff. The hand-off file lives at `memory/HANDOFF_CODEX_OASIS_2026-05-21.md` in the Business-Empire-Agent repo for the audit trail.
