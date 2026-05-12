# Safe Interaction

Your agent is autonomous, not omnipotent. Some asks are safe to fire-and-forget; others should never run without your eyes on the screen. This page draws the line.

## Green light — fire and forget

The agent can do these without supervision. It does them all day:

- **Read your data.** Pipeline, contacts, recent runs, retrieval queries against memory/skills/brain.
- **Draft content.** Emails, social posts, blog drafts, meeting notes. The agent writes; you publish.
- **Summarize and explain.** "What did we do last sprint?" "Why is X performing better than Y?" "Translate this contract into plain English."
- **Run analysis CLIs.** `state_manager.py status`, `memory_retriever.py query`, `self_audit.py`, `briefing.py`. Read-only by design.
- **Tick the autonomous loop.** The reasoning daemon runs continuously and surfaces what it found via the dashboard. It does not act on the world without an explicit ask.

## Yellow light — review before approving

These ask the agent to do something but the agent will pause and confirm before executing:

- **Send messages on your behalf.** Email, DM, SMS — the send_gateway routes everything through a draft-critic + approval flow before transmission.
- **Mutate your CRM or pipeline.** Creating leads, marking deals won/lost, advancing stages.
- **Schedule social posts.** Content drafted by the agent, scheduled by you.
- **Modify code in your repo.** The agent can edit, but every Edit/Write goes through `state_guard` (blocks auto-generated files) and `secret_guard` (blocks `.env.agents` reads).

When you see a "review needed" prompt in the Inbox, look at it. The agent is asking, not ordering.

## Red light — never approved without you on the call

These trigger explicit human-in-the-loop confirmation. No background mode. No "yes to all." You read the change and approve it personally:

- **Money movement.** Stripe charges, refunds, payouts. The agent drafts the request; you approve in the Stripe UI.
- **Production deploys.** `vercel --prod`, `git push --force`, prod database migrations.
- **Destructive SQL.** `DROP`, `TRUNCATE`, `DELETE` without a `WHERE`, `ALTER ... DROP COLUMN`. `exec_guard` blocks these in `enforce` mode regardless.
- **Anything touching `.env.agents`.** The file is not LLM-readable. If the agent claims it needs to read your credentials, something is wrong — call it out.
- **Bulk outreach.** Sending to >25 recipients in a 24-hour window. Daily caps live in `send_gateway.py`.

## How to ask safely

Three habits that prevent 90% of agent regret:

1. **Be specific about scope.** "Update X in Y file" is safer than "clean up the codebase." Surgical asks produce surgical changes.
2. **Ask the agent to plan before executing** for anything multi-step. "Plan the migration; don't run it yet." You read the plan, then tell it to proceed.
3. **Watch the audit logs.** `state/exec_guard.log` shows every command the bouncer flagged. If you see entries you didn't expect, ask the agent to explain.

## What the guards are doing

Three guards run on every tool call:

- **`secret_guard`** — denies the LLM read access to `.env.agents`, `.pem`, `.key`, `credentials.json`. If the agent runs `cat .env.agents | grep STRIPE`, the guard blocks before the shell even sees it.
- **`exec_guard`** — denies destructive Bash patterns. `DROP TABLE`, `rm -rf /` (outside `tmp/`), force-push to main, fork bombs.
- **`state_guard`** — denies edits on auto-generated state mirrors. Hand-edits to `memory/SESSION_LOG.md` between the AUTO-GENERATED markers would get clobbered on the next export, so the guard makes the failure loud.

You can see each guard's mode (`enforce` / `report` / `off`) on the System Health page.

## The contract

The agent will do real work for you. You will not babysit every action. In exchange, the agent will not perform money movement, production deploys, or destructive SQL without your explicit approval. The guards keep the agent honest. The dashboard keeps you informed. That's the whole deal.

## Related

- [[docs/playbooks/INDEX]]
- [[docs/playbooks/01-getting-started]]
- [[docs/playbooks/03-when-to-call-cc]]
