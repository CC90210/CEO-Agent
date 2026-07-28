---
tags: [docs]
last_updated: 2026-05-11
---

# Pause and Rollback

Two principles drive the V6.0 architecture: **the agent should be safe by default**, and **you should always have a way to stop it**. This page is the kill-switch documentation.

## The three-tier pause

### Tier 1 — Soft pause (5 seconds)

Stop the autonomous reasoning loop without touching the state DB or guards. The agent goes idle but the dashboard stays live and you can still query it manually.

```bash
docker compose -f infra/docker-compose.local.yml stop bravo-core
# cloud:
docker compose -f infra/docker-compose.cloud.yml stop bravo-core
```

Restart later with:

```bash
docker compose -f infra/docker-compose.local.yml start bravo-core
```

No state is lost. The agent picks up from its last heartbeat.

### Tier 2 — Hard pause (30 seconds)

Stop every daemon. Useful when you suspect prompt injection or just want a clean break.

```bash
docker compose -f infra/docker-compose.local.yml down
```

The DB and audit logs persist on the host filesystem. Bring everything back with `up -d` whenever you're ready. Note: `down` removes containers but preserves volumes — your data survives.

### Tier 3 — Revert to V5.5 behavior (instant)

Flip one environment variable in `.env.agents`:

```ini
EMPIRE_V6_MODE=off
```

This restores V5.5 flat-file behavior. The database stops being authoritative. Markdown files become the source of truth again. Hooks default to safe modes (`secret_guard=report`, `exec_guard=report`, `state_guard=off`) regardless of any per-hook overrides.

You don't lose data. The DB still exists; it just isn't driving anything until you flip the var back.

## Surgical hook disable

If a single guard is misbehaving (false-positive blocks during the soak), turn that one off without touching the others:

```ini
EMPIRE_HOOK_EXEC_GUARD=off       # was 'enforce' or 'report'
EMPIRE_HOOK_SECRET_GUARD=off
EMPIRE_HOOK_STATE_GUARD=off
```

Restart Docker for the change to take effect:

```bash
docker compose -f infra/docker-compose.local.yml up -d
```

`secret_guard=off` is the riskiest of the three — only do this knowingly, and only as a temporary measure. The other two are lower-risk to disable for debugging.

## Rolling back a bad agent action

The agent took a destructive action you didn't approve. Steps:

1. **Pause** (Tier 1 or Tier 2 above) so it doesn't compound.
2. **Identify the action.** Check `state/state_manager.log` for the most recent `op` entries:

   ```bash
   tail -20 state/state_manager.log | jq .
   ```

3. **Check git** if the action touched code:

   ```bash
   git status
   git diff
   git log --since='30 minutes ago'
   ```

4. **Restore** from the last known-good state. For files: `git checkout HEAD -- <file>`. For database rows: V6.0 keeps an audit trail in `state_transaction`, so you can see exactly which writes happened, but reversing them is per-table — drop into `sqlite3 state/empire_state.db` and use the audit log as a guide.

   For Supabase data: every `lead_interactions` write is timestamped. The send_gateway also keeps a `confirmed_at IS NULL` reservation step, so unsent drafts can be cancelled by deleting their row before send time.

5. **Resume** when you've verified the surgical fix.

## Restoring from a clean install

If the local state is so confused that surgical recovery isn't worth it, you can rebuild from a fresh clone without losing your credentials:

```bash
# 1. Back up the env and state files (the parts that took setup time)
cp .env.agents ~/bravo-backup-env.agents
cp -r state/ ~/bravo-backup-state/

# 2. Burn the working tree
cd ..
mv Business-Empire-Agent Business-Empire-Agent.bak
git clone https://github.com/CC90210/CEO-Agent.git Business-Empire-Agent
cd Business-Empire-Agent

# 3. Restore your credentials and (optionally) your DB
cp ~/bravo-backup-env.agents .env.agents
chmod 600 .env.agents
cp -r ~/bravo-backup-state/ state/

# 4. Reinstall deps and rebuild containers
bash install.sh
docker compose -f infra/docker-compose.local.yml up -d --build
```

Total time: ~10 minutes. The backup is your insurance.

## What you can NOT lose

Three things are physically impossible to wipe by accident:

1. **`.env.agents`** — gitignored, immune to `git checkout`, write-blocked by `secret_guard`.
2. **`state/migrations/`** — checked into git; even a full `state/` directory wipe restores them on next clone.
3. **Supabase data** — lives in the cloud, not in this repo. Burning the local working tree doesn't touch your CRM or pipeline rows.

Everything else is reproducible. That's the design.

## Related

- [[docs/playbooks/INDEX]]
- [[docs/playbooks/01-getting-started]]
- [[docs/playbooks/02-safe-interaction]]


## Related (graph)

- [[docs/playbooks/INDEX]]
- [[docs/playbooks/01-getting-started]]
- [[docs/playbooks/02-safe-interaction]]
- [[docs/playbooks/03-when-to-call-cc]]
