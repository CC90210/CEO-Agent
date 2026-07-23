---
name: INTENTS
description: Verb-by-verb playbook. For each kind of operator request, the exact sequence the agent should run.
mutability: SEMI-MUTABLE
tags: [brain, agent-only, playbook]
last_updated: 2026-07-22
freshness_threshold_days: 30
verified: 2026-07-22
---
# INTENTS — Verb-by-Verb Playbook

> Reached from `brain/AGENT_ROUTER.md` when an intent needs more than a one-line "read this file" answer.

---

## "Send an email to <X>"

In chat (bridge mode), this runs through the `run_script` tool with `confirm:true` gating for the actual send. NEVER tell the operator to type the python command.

1. Classify the send first: replying to an INBOUND lead (funnel/DM/social — the primary motion) → compose directly and use the send_gateway steps below, skipping outreach framing. COLD/follow-up OUTREACH (on-demand only, not the default motion) → read `skills/outreach-send/SKILL.md` for the canonical outreach path.
2. Confirm the recipient exists: call `run_script` with `lead_engine_list` (args like `--status all --limit 50`) and find them. If missing, ASK before creating — `lead_engine_add` is a mutating action that needs `confirm:true` and same-turn operator approval.
3. Compose the draft inline in chat. Voice rules from `brain/SOUL.md` if not already in your prompt.
4. **Pre-flight:** call `run_script` with `send_gateway_can_act` (args: `--lead-id <id> --channel email`). The gateway enforces 8 gates (CASL, cooldown, daily/hourly cap, domain cap, reputation, draft critic, bounce circuit, reservation guard). If a gate blocks, surface the reason — do NOT bypass.
5. **Operator confirmation:** show the draft + gate verdict in chat. ASK for explicit approval ("send it" / "yes" / "ship"). Do NOT auto-send.
6. **Send:** after explicit approval in the same turn, call `run_script` with `send_gateway_send` (args: `--channel email --agent-source bravo --to ... --subject "..." --body "..."`) AND `confirm: true`. Without `confirm:true` the bridge returns `confirm_required` — that's the safety net, don't try to bypass it.
7. Confirm in chat: recipient, subject, gate verdict, message id from the gateway's stdout.

---

## "Apply this database migration"

1. Confirm migration file is in `database/<NNN>_<name>.sql`. If not, write it with the next number.
2. Run `python scripts/apply_migration.py database/<NNN>_<name>.sql`. The script applies through Supabase Management API; gates on dangerous patterns (`DROP TABLE`, `TRUNCATE`, naked `GRANT`/`REVOKE`).
3. If gated, surface the reason. Operator may approve via the Supabase Dashboard SQL editor — only then do you suggest a manual path.
4. Confirm post-apply: `python scripts/integrations/supabase_tool.py select <new_table> --project bravo --limit 1` to verify the schema is live.
5. Update `brain/CHANGELOG.md` with the migration name + one-line purpose.

---

## "Push this to production"

1. Run typecheck + build locally first: from the relevant app dir, `npm run typecheck` then `npm run build`. If either fails, fix before commit.
2. `git status` to confirm what's staged. Add explicitly — never `git add -A` without listing files first.
3. Compose a commit message: 1-line title, blank, body. End with the standard `Co-Authored-By` trailer.
4. `git commit -m "$(cat <<'EOF' … EOF)"` (HEREDOC pattern preserves newlines).
5. `git push`. Vercel deploys automatically; verify green with `npx vercel ls` (look for the topmost deployment to flip from Building → Ready).
6. Confirm in chat: commit hash, what changed, deploy URL once green.

---

## "Update my dashboard / profile / settings"

1. Read `oasis-command-center:lib/agent-actions.ts` to confirm the action shape (allowed fields, validators).
2. Emit a `<dashboard-action type="…">{…}</dashboard-action>` marker in your chat reply. The chat route parses it post-stream and applies via `runAction()`.
3. Confirm in chat with one line: "Set primary agent to Atlas. Refresh the page to see it stick."

Allowed action types: `update_profile`, `toggle_agent_enabled`, `set_primary_agent`, `update_mrr`. Anything else needs a new handler in `agent-actions.ts` first — don't fake it.

---

## "Schedule / run a cron"

1. For Vercel-hosted crons (the dashboard's): edit `oasis-command-center:vercel.json`'s `crons` array. Push. Vercel picks it up on next deploy.
2. For local-machine crons (most of `scripts/*`): there's no central scheduler. The convention is `python scripts/<name>.py` invoked from the operator's task scheduler / launchd / systemd. Tell them what to schedule, but if they ask you to "automate it," wire it via `oasis-command-center:vercel.json` if it's HTTP-pingable, or surface the OS-specific install command.
3. Confirm in chat: where it's now scheduled, when next run is.

---

## "Find / search / look up"

1. **Code or files:** use the `read_file` tool you already have. Pattern-match starting from the indexes (`brain/AGENT_ROUTER.md`, `skills/INDEX.md`, `brain/CAPABILITIES.md`).
2. **Web search:** `python scripts/integrations/firecrawl_tool.py search "<query>"` then `read <url>` to extract structured content.
3. **Database:** `python scripts/integrations/supabase_tool.py select <table> --project bravo --eq '{"…":"…"}' --limit N`.
4. **Memory / past sessions:** read `memory/SESSION_LOG.md` (recent) or `memory/ARCHIVES/` (older).

---

## "Scrape <URL>" / "Get the content of this page" / "Pull data from <site>"

**DEFAULT (V6.7+, 2026-05-16):** call `research_fetch.py` — it auto-escalates Firecrawl → CloakBrowser based on actual response and remembers per-domain so subsequent calls skip straight to the right tier.

```bash
python scripts/research_fetch.py <url> --json
```

Result includes `tier_used`, `tiers_tried`, `reputation.hit`, `reputation.start_tier`, `errors` per tier. Skill: `skills/research-fetch/SKILL.md`. Reputation DB: `state/site_reputation.db`.

**Drop down to a specific tier only when you need its unique features:**

1. **Firecrawl** specifically — for `crawl` (multi-page), `extract` (LLM-schema), `map` (URL inventory), `search` (search-and-scrape in one call):
   ```bash
   python scripts/integrations/firecrawl_tool.py {crawl|extract|map|search} ...
   ```

2. **CloakBrowser** specifically — for interactive flows on protected sites, screenshots, or forcing the stealth tier:
   ```bash
   python scripts/browser/cloak_browser_tool.py goto <url> --eval "() => document.title"
   python scripts/browser/cloak_browser_tool.py scrape <url> --screenshot evidence/<slug>.png
   ```
   For Akamai/Kasada-tier hardness, set `CLOAK_PROXY_URL` in `.env.agents` (residential proxy). If a target starts blocking unexpectedly, run `cloak_browser_tool.py check-stealth --json`.

3. **Browser Harness** — when you need to act AS CC inside CC's logged-in account. See `skills/browser-harness/SKILL.md` and `browser/SAFETY.md` — sends/posts/billing/destructive actions still need explicit CC approval.

4. **Playwright MCP** — interactive flow / visual snapshot on an UNPROTECTED site (`browser_navigate`, `browser_snapshot`, `browser_click`). Do NOT use raw Playwright on protected sites.

Skill refs: [skills/research-fetch/SKILL.md](../skills/research-fetch/SKILL.md) · [skills/cloak-browser/SKILL.md](../skills/cloak-browser/SKILL.md) · [skills/web-scraping/SKILL.md](../skills/web-scraping/SKILL.md).

---

## "Switch me to <agent>" / "Have <agent> do this"

1. If the chat picker switched the agent, the bridge already `cd`'d for you — your CLAUDE.md changed.
2. If the operator typed it in chat ("ask Atlas to recalc tax"), you have two options:
   - Surface the delegation: explain that the operator should switch in the picker, or that this is a `bravo agent run atlas …` task.
   - For cross-agent work that doesn't need the user-facing agent, post to `tmp/agent_inbox/` via `python scripts/core/agent_inbox.py post --to atlas --priority high --body "…"`. Atlas reads its inbox at session start.

---

## "Stop / pause / undo"

1. **Outbound mid-flight:** `BRAVO_FORCE_DRY_RUN=1` env var — every send routes to dry-run. Set on the local shell or in `.env.agents`.
2. **Cron:** comment the line in `oasis-command-center:vercel.json` and push.
3. **Last action emitted via dashboard-action:** there's no automated undo. Emit a compensating action (e.g. `update_profile` with the previous value) in the next turn after the operator confirms.

---

## "Audit the system" / "health check"

1. Run `python scripts/core/self_audit.py --json`. Health score < 90 → drift to investigate. Health score < 70 → STOP and surface to CC before any new work.
2. Drill into specific drift items: `python scripts/capability_query.py drift`.
3. Check freshness: `python scripts/core/memory_aging.py stale --days 7 --json` for memory. `python scripts/fleet_health.py --json` for cross-agent rollup.
4. If self_audit flags MCP config drift: `mcp_configs_in_sync: false` → reconcile `.claude/mcp.json` ↔ `.vscode/mcp.json` ↔ `~/.gemini/settings.json`. Credentials live ONLY in `.env.agents`.
5. Confirm in chat: health score, top 3 issues, recommended fix order, whether you can fix them yourself or need CC approval.

---

## "Clean up the repo" / "delete junk"

1. Default to dry-run: `python scripts/core/system_cleanup.py` (no `--apply` flag = report only). Read the output before doing anything.
2. The script preserves the active repo via a safety guard (V6.1.1). It targets pip/npm caches, redundant install clones, old `tmp/` files, `__pycache__` trees, scaffold backups.
3. If the report includes anything outside its allowlist, STOP and surface to CC. Don't manually `rm -rf` to "help."
4. Apply with `python scripts/core/system_cleanup.py --apply` ONLY after CC confirms.
5. After apply: `git status` to confirm only intended deletions, then re-run `self_audit.py` to verify health didn't regress.

---

## "What's the current date / day-of-week / time?"

1. Compute. Never quote from prompt context, system reminders, or memory.
   - Date: `python -c "from datetime import date; print(date.today().isoformat())"`
   - Day name: `python -c "from datetime import date; print(date.today().strftime('%A'))"`
   - Days remaining to a deadline: `python -c "from datetime import date; print((date(YYYY,M,D)-date.today()).days)"`
2. State the result directly. Day-of-week hallucination is a 3-time logged repeat offense — treat this rule as load-bearing, not optional.
3. For "what's the current status?": run `read_file("brain/STATE.md")` AND verify its `last_updated` against today via `memory_aging.py stale --days 7 --json`. If stale, say so and ask CC for current state.

---

## "Create a new skill / agent / workflow"

1. Read `skills/agent-forge/SKILL.md` for the canonical creation flow.
2. Check overlap first: `python scripts/register_skill.py route "<the task this skill would handle>" --json`. If the resolver already returns a high-confidence match, **enhance the existing skill** instead of creating a new one. Overlap > 50% = enhance, not create.
3. For a new skill: `python scripts/register_skill.py create <skill-slug>` scaffolds `skills/<slug>/SKILL.md` with proper frontmatter (name, description, triggers, owner, tier, risk).
4. For a new sub-agent: drop the file in `agents/<name>.md` (canonical Bravo persona, full Decision Autonomy / Quality Gates / Anti-Patterns sections) OR `.claude/agents/<name>.md` (Claude Code native one-shot spawn). Read `brain/ORCHESTRATION.md` "Layer Selection Matrix" before deciding which.
5. For a new workflow: drop `.agents/workflows/<verb>.md`. The trigger is `/<verb>` in chat.
6. After creating any of the above: `python scripts/register_skill.py sync-all --deactivate-missing --json` to refresh the runtime catalog. Then `python scripts/build_capability_graph.py` to update the graph.
7. Update `brain/WHEN_TO_USE_SKILLS.md` (skills only — add a row to the right section with trigger phrase + don't-use-when guard).

---

## "Diagnose why you made a mistake"

1. Read `memory/MISTAKES.md` to see whether this exact failure mode is already logged. If yes, the prevention is already there — apply it.
2. If new: write a new entry at the top of MISTAKES.md with these exact subsections:
   - **Failure:** (1-2 sentences — what went wrong, observably)
   - **Why it slipped:** (root cause, not a symptom — keep asking "but why?" until you hit something a person can change)
   - **Prevention:** (1-N concrete rules; ideally one is a *system rail* like a hook, lint check, or test, not just "I will remember")
   - **Tag:** (semantic tag like `cold-outreach-blocker`, `tz-bug`, `repeat-offense`)
3. If the prevention requires a code change (lint hook, regression test, schema migration), do that change in the same turn — don't leave it as an aspirational rule.
4. If the mistake is the third+ instance of the same pattern, escalate: it's a structural issue, not a discipline issue. Add a router entry, EXECUTION_RULES rule, or hook to make it mechanically impossible.
5. See `brain/BRAIN_LOOP.md` Reflexion section for the full multi-step protocol when the failure was costly.

---

## "Check whether memories are stale"

1. Run `python scripts/core/memory_aging.py stale --days 7 --json`. Output is a per-line breakdown: file, line number, days since last referenced date, the title.
2. Cross-check frontmatter: each `memory/*.md` should have `last_updated:` and `freshness_threshold_days:`. If a file is missing either, that's drift — patch the frontmatter.
3. For body-level staleness (a fresh-stamped file with a stale sentence inside, e.g. an outdated Sprint roadmap inside a fresh ACTIVE_TASKS): treat the sentence as archived, not the file. Move it to `memory/ARCHIVES/<YYYY-MM-topic>.md` with a header explaining when and why it was archived.
4. NEVER quote a stale memory as current truth. NEVER silently "refresh" the timestamp without verifying the body is actually current — that just moves the lie forward.

---

## "Generate a CEO briefing / status report"

1. Read `state/snapshots/latest_briefing.json`. If `ts` < 24h old, use it as the spine — it has pipeline (tenant-scoped), follow-ups, client alerts, top warm leads. **No MRR — revenue is Atlas's brief, never Bravo's.**
2. If stale or missing, run `python scripts/snapshots/briefing_snapshot.py` (one subprocess, writes the snapshot). Then read it.
3. Add what isn't in the snapshot: Atlas STATE.md (`C:\Users\User\APPS\trading-agent\brain\STATE.md` — READ ONLY), blocked items from `memory/ACTIVE_TASKS.md`, today's #1 priority.
4. Format per `skills/ceo-briefing/SKILL.md`. Keep under 30 lines. End with the #1 priority — make it impossible to ignore.
5. Do NOT run `lead_engine.py` / `client_health.py` live unless the snapshot path errored — the whole point of the snapshot is to avoid that 30–60 sec retrieval tax. Never run `revenue_engine.py` for a briefing at all (Atlas-owned).

---

## "Draft a proposal or SOW"

1. Read `brain/DEAL_ARCHITECTURE.md` for the canonical proposal structure + pricing tiers. Then `skills/proposal-generation/SKILL.md` for the format.
2. Ask CC for the deal shape if not given: prospect, scope, MRR or one-time, deadline, any compliance constraints. Don't fabricate.
3. Compose the draft inline. Voice rules from `brain/SOUL.md`. Avoid AI-slop phrasing ("unlock the power of…", "transform your…").
4. Show CC the draft + a one-sentence rationale per pricing tier. ASK before sending — proposals route through `send_gateway` like any outbound (see "Send an email to <X>" intent).
5. After CC approves: send via `send_gateway`, log the deal as a lead-stage update via `lead_engine.py update --id <id> --stage proposal_sent`.

---

## "Score a lead / qualify for outreach"

1. Snapshot-first: read `state/snapshots/latest_leads.json`. If the lead is already in `qualified_leads` (score ≥ 60), you have everything — current score, MRR potential, last contact, next action due.
2. If not in the snapshot (new lead) or stale: `python scripts/lead_engine.py score --lead-id <id> --json` recomputes and saves the score.
3. Read `skills/sales-methodology/SKILL.md` for the NEPQ framework before drafting any outreach. Lead with the prospect's problem, not OASIS's solution.
4. Surface to CC: score, suggested next action, draft message if appropriate. Routes through `send_gateway` for the actual send (see "Send an email to <X>" intent).

---

## "Log a decision or pattern"

1. If it's a decision (architectural, business, commitment): append to `memory/DECISIONS.md`. Format: `## YYYY-MM-DD — <one-line title>` + body sections **Context**, **Decision**, **Why**, **Alternatives rejected**.
2. If it's a pattern that worked (validated approach worth repeating): append to `memory/PATTERNS.md` as `[P]` (probationary). Promote to `[V]` after 3 successful re-uses.
3. If it's a mistake or correction: use the "Diagnose why you made a mistake" intent above — that flows to `memory/MISTAKES.md`, not here.
4. Cross-link: every new entry should link to the file/skill/script it relates to via wiki-link `[[brain/X]]` so the Obsidian graph stays connected.
5. Update `memory/MEMORY.md` index if the decision/pattern is high-leverage (something future-CC must know without grepping).
6. The `skills/memory-journaling/SKILL.md` skill is the guided form for this — invoke it if CC says "journal X" or "log a decision."

---

## "Sync an external data source" (Stripe / Supabase / GWS / webhooks)

1. Read `skills/integrations-sync/SKILL.md` for the canonical refresh patterns per integration.
2. Stripe → revenue_events: `python scripts/revenue_engine.py sync-stripe --json`. Idempotent (uses Stripe event IDs). Verify with `revenue_engine.py mrr --json` after.
3. Supabase tables: prefer `n8n_tool.py execute <workflow-id>` if a sync workflow exists; otherwise `supabase_tool.py upsert` with explicit `--on-conflict <column>` to stay idempotent.
4. GWS (Gmail/Calendar): `google_tool.py gmail list --since <iso>` or `calendar events --since <iso>` — pull only the delta, not the full mailbox.
5. After any sync: rebuild affected snapshots so the read-path sees fresh data — `python scripts/snapshots/briefing_snapshot.py` (or whichever is downstream of what you just synced).
6. Surface to CC: what was synced, row counts, any errors that hit the `_error` field in the snapshot JSON.

---

## "Publish to social / schedule content / post on X-Instagram-LinkedIn"

1. **This is Maven's domain, not Bravo's.** Maven (CMO-Agent) owns content + social since 2026-04-26. Don't post directly from this repo.
2. Route: tell CC to switch to Maven in the chat picker, OR delegate via `python scripts/core/agent_inbox.py post --to maven --from bravo --priority normal --subject "<task>" --body "<context + ask>"`. Maven reads its inbox at session start.
3. For the actual stack, refer CC to `C:\Users\User\CMO-Agent\` — that's Maven's repo. `late_tool.py` (now Zernio) lives there and handles cross-platform scheduling.
4. The ONE exception: if CC explicitly says "post this from Bravo," surface the boundary and ask if they're sure before running `late_tool.py` from this repo.

---

## "Integrate a new tool / GitHub repo / open-source code / research"

CC drops a URL, a paste, a file path, a research request, or any vague pointer like "I saw this cool repo." Standing pattern (V6.8.3, 2026-05-16):

1. **Load the canonical workflow** — `prompts/INTEGRATE_NEW_TOOL.md`. Don't paraphrase the 6 phases; follow them exactly.
2. **Identity probe first** — Bravo / Maven / Atlas / client agent. The integration lands in the agent that owns the relevant domain.
3. **Phase 1 — name the problem this actually solves.** If "looks cool" is the only justification, STOP and push back on CC.
4. **Phase 2 — parallel audit.** Spawn the researcher agent (external) + Explore agent (our side) in a single message. Wait for both. Synthesize yourself.
5. **Phase 3 — write to `~/.claude/plans/<slug>.md`.** Include ADR-0001 hard/soft dep classification, completeness scores 0-10. ExitPlanMode for non-trivial work.
6. **Phase 4 — substrate → conventions → vocabulary → distribution.** Commit per layer with V6.X.Y semantic versioning.
7. **Phase 5 — 4 symbiosis tests** after each layer: graph rebuild, retriever pickup, resolver behavior, end-to-end behavior change. Loop back if any fail.
8. **Phase 6 — propagate to siblings** per V6.8.1 contract (CONTEXT.md + V68_AGENT_OS_PATTERNS.md). Log a `[P]` pattern in `memory/PATTERNS.md`. State sync. Memory sync line.

**Reference case:** mattpocock/skills audit → commits 5aeb5fb → bec2fcc → 5335556 (Bravo), da1e5aa → 00d8e14 (Maven), 1699c9e → 18e89af (Atlas). Plan file: `~/.claude/plans/i-found-a-really-parallel-pascal.md`.

**Dashboard access:** `/playbook/prompts` → category **System integration** → click **"Integrate a new tool / repo / research"** → paste resource at end. The same prompt is also pasteable directly from `prompts/INTEGRATE_NEW_TOOL.md`.

**Anti-slop guardrails:** no stub functions, no "Proposed future tooling" claims in ADRs, no duplicate scripts, no substrate touches without need. See the full guardrails block in the prompt body.

---

## How to extend this file

Add new sections when an intent recurs. Sections are first-person playbooks, not reference docs — write them as if instructing the agent on its first day. Keep each section under ~15 lines so it's cheap to load.

## Obsidian Links
- **Core router (the 5 brain entry points):** [[brain/AGENT_ROUTER]] · [[brain/EXECUTION_RULES]] · INTENTS (this file) · [[brain/WHEN_TO_USE_SKILLS]] · [[brain/QUICK_REFERENCE]]
- [[skills/outreach-send/SKILL]] | [[skills/code-review/SKILL]] | [[skills/ship/SKILL]]
