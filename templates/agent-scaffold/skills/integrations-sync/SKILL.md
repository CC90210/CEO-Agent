---
name: integrations-sync
description: Idempotent refresh patterns for {{AGENT_NAME}}'s external data sources. Codifies safe sync flow with audit log so agents stop reinventing dedupe/dry-run logic per source. V6.7 default skill.
tags: [skill, integrations, data, sync, idempotent]
triggers: ["sync integrations", "refresh data", "pull latest", "integrations sync"]
owner: {{agent_name}}
tier: T2
risk: medium
canonical_pattern: ../../../Business-Empire-Agent/skills/integrations-sync/SKILL.md
---

# Integrations Sync — {{AGENT_NAME}} Refresh Patterns

## Overview

Every external data source needs a refresh path. Without a codified pattern, agents reinvent dedupe + dry-run + audit logic, and stale data quietly poisons downstream snapshots.

This skill is the canonical reference for "how do I safely refresh X" in {{AGENT_NAME}}'s domain. Always idempotent. Always logs. Always has a dry-run.

**When to invoke:**
- Operator says "refresh X" / "sync Y" / "pull latest"
- A Prep Table snapshot has stale upstream data
- Before generating a briefing if `state/snapshots/latest_briefing.json` > 24h old

**Trigger:** `sync integrations`, `/integrations-sync`, "refresh <source>"

## Core Principles

1. **Idempotent or dry-run.** Every sync command supports re-running without duplicating data OR has `--dry-run`.
2. **Audit log.** Every sync writes a one-line JSONL entry to `state/integrations_sync.log`.
3. **Pull only the delta.** Use `--since <iso>` or platform-equivalent. Full re-syncs are explicit (`--full`) and require operator confirmation.
4. **Downstream rebuild.** After syncing a Pantry source, rebuild the Prep Table snapshot that consumes it.

## Source-by-Source Playbook

Fill in per-source playbooks here as {{AGENT_NAME}} wires integrations. Template:

### (Source name) → (target table/file)

```bash
python scripts/<source>_tool.py sync --since "<iso>" --json
```

- Idempotent: (explain the dedupe key)
- Verify: (one-line check)
- Downstream: rebuild (which snapshot)

## Audit Log Format

`state/integrations_sync.log` JSONL:

```json
{"ts":"2026-05-14T22:00:00Z","source":"<name>","action":"sync","mode":"incremental","since":"<iso>","rows":N,"errors":0}
```

If `errors > 0`, append to `state/integrations_sync.errors.log` with the stderr blob.

## Execution Protocol

1. **Identify the source** from operator's request.
2. **Dry-run first if mutating.** Surface the diff before applying.
3. **Sync the delta.** Pull `--since` last-success-ts.
4. **Verify** with per-source check.
5. **Rebuild downstream snapshot.**
6. **Log to audit JSONL.**
7. **Confirm in chat:** source, mode, row delta, downstream rebuilt, audit log path.

## Anti-Patterns

- ❌ Sync without `--on-conflict` or equivalent dedupe → silent duplicate insertion.
- ❌ Full re-sync as default. Always pull delta.
- ❌ Sync-ing Pantry but not rebuilding the affected Prep Table. Snapshot is now stale.
- ❌ Burying errors. Always log; always surface.
- ❌ Skipping the JSONL audit. Without the trail there's no way to debug divergence.

## Integration

- **brain/DATA_TAXONOMY.md** — the Pantry source registry
- **scripts/*_tool.py** — the underlying CLI wrappers
- **scripts/snapshots/** — Prep Tables that consume these sources
- **state/integrations_sync.log** — the audit trail

## Obsidian Links
- [[brain/DATA_TAXONOMY]] | [[brain/INTENTS]]
- [[skills/silver-platter/SKILL]] | [[skills/memory-journaling/SKILL]]
