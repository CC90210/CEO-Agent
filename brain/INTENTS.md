---
name: INTENTS
description: Verb-by-verb playbook. For each kind of operator request, the exact sequence the agent should run.
mutability: SEMI-MUTABLE
tags: [brain, agent-only, playbook]
last_updated: 2026-05-06
---

# INTENTS — Verb-by-Verb Playbook

> Reached from `brain/AGENT_ROUTER.md` when an intent needs more than a one-line "read this file" answer.

---

## "Send an email to <X>"

1. Read `skills/outreach-send/SKILL.md` for the canonical send path.
2. Confirm the recipient is in `lead_engine` already, or create with `python scripts/lead_engine.py add …`.
3. Compose the draft. Voice rules in `brain/SOUL.md` if you don't already have them in prompt.
4. Run `python scripts/send_gateway.py can-act --lead-id <id> --channel email` first. The gateway enforces 8 gates (CASL, cooldown, daily/hourly cap, domain cap, reputation, draft critic, bounce circuit, reservation guard). If it returns a block reason, surface that — don't bypass.
5. If `can-act` is green, `python scripts/send_gateway.py send --channel email --agent-source bravo --to … --subject … --body …`.
6. Confirm in chat: who, what, gate verdict, message id returned by gateway.

---

## "Apply this database migration"

1. Confirm migration file is in `database/<NNN>_<name>.sql`. If not, write it with the next number.
2. Run `python scripts/apply_migration.py database/<NNN>_<name>.sql`. The script applies through Supabase Management API; gates on dangerous patterns (`DROP TABLE`, `TRUNCATE`, naked `GRANT`/`REVOKE`).
3. If gated, surface the reason. Operator may approve via the Supabase Dashboard SQL editor — only then do you suggest a manual path.
4. Confirm post-apply: `python scripts/supabase_tool.py select <new_table> --project bravo --limit 1` to verify the schema is live.
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

1. Read `apps/command-center/lib/agent-actions.ts` to confirm the action shape (allowed fields, validators).
2. Emit a `<dashboard-action type="…">{…}</dashboard-action>` marker in your chat reply. The chat route parses it post-stream and applies via `runAction()`.
3. Confirm in chat with one line: "Set primary agent to Atlas. Refresh the page to see it stick."

Allowed action types: `update_profile`, `toggle_agent_enabled`, `set_primary_agent`, `update_mrr`. Anything else needs a new handler in `agent-actions.ts` first — don't fake it.

---

## "Schedule / run a cron"

1. For Vercel-hosted crons (the dashboard's): edit `apps/command-center/vercel.json`'s `crons` array. Push. Vercel picks it up on next deploy.
2. For local-machine crons (most of `scripts/*`): there's no central scheduler. The convention is `python scripts/<name>.py` invoked from the operator's task scheduler / launchd / systemd. Tell them what to schedule, but if they ask you to "automate it," wire it via `apps/command-center/vercel.json` if it's HTTP-pingable, or surface the OS-specific install command.
3. Confirm in chat: where it's now scheduled, when next run is.

---

## "Find / search / look up"

1. **Code or files:** use the `read_file` tool you already have. Pattern-match starting from the indexes (`brain/AGENT_ROUTER.md`, `skills/INDEX.md`, `brain/CAPABILITIES.md`).
2. **Web search:** `python scripts/firecrawl_tool.py search "<query>"` then `read <url>` to extract structured content.
3. **Database:** `python scripts/supabase_tool.py select <table> --project bravo --eq '{"…":"…"}' --limit N`.
4. **Memory / past sessions:** read `memory/SESSION_LOG.md` (recent) or `memory/ARCHIVES/` (older).

---

## "Switch me to <agent>" / "Have <agent> do this"

1. If the chat picker switched the agent, the bridge already `cd`'d for you — your CLAUDE.md changed.
2. If the operator typed it in chat ("ask Atlas to recalc tax"), you have two options:
   - Surface the delegation: explain that the operator should switch in the picker, or that this is a `bravo agent run atlas …` task.
   - For cross-agent work that doesn't need the user-facing agent, post to `tmp/agent_inbox/` via `python scripts/agent_inbox.py post --to atlas --priority high --body "…"`. Atlas reads its inbox at session start.

---

## "Stop / pause / undo"

1. **Outbound mid-flight:** `BRAVO_FORCE_DRY_RUN=1` env var — every send routes to dry-run. Set on the local shell or in `.env.agents`.
2. **Cron:** comment the line in `apps/command-center/vercel.json` and push.
3. **Last action emitted via dashboard-action:** there's no automated undo. Emit a compensating action (e.g. `update_profile` with the previous value) in the next turn after the operator confirms.

---

## How to extend this file

Add new sections when an intent recurs. Sections are first-person playbooks, not reference docs — write them as if instructing the agent on its first day. Keep each section under ~15 lines so it's cheap to load.
