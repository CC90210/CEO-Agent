# When to Escalate

Your agent runs continuously. Most of what it does is invisible. This page is the list of conditions where you (the human operator) need to step in.

## The five escalation triggers

### 1. The same guard fires repeatedly

Open the System Health page. If `exec_guard` or `secret_guard` shows blocked-counts climbing into the dozens within an hour, the agent is either confused (a prompt-injection attempt is leaking through, the LLM is misinterpreting an instruction) or actively probing the limits. Either way: pause it (see the next playbook page).

The healthy baseline is 0–3 blocks per day during normal operation, almost all of them `irreversible-allowlist` entries (legitimate `git push`, `vercel deploy`).

### 2. State drift detected

Run this from a terminal:

```bash
python scripts/state_manager.py export --check
```

Exit 0 = mirrors match the database. Exit 1 = drift. Drift means someone hand-edited a file that's supposed to be auto-generated (`memory/SESSION_LOG.md` between markers, `brain/STATE.md` heartbeat block). Investigate the diff:

```bash
git diff memory/SESSION_LOG.md brain/STATE.md
```

If the change looks legitimate (a teammate edited intentionally), regenerate cleanly with `python scripts/state_manager.py export`. If it looks like the agent did it, escalate.

### 3. The agent claims it can't access your credentials

This is correct and expected. The agent should not be reading `.env.agents`. CLI tool wrappers (`scripts/stripe_tool.py`, `scripts/supabase_tool.py`) load secrets internally and return sanitized JSON.

If the agent tells you "I need you to paste your Stripe key," **stop**. Either:

- The agent is missing a wrapper for the service it's trying to use → tell it to build the wrapper first (see `skills/cli-anything/SKILL.md`).
- A guard is misconfigured → check `EMPIRE_HOOK_SECRET_GUARD` env var; should be `enforce` or at least `report`.
- The agent has been prompt-injected → discard the conversation, open a fresh session, and tell it what you actually wanted.

You should never paste credentials into a chat with the agent. Ever.

### 4. A tick has been silent for >30 minutes

The autonomous reasoning loop ticks every few minutes. A 30+ minute gap means the daemon crashed, lost network, or got stuck on a blocked action. Check:

```bash
docker compose -f infra/docker-compose.local.yml logs -f bravo-core | tail -50
# or on cloud:
docker compose -f infra/docker-compose.cloud.yml logs -f bravo-core | tail -50
```

If you see Python tracebacks or repeated retries, restart the daemon:

```bash
docker compose -f infra/docker-compose.local.yml restart bravo-core
```

If it crashes again on restart, escalate to the engineering channel with the last 200 log lines.

### 5. Something feels wrong

This is the most important one and the hardest to operationalize. The agent is statistical software. It will sometimes do the wrong thing in a way that looks plausible. If a draft email reads slightly off, a number doesn't match what you remember, a "task complete" message lands in your Inbox for work you didn't ask for — pause and investigate.

The cost of a false-positive escalation is one minute of your time. The cost of a false-negative is a refund issued to the wrong customer.

## How to escalate

If you have an OASIS support contract, the agent has an `agent_inbox` channel — drop a high-priority message:

```bash
python scripts/agent_inbox.py post --to oasis-support --priority high \
  --note "Suspected prompt-injection in conversation X — halting agent for review"
```

Otherwise, email the operator who installed your agent. Include:

1. The relevant timestamp from `state/state_manager.log` or guard logs.
2. The last command/conversation that triggered concern.
3. Whether you've paused the agent yet.

## What NOT to escalate

- A guard blocked one command, you re-issued a safer form, work continued. That's the system working as designed.
- The agent declined to do something it wasn't authorized for. Same — that's the contract.
- A draft message you didn't approve. The agent drafts; you publish. If you don't want the draft, delete it.

## Related

- [[docs/playbooks/INDEX]]
- [[docs/playbooks/01-getting-started]]
- [[docs/playbooks/02-safe-interaction]]
